"""반품정보 조회. 재입고 대기 엑셀 헤더를 그대로 필터하고 내려받는다."""
from __future__ import annotations

import io
import json
import re
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from logic.db import ensure_tables, get_connection, now_str

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
    "수정사항메모",
)
MEMO_HEADER = "수정사항메모"
DEFECT_VALUES = ("정상", "불량")
DEFECT_BATCH_LIMIT = 200
MANUAL_TEXT_LIMITS = {
    "상태": 50,
    "등록자": 50,
    "관리번호": 100,
    "주문번호": 100,
    "수령자": 100,
    "판매처": 200,
    "상품명": 300,
    "바코드": 100,
    "옵션": 300,
    "불량": 100,
    "공급처": 200,
    "CS이력": 20000,
    "반품메모": 4000,
    "수정사항메모": 4000,
}
MANUAL_CONTENT_HEADERS = tuple(name for name in RETURN_HEADERS if name not in {"등록일", "등록자"})
SOURCE_HEADER = "입력구분"
MANUAL_MARK = "수동 입력"
QTY_MAX = 1_000_000
HIDDEN_COLUMNS = {"id", "deleted_at", "deleted_by"}
EDITABLE_HEADERS = tuple([*RETURN_HEADERS, MEMO_HEADER])
LIVE_SQL = "(deleted_at IS NULL OR TRIM(COALESCE(deleted_at, '')) = '')"
LOG_ACTIONS = ("create", "update", "delete", "restore")
ACTION_LABELS = {"create": "추가", "update": "수정", "delete": "삭제", "restore": "복구"}


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _columns(con) -> list[str]:
    existing = [row[1] for row in con.execute("PRAGMA table_info(return_info)")]
    ordered = [name for name in RETURN_HEADERS if name in existing]
    if MEMO_HEADER in existing and MEMO_HEADER not in ordered:
        if "반품메모" in ordered:
            ordered.insert(ordered.index("반품메모") + 1, MEMO_HEADER)
        else:
            ordered.append(MEMO_HEADER)
    extras = [name for name in existing if name not in ordered and name not in HIDDEN_COLUMNS]
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
    clauses = [LIVE_SQL]
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


_MIDNIGHT_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]00:00:00(?:\.\d+)?$")


def _date_cell(value):
    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        match = _MIDNIGHT_DATE.match(value.strip())
        if match:
            return match.group(1)
    return value


def _cell(value, column: str | None = None):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if column in DATE_HEADERS:
        return _date_cell(value)
    return value


