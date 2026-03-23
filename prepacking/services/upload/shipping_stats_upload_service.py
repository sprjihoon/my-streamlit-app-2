from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import threading
from pathlib import Path

from prepacking.common.date_helper import now_str
from prepacking.config import PP_UPLOAD_DIR
from prepacking.database import ensure_pp_tables, get_pp_connection

from prepacking.services.upload.file_parser_service import parse_shipping_file

logger = logging.getLogger(__name__)


class DuplicateFileError(Exception):
    """동일한 파일이 이미 업로드되어 있을 때 발생."""

    def __init__(self, file_name: str, upload_id: int):
        self.file_name = file_name
        self.upload_id = upload_id
        super().__init__(f"동일한 파일이 이미 업로드되어 있습니다. (파일: {file_name}, ID: {upload_id})")


def _safe_dest_name(original: str) -> str:
    base = Path(original).name
    base = re.sub(r"[^\w.\-가-힣ㄱ-ㅎㅏ-ㅣ\s]", "_", base, flags=re.UNICODE).strip()
    if not base:
        base = "upload"
    ts = now_str("%Y%m%d_%H%M%S")
    return f"{ts}_{base}"


def _compute_file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_row_exists(con, shipping_date: str, supplier_name: str,
                      order_no: str, invoice_no: str, product_name: str,
                      option_name: str, sku_code: str, qty: int) -> bool:
    cur = con.execute(
        """
        SELECT 1 FROM pp_shipping_stats
        WHERE shipping_date = ? AND supplier_name = ? AND order_no = ?
          AND invoice_no = ? AND product_name = ? AND option_name = ?
          AND sku_code = ? AND qty = ?
        LIMIT 1
        """,
        (shipping_date, supplier_name, order_no, invoice_no,
         product_name, option_name, sku_code, qty),
    )
    return cur.fetchone() is not None


def _process_upload_background(
    upload_id: int,
    dest: str,
    supplier_name: str,
) -> None:
    """백그라운드 스레드에서 파일 파싱 및 DB 저장을 수행."""
    try:
        rows = parse_shipping_file(dest)
        dates = [r["shipping_date"] for r in rows if r.get("shipping_date")]
        data_start = min(dates) if dates else None
        data_end = max(dates) if dates else None
        total_count = len(rows)

        with get_pp_connection() as con:
            batch = []
            skipped = 0
            seen_in_batch: set[tuple] = set()

            for r in rows:
                raw = json.dumps(dict(r), ensure_ascii=False)
                row_supplier = (r.get("supplier_name") or "").strip() or supplier_name
                sd = r.get("shipping_date") or ""
                ono = r.get("order_no") or ""
                ino = r.get("invoice_no") or ""
                pn = r.get("product_name") or ""
                on_ = r.get("option_name") or ""
                sc = r.get("sku_code") or ""
                q = int(r.get("qty") or 1)

                dedup_key = (sd, row_supplier, ono, ino, pn, on_, sc, q)
                if dedup_key in seen_in_batch:
                    skipped += 1
                    continue

                if _check_row_exists(con, sd, row_supplier, ono, ino, pn, on_, sc, q):
                    skipped += 1
                    seen_in_batch.add(dedup_key)
                    continue

                seen_in_batch.add(dedup_key)
                batch.append((
                    upload_id,
                    r.get("shipping_date") or None,
                    row_supplier,
                    ono, ino,
                    r.get("combo_no") or "",
                    pn, on_, sc,
                    r.get("barcode") or "",
                    q,
                    int(r.get("inner_qty") or 1),
                    r.get("admin_product_qty") or "",
                    raw,
                ))

            inserted_count = len(batch)

            if batch:
                con.executemany(
                    """
                    INSERT INTO pp_shipping_stats (
                        upload_id, shipping_date, supplier_name, order_no, invoice_no, combo_no,
                        product_name, option_name, sku_code, barcode, qty, inner_qty,
                        admin_product_qty, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

            con.execute(
                """
                UPDATE pp_upload_files
                SET upload_status = 'completed',
                    row_count = ?,
                    skipped_count = ?,
                    total_count = ?,
                    data_start_date = ?,
                    data_end_date = ?
                WHERE upload_id = ?
                """,
                (inserted_count, skipped, total_count, data_start, data_end, upload_id),
            )
            con.commit()

        logger.info("Upload %d completed: %d inserted, %d skipped out of %d total",
                     upload_id, inserted_count, skipped, total_count)

    except Exception:
        logger.exception("Background upload processing failed for upload_id=%d", upload_id)
        try:
            with get_pp_connection() as con:
                con.execute(
                    """
                    UPDATE pp_upload_files
                    SET upload_status = 'failed',
                        error_message = ?
                    WHERE upload_id = ?
                    """,
                    ("파일 처리 중 오류가 발생했습니다.", upload_id),
                )
                con.commit()
        except Exception:
            logger.exception("Failed to update error status for upload_id=%d", upload_id)


def upload_shipping_stats(
    file_path: str, supplier_name: str = "", uploaded_by: str = "", note: str = ""
) -> dict:
    ensure_pp_tables()
    PP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(file_path)

    file_hash = _compute_file_hash(file_path)

    with get_pp_connection() as con:
        dup = con.execute(
            "SELECT upload_id, file_name FROM pp_upload_files WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()
        if dup:
            raise DuplicateFileError(file_name=dup[1], upload_id=dup[0])

    dest_name = _safe_dest_name(src.name)
    dest = PP_UPLOAD_DIR / dest_name
    shutil.copy2(src, dest)

    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_upload_files (
                file_name, file_hash, uploaded_by, row_count, note, upload_status
            ) VALUES (?, ?, ?, 0, ?, 'processing')
            """,
            (dest_name, file_hash, uploaded_by, note),
        )
        upload_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
        con.commit()

    thread = threading.Thread(
        target=_process_upload_background,
        args=(upload_id, str(dest), supplier_name),
        daemon=True,
    )
    thread.start()

    return {
        "upload_id": upload_id,
        "file_name": dest_name,
        "upload_status": "processing",
    }
