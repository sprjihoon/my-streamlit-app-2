"""일지 직전 기록 포인터와 소유권 검증. 저장 본체는 호출만 한다."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from backend.app.services.bot_intent import JOURNAL_ALLOWED_FIELDS, journal_fields_only
from backend.app.services.journal_adapter import (
    SAFE_ERROR,
    parse_iso_date,
    resolve_vendor,
    sanitize_user_error,
)
from logic.db import get_connection

logger = logging.getLogger(__name__)
SEOUL = ZoneInfo("Asia/Seoul")

_FIELD_COL = {
    "vendor": "업체명",
    "work_type": "분류",
    "unit_price": "단가",
    "qty": "수량",
    "date": "날짜",
    "remark": "비고1",
}
_COL_LABEL = {
    "업체명": "업체",
    "분류": "작업",
    "단가": "단가",
    "수량": "수량",
    "날짜": "날짜",
    "비고1": "비고",
    "합계": "합계",
}


def _room(user_id: str, channel_id: Optional[str]) -> Tuple[str, str]:
    uid = (user_id or "").strip()
    cid = (channel_id or "").strip() or uid
    return uid, cid


def ensure_last_saved_table() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS journal_last_saved_v2 (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                work_log_id INTEGER NOT NULL,
                updated_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
            """
        )
        con.commit()


def remember_last_saved(user_id: str, channel_id: Optional[str], work_log_id: int) -> None:
    ensure_last_saved_table()
    uid, cid = _room(user_id, channel_id)
    with get_connection() as con:
        con.execute(
            """
            INSERT INTO journal_last_saved_v2 (user_id, channel_id, work_log_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, channel_id) DO UPDATE SET
                work_log_id = excluded.work_log_id,
                updated_at = excluded.updated_at
            """,
            (uid, cid, int(work_log_id), datetime.now(SEOUL).isoformat()),
        )
        con.commit()