def _rows(con, columns: list[str], where: str, params: list, limit: int, offset: int):
    col_sql = ", ".join(f"[{name}]" for name in columns)
    order = "id DESC"
    if "등록일" in columns:
        order = "substr(COALESCE([등록일], ''), 1, 10) DESC, id DESC"
    fetched = con.execute(
        f"""SELECT id, {col_sql}
            FROM return_info {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    total = con.execute(
        f"SELECT COUNT(*) FROM return_info {where}", params
    ).fetchone()[0]
    rows = []
    for record in fetched:
        row = {"id": int(record[0])}
        for col_index, column in enumerate(columns):
            row[column] = _cell(record[col_index + 1], column)
        rows.append(row)
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
                      AND {LIVE_SQL}
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


def _session_actor(token: str) -> tuple[int, str]:
    text = token.strip()
    if not text:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    with get_connection() as con:
        row = con.execute(
            """SELECT u.user_id, u.nickname
               FROM sessions s JOIN users u ON s.user_id = u.user_id
               WHERE s.token = ?""",
            (text,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return int(row[0]), (str(row[1]).strip() if row[1] else "")


def _session_nickname(token: str) -> str:
    return _session_actor(token)[1]


def _manual_text(name: str, value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{name} 값이 올바르지 않습니다.")
    text = value.strip()
    if not text:
        return None
    limit = MANUAL_TEXT_LIMITS.get(name, 500)
    if len(text) > limit:
        raise HTTPException(status_code=400, detail=f"{name}은(는) {limit}자까지입니다.")
    return text


def _manual_date(name: str, value, required: bool) -> str | None:
    text = _manual_text(name, value)
    if text is None:
        if required:
            raise HTTPException(status_code=400, detail="등록일을 입력해 주세요.")
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise HTTPException(status_code=400, detail=f"{name}은(는) YYYY-MM-DD 형식입니다.")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name}은(는) YYYY-MM-DD 형식입니다.") from None
    return text


def _manual_qty(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, (list, dict)):
        raise HTTPException(status_code=400, detail="수량은 0 이상의 정수로 입력해 주세요.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise HTTPException(status_code=400, detail="수량은 0 이상의 정수로 입력해 주세요.")
    if number < 0 or number > QTY_MAX:
        raise HTTPException(status_code=400, detail="수량은 0 이상의 정수로 입력해 주세요.")
    return number


def _normalize_manual_row(payload, nickname: str) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="입력 형식이 올바르지 않습니다.")
    allowed = set(RETURN_HEADERS) | {MEMO_HEADER}
    if any(key not in allowed for key in payload):
        raise HTTPException(status_code=400, detail="허용되지 않은 항목이 있습니다.")
    values = {}
    for name in RETURN_HEADERS:
        raw = payload.get(name)
        if name in DATE_HEADERS:
            values[name] = _manual_date(name, raw, required=(name == "등록일"))
        elif name == "수량":
            values[name] = _manual_qty(raw)
        else:
            values[name] = _manual_text(name, raw)
    values[MEMO_HEADER] = _manual_text(MEMO_HEADER, payload.get(MEMO_HEADER))
    if not values.get("등록자") and nickname:
        values["등록자"] = nickname
    if not any(values.get(name) not in (None, "") for name in (*MANUAL_CONTENT_HEADERS, MEMO_HEADER)):
        raise HTTPException(status_code=400, detail="등록일 외에 내용을 하나 이상 입력해 주세요.")
    return values


def _same_return_row(con, values: dict, exclude_id: int | None = None) -> bool:
    present = set(_columns(con))
    clauses: list[str] = []
    params: list = []
    for name in RETURN_HEADERS:
        if name not in present:
            continue
        value = values.get(name)
        if name == "수량":
            if value is None:
                clauses.append(
                    f"([{name}] IS NULL OR TRIM(COALESCE(CAST([{name}] AS TEXT), '')) = '')"
                )
            else:
                clauses.append(f"[{name}] = ?")
                params.append(value)
            continue
        if name in DATE_HEADERS:
            clauses.append(f"substr(TRIM(COALESCE(CAST([{name}] AS TEXT), '')), 1, 10) = ?")
            params.append(value or "")
            continue
        clauses.append(f"TRIM(COALESCE(CAST([{name}] AS TEXT), '')) = ?")
        params.append(value or "")
    if not clauses:
        return False
    clauses.append(LIVE_SQL)
    if exclude_id is not None:
        clauses.append("id != ?")
        params.append(exclude_id)
    found = con.execute(
        "SELECT 1 FROM return_info WHERE " + " AND ".join(clauses) + " LIMIT 1",
        params,
    ).fetchone()
    return found is not None


def _insert_return_row(con, values: dict) -> int:
    present = set(_columns(con))
    names = [name for name in (*RETURN_HEADERS, MEMO_HEADER) if name in present]
    if SOURCE_HEADER in present:
        names.append(SOURCE_HEADER)
    if not names:
        raise HTTPException(status_code=500, detail="반품정보 항목을 저장할 수 없습니다.")
    col_sql = ", ".join(f"[{name}]" for name in names)
    marks = ", ".join("?" for _name in names)
    cursor = con.execute(
        f"INSERT INTO return_info ({col_sql}) VALUES ({marks})",
        [values.get(name) for name in names],
    )
    return int(cursor.lastrowid)


@router.post("")
@router.post("/")
async def create_return_info(request: Request, payload: dict = Body(...)):
    """로그인한 사용자가 헤더별 값을 한 건 저장한다. 엑셀 업로드와 작업일지는 바꾸지 않는다."""
    actor = _session_actor(request.query_params.get("token") or "")
    values = _normalize_manual_row(payload, actor[1])
    values[SOURCE_HEADER] = MANUAL_MARK
    ensure_tables()
    with get_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            if _same_return_row(con, values):
                con.rollback()
                raise HTTPException(status_code=409, detail="같은 내용의 반품정보가 이미 있습니다.")
            row_id = _insert_return_row(con, values)
            stored = dict(values)
            stored["id"] = row_id
            _write_log(
                con,
                row_id=row_id,
                action="create",
                actor=actor,
                summary=_action_summary("추가", stored),
                changes=_filled_changes(stored),
                snapshot=stored,
            )
            con.commit()
        except HTTPException:
            raise
        except Exception:
            con.rollback()
            raise
    return {"id": row_id, "row": values}


def _action_summary(label: str, row: dict) -> str:
    name = str(row.get("상품명") or "").strip() or "상품명 없음"
    number = str(row.get("관리번호") or "").strip()
    if number:
        return f"{label} · {name} · {number}"
    return f"{label} · {name}"


def _json_ready(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _write_log(con, *, row_id: int | None, action: str, actor: tuple[int, str], summary: str, changes=None, snapshot=None, restored_log_id: int | None = None) -> int:
    cursor = con.execute(
        """INSERT INTO return_info_log
           (return_info_id, action, actor_id, actor_name, summary, changes_json, snapshot_json, restored_log_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            row_id,
            action,
            actor[0],
            actor[1],
            summary,
            json.dumps(changes, ensure_ascii=False) if changes is not None else None,
            json.dumps(snapshot, ensure_ascii=False, default=_json_ready) if snapshot is not None else None,
            restored_log_id,
            now_str(),
        ),
    )
    return int(cursor.lastrowid)


