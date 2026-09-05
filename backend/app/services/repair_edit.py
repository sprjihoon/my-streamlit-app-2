"""수선 직전 기록 수정 adapter. insert/사진 판독 본체는 호출하지 않는다."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services.bot_intent import (
    ACTION_CANCEL,
    ACTION_CONFIRM,
    ACTION_PROVIDE_FIELD,
    ACTION_UPDATE,
    TARGET_LAST_SAVED,
    BotIntent,
    allowed_fields_only,
    draft_fields_only,
    parse_bot_intent,
    rejected_draft_field_names,
    rejected_field_names,
)
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection

ENTRY_UPDATE = "repair_update"
ENTRY_DRAFT = "repair"
ASK_FIELDS = "어떤 내용을 수정할까요?"
NO_RECORD = "직전 저장 기록을 찾을 수 없습니다."
ALREADY = "이미 수정했어요. 같은 확인으로는 다시 저장하지 않아요."
CANCELLED = "🚫 직전 수선일지 수정을 취소했어요."
MODE_BLOCKED = "수선모드에서만 직전 저장 내용을 수정할 수 있어요."
DRAFT_BLOCKED = (
    "현재 작성 중인 수선이 있습니다. "
    "먼저 현재 수선을 저장하거나 취소한 뒤 직전 저장 내용을 수정해주세요."
)
FIELD_BLOCKED = "허용되지 않은 수정 항목이 있어 반영하지 않았어요."

_FIELD_COL = {
    "unit_price": "비용",
    "qty": "수량",
    "defect": "불량명",
    "work_type": "작업",
    "remark": "비고",
    "vendor": "업체명",
    "product": "제품명",
}
_COL_LABEL = {
    "비용": "금액",
    "수량": "건수",
    "불량명": "불량",
    "작업": "작업",
    "비고": "비고",
    "업체명": "업체",
    "제품명": "제품",
}


def _room(user_id: str, channel_id: Optional[str]) -> Tuple[str, str]:
    uid = (user_id or "").strip()
    cid = (channel_id or "").strip() or uid
    return uid, cid


def ensure_last_saved_table() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS repair_last_saved_v2 (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                repair_record_id INTEGER NOT NULL,
                saved_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
            """
        )
        con.commit()


def remember_last_saved(user_id: str, channel_id: Optional[str], repair_record_id: int) -> None:
    ensure_last_saved_table()
    uid, cid = _room(user_id, channel_id)
    with get_connection() as con:
        con.execute(
            """
            INSERT INTO repair_last_saved_v2 (user_id, channel_id, repair_record_id, saved_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, channel_id) DO UPDATE SET
                repair_record_id = excluded.repair_record_id,
                saved_at = excluded.saved_at
            """,
            (uid, cid, int(repair_record_id), datetime.now().isoformat()),
        )
        con.commit()


