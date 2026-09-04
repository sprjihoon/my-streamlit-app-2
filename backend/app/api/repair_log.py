"""
backend/app/api/repair_log.py - 수선작업일지 API
───────────────────────────────────────
기존 work_log와 분리. 인보이스 계산에 사용하지 않음.
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.config import settings
from backend.app.services import repair_catalog
from logic.db import get_connection

router = APIRouter(prefix="/repair-log", tags=["repair-log"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "repair"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ─────────────────────────────────────
# Models
# ─────────────────────────────────────

class RepairLogCreate(BaseModel):
    날짜: str
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    바코드: Optional[str] = None
    불량명: Optional[str] = None
    작업: str
    수량: int = 1
    비용: int
    비고: Optional[str] = None
    작성자: Optional[str] = None
    출처: str = "manual"


class RepairLogUpdate(BaseModel):
    날짜: Optional[str] = None
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    바코드: Optional[str] = None
    불량명: Optional[str] = None
    작업: Optional[str] = None
    수량: Optional[int] = None
    비용: Optional[int] = None
    비고: Optional[str] = None


class BarcodeCreate(BaseModel):
    바코드: str
    업체명: str
    제품명: str
    옵션: Optional[str] = None
    상품코드: Optional[str] = None
    로케이션: Optional[str] = None
    상품명: Optional[str] = None
    출처: str = "manual"


class BarcodeUpdate(BaseModel):
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    상품코드: Optional[str] = None
    로케이션: Optional[str] = None
    상품명: Optional[str] = None


# ─────────────────────────────────────
# DB
# ─────────────────────────────────────

def ensure_repair_tables():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_barcode (
                바코드 TEXT PRIMARY KEY,
                업체명 TEXT NOT NULL,
                제품명 TEXT NOT NULL,
                옵션 TEXT,
                상품코드 TEXT,
                로케이션 TEXT,
                상품명 TEXT,
                출처 TEXT,
                저장시간 TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_work_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                날짜 TEXT,
                업체명 TEXT,
                제품명 TEXT,
                옵션 TEXT,
                바코드 TEXT,
                작업 TEXT,
                수량 INTEGER DEFAULT 1,
                비용 INTEGER DEFAULT 0,
                비고 TEXT,
                작성자 TEXT,
                저장시간 TIMESTAMP,
                출처 TEXT,
                barcode_image TEXT,
                before_image TEXT,
                after_image TEXT
            )
        """)
        con.commit()
    repair_catalog.ensure_catalog_tables()


class WorkTypeBody(BaseModel):
    작업명: str
    기본비용: int
    별칭: Optional[str] = None


class DefectBody(BaseModel):
    불량명: str
    별칭: Optional[str] = None


