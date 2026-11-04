"""반품정보 조회. 재입고 대기 엑셀 헤더를 그대로 필터하고 내려받는다."""
from __future__ import annotations

import io
import re
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from logic.db import ensure_tables, get_connection

router = APIRouter(prefix="/return-info", tags=["Return Info"])

RETURN_HEADERS = [
    "상태",
    "등록일",
    "등록자",
    "입고일",
    "관리번호",
    "발주일",
    "판매처",
    "주문번호",
    "수령자",
    "상품명",
    "바코드",
    "옵션",
    "수량",
    "불량",
    "CS이력",
    "반품메모",
    "공급처",
]
DATE_HEADERS = ("등록일", "입고일", "발주일")
CHOICE_HEADERS = ("판매처", "상품명", "공급처")
MULTI_HEADERS = ("판매처", "공급처")
FILTER_SKIP = {"CS이력"}
OPTION_LIMIT = 2000
EXPORT_LIMIT = 20000
REPORT_HEADERS = (
    "등록일",
    "등록자",
    "관리번호",
    "주문번호",
    "판매처",
    "수령자",
    "상품명",
    "옵션",
    "바코드",
    "수량",
    "불량",
    "CS이력",
    "반품메모",
)


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _columns(con) -> list[str]:
    existing = [row[1] for row in con.execute("PRAGMA table_info(return_info)")]
    ordered = [name for name in RETURN_HEADERS if name in existing]
    extras = [name for name in existing if name not in ordered and name != "id"]
    return ordered + extras


def _values(query, name: str) -> list[str]:
    raw = query.getlist(name) if hasattr(query, "getlist") else [query.get(name) or ""]
    values: list[str] = []
    for item in raw:
        for part in str(item or "").split("\n"):
            text = part.strip()
            if text and text not in values:
                values.append(text)
    return values


def _where(columns: list[str], query) -> tuple[str, list]:
    clauses = ["1=1"]
    params: list = []
    keyword = (query.get("q") or "").strip()
    if len(keyword) > 100:
        raise HTTPException(status_code=400, detail="검색어는 100자까지입니다.")
    if keyword and columns:
        params.extend(_like(keyword) for _name in columns)
        clauses.append(
            "("
            + " OR ".join(
                f"CAST(COALESCE([{name}], '') AS TEXT) LIKE ? ESCAPE '\\'" for name in columns
            )
            + ")"
        )
    present = set(columns)
    for name in columns:
        if name in DATE_HEADERS:
            start = (query.get(f"{name}_from") or "").strip()
            end = (query.get(f"{name}_to") or "").strip()
            if start:
                clauses.append(f"substr(COALESCE([{name}], ''), 1, 10) >= ?")
                params.append(start)
            if end:
                clauses.append(f"substr(COALESCE([{name}], ''), 1, 10) <= ?")
                params.append(end)
            continue
        if name not in present or name in FILTER_SKIP:
            continue
        if name in MULTI_HEADERS:
            values = _values(query, name)
            if not values:
                continue
            if len(values) == 1:
                clauses.append(f"TRIM(COALESCE([{name}], '')) LIKE ? ESCAPE '\\'")
                params.append(_like(values[0]))
            else:
                clauses.append(
                    "("
                    + " OR ".join(f"TRIM(COALESCE([{name}], '')) = ?" for _value in values)
                    + ")"
                )
                params.extend(values)
            continue
        text = (query.get(name) or "").strip()
        if not text:
            continue
        if name in CHOICE_HEADERS:
            clauses.append(f"TRIM(COALESCE([{name}], '')) LIKE ? ESCAPE '\\'")
            params.append(_like(text))
            continue
        clauses.append(f"[{name}] LIKE ? ESCAPE '\\'")
        params.append(_like(text))
    return "WHERE " + " AND ".join(clauses), params