def get_last_saved_id(user_id: str, channel_id: Optional[str]) -> Optional[int]:
    ensure_last_saved_table()
    uid, cid = _room(user_id, channel_id)
    with get_connection() as con:
        row = con.execute(
            """
            SELECT repair_record_id FROM repair_last_saved_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()
    return int(row[0]) if row else None


def fetch_owned_repair(user_id: str, channel_id: Optional[str], record_id: int) -> Optional[Dict[str, Any]]:
    """포인터와 id가 일치하는 이 방 기록만 반환. 다른 방·사용자 기록은 보지 않는다."""
    from backend.app.api.repair_log import ensure_repair_tables

    ensure_repair_tables()
    ensure_last_saved_table()
    uid, cid = _room(user_id, channel_id)
    with get_connection() as con:
        pointer = con.execute(
            """
            SELECT repair_record_id FROM repair_last_saved_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()
        if not pointer or int(pointer[0]) != int(record_id):
            return None
        row = con.execute(
            """
            SELECT id, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고
            FROM repair_work_log WHERE id = ?
            """,
            (int(record_id),),
        ).fetchone()
    if not row:
        return None
    keys = ("id", "업체명", "제품명", "옵션", "바코드", "불량명", "작업", "수량", "비용", "비고")
    return dict(zip(keys, row))


def _is_repair_mode(user_id: str, channel_id: Optional[str]) -> bool:
    from backend.app.services.bot_mode import MODE_REPAIR, get_mode

    return get_mode(user_id, channel_id) == MODE_REPAIR


def _get_repair_draft(user_id: str, channel_id: Optional[str]) -> Dict[str, Any]:
    state = get_conversation_manager().get_state(user_id, channel_id)
    if not state or state.get("expired"):
        return {}
    data = state.get("pending_data") or {}
    if data.get("entry_type") != ENTRY_DRAFT:
        return {}
    return data


def apply_owned_repair_fields(
    user_id: str,
    channel_id: Optional[str],
    record_id: int,
    fields: Dict[str, Any],
    editor: Optional[str],
) -> Dict[str, Any]:
    if not _is_repair_mode(user_id, channel_id):
        return {"success": False, "error": "mode_not_repair"}
    if rejected_field_names(fields):
        return {"success": False, "error": "field_not_allowed"}
    owned = fetch_owned_repair(user_id, channel_id, record_id)
    if not owned:
        return {"success": False, "error": "owned_record_missing"}
    safe_fields = allowed_fields_only(fields)
    updates: List[str] = []
    params: List[Any] = []
    for key, col in _FIELD_COL.items():
        if key not in safe_fields:
            continue
        updates.append(f"{col} = ?")
        params.append(safe_fields[key])
    if not updates:
        return {"success": False, "error": "no_fields"}
    updates.append("수정자 = ?")
    params.append(editor or "bot")
    updates.append("수정시간 = ?")
    params.append(datetime.now().isoformat())
    uid, cid = _room(user_id, channel_id)
    params.extend([int(record_id), uid, cid])
    with get_connection() as con:
        cur = con.execute(
            f"""
            UPDATE repair_work_log SET {", ".join(updates)}
            WHERE id = ?
              AND id = (
                  SELECT repair_record_id FROM repair_last_saved_v2
                  WHERE user_id = ? AND channel_id = ?
              )
            """,
            params,
        )
        con.commit()
        if cur.rowcount != 1:
            return {"success": False, "error": "update_rejected"}
    return {"success": True, "id": int(record_id)}


def _row_to_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "unit_price": row.get("비용"),
        "qty": row.get("수량"),
        "defect": row.get("불량명"),
        "work_type": row.get("작업"),
        "remark": row.get("비고"),
        "vendor": row.get("업체명"),
        "product": row.get("제품명"),
    }


def _preview_line(fields: Dict[str, Any]) -> str:
    vendor = fields.get("vendor") or "?"
    product = fields.get("product") or "?"
    defect = fields.get("defect") or "-"
    work = fields.get("work_type") or "-"
    qty = fields.get("qty") if fields.get("qty") is not None else "?"
    price = fields.get("unit_price")
    price_txt = f"{int(price):,}원" if price is not None else "-"
    return f"{vendor} / {product} / {defect} / {work} / {qty}건 / {price_txt}"