def _value_changed(name: str, before, after) -> bool:
    if name == "수량":
        return before != after
    if name in DATE_HEADERS:
        return str(before or "")[:10] != str(after or "")[:10]
    return str(before or "").strip() != str(after or "").strip()


def _filled_changes(row: dict) -> list[dict]:
    changes = []
    for name in (*RETURN_HEADERS, MEMO_HEADER, SOURCE_HEADER):
        value = row.get(name)
        if value in (None, ""):
            continue
        changes.append({"field": name, "before": None, "after": _json_ready(value)})
    return changes


def _load_row(con, row_id: int) -> dict | None:
    columns = _columns(con)
    if not columns:
        return None
    col_sql = ", ".join(f"[{name}]" for name in columns)
    record = con.execute(
        f"SELECT id, deleted_at, {col_sql} FROM return_info WHERE id = ?",
        (row_id,),
    ).fetchone()
    if not record:
        return None
    row = {"id": int(record[0]), "deleted_at": record[1]}
    for index, name in enumerate(columns):
        row[name] = _cell(record[index + 2], name)
    return row


def _public_row(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in HIDDEN_COLUMNS and key != "deleted_at"}


def _snapshot(row: dict) -> dict:
    return {key: _json_ready(value) for key, value in _public_row(row).items()}


def _normalize_patch(payload) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=400, detail="바꿀 항목을 입력해 주세요.")
    if any(key not in EDITABLE_HEADERS for key in payload):
        raise HTTPException(status_code=400, detail="허용되지 않은 항목이 있습니다.")
    values = {}
    for name, raw in payload.items():
        if name in DATE_HEADERS:
            values[name] = _manual_date(name, raw, required=False)
        elif name == "수량":
            values[name] = _manual_qty(raw)
        else:
            values[name] = _manual_text(name, raw)
    return values


def _defect_ids(value) -> list[int]:
    if not isinstance(value, list) or not value:
        raise HTTPException(status_code=400, detail="변경할 행을 선택해 주세요.")
    if len(value) > DEFECT_BATCH_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"한 번에 {DEFECT_BATCH_LIMIT}건까지 변경할 수 있습니다.",
        )
    ids: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise HTTPException(status_code=400, detail="선택한 행이 올바르지 않습니다.")
        if item not in ids:
            ids.append(item)
    return ids