def _cell(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _rows(con, columns: list[str], where: str, params: list, limit: int, offset: int):
    col_sql = ", ".join(f"[{name}]" for name in columns)
    order = "id DESC"
    if "등록일" in columns:
        order = "substr(COALESCE([등록일], ''), 1, 10) DESC, id DESC"
    fetched = con.execute(
        f"""SELECT {col_sql}
            FROM return_info {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    total = con.execute(
        f"SELECT COUNT(*) FROM return_info {where}", params
    ).fetchone()[0]
    rows = [
        {column: _cell(fetched[index][col_index]) for col_index, column in enumerate(columns)}
        for index in range(len(fetched))
    ]
    return rows, int(total)


@router.get("/options")
async def return_info_options():
    """판매처, 상품명, 공급처의 올라간 값을 중복 없이 돌려준다."""
    ensure_tables()
    result = {name: [] for name in CHOICE_HEADERS}
    with get_connection() as con:
        present = set(_columns(con))
        for name in CHOICE_HEADERS:
            if name not in present:
                continue
            fetched = con.execute(
                f"""SELECT DISTINCT TRIM([{name}]) AS value
                    FROM return_info
                    WHERE TRIM(COALESCE([{name}], '')) != ''
                    ORDER BY value
                    LIMIT ?""",
                (OPTION_LIMIT,),
            ).fetchall()
            result[name] = [row[0] for row in fetched]
    return result


@router.get("")
@router.get("/")
async def list_return_info(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """헤더별 필터와 페이지로 반품정보를 조회한다."""
    ensure_tables()
    with get_connection() as con:
        columns = _columns(con)
        if not columns:
            return {"columns": RETURN_HEADERS, "rows": [], "total": 0, "page": page, "page_size": page_size}
        where, params = _where(columns, request.query_params)
        rows, total = _rows(con, columns, where, params, page_size, (page - 1) * page_size)
    return {
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/export")
async def export_return_info(request: Request):
    """현재 필터의 전체 행을 원본 헤더 순서의 엑셀로 내려받는다."""
    ensure_tables()
    with get_connection() as con:
        columns = _columns(con) or list(RETURN_HEADERS)
        where, params = _where(columns, request.query_params)
        total = con.execute(
            f"SELECT COUNT(*) FROM return_info {where}", params
        ).fetchone()[0]
        if total == 0:
            raise HTTPException(status_code=404, detail="조건에 맞는 반품정보가 없습니다.")
        if total > EXPORT_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"엑셀은 한 번에 {EXPORT_LIMIT}건까지입니다. 필터를 더 좁혀 주세요. (현재 {total}건)",
            )
        rows, _total = _rows(con, columns, where, params, int(total), 0)
    frame = pd.DataFrame(rows, columns=columns)
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=return_info.xlsx"},
    )


def _author_name(token: str) -> str:
    if not token.strip():
        return ""
    with get_connection() as con:
        row = con.execute(
            """SELECT u.nickname
               FROM sessions s JOIN users u ON s.user_id = u.user_id
               WHERE s.token = ?""",
            (token.strip(),),
        ).fetchone()
    return str(row[0]).strip() if row and row[0] else ""


def _report_filename(supplier: str, today: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|,\s]+', "_", supplier).strip("._")
    stem = f"{safe}_{today}" if safe else f"반품보고서_{today}"
    return f"{stem}.xlsx"


def _supplier_label(rows: list[dict]) -> str:
    names: list[str] = []
    for row in rows:
        name = str(row.get("공급처") or "").strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def _report_workbook(rows: list[dict], supplier: str, author: str, today: str) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "반품 보고서"
    title_font = Font(name="맑은 고딕", size=22, bold=True)
    label_font = Font(name="맑은 고딕", size=11, bold=True)
    body_font = Font(name="맑은 고딕", size=10)
    header_fill = PatternFill("solid", fgColor="E8EEF4")
    wrap = Alignment(wrap_text=True, vertical="top")
    sheet["A1"] = "반품 보고서"
    sheet["A1"].font = title_font
    sheet["A1"].alignment = Alignment(vertical="center")
    sheet.merge_cells("A1:D1")
    sheet.row_dimensions[1].height = 32
    info = (("공급처", supplier), ("작성일", today), ("등록자", author))
    for index, (label, value) in enumerate(info, start=3):
        sheet.cell(index, 1, label).font = label_font
        sheet.cell(index, 2, value).font = body_font
    header_row = 7
    headers = ("번호", *REPORT_HEADERS)
    for col_index, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_index, header)
        cell.font = label_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    for row_index, row in enumerate(rows, start=1):
        values = [row_index, *[row.get(name) for name in REPORT_HEADERS]]
        for col_index, value in enumerate(values, start=1):
            cell = sheet.cell(header_row + row_index, col_index, _cell(value) if col_index > 1 else value)
            cell.font = body_font
            cell.alignment = wrap
    widths = {
        "번호": 8,
        "등록일": 14,
        "등록자": 12,
        "관리번호": 16,
        "주문번호": 16,
        "판매처": 16,
        "수령자": 12,
        "상품명": 22,
        "옵션": 16,
        "바코드": 18,
        "수량": 8,
        "불량": 10,
        "CS이력": 40,
        "반품메모": 28,
    }
    for col_index, header in enumerate(headers, start=1):
        sheet.column_dimensions[get_column_letter(col_index)].width = widths.get(header, 14)
    sheet.freeze_panes = "A8"
    sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(headers))}{header_row + max(len(rows), 1)}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@router.get("/report")
async def report_return_info(request: Request):
    """현재 필터의 전체 행을 고객 전달용 반품 보고서 엑셀로 내려받는다."""
    ensure_tables()
    with get_connection() as con:
        columns = _columns(con) or list(RETURN_HEADERS)
        where, params = _where(columns, request.query_params)
        total = con.execute(
            f"SELECT COUNT(*) FROM return_info {where}", params
        ).fetchone()[0]
        if total == 0:
            raise HTTPException(status_code=404, detail="조건에 맞는 반품정보가 없습니다.")
        if total > EXPORT_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"보고서는 한 번에 {EXPORT_LIMIT}건까지입니다. 필터를 더 좁혀 주세요. (현재 {total}건)",
            )
        rows, _total = _rows(con, columns, where, params, int(total), 0)
    supplier = _supplier_label(rows)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    payload = _report_workbook(
        rows,
        supplier,
        _author_name(request.query_params.get("token") or ""),
        today,
    )
    filename = quote(_report_filename(supplier, today))
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"return_report.xlsx\"; filename*=UTF-8''{filename}"},
    )