def _merge_fields(before: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(before)
    for key in _FIELD_COL:
        if key in patch and patch[key] not in (None, ""):
            out[key] = patch[key]
    return out


def _get_update_pending(user_id: str, channel_id: Optional[str]) -> Dict[str, Any]:
    state = get_conversation_manager().get_state(user_id, channel_id)
    if not state:
        return {}
    data = state.get("pending_data") or {}
    if data.get("entry_type") != ENTRY_UPDATE:
        return {}
    return data


def _set_update_pending(
    user_id: str,
    channel_id: str,
    data: Dict[str, Any],
    missing: List[str],
    question: str,
) -> None:
    data = {**data, "entry_type": ENTRY_UPDATE, "action": ACTION_UPDATE, "target": TARGET_LAST_SAVED}
    get_conversation_manager().set_state(
        user_id=user_id,
        channel_id=channel_id or "",
        pending_data=data,
        missing=missing,
        last_question=question,
    )


def _clear_update_pending(user_id: str, channel_id: Optional[str]) -> None:
    get_conversation_manager().clear_state(user_id, channel_id)


def _confirm_message(record_id: int, before: Dict[str, Any], after: Dict[str, Any]) -> str:
    changed = [label for key, label in (
        ("unit_price", "금액"),
        ("qty", "건수"),
        ("defect", "불량"),
        ("work_type", "작업"),
    ) if before.get(key) != after.get(key)]
    focus = ", ".join(changed) if changed else "내용"
    return (
        f"직전 수선일지 #{record_id}를 이렇게 수정할까요?\n"
        f"변경 전: {_preview_line(before)}\n"
        f"변경 후: {_preview_line(after)}\n"
        f"바뀌는 항목: {focus}\n"
        f"맞으면 '네', 아니면 '취소'"
    )


def _draft_change_summary(patch: Dict[str, Any]) -> str:
    bits: List[str] = []
    if "unit_price" in patch:
        bits.append(f"금액을 {int(patch['unit_price']):,}원으로 바꿨어요.")
    if "qty" in patch:
        bits.append(f"건수를 {int(patch['qty'])}건으로 바꿨어요.")
    if "defect" in patch:
        bits.append(f"불량을 {patch['defect']}(으)로 바꿨어요.")
    if "work_type" in patch:
        bits.append(f"작업을 {patch['work_type']}(으)로 바꿨어요.")
    if "vendor" in patch:
        bits.append(f"업체를 {patch['vendor']}(으)로 바꿨어요.")
    if "product" in patch:
        bits.append(f"제품을 {patch['product']}(으)로 바꿨어요.")
    if "option" in patch:
        bits.append(f"옵션을 {patch['option']}(으)로 바꿨어요.")
    return " ".join(bits) or "작성 중인 내용을 바꿨어요."


_HOLD_DRAFT_STEPS = frozenset(("photos", "barcode"))


def _apply_fields_to_draft(
    user_id: str,
    channel_id: str,
    draft: Dict[str, Any],
    fields: Dict[str, Any],
) -> Optional[str]:
    """작성 중 draft에만 필드 정정을 넣고, 사진·바코드 대기는 유지한다."""
    if rejected_draft_field_names(fields):
        return FIELD_BLOCKED
    patch = draft_fields_only(fields)
    if not patch:
        return None
    if "vendor" in patch:
        from backend.app.api.repair_log import _resolve_vendor
        from logic.db import get_connection

        with get_connection() as con:
            patch["vendor"] = _resolve_vendor(con, patch["vendor"])
    state = get_conversation_manager().get_state(user_id, channel_id) or {}
    if state.get("expired"):
        return None
    missing = list(state.get("missing") or [])
    last_q = state.get("last_question") or ""
    updated = {**draft, **patch, "entry_type": ENTRY_DRAFT}
    if "unit_price" in patch:
        updated["price_stated"] = True
    for key in list(missing):
        if key in patch and updated.get(key) not in (None, ""):
            missing.remove(key)
    hold_wait = any(step in missing for step in _HOLD_DRAFT_STEPS)
    filled_current = any(key in patch for key in _HOLD_DRAFT_STEPS)
    if hold_wait and not filled_current:
        get_conversation_manager().set_state(
            user_id=user_id,
            channel_id=channel_id or "",
            pending_data=updated,
            missing=missing,
            last_question=last_q,
        )
        summary = _draft_change_summary(patch)
        if last_q and last_q not in summary:
            return f"{summary}\n{last_q}"
        return summary
    from backend.app.services.repair_bot import continue_after_photos_or_text

    return continue_after_photos_or_text(updated, user_id, channel_id)


def _start_or_ask(user_id: str, channel_id: str, user_name: Optional[str], fields: Dict[str, Any]) -> str:
    if not _is_repair_mode(user_id, channel_id):
        return MODE_BLOCKED
    if rejected_field_names(fields):
        return FIELD_BLOCKED
    fields = allowed_fields_only(fields)
    record_id = get_last_saved_id(user_id, channel_id)
    if record_id is None:
        return NO_RECORD
    row = fetch_owned_repair(user_id, channel_id, record_id)
    if row is None:
        return NO_RECORD
    before = _row_to_fields(row)
    data = {
        "repair_record_id": record_id,
        "before": before,
        "after": before,
        "fields": {},
        "applied": False,
        "user_name": user_name,
    }
    if not fields:
        q = f"직전 수선일지 #{record_id}예요. {ASK_FIELDS}"
        _set_update_pending(user_id, channel_id, data, ["fields"], q)
        return q
    after = _merge_fields(before, fields)
    if after == before:
        q = f"직전 수선일지 #{record_id}예요. 바뀐 값이 없어요. {ASK_FIELDS}"
        _set_update_pending(user_id, channel_id, data, ["fields"], q)
        return q
    data["after"] = after
    data["fields"] = fields
    q = _confirm_message(record_id, before, after)
    _set_update_pending(user_id, channel_id, data, ["confirm"], q)
    return q


def handle_repair_edit(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str] = None,
    intent: Optional[BotIntent] = None,
) -> Optional[str]:
    """수정 흐름이면 응답 문자열, 아니면 None (기존 수선 저장 경로로)."""
    pending = _get_update_pending(user_id, channel_id)
    intent = intent or parse_bot_intent(text)
    draft = _get_repair_draft(user_id, channel_id)
    field_patch = intent.action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD) and bool(intent.fields)

    if draft and not pending:
        if intent.action == ACTION_UPDATE and intent.target == TARGET_LAST_SAVED and intent.explicit_last_saved:
            return DRAFT_BLOCKED
        if field_patch:
            qty_only = set(intent.fields) <= {"qty"}
            if draft.get("awaiting_price_confirm") and qty_only and intent.action == ACTION_PROVIDE_FIELD:
                return None
            return _apply_fields_to_draft(user_id, channel_id, draft, intent.fields)
        return None

    if pending:
        if not _is_repair_mode(user_id, channel_id):
            _clear_update_pending(user_id, channel_id)
            return MODE_BLOCKED
        if intent.action == ACTION_CANCEL:
            _clear_update_pending(user_id, channel_id)
            return CANCELLED
        if pending.get("applied"):
            if intent.action == ACTION_CONFIRM:
                return ALREADY
            if intent.action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD):
                return _start_or_ask(user_id, channel_id, user_name, intent.fields)
            _clear_update_pending(user_id, channel_id)
            return None
        if intent.action == ACTION_CONFIRM:
            if pending.get("applied"):
                return ALREADY
            record_id = pending.get("repair_record_id")
            fields = pending.get("fields") or {}
            if rejected_field_names(fields):
                _clear_update_pending(user_id, channel_id)
                return FIELD_BLOCKED
            if not record_id or not fields:
                q = ASK_FIELDS
                _set_update_pending(user_id, channel_id, pending, ["fields"], q)
                return q
            result = apply_owned_repair_fields(
                user_id, channel_id, int(record_id), fields, user_name or pending.get("user_name"),
            )
            if not result.get("success"):
                err = result.get("error")
                _clear_update_pending(user_id, channel_id)
                if err == "mode_not_repair":
                    return MODE_BLOCKED
                if err == "field_not_allowed":
                    return FIELD_BLOCKED
                return NO_RECORD
            pending["applied"] = True
            q = (
                f"✅ 수선일지 #{record_id}를 수정했어요.\n"
                f"{_preview_line(pending.get('after') or {})}"
            )
            _set_update_pending(user_id, channel_id, pending, [], q)
            return q
        if intent.fields or intent.action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD):
            if rejected_field_names(intent.fields) or rejected_field_names(pending.get("fields") or {}):
                _clear_update_pending(user_id, channel_id)
                return FIELD_BLOCKED
            before = pending.get("before") or {}
            merged_patch = allowed_fields_only({**(pending.get("fields") or {}), **intent.fields})
            after = _merge_fields(before, merged_patch)
            pending["fields"] = merged_patch
            pending["after"] = after
            pending["applied"] = False
            record_id = pending.get("repair_record_id")
            if not record_id:
                return NO_RECORD
            if after == before:
                q = f"직전 수선일지 #{record_id}예요. 바뀐 값이 없어요. {ASK_FIELDS}"
                _set_update_pending(user_id, channel_id, pending, ["fields"], q)
                return q
            q = _confirm_message(int(record_id), before, after)
            _set_update_pending(user_id, channel_id, pending, ["confirm"], q)
            return q
        q = pending.get("last_prompt") or ASK_FIELDS
        if not pending.get("fields"):
            return f"직전 수선일지 #{pending.get('repair_record_id')}예요. {ASK_FIELDS}"
        return _confirm_message(
            int(pending["repair_record_id"]),
            pending.get("before") or {},
            pending.get("after") or {},
        )

    if intent.target == TARGET_LAST_SAVED and intent.action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD):
        return _start_or_ask(user_id, channel_id, user_name, intent.fields)
    return None