def _normalize_defect_update(payload) -> tuple[list[int], str, str | None]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="입력 형식이 올바르지 않습니다.")
    allowed = {"ids", "불량", MEMO_HEADER}
    if any(key not in allowed for key in payload):
        raise HTTPException(status_code=400, detail="불량과 수정사항메모만 변경할 수 있습니다.")
    if "불량" not in payload:
        raise HTTPException(status_code=400, detail="불량은 정상 또는 불량만 선택할 수 있습니다.")
    defect = payload.get("불량")
    if defect not in DEFECT_VALUES:
        raise HTTPException(status_code=400, detail="불량은 정상 또는 불량만 선택할 수 있습니다.")
    memo = None
    if MEMO_HEADER in payload:
        memo = _manual_text(MEMO_HEADER, payload.get(MEMO_HEADER))
    return _defect_ids(payload.get("ids")), defect, memo


@router.post("/defect")
async def update_return_info_defect(request: Request, payload: dict = Body(...)):
    """선택한 반품정보의 불량만 정상 또는 불량으로 바꾼다. 메모가 있으면 같은 행에 남긴다."""
    actor = _session_actor(request.query_params.get("token") or "")
    ids, defect, memo = _normalize_defect_update(payload)
    ensure_tables()
    marks = ", ".join("?" for _item in ids)
    with get_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            found = con.execute(
                f"""SELECT id, [불량], [{MEMO_HEADER}], [상품명], [관리번호]
                    FROM return_info
                    WHERE id IN ({marks}) AND {LIVE_SQL}""",
                ids,
            ).fetchall()
            if len(found) != len(ids):
                con.rollback()
                raise HTTPException(status_code=404, detail="선택한 반품정보 중 없는 행이 있습니다.")
            if memo:
                con.execute(
                    f"UPDATE return_info SET [불량]=?, [{MEMO_HEADER}]=? WHERE id IN ({marks}) AND {LIVE_SQL}",
                    [defect, memo, *ids],
                )
            else:
                con.execute(
                    f"UPDATE return_info SET [불량]=? WHERE id IN ({marks}) AND {LIVE_SQL}",
                    [defect, *ids],
                )
            by_id = {int(row[0]): row for row in found}
            for row_id in ids:
                current = by_id[row_id]
                changes = []
                if _value_changed("불량", current[1], defect):
                    changes.append({"field": "불량", "before": current[1], "after": defect})
                if memo is not None and _value_changed(MEMO_HEADER, current[2], memo):
                    changes.append({"field": MEMO_HEADER, "before": current[2], "after": memo})
                if not changes:
                    continue
                target = {"상품명": current[3], "관리번호": current[4]}
                _write_log(
                    con,
                    row_id=row_id,
                    action="update",
                    actor=actor,
                    summary=_action_summary("수정", target),
                    changes=changes,
                )
            con.commit()
        except HTTPException:
            raise
        except Exception:
            con.rollback()
            raise
    result = {"updated": len(ids), "불량": defect}
    if memo:
        result[MEMO_HEADER] = memo
    return result


@router.patch("/{row_id}")
async def update_return_info(row_id: int, request: Request, payload: dict = Body(...)):
    """한 행에서 바뀐 항목만 저장하고 누가 무엇을 바꿨는지 남긴다."""
    actor = _session_actor(request.query_params.get("token") or "")
    values = _normalize_patch(payload)
    ensure_tables()
    with get_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            current = _load_row(con, row_id)
            if not current or str(current.get("deleted_at") or "").strip():
                con.rollback()
                raise HTTPException(status_code=404, detail="반품정보를 찾을 수 없습니다.")
            changes = []
            for name, after in values.items():
                if _value_changed(name, current.get(name), after):
                    changes.append({"field": name, "before": _json_ready(current.get(name)), "after": _json_ready(after)})
            if not changes:
                con.rollback()
                return {"id": row_id, "changed": False, "row": _public_row(current)}
            merged = {name: current.get(name) for name in RETURN_HEADERS}
            merged.update({name: values[name] for name in values if name in RETURN_HEADERS})
            if _same_return_row(con, merged, exclude_id=row_id):
                con.rollback()
                raise HTTPException(status_code=409, detail="같은 내용의 반품정보가 이미 있습니다.")
            assignments = ", ".join(f"[{name}]=?" for name in values)
            con.execute(
                f"UPDATE return_info SET {assignments} WHERE id=? AND {LIVE_SQL}",
                [*values.values(), row_id],
            )
            updated = _load_row(con, row_id)
            _write_log(
                con,
                row_id=row_id,
                action="update",
                actor=actor,
                summary=_action_summary("수정", updated or current),
                changes=changes,
            )
            con.commit()
        except HTTPException:
            raise
        except Exception:
            con.rollback()
            raise
    return {"id": row_id, "changed": True, "row": _public_row(updated or current)}