def get_last_saved_id(user_id: str, channel_id: Optional[str]) -> Optional[int]:
    ensure_last_saved_table()
    uid, cid = _room(user_id, channel_id)
    with get_connection() as con:
        row = con.execute(
            """
            SELECT work_log_id FROM journal_last_saved_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()
    return int(row[0]) if row else None


def fetch_owned_work_log(user_id: str, record_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as con:
        row = con.execute(
            """
            SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, works_user_id
            FROM work_log
            WHERE id = ? AND works_user_id = ?
            """,
            (int(record_id), (user_id or "").strip()),
        ).fetchone()
    if not row:
        return None
    keys = ("id", "날짜", "업체명", "분류", "단가", "수량", "합계", "비고1", "works_user_id")
    return dict(zip(keys, row))


def list_owned_candidates(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 비고1
            FROM work_log
            WHERE works_user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            ((user_id or "").strip(), max(2, min(int(limit), 5))),
        ).fetchall()
    out = []
    for row in rows:
        out.append({
            "id": row[0],
            "날짜": row[1],
            "업체명": row[2],
            "분류": row[3],
            "단가": row[4],
            "수량": row[5],
            "합계": row[6],
            "비고1": row[7],
        })
    return out


def row_to_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "vendor": row.get("업체명"),
        "work_type": row.get("분류"),
        "unit_price": row.get("단가"),
        "qty": row.get("수량"),
        "date": row.get("날짜"),
        "remark": row.get("비고1") or "",
        "total": row.get("합계"),
        "id": row.get("id"),
    }


def preview_line(fields: Dict[str, Any]) -> str:
    vendor = fields.get("vendor") or ""
    work = fields.get("work_type") or ""
    qty = fields.get("qty") or 1
    price = fields.get("unit_price") or 0
    date = fields.get("date") or ""
    remark = fields.get("remark") or ""
    total = fields.get("total")
    if total in (None, ""):
        try:
            total = int(price) * int(qty)
        except (TypeError, ValueError):
            total = 0
    bits = [f"{date} {vendor} {work} {int(qty)}건 {int(price):,}원 (합계 {int(total):,}원)".strip()]
    if remark:
        bits.append(f"비고 {remark}")
    return " ".join(bits)


def merge_record_fields(before: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    after = dict(before)
    for key in JOURNAL_ALLOWED_FIELDS:
        if key in ("total_amount", "amount_type"):
            continue
        if key in patch and patch[key] not in (None, ""):
            after[key] = patch[key]
    try:
        after["total"] = int(after.get("unit_price") or 0) * int(after.get("qty") or 1)
    except (TypeError, ValueError):
        after["total"] = after.get("total")
    return after


def _is_journal_mode(user_id: str, channel_id: Optional[str]) -> bool:
    from backend.app.services.bot_mode import MODE_JOURNAL, get_mode

    return get_mode(user_id, channel_id) == MODE_JOURNAL


def validate_update_fields(fields: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    patch = journal_fields_only(fields)
    if "unit_price" in patch:
        try:
            price = int(patch["unit_price"])
        except (TypeError, ValueError):
            return None, "단가는 0보다 큰 숫자여야 해요."
        if price <= 0:
            return None, "단가는 0보다 커야 해요."
        patch["unit_price"] = price
    if "qty" in patch:
        try:
            qty = int(patch["qty"])
        except (TypeError, ValueError):
            return None, "수량은 0보다 큰 숫자여야 해요."
        if qty <= 0:
            return None, "수량은 0보다 커야 해요."
        patch["qty"] = qty
    if patch.get("date"):
        parsed = parse_iso_date(patch["date"])
        if not parsed:
            return None, "날짜는 실제 있는 YYYY-MM-DD 형식으로 알려주세요."
        patch["date"] = parsed
    if patch.get("vendor"):
        resolved, similar = resolve_vendor(str(patch["vendor"]))
        if not resolved:
            hint = f" 비슷한 업체: {', '.join(similar)}" if similar else ""
            return None, f"'{patch['vendor']}'은(는) 등록되지 않은 업체입니다.{hint}"
        patch["vendor"] = resolved
    return patch, None


def apply_owned_work_log_fields(
    user_id: str,
    channel_id: Optional[str],
    record_id: int,
    fields: Dict[str, Any],
    user_name: Optional[str],
) -> Dict[str, Any]:
    if not _is_journal_mode(user_id, channel_id):
        return {"success": False, "error": "mode_not_journal"}
    pointer = get_last_saved_id(user_id, channel_id)
    from backend.app.services.bot_target import listed_record_ids

    listed = listed_record_ids(user_id, channel_id, "journal")
    if not (
        (pointer is not None and int(pointer) == int(record_id))
        or int(record_id) in listed
    ):
        return {"success": False, "error": "pointer_mismatch"}
    owned = fetch_owned_work_log(user_id, record_id)
    if owned is None:
        return {"success": False, "error": "not_owned"}
    patch, err = validate_update_fields(fields)
    if err:
        return {"success": False, "error": err}
    if not patch:
        return {"success": False, "error": "empty_patch"}
    from backend.app.services.bot_tools import _update_work_log

    args: Dict[str, Any] = {"log_id": int(record_id), "append_remark": False}
    if "vendor" in patch:
        args["new_vendor"] = patch["vendor"]
    if "work_type" in patch:
        args["new_work_type"] = patch["work_type"]
    if "unit_price" in patch:
        args["new_unit_price"] = patch["unit_price"]
    if "qty" in patch:
        args["new_qty"] = patch["qty"]
    if "remark" in patch:
        args["new_remark"] = patch["remark"]
    try:
        result = _update_work_log(args, user_id, user_name)
    except Exception:
        logger.exception("journal_update_failed")
        return {"success": False, "error": SAFE_ERROR}
    if result.get("success") and result.get("log_id"):
        try:
            remember_last_saved(user_id, channel_id, int(result["log_id"]))
        except Exception:
            logger.exception("journal_last_saved_pointer_failed")
    if not result.get("success"):
        result["error"] = sanitize_user_error(result.get("error"))
    return result


def delete_owned_work_log(
    user_id: str,
    channel_id: Optional[str],
    record_id: int,
    user_name: Optional[str],
) -> Dict[str, Any]:
    if not _is_journal_mode(user_id, channel_id):
        return {"success": False, "error": "mode_not_journal"}
    pointer = get_last_saved_id(user_id, channel_id)
    if pointer is None or int(pointer) != int(record_id):
        return {"success": False, "error": "pointer_mismatch"}
    owned = fetch_owned_work_log(user_id, record_id)
    if owned is None:
        return {"success": False, "error": "not_owned"}
    from backend.app.services.bot_tools import _delete_work_log

    try:
        result = _delete_work_log({"log_id": int(record_id)}, user_id, user_name)
    except Exception:
        logger.exception("journal_delete_failed")
        return {"success": False, "error": SAFE_ERROR}
    if not result.get("success"):
        result["error"] = sanitize_user_error(result.get("error"))
    return result


def add_owned_memo(
    user_id: str,
    record_id: int,
    memo: str,
    user_name: Optional[str],
) -> Dict[str, Any]:
    owned = fetch_owned_work_log(user_id, record_id)
    if owned is None:
        return {"success": False, "error": "not_owned"}
    from backend.app.services.bot_tools import _add_memo

    try:
        result = _add_memo({"log_id": int(record_id), "memo": memo}, user_id, user_name)
    except Exception:
        logger.exception("journal_memo_failed")
        return {"success": False, "error": SAFE_ERROR}
    if not result.get("success"):
        result["error"] = sanitize_user_error(result.get("error"))
    return result
