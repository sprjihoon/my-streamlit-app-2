"""Barcode product table and repair catalog endpoints."""
from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

from logic.db import get_connection

import pandas as pd
from fastapi import File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.services import repair_catalog

from .common import (
    _clean,
    _clean_vendor,
    _lookup_barcode,
    _resolve_vendor,
    _strip_option,
    ensure_repair_tables,
)
from .router import router

class BarcodeCreate(BaseModel):
    바코드: str
    업체명: str
    제품명: str
    옵션: Optional[str] = None
    도매처: Optional[str] = None
    도매처주소: Optional[str] = None    # 공급처 위치
    도매처연락처: Optional[str] = None  # 공급처 연락처
    상품코드: Optional[str] = None
    로케이션: Optional[str] = None
    상품명: Optional[str] = None
    출처: str = "manual"


class BarcodeUpdate(BaseModel):
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    도매처: Optional[str] = None
    도매처주소: Optional[str] = None    # 공급처 위치
    도매처연락처: Optional[str] = None  # 공급처 연락처
    상품코드: Optional[str] = None
    로케이션: Optional[str] = None
    상품명: Optional[str] = None

class WorkTypeBody(BaseModel):
    작업명: str
    기본비용: int
    별칭: Optional[str] = None


class DefectBody(BaseModel):
    불량명: str
    별칭: Optional[str] = None

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


def _find_col_idx(columns, *names) -> Optional[int]:
    """컬럼명으로 첫 번째 매칭 인덱스 반환."""
    for name in names:
        for i, c in enumerate(columns):
            if str(c).strip() == name:
                return i
    return None


def _find_vendor_col_idx(columns) -> Optional[int]:
    """첫 번째 '공급처' 열 인덱스 = 화주사(업체명).
    중복 컬럼명이 있어도 위치 기반으로 정확히 접근한다."""
    for i, c in enumerate(columns):
        if str(c).strip() == "공급처":
            return i
    return _find_col_idx(columns, "업체명")


def _find_wholesale_col_idx(columns) -> Optional[int]:
    """마지막 '공급처' 열 인덱스 = 도매처.
    '공급처' 컬럼이 2개 이상일 때만 반환."""
    idxs = [i for i, c in enumerate(columns) if str(c).strip() == "공급처"]
    if len(idxs) >= 2:
        return idxs[-1]
    return None