@router.delete("/{row_id}")
async def delete_return_info(row_id: int, request: Request):
    """목록에서 한 행을 감추고, 로그에 원문을 남겨 되돌릴 수 있게 한다."""
    actor = _session_actor(request.query_params.get("token") or "")
    ensure_tables()
    with get_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            current = _load_row(con, row_id)
            if not current or str(current.get("deleted_at") or "").strip():
                con.rollback()
                raise HTTPException(status_code=404, detail="반품정보를 찾을 수 없습니다.")
            stamp = now_str()
            con.execute(
                f"UPDATE return_info SET deleted_at=?, deleted_by=? WHERE id=? AND {LIVE_SQL}",
                (stamp, actor[1], row_id),
            )
            _write_log(
                con,
                row_id=row_id,
                action="delete",
                actor=actor,
                summary=_action_summary("삭제", current),
                snapshot=_snapshot(current),
            )
            con.commit()
        except HTTPException:
            raise
        except Exception:
            con.rollback()
            raise
    return {"id": row_id, "deleted": True}


def _log_filters(query) -> tuple[str, list]:
    clauses = ["1=1"]
    params: list = []
    action = (query.get("action") or "").strip()
    if action:
        if action not in LOG_ACTIONS:
            raise HTTPException(status_code=400, detail="작업 종류가 올바르지 않습니다.")
        clauses.append("action = ?")
        params.append(action)
    actor = (query.get("actor") or "").strip()
    if len(actor) > 50:
        raise HTTPException(status_code=400, detail="작업자 검색은 50자까지입니다.")
    if actor:
        clauses.append("COALESCE(actor_name, '') LIKE ? ESCAPE '\\'")
        params.append(_like(actor))
    keyword = (query.get("q") or "").strip()
    if len(keyword) > 100:
        raise HTTPException(status_code=400, detail="검색어는 100자까지입니다.")
    if keyword:
        needle = _like(keyword)
        clauses.append("(COALESCE(summary, '') LIKE ? ESCAPE '\\' OR COALESCE(changes_json, '') LIKE ? ESCAPE '\\' OR COALESCE(actor_name, '') LIKE ? ESCAPE '\\')")
        params.extend((needle, needle, needle))
    start = (query.get("date_from") or "").strip()
    end = (query.get("date_to") or "").strip()
    if start:
        clauses.append("substr(created_at, 1, 10) >= ?")
        params.append(start)
    if end:
        clauses.append("substr(created_at, 1, 10) <= ?")
        params.append(end)
    return "WHERE " + " AND ".join(clauses), params


def _log_entry(record, can_restore: bool) -> dict:
    changes = []
    if record[6]:
        try:
            parsed = json.loads(record[6])
            if isinstance(parsed, list):
                changes = parsed
        except json.JSONDecodeError:
            changes = []
    return {
        "id": int(record[0]),
        "return_info_id": int(record[1]) if record[1] is not None else None,
        "action": record[2],
        "action_label": ACTION_LABELS.get(record[2], record[2]),
        "actor_name": record[3] or "",
        "summary": record[4] or "",
        "changes": changes,
        "created_at": record[5],
        "can_restore": can_restore,
    }


