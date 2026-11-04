"""반품정보 조회. 재입고 대기 엑셀 헤더를 그대로 필터하고 내려받는다."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

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
    "옵션",
    "수량",
    "불량",
    "CS이력",
    "반품메모",
    "바코드",
]
DATE_HEADERS = ("등록일", "입고일", "발주일")
EXPORT_LIMIT = 20000


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _columns(con) -> list[str]:
    existing = [row[1] for row in con.execute("PRAGMA table_info(return_info)")]
    ordered = [name for name in RETURN_HEADERS if name in existing]
    extras = [name for name in existing if name not in ordered and name != "id"]
    return ordered + extras


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
        if name not in present:
            continue
        text = (query.get(name) or "").strip()
        if text:
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