def _clean(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    if s.lower() in ("", "nan", "none"):
        return None
    return s


def _strip_option(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return v.strip().strip("[]").strip()


def _lookup_barcode(con, barcode: str) -> Optional[dict]:
    if not barcode:
        return None
    row = con.execute(
        """SELECT 바코드, 업체명, 제품명, 옵션, 상품코드, 로케이션, 상품명
           FROM repair_barcode WHERE 바코드 = ?""",
        (barcode.strip(),),
    ).fetchone()
    if not row:
        return None
    return {
        "바코드": row[0],
        "업체명": row[1],
        "제품명": row[2],
        "옵션": row[3],
        "상품코드": row[4],
        "로케이션": row[5],
        "상품명": row[6],
    }


def _resolve_vendor(con, vendor: str) -> str:
    """별칭이면 정식 업체명으로. 없으면 원문 유지."""
    if not vendor:
        return vendor
    raw = vendor.strip()
    row = con.execute(
        """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
           UNION
           SELECT vendor FROM aliases
           WHERE LOWER(alias) = LOWER(?) AND file_type IN ('work_log', 'all')""",
        (raw, raw),
    ).fetchone()
    if row:
        return row[0]
    # 자체제작_베으 → 베으 부분 일치 별칭
    suffix = raw.split("_")[-1] if "_" in raw else raw
    if suffix != raw:
        row = con.execute(
            """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
               UNION
               SELECT vendor FROM aliases
               WHERE LOWER(alias) = LOWER(?) AND file_type IN ('work_log', 'all')""",
            (suffix, suffix),
        ).fetchone()
        if row:
            return row[0]
    return raw


async def _save_upload(file: UploadFile) -> str:
    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(await file.read())
    return filename


def _delete_image(filename: Optional[str]):
    if not filename:
        return
    path = UPLOAD_DIR / filename
    if path.exists() and path.parent == UPLOAD_DIR:
        try:
            path.unlink()
        except OSError:
            pass


# ─────────────────────────────────────
# Excel helpers
# ─────────────────────────────────────

def _parse_html_table(content: bytes) -> pd.DataFrame:
    """카페24/창고용 HTML(.xls) 표를 표준 라이브러리로 읽는다."""
    from html.parser import HTMLParser

    class _TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: list[list[str]] = []
            self._row: Optional[list[str]] = None
            self._cell: Optional[str] = None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._row = []
            elif tag == "td" and self._row is not None:
                self._cell = ""

        def handle_data(self, data):
            if self._cell is not None:
                self._cell += data

        def handle_endtag(self, tag):
            if tag == "td" and self._row is not None and self._cell is not None:
                self._row.append(self._cell.strip())
                self._cell = None
            elif tag == "tr" and self._row is not None:
                if self._row:
                    self.rows.append(self._row)
                self._row = None

    parser = _TableParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    if len(parser.rows) < 2:
        raise HTTPException(status_code=400, detail="엑셀(HTML)에서 표를 찾지 못했습니다.")
    header = parser.rows[0]
    width = len(header)
    body = [r + [""] * (width - len(r)) for r in parser.rows[1:] if any(r)]
    return pd.DataFrame(body, columns=header)


def _read_product_table(content: bytes) -> pd.DataFrame:
    head = content[:400].lstrip()
    is_html = head.startswith(b"<") or b"<html" in head.lower() or b"<meta" in head.lower()
    if is_html:
        return _parse_html_table(content)
    try:
        return pd.read_excel(io.BytesIO(content))
    except Exception:
        try:
            return _parse_html_table(content)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="엑셀 파일을 읽을 수 없습니다.")


def _find_col(columns, *names) -> Optional[str]:
    normalized = {str(c).strip(): c for c in columns}
    for name in names:
        if name in normalized:
            return normalized[name]
    return None


def _find_vendor_col(columns) -> Optional[str]:
    """공급처가 여러 개면 마지막 열만 업체명. '공급처 상품명' 등은 제외."""
    matches = [c for c in columns if str(c).strip() == "공급처"]
    if matches:
        return matches[-1]
    return _find_col(columns, "업체명")


def _parse_barcode_rows(df: pd.DataFrame) -> List[dict]:
    barcode_col = _find_col(df.columns, "바코드")
    vendor_col = _find_vendor_col(df.columns)
    short_name_col = _find_col(df.columns, "공급처 상품명", "제품명")
    long_name_col = _find_col(df.columns, "상품명")
    option_col = _find_col(df.columns, "옵션")
    code_col = _find_col(df.columns, "상품코드")
    loc_col = _find_col(df.columns, "로케이션")

    if not barcode_col:
        raise HTTPException(status_code=400, detail="바코드 열이 없습니다.")
    if not vendor_col:
        raise HTTPException(status_code=400, detail="공급처(업체명) 열이 없습니다.")

    rows = []
    for _, r in df.iterrows():
        barcode = _clean(r.get(barcode_col))
        vendor = _clean(r.get(vendor_col))
        short_name = _clean(r.get(short_name_col)) if short_name_col else None
        long_name = _clean(r.get(long_name_col)) if long_name_col else None
        product = short_name or long_name
        if not barcode or not vendor or not product:
            continue
        rows.append({
            "바코드": barcode,
            "업체명": vendor,
            "제품명": product,
            "옵션": _strip_option(_clean(r.get(option_col))) if option_col else None,
            "상품코드": _clean(r.get(code_col)) if code_col else None,
            "로케이션": _clean(r.get(loc_col)) if loc_col else None,
            "상품명": long_name,
        })
    return rows


# ─────────────────────────────────────
# Barcode endpoints (/{id} 보다 앞)
# ─────────────────────────────────────

@router.get("/barcodes")
async def list_barcodes(
    q: Optional[str] = None,
    vendor: Optional[str] = None,
    limit: int = Query(default=100, le=2000),
    offset: int = 0,
):
    ensure_repair_tables()
    with get_connection() as con:
        where = "WHERE 1=1"
        params: list = []
        if q:
            where += " AND (바코드 LIKE ? OR 제품명 LIKE ? OR 상품명 LIKE ? OR 옵션 LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like, like, like])
        if vendor:
            where += " AND 업체명 = ?"
            params.append(vendor)

        total = con.execute(f"SELECT COUNT(*) FROM repair_barcode {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT 바코드, 업체명, 제품명, 옵션, 상품코드, 로케이션, 상품명, 출처, 저장시간
                FROM repair_barcode {where}
                ORDER BY 저장시간 DESC, 바코드
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        vendors = [
            r[0] for r in con.execute(
                "SELECT DISTINCT 업체명 FROM repair_barcode WHERE 업체명 IS NOT NULL ORDER BY 업체명"
            ).fetchall()
        ]

    items = []
    for r in rows:
        items.append({
            "바코드": r[0],
            "업체명": r[1],
            "제품명": r[2],
            "옵션": r[3],
            "상품코드": r[4],
            "로케이션": r[5],
            "상품명": r[6],
            "출처": r[7],
            "저장시간": str(r[8]) if r[8] else None,
        })
    return {"items": items, "total": total, "filters": {"vendors": vendors}}


@router.get("/barcodes/lookup/{barcode}")
async def lookup_barcode(barcode: str):
    ensure_repair_tables()
    with get_connection() as con:
        found = _lookup_barcode(con, barcode)
    if not found:
        raise HTTPException(status_code=404, detail="등록되지 않은 바코드입니다.")
    return found


@router.get("/barcodes/template")
async def barcode_template():
    output = io.BytesIO()
    df = pd.DataFrame(columns=["바코드", "업체명", "제품명", "옵션", "상품코드", "로케이션", "상품명"])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="바코드")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=repair_barcode_template.xlsx"},
    )