@router.get("/logs")
async def list_return_info_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """반품정보 추가, 수정, 삭제, 복구를 작업자별로 보여 준다."""
    _session_actor(request.query_params.get("token") or "")
    ensure_tables()
    where, params = _log_filters(request.query_params)
    offset = (page - 1) * page_size
    with get_connection() as con:
        total = con.execute(
            f"SELECT COUNT(*) FROM return_info_log {where}", params
        ).fetchone()[0]
        counts = {
            action: con.execute(
                f"SELECT COUNT(*) FROM return_info_log {where} AND action = ?",
                [*params, action],
            ).fetchone()[0]
            for action in LOG_ACTIONS
        }
        fetched = con.execute(
            f"""SELECT id, return_info_id, action, actor_name, summary, created_at, changes_json, restored_at
                FROM return_info_log {where}
                ORDER BY id DESC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    rows = [
        _log_entry(record, can_restore=record[2] == "delete" and not str(record[7] or "").strip())
        for record in fetched
    ]
    return {
        "rows": rows,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "summary": {action: int(counts[action]) for action in LOG_ACTIONS},
    }


def _restore_values(snapshot: dict, present: set[str]) -> dict:
    values = {}
    for name in present:
        if name in HIDDEN_COLUMNS or name == "id":
            continue
        if name in snapshot:
            values[name] = snapshot.get(name)
    return values


@router.post("/logs/{log_id}/restore")
async def restore_return_info(log_id: int, request: Request):
    """삭제 로그의 원문으로 그 행을 목록에 다시 넣는다."""
    actor = _session_actor(request.query_params.get("token") or "")
    ensure_tables()
    with get_connection() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            log = con.execute(
                """SELECT id, return_info_id, action, snapshot_json, restored_at
                   FROM return_info_log WHERE id = ?""",
                (log_id,),
            ).fetchone()
            if not log or log[2] != "delete" or not log[3]:
                con.rollback()
                raise HTTPException(status_code=404, detail="되돌릴 삭제 기록을 찾을 수 없습니다.")
            if str(log[4] or "").strip():
                con.rollback()
                raise HTTPException(status_code=409, detail="이미 되돌린 삭제입니다.")
            try:
                snapshot = json.loads(log[3])
            except json.JSONDecodeError:
                snapshot = None
            if not isinstance(snapshot, dict):
                con.rollback()
                raise HTTPException(status_code=404, detail="되돌릴 삭제 기록을 찾을 수 없습니다.")
            row_id = int(log[1]) if log[1] is not None else None
            business = {name: snapshot.get(name) for name in RETURN_HEADERS}
            if _same_return_row(con, business, exclude_id=row_id):
                con.rollback()
                raise HTTPException(status_code=409, detail="같은 내용의 반품정보가 이미 있습니다.")
            present = {row[1] for row in con.execute("PRAGMA table_info(return_info)")}
            values = _restore_values(snapshot, present)
            current = _load_row(con, row_id) if row_id else None
            if current and not str(current.get("deleted_at") or "").strip():
                con.rollback()
                raise HTTPException(status_code=409, detail="이미 목록에 있는 반품정보입니다.")
            if current:
                assignments = ", ".join(f"[{name}]=?" for name in values)
                con.execute(
                    f"UPDATE return_info SET {assignments}, deleted_at=NULL, deleted_by=NULL WHERE id=?",
                    [*values.values(), row_id],
                )
            else:
                names = list(values)
                if row_id and "id" in present:
                    names = ["id", *names]
                    stored_values = [row_id, *values.values()]
                else:
                    stored_values = list(values.values())
                col_sql = ", ".join(f"[{name}]" for name in names)
                marks = ", ".join("?" for _name in names)
                cursor = con.execute(
                    f"INSERT INTO return_info ({col_sql}) VALUES ({marks})",
                    stored_values,
                )
                row_id = int(cursor.lastrowid)
            restored = _load_row(con, row_id)
            con.execute(
                "UPDATE return_info_log SET restored_at=? WHERE id=?",
                (now_str(), log_id),
            )
            _write_log(
                con,
                row_id=row_id,
                action="restore",
                actor=actor,
                summary=_action_summary("복구", restored or snapshot),
                snapshot=_snapshot(restored) if restored else snapshot,
                restored_log_id=log_id,
            )
            con.commit()
        except HTTPException:
            raise
        except Exception:
            con.rollback()
            raise
    return {"id": log_id, "return_info_id": row_id, "restored": True}


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
        "수정사항메모": 28,
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
