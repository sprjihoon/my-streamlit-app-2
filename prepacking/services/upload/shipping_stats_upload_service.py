from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from prepacking.common.date_helper import now_str
from prepacking.config import PP_UPLOAD_DIR
from prepacking.database import ensure_pp_tables, get_pp_connection

from prepacking.services.upload.file_parser_service import parse_shipping_file


def _safe_dest_name(original: str) -> str:
    base = Path(original).name
    base = re.sub(r"[^\w.\-가-힣ㄱ-ㅎㅏ-ㅣ\s]", "_", base, flags=re.UNICODE).strip()
    if not base:
        base = "upload"
    ts = now_str("%Y%m%d_%H%M%S")
    return f"{ts}_{base}"


def upload_shipping_stats(
    file_path: str, supplier_name: str, uploaded_by: str = "", note: str = ""
) -> dict:
    ensure_pp_tables()
    PP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(file_path)
    dest_name = _safe_dest_name(src.name)
    dest = PP_UPLOAD_DIR / dest_name
    shutil.copy2(src, dest)
    rows = parse_shipping_file(str(dest))
    dates = [r["shipping_date"] for r in rows if r.get("shipping_date")]
    data_start = min(dates) if dates else None
    data_end = max(dates) if dates else None
    row_count = len(rows)
    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_upload_files (
                file_name, uploaded_by, data_start_date, data_end_date, row_count, note
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (dest_name, uploaded_by, data_start, data_end, row_count, note),
        )
        upload_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
        batch = []
        for r in rows:
            raw = json.dumps(dict(r), ensure_ascii=False)
            batch.append(
                (
                    upload_id,
                    r.get("shipping_date") or None,
                    supplier_name,
                    r.get("order_no") or "",
                    r.get("invoice_no") or "",
                    r.get("combo_no") or "",
                    r.get("product_name") or "",
                    r.get("option_name") or "",
                    r.get("sku_code") or "",
                    r.get("barcode") or "",
                    int(r.get("qty") or 1),
                    int(r.get("inner_qty") or 1),
                    r.get("admin_product_qty") or "",
                    raw,
                )
            )
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
        con.commit()
    return {
        "upload_id": upload_id,
        "file_name": dest_name,
        "row_count": row_count,
        "data_start_date": data_start,
        "data_end_date": data_end,
    }