@router.post("/barcodes/upload")
async def upload_barcodes(file: UploadFile = File(...)):
    ensure_repair_tables()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    df = _read_product_table(content)
    parsed = _parse_barcode_rows(df)
    if not parsed:
        raise HTTPException(status_code=400, detail="유효한 바코드 행이 없습니다. 바코드/공급처/제품명을 확인하세요.")

    now = datetime.now().isoformat()
    inserted = 0
    updated = 0
    with get_connection() as con:
        for row in parsed:
            vendor = _resolve_vendor(con, row["업체명"])
            exists = con.execute(
                "SELECT 1 FROM repair_barcode WHERE 바코드 = ?", (row["바코드"],)
            ).fetchone()
            con.execute(
                """INSERT INTO repair_barcode
                   (바코드, 업체명, 제품명, 옵션, 상품코드, 로케이션, 상품명, 출처, 저장시간)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'excel', ?)
                   ON CONFLICT(바코드) DO UPDATE SET
                     업체명=excluded.업체명,
                     제품명=excluded.제품명,
                     옵션=excluded.옵션,
                     상품코드=excluded.상품코드,
                     로케이션=excluded.로케이션,
                     상품명=excluded.상품명,
                     출처='excel',
                     저장시간=excluded.저장시간""",
                (
                    row["바코드"], vendor, row["제품명"], row["옵션"],
                    row["상품코드"], row["로케이션"], row["상품명"], now,
                ),
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        con.commit()

    add_log(
        action_type="수선바코드_업로드",
        target_type="repair_barcode",
        target_name=file.filename or "excel",
        user_nickname="웹",
        details=f"신규 {inserted}건, 갱신 {updated}건",
    )
    return {
        "success": True,
        "inserted": inserted,
        "updated": updated,
        "total": inserted + updated,
        "message": f"바코드 {inserted + updated}건 반영 (신규 {inserted}, 갱신 {updated})",
    }


@router.post("/barcodes")
async def create_barcode(data: BarcodeCreate):
    ensure_repair_tables()
    barcode = data.바코드.strip()
    if not barcode or not data.업체명.strip() or not data.제품명.strip():
        raise HTTPException(status_code=400, detail="바코드, 업체명, 제품명은 필수입니다.")

    now = datetime.now().isoformat()
    with get_connection() as con:
        vendor = _resolve_vendor(con, data.업체명.strip())
        exists = con.execute("SELECT 1 FROM repair_barcode WHERE 바코드 = ?", (barcode,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="이미 등록된 바코드입니다.")
        con.execute(
            """INSERT INTO repair_barcode
               (바코드, 업체명, 제품명, 옵션, 상품코드, 로케이션, 상품명, 출처, 저장시간)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                barcode, vendor, data.제품명.strip(), _strip_option(data.옵션),
                _clean(data.상품코드), _clean(data.로케이션), _clean(data.상품명),
                data.출처, now,
            ),
        )
        con.commit()

    add_log(
        action_type="수선바코드_생성",
        target_type="repair_barcode",
        target_id=barcode,
        target_name=f"{vendor} {data.제품명}",
        user_nickname="웹",
        details=f"바코드: {barcode}",
    )
    return {"success": True, "바코드": barcode, "message": "바코드가 등록되었습니다."}


@router.put("/barcodes/{barcode}")
async def update_barcode(barcode: str, data: BarcodeUpdate):
    ensure_repair_tables()
    updates, params = [], []
    with get_connection() as con:
        existing = con.execute(
            "SELECT 바코드 FROM repair_barcode WHERE 바코드 = ?", (barcode,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="바코드를 찾을 수 없습니다.")

        if data.업체명 is not None:
            updates.append("업체명 = ?")
            params.append(_resolve_vendor(con, data.업체명.strip()))
        if data.제품명 is not None:
            updates.append("제품명 = ?")
            params.append(data.제품명.strip())
        if data.옵션 is not None:
            updates.append("옵션 = ?")
            params.append(_strip_option(data.옵션))
        if data.상품코드 is not None:
            updates.append("상품코드 = ?")
            params.append(_clean(data.상품코드))
        if data.로케이션 is not None:
            updates.append("로케이션 = ?")
            params.append(_clean(data.로케이션))
        if data.상품명 is not None:
            updates.append("상품명 = ?")
            params.append(_clean(data.상품명))

        if not updates:
            raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")
        params.append(barcode)
        con.execute(f"UPDATE repair_barcode SET {', '.join(updates)} WHERE 바코드 = ?", params)
        con.commit()

    return {"success": True, "message": "바코드가 수정되었습니다."}


@router.delete("/barcodes/{barcode}")
async def delete_barcode(barcode: str):
    ensure_repair_tables()
    with get_connection() as con:
        existing = con.execute(
            "SELECT 바코드 FROM repair_barcode WHERE 바코드 = ?", (barcode,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="바코드를 찾을 수 없습니다.")
        con.execute("DELETE FROM repair_barcode WHERE 바코드 = ?", (barcode,))
        con.commit()
    return {"success": True, "message": "바코드가 삭제되었습니다."}


@router.get("/catalog")
async def get_catalog():
    ensure_repair_tables()
    return {
        "work_types": repair_catalog.list_work_types(),
        "defects": repair_catalog.list_defects(),
    }


@router.get("/catalog/price")
async def get_catalog_price(work_type: str, vendor: Optional[str] = None):
    ensure_repair_tables()
    return repair_catalog.lookup_repair_price(vendor, work_type)


@router.post("/catalog/work-types")
async def save_work_type(data: WorkTypeBody):
    ensure_repair_tables()
    if not data.작업명.strip():
        raise HTTPException(status_code=400, detail="작업명은 필수입니다.")
    repair_catalog.upsert_work_type(data.작업명, data.기본비용, data.별칭)
    return {"success": True, "message": "작업이 저장되었습니다."}


@router.delete("/catalog/work-types/{name}")
async def remove_work_type(name: str):
    ensure_repair_tables()
    if not repair_catalog.delete_work_type(name):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"success": True, "message": "작업이 삭제되었습니다."}


@router.post("/catalog/defects")
async def save_defect(data: DefectBody):
    ensure_repair_tables()
    if not data.불량명.strip():
        raise HTTPException(status_code=400, detail="불량명은 필수입니다.")
    repair_catalog.upsert_defect(data.불량명, data.별칭)
    return {"success": True, "message": "불량명이 저장되었습니다."}


@router.delete("/catalog/defects/{name}")
async def remove_defect(name: str):
    ensure_repair_tables()
    if not repair_catalog.delete_defect(name):
        raise HTTPException(status_code=404, detail="불량명을 찾을 수 없습니다.")
    return {"success": True, "message": "불량명이 삭제되었습니다."}


# ─────────────────────────────────────
# Image + export (/{id} 보다 앞)
# ─────────────────────────────────────

@router.get("/image/{filename}")
async def get_repair_image(filename: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(path)


@router.get("/stats")
async def get_stats(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
):
    ensure_repair_tables()
    where = "WHERE 1=1"
    params: list = []
    if period_from:
        where += " AND 날짜 >= ?"
        params.append(period_from)
    if period_to:
        where += " AND 날짜 <= ?"
        params.append(period_to)

    with get_connection() as con:
        total = con.execute(f"SELECT COUNT(*) FROM repair_work_log {where}", params).fetchone()[0]
        amount = con.execute(
            f"SELECT COALESCE(SUM(비용), 0) FROM repair_work_log {where}", params
        ).fetchone()[0]
        today = con.execute(
            f"SELECT COUNT(*) FROM repair_work_log {where} AND 날짜 = date('now', 'localtime')",
            params,
        ).fetchone()[0]
        by_source = [
            {"출처": r[0], "count": r[1]}
            for r in con.execute(
                f"SELECT COALESCE(출처, 'unknown'), COUNT(*) FROM repair_work_log {where} GROUP BY 출처",
                params,
            ).fetchall()
        ]
    return {
        "total": total,
        "total_amount": int(amount or 0),
        "today": today,
        "by_source": by_source,
    }


@router.get("/export")
async def export_logs(
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    ensure_repair_tables()
    with get_connection() as con:
        rows = con.execute(
            """SELECT 날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고, 작성자, 출처, 저장시간
               FROM repair_work_log
               WHERE 날짜 >= ? AND 날짜 <= ?
               ORDER BY 날짜 DESC, id DESC""",
            (start_date, end_date),
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="해당 기간에 수선일지가 없습니다.")

    df = pd.DataFrame(rows, columns=[
        "날짜", "업체명", "제품명", "옵션", "바코드", "불량명", "작업", "수량", "비용", "비고", "작성자", "출처", "저장시간",
    ])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="수선일지")
        summary = (
            df.groupby("업체명", dropna=False)
            .agg(건수=("날짜", "count"), 합계=("비용", "sum"))
            .reset_index()
        )
        summary.to_excel(writer, index=False, sheet_name="업체별 요약")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=repair_log_{start_date}_{end_date}.xlsx"
        },
    )


# ─────────────────────────────────────
# Repair logs
# ─────────────────────────────────────

@router.get("")
@router.get("/")
async def list_logs(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    vendor: Optional[str] = None,
    work_type: Optional[str] = None,
    defect: Optional[str] = None,
    author: Optional[str] = None,
    limit: int = Query(default=50, le=2000),
    offset: int = 0,
):
    ensure_repair_tables()
    where = "WHERE 1=1"
    params: list = []
    if period_from:
        where += " AND 날짜 >= ?"
        params.append(period_from)
    if period_to:
        where += " AND 날짜 <= ?"
        params.append(period_to)
    if vendor:
        where += " AND 업체명 = ?"
        params.append(vendor)
    if work_type:
        where += " AND 작업 LIKE ?"
        params.append(f"%{work_type}%")
    if defect:
        where += " AND 불량명 LIKE ?"
        params.append(f"%{defect}%")
    if author:
        where += " AND 작성자 LIKE ?"
        params.append(f"%{author}%")

    with get_connection() as con:
        total = con.execute(f"SELECT COUNT(*) FROM repair_work_log {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고,
                       작성자, 저장시간, 출처, barcode_image, before_image, after_image
                FROM repair_work_log {where}
                ORDER BY COALESCE(저장시간, 날짜) DESC, id DESC
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        vendors = [r[0] for r in con.execute(
            "SELECT DISTINCT 업체명 FROM repair_work_log WHERE 업체명 IS NOT NULL ORDER BY 업체명"
        ).fetchall()]
        work_types = [r[0] for r in con.execute(
            "SELECT DISTINCT 작업 FROM repair_work_log WHERE 작업 IS NOT NULL ORDER BY 작업"
        ).fetchall()]
        defects = [r[0] for r in con.execute(
            "SELECT DISTINCT 불량명 FROM repair_work_log WHERE 불량명 IS NOT NULL ORDER BY 불량명"
        ).fetchall()]
        authors = [r[0] for r in con.execute(
            "SELECT DISTINCT 작성자 FROM repair_work_log WHERE 작성자 IS NOT NULL ORDER BY 작성자"
        ).fetchall()]

    logs = []
    for r in rows:
        logs.append({
            "id": r[0],
            "날짜": r[1],
            "업체명": r[2],
            "제품명": r[3],
            "옵션": r[4],
            "바코드": r[5],
            "불량명": r[6],
            "작업": r[7],
            "수량": r[8],
            "비용": r[9],
            "비고": r[10],
            "작성자": r[11],
            "저장시간": str(r[12]) if r[12] else None,
            "출처": r[13],
            "barcode_image": r[14],
            "before_image": r[15],
            "after_image": r[16],
        })
    return {
        "logs": logs,
        "total": total,
        "filters": {"vendors": vendors, "work_types": work_types, "defects": defects, "authors": authors},
    }


def insert_repair_log_record(
    *,
    날짜: str,
    작업: str,
    비용: int,
    업체명: Optional[str] = None,
    제품명: Optional[str] = None,
    옵션: Optional[str] = None,
    바코드: Optional[str] = None,
    불량명: Optional[str] = None,
    수량: int = 1,
    비고: Optional[str] = None,
    작성자: Optional[str] = None,
    출처: str = "manual",
    barcode_image: Optional[str] = None,
    before_image: Optional[str] = None,
    after_image: Optional[str] = None,
    price_stated: bool = False,
) -> dict:
    """수선일지 한 건 저장. 봇/웹 공통."""
    ensure_repair_tables()
    if not (작업 or "").strip() or 비용 is None:
        raise ValueError("작업과 비용은 필수입니다.")

    qty = 수량 or 1
    now = datetime.now().isoformat()
    vendor, product, option = 업체명, 제품명, _strip_option(옵션)
    barcode = _clean(바코드)
    work = 작업.strip()
    defect = _clean(불량명)
    resolved_work = repair_catalog.resolve_work_type(work)
    if resolved_work:
        work = resolved_work["작업명"]
    resolved_defect = repair_catalog.resolve_defect(defect)
    if resolved_defect:
        defect = resolved_defect["불량명"]

    with get_connection() as con:
        if barcode:
            found = _lookup_barcode(con, barcode)
            if found:
                vendor = vendor or found["업체명"]
                product = product or found["제품명"]
                option = option or found["옵션"]
        if vendor:
            vendor = _resolve_vendor(con, vendor)
        if not vendor or not product:
            raise ValueError("업체명과 제품명이 필요합니다. 바코드를 등록하거나 직접 입력하세요.")

        cur = con.execute(
            """INSERT INTO repair_work_log
               (날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고, 작성자, 저장시간, 출처,
                barcode_image, before_image, after_image)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                날짜, vendor, product, option, barcode, defect, work,
                qty, int(비용), _clean(비고), _clean(작성자), now, 출처,
                barcode_image, before_image, after_image,
            ),
        )
        con.commit()
        log_id = cur.lastrowid

    add_log(
        action_type="수선일지_생성",
        target_type="repair_work_log",
        target_id=str(log_id),
        target_name=f"{vendor} {work}",
        user_nickname=작성자 or "웹",
        details=f"날짜: {날짜}, 비용: {비용:,}원",
    )
    if price_stated:
        msg = f"표기된 가격 {int(비용):,}원으로 저장했습니다. ({vendor} {work})"
    else:
        msg = f"수선일지를 저장했습니다. {vendor} / {product} / {work} {int(비용):,}원"
    return {
        "success": True,
        "id": log_id,
        "message": msg,
        "업체명": vendor,
        "제품명": product,
        "옵션": option,
        "바코드": barcode,
        "불량명": defect,
        "작업": work,
        "비용": int(비용),
    }


def save_image_bytes(data: bytes, ext: str = ".jpg") -> str:
    ensure_repair_tables()
    ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    if ext not in IMAGE_EXTS:
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return filename


def upsert_repair_barcode_record(
    barcode: str,
    업체명: str,
    제품명: str,
    옵션: Optional[str] = None,
    출처: str = "bot",
) -> dict:
    ensure_repair_tables()
    code = _clean(barcode)
    vendor = _clean(업체명)
    product = _clean(제품명)
    if not code or not vendor or not product:
        raise ValueError("바코드, 업체명, 제품명은 필수입니다.")
    now = datetime.now().isoformat()
    with get_connection() as con:
        vendor = _resolve_vendor(con, vendor)
        con.execute(
            """INSERT INTO repair_barcode (바코드, 업체명, 제품명, 옵션, 출처, 저장시간)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(바코드) DO UPDATE SET
                 업체명=excluded.업체명,
                 제품명=excluded.제품명,
                 옵션=COALESCE(excluded.옵션, repair_barcode.옵션),
                 출처=excluded.출처,
                 저장시간=excluded.저장시간""",
            (code, vendor, product, _strip_option(옵션), 출처, now),
        )
        con.commit()
    return {"바코드": code, "업체명": vendor, "제품명": product, "옵션": _strip_option(옵션)}


@router.post("")
async def create_log(data: RepairLogCreate):
    try:
        return insert_repair_log_record(
            날짜=data.날짜,
            작업=data.작업,
            비용=data.비용,
            업체명=data.업체명,
            제품명=data.제품명,
            옵션=data.옵션,
            바코드=data.바코드,
            불량명=data.불량명,
            수량=data.수량,
            비고=data.비고,
            작성자=data.작성자,
            출처=data.출처,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{log_id}/photos")
async def upload_photos(
    log_id: int,
    before: Optional[UploadFile] = File(None),
    after: Optional[UploadFile] = File(None),
    barcode: Optional[UploadFile] = File(None),
):
    ensure_repair_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT before_image, after_image, barcode_image FROM repair_work_log WHERE id = ?",
            (log_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="수선일지를 찾을 수 없습니다.")

        updates, params = [], []
        mapping = [
            ("before", before, "before_image", row[0]),
            ("after", after, "after_image", row[1]),
            ("barcode", barcode, "barcode_image", row[2]),
        ]
        saved = {}
        for _, upload, col, old in mapping:
            if upload and upload.filename:
                filename = await _save_upload(upload)
                _delete_image(old)
                updates.append(f"{col} = ?")
                params.append(filename)
                saved[col] = filename

        if not updates:
            raise HTTPException(status_code=400, detail="업로드할 사진이 없습니다.")
        params.append(log_id)
        con.execute(f"UPDATE repair_work_log SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()

    return {"success": True, "saved": saved, "message": "사진이 저장되었습니다."}


@router.put("/{log_id}")
async def update_log(log_id: int, data: RepairLogUpdate):
    ensure_repair_tables()
    with get_connection() as con:
        existing = con.execute(
            "SELECT id, 업체명, 작업 FROM repair_work_log WHERE id = ?", (log_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="수선일지를 찾을 수 없습니다.")

        payload = data.model_dump(exclude_unset=True)
        if "옵션" in payload:
            payload["옵션"] = _strip_option(payload["옵션"])
        if "바코드" in payload:
            payload["바코드"] = _clean(payload["바코드"])
        if "작업" in payload and payload["작업"]:
            resolved = repair_catalog.resolve_work_type(payload["작업"])
            payload["작업"] = resolved["작업명"] if resolved else payload["작업"].strip()
        if "불량명" in payload and payload["불량명"]:
            resolved_d = repair_catalog.resolve_defect(payload["불량명"])
            payload["불량명"] = resolved_d["불량명"] if resolved_d else payload["불량명"].strip()
        if "업체명" in payload and payload["업체명"]:
            payload["업체명"] = _resolve_vendor(con, payload["업체명"])

        updates, params = [], []
        for col, val in payload.items():
            updates.append(f"{col} = ?")
            params.append(val)

        if not updates:
            raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")
        params.append(log_id)
        con.execute(f"UPDATE repair_work_log SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()

    return {"success": True, "message": "수선일지가 수정되었습니다."}


@router.delete("/{log_id}")
async def delete_log(log_id: int):
    ensure_repair_tables()
    with get_connection() as con:
        row = con.execute(
            """SELECT 날짜, 업체명, 작업, 비용, barcode_image, before_image, after_image
               FROM repair_work_log WHERE id = ?""",
            (log_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="수선일지를 찾을 수 없습니다.")
        con.execute("DELETE FROM repair_work_log WHERE id = ?", (log_id,))
        con.commit()

    for fn in (row[4], row[5], row[6]):
        _delete_image(fn)

    add_log(
        action_type="수선일지_삭제",
        target_type="repair_work_log",
        target_id=str(log_id),
        target_name=f"{row[1]} {row[2]}",
        user_nickname="웹",
        details=f"날짜: {row[0]}, 비용: {row[3] or 0:,}원",
    )
    return {"success": True, "message": "수선일지가 삭제되었습니다."}