def _parse_barcode_rows(df: pd.DataFrame) -> List[dict]:
    cols = list(df.columns)

    barcode_idx = _find_col_idx(cols, "바코드")
    vendor_idx = _find_vendor_col_idx(cols)
    wholesale_idx = _find_wholesale_col_idx(cols)
    short_name_idx = _find_col_idx(cols, "공급처 상품명", "제품명")
    long_name_idx = _find_col_idx(cols, "상품명")
    option_idx = _find_col_idx(cols, "공급처 옵션", "옵션")
    code_idx = _find_col_idx(cols, "상품코드")
    loc_idx = _find_col_idx(cols, "로케이션")
    sup_loc_idx = _find_col_idx(cols, "공급처 위치", "도매처주소")
    sup_contact_idx = _find_col_idx(cols, "공급처 연락처", "도매처연락처")

    if barcode_idx is None:
        raise HTTPException(status_code=400, detail="바코드 열이 없습니다.")
    if vendor_idx is None:
        raise HTTPException(status_code=400, detail="공급처(업체명) 열이 없습니다.")

    rows = []
    for _, r in df.iterrows():
        barcode = _clean(r.iloc[barcode_idx])
        vendor = _clean_vendor(r.iloc[vendor_idx])
        wholesale = _clean_vendor(r.iloc[wholesale_idx]) if wholesale_idx is not None else None
        short_name = _clean(r.iloc[short_name_idx]) if short_name_idx is not None else None
        long_name = _clean(r.iloc[long_name_idx]) if long_name_idx is not None else None
        product = short_name or long_name
        if not barcode or not vendor or not product:
            continue
        rows.append({
            "바코드": barcode,
            "업체명": vendor,
            "도매처": wholesale,
            "제품명": product,
            "옵션": _strip_option(_clean(r.iloc[option_idx])) if option_idx is not None else None,
            "도매처주소": _clean(r.iloc[sup_loc_idx]) if sup_loc_idx is not None else None,
            "도매처연락처": _clean(r.iloc[sup_contact_idx]) if sup_contact_idx is not None else None,
            "상품코드": _clean(r.iloc[code_idx]) if code_idx is not None else None,
            "로케이션": _clean(r.iloc[loc_idx]) if loc_idx is not None else None,
            "상품명": long_name,
        })
    return rows

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
            where += " AND (바코드 LIKE ? OR 제품명 LIKE ? OR 상품명 LIKE ? OR 옵션 LIKE ? OR 도매처 LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like, like, like, like])
        if vendor:
            # 별칭 테이블에서 해당 vendor에 연결된 모든 업체명 수집
            vendor_names = [vendor]
            try:
                alias_row = con.execute(
                    "SELECT aliases FROM inbound_vendor_aliases WHERE canonical=?", (vendor,)
                ).fetchone()
                if alias_row and alias_row[0]:
                    vendor_names += [a.strip() for a in alias_row[0].split(',') if a.strip()]
                # vendor가 별칭으로 등록된 경우 canonical도 추가
                canon_rows = con.execute(
                    "SELECT canonical FROM inbound_vendor_aliases WHERE ',' || aliases || ',' LIKE ?",
                    (f"%,{vendor},%",)
                ).fetchall()
                for r in canon_rows:
                    if r[0] and r[0] not in vendor_names:
                        vendor_names.append(r[0])
            except Exception:
                pass
            ph = ','.join('?' * len(vendor_names))
            where += f" AND 업체명 IN ({ph})"
            params.extend(vendor_names)

        total = con.execute(f"SELECT COUNT(*) FROM repair_barcode {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT 바코드, 업체명, 제품명, 옵션, 상품코드, 로케이션, 상품명, 출처, 저장시간, 도매처, 도매처주소, 도매처연락처
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
            "도매처": r[9] if len(r) > 9 else None,
            "도매처주소": r[10] if len(r) > 10 else None,
            "도매처연락처": r[11] if len(r) > 11 else None,
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
    df = pd.DataFrame(columns=[
        "바코드", "업체명", "공급처 상품명", "공급처 옵션",
        "공급처 위치", "공급처 연락처", "공급처",   # 공급처=도매처(마지막 열)
        "상품코드", "로케이션", "상품명",
    ])
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
                   (바코드, 업체명, 도매처, 제품명, 옵션, 도매처주소, 도매처연락처, 상품코드, 로케이션, 상품명, 출처, 저장시간)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel', ?)
                   ON CONFLICT(바코드) DO UPDATE SET
                     업체명=excluded.업체명,
                     도매처=excluded.도매처,
                     제품명=excluded.제품명,
                     옵션=excluded.옵션,
                     도매처주소=COALESCE(excluded.도매처주소, 도매처주소),
                     도매처연락처=COALESCE(excluded.도매처연락처, 도매처연락처),
                     상품코드=excluded.상품코드,
                     로케이션=excluded.로케이션,
                     상품명=excluded.상품명,
                     출처='excel',
                     저장시간=excluded.저장시간""",
                (
                    row["바코드"], vendor, row.get("도매처"), row["제품명"], row.get("옵션"),
                    row.get("도매처주소"), row.get("도매처연락처"),
                    row.get("상품코드"), row.get("로케이션"), row.get("상품명"), now,
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
               (바코드, 업체명, 도매처, 제품명, 옵션, 도매처주소, 도매처연락처, 상품코드, 로케이션, 상품명, 출처, 저장시간)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                barcode, vendor, _clean(data.도매처), data.제품명.strip(), _strip_option(data.옵션),
                _clean(data.도매처주소), _clean(data.도매처연락처),
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
        if data.도매처 is not None:
            updates.append("도매처 = ?")
            params.append(_clean(data.도매처))
        if data.도매처주소 is not None:
            updates.append("도매처주소 = ?")
            params.append(_clean(data.도매처주소))
        if data.도매처연락처 is not None:
            updates.append("도매처연락처 = ?")
            params.append(_clean(data.도매처연락처))
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


@router.delete("/barcodes")
async def delete_all_barcodes():
    """repair_barcode 테이블 전체 삭제 (잘못 업로드된 데이터 초기화용)."""
    ensure_repair_tables()
    with get_connection() as con:
        cnt = con.execute("SELECT COUNT(*) FROM repair_barcode").fetchone()[0]
        con.execute("DELETE FROM repair_barcode")
        con.commit()
    return {"success": True, "deleted": cnt, "message": f"{cnt}건의 바코드 데이터를 모두 삭제했습니다."}


@router.get("/catalog")
async def get_catalog():
    ensure_repair_tables()
    return {
        "work_types": repair_catalog.list_work_types(),
        "defects": repair_catalog.list_defects(),
    }


@router.get("/catalog/price")
async def get_catalog_price(
    work_type: str,
    vendor: Optional[str] = None,
    product: Optional[str] = None,
):
    ensure_repair_tables()
    return repair_catalog.lookup_repair_price(vendor, work_type, product)


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
