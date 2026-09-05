"""일지모드 상태 머신. GPT는 의미만 구조화하고, 검증·저장은 여기서 한다."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.bot_intent import (
    ACTION_CANCEL,
    ACTION_CONFIRM,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_PROVIDE_FIELD,
    ACTION_UNKNOWN,
    ACTION_UPDATE,
    TARGET_DRAFT,
    TARGET_LAST_SAVED,
    TARGET_SELECTED_RECORD,
    journal_fields_only,
)
from backend.app.services.bot_mode import MODE_JOURNAL, get_mode
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.journal_adapter import (
    SAFE_ERROR,
    extract_journal_fields_local,
    get_processed_event,
    lookup_price_history,
    missing_required,
    remember_processed_event,
    sanitize_user_error,
    save_journal_entries,
    seoul_today,
    validate_journal_entry,
)
from backend.app.services.journal_edit import (
    apply_owned_work_log_fields,
    delete_owned_work_log,
    fetch_owned_work_log,
    get_last_saved_id,
    list_owned_candidates,
    merge_record_fields,
    preview_line,
    row_to_fields,
    validate_update_fields,
)

logger = logging.getLogger(__name__)

ENTRY_JOURNAL = "journal"
MODE_BLOCKED = "일지모드에서만 작업일지를 저장·수정·삭제할 수 있어요."
CANCELLED = "🚫 일지 입력을 취소했어요."
NO_POINTER = "이 방에서 직전에 저장한 작업일지가 없어요. 고칠 기록을 골라주세요."
ALREADY = "이미 반영했어요. 같은 확인으로는 다시 실행하지 않아요."
ASK_ONCE = "업체, 작업, 단가를 다시 알려주세요."
FIELD_LABELS = {
    "vendor": "업체",
    "work_type": "작업",
    "unit_price": "단가",
}


def _mgr():
    return get_conversation_manager()


def _get_pending(user_id: str, channel_id: Optional[str]) -> Dict[str, Any]:
    state = _mgr().get_state(user_id, channel_id) or {}
    data = dict(state.get("pending_data") or {})
    if data.get("entry_type") != ENTRY_JOURNAL:
        return {}
    return data


def _set_pending(
    user_id: str,
    channel_id: Optional[str],
    data: Dict[str, Any],
    missing: List[str],
    question: str,
) -> None:
    payload = {**data, "entry_type": ENTRY_JOURNAL, "last_prompt": question}
    _mgr().set_state(
        user_id=user_id,
        channel_id=channel_id or "",
        pending_data=payload,
        missing=missing,
        last_question=question,
    )


def _clear_pending(user_id: str, channel_id: Optional[str]) -> None:
    _mgr().clear_state(user_id, channel_id)


def _is_journal_mode(user_id: str, channel_id: Optional[str]) -> bool:
    return get_mode(user_id, channel_id) == MODE_JOURNAL


def _draft_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    return journal_fields_only({
        k: data.get(k)
        for k in ("vendor", "work_type", "unit_price", "qty", "date", "remark", "total_amount", "amount_type")
    })


def _merge_draft(data: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(data)
    for key, value in journal_fields_only(incoming).items():
        merged[key] = value
    return merged


def _conflicts_with_draft(draft: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    if not draft:
        return False
    old_vendor = draft.get("vendor")
    old_work = draft.get("work_type")
    new_vendor = incoming.get("vendor")
    new_work = incoming.get("work_type")
    if new_vendor and old_vendor and str(new_vendor) != str(old_vendor):
        return bool(old_work or old_vendor)
    if new_work and old_work and str(new_work) != str(old_work) and incoming.get("unit_price"):
        return True
    return False


def _ask_missing(user_id: str, channel_id: Optional[str], data: Dict[str, Any]) -> str:
    missing = missing_required(data)
    labels = [FIELD_LABELS[k] for k in missing if k in FIELD_LABELS]
    if not labels:
        question = "남은 정보를 알려주세요."
    elif len(labels) == 1:
        question = f"{labels[0]}를 알려주세요."
    else:
        question = f"{', '.join(labels)}를 알려주세요."
    _set_pending(user_id, channel_id, {**data, "step": "awaiting_fields"}, missing, question)
    return question


def _format_save_reply(result: Dict[str, Any]) -> str:
    if result.get("success") and not result.get("partial"):
        return f"✅ {result.get('message') or '저장했어요.'}"
    if result.get("partial"):
        return f"⚠️ {result.get('message')}"
    return f"❌ {sanitize_user_error(result.get('message') or result.get('error'))}"


def _try_save(
    user_id: str,
    channel_id: Optional[str],
    entries: List[Dict[str, Any]],
    user_name: Optional[str],
    event_id: Optional[str],
    keep_draft: Optional[Dict[str, Any]] = None,
) -> str:
    if event_id:
        cached = get_processed_event(event_id)
        if cached:
            return cached
    result = save_journal_entries(entries, user_id, user_name, channel_id)
    if result.get("success") and not result.get("partial"):
        _clear_pending(user_id, channel_id)
        reply = _format_save_reply(result)
        remember_processed_event(event_id, user_id, channel_id, reply)
        return reply
    if result.get("partial"):
        _clear_pending(user_id, channel_id)
        return _format_save_reply(result)
    draft = keep_draft if keep_draft is not None else (entries[0] if entries else {})
    first_err = ""
    if result.get("failures"):
        first_err = result["failures"][0].get("error") or ""
    if first_err.startswith("missing:"):
        return _ask_missing(user_id, channel_id, draft)
    if first_err == "ask_unit_from_total":
        q = "총액이 수량으로 나누어떨어지지 않아요. 개당 단가를 알려주세요."
        _set_pending(user_id, channel_id, {**draft, "step": "awaiting_fields"}, ["unit_price"], q)
        return q
    if first_err == "ask_amount_type":
        q = "그 금액이 개당인가요, 총액인가요?"
        _set_pending(
            user_id, channel_id,
            {**draft, "step": "awaiting_amount_type", "amount_type_asked": True},
            ["amount_type"], q,
        )
        return q
    similar = []
    if result.get("failures"):
        similar = result["failures"][0].get("similar_vendors") or []
    q = sanitize_user_error(first_err or result.get("message"))
    if similar and "비슷한 업체" not in q:
        q = f"{q} 비슷한 업체: {', '.join(similar)}"
    missing = missing_required(draft) or (["vendor"] if "업체" in q else [])
    _set_pending(user_id, channel_id, {**draft, "step": "awaiting_fields"}, missing, q)
    return f"❌ {q}"


def _maybe_price_lookup(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if data.get("unit_price"):
        return None
    if data.get("total_amount") and data.get("amount_type") in ("total", "unknown"):
        return None
    if not data.get("work_type"):
        return None
    return lookup_price_history(data.get("vendor") or "", data.get("work_type") or "")


def _continue_create(
    user_id: str,
    channel_id: Optional[str],
    data: Dict[str, Any],
    user_name: Optional[str],
    event_id: Optional[str],
) -> str:
    if data.get("qty") in (None, ""):
        data["qty"] = 1
    if not data.get("date"):
        data["date"] = seoul_today()
    ok, cleaned, err = validate_journal_entry(data, require_complete=False)
    if not ok and err not in (None, "ask_unit_from_total", "ask_amount_type") and not str(err).startswith("missing:"):
        q = sanitize_user_error(err)
        kept = dict(data)
        if "단가" in q:
            kept.pop("unit_price", None)
        if "수량" in q:
            kept.pop("qty", None)
        if "날짜" in q:
            kept.pop("date", None)
        if "업체" in q:
            kept.pop("vendor", None)
        _set_pending(user_id, channel_id, {**kept, "step": "awaiting_fields"}, missing_required(kept), q)
        return f"❌ {q}"
    if cleaned:
        data = {**data, **cleaned}
    if err == "ask_amount_type" and not data.get("amount_type_asked"):
        q = "그 금액이 개당인가요, 총액인가요?"
        _set_pending(
            user_id, channel_id,
            {**data, "step": "awaiting_amount_type", "amount_type_asked": True},
            ["amount_type"], q,
        )
        return q
    if err == "ask_unit_from_total":
        q = "총액이 수량으로 나누어떨어지지 않아요. 개당 단가를 알려주세요."
        _set_pending(user_id, channel_id, {**data, "step": "awaiting_fields"}, ["unit_price"], q)
        return q
    if missing_required(data):
        if not data.get("unit_price") and data.get("vendor") and data.get("work_type"):
            looked = _maybe_price_lookup(data)
            if looked and looked.get("ambiguous"):
                cands = looked.get("work_candidates") or []
                q = "작업명이 여러 개예요. " + ", ".join(cands[:5]) + " 중에서 골라주세요."
                _set_pending(
                    user_id, channel_id,
                    {**data, "step": "awaiting_price_choice", "price_candidates": cands},
                    ["work_type"], q,
                )
                return q
            if looked and looked.get("found") and not looked.get("ambiguous"):
                price = looked.get("most_recent_price")
                if price:
                    data["suggested_price"] = int(price)
                    q = (
                        f"{data.get('vendor') or ''} {data.get('work_type')} 최근 단가가 "
                        f"{int(price):,}원이에요. 이 가격으로 할까요?"
                    )
                    _set_pending(
                        user_id, channel_id,
                        {**data, "step": "awaiting_price", "unit_price": int(price)},
                        [], q,
                    )
                    return q
        return _ask_missing(user_id, channel_id, data)
    return _try_save(user_id, channel_id, [data], user_name, event_id, keep_draft=data)


def _preview_update(record_id: int, before: Dict[str, Any], after: Dict[str, Any]) -> str:
    return (
        f"직전 작업일지 #{record_id}를 이렇게 수정할까요?\n"
        f"변경 전: {preview_line(before)}\n"
        f"변경 후: {preview_line(after)}\n"
        f"맞으면 '네', 아니면 '취소'"
    )


def _preview_delete(record_id: int, before: Dict[str, Any]) -> str:
    return (
        f"직전 작업일지 #{record_id}를 삭제할까요?\n"
        f"대상: {preview_line(before)}\n"
        f"맞으면 '네', 아니면 '취소'"
    )


def _start_last_saved(
    user_id: str,
    channel_id: Optional[str],
    action: str,
    fields: Dict[str, Any],
    user_name: Optional[str],
) -> str:
    if not _is_journal_mode(user_id, channel_id):
        return MODE_BLOCKED
    record_id = get_last_saved_id(user_id, channel_id)
    if record_id is None:
        cands = list_owned_candidates(user_id)
        if not cands:
            return NO_POINTER
        q = "고칠 기록을 번호로 골라주세요.\n" + "\n".join(
            f"{i+1}. #{row['id']} {preview_line(row_to_fields(row))}" for i, row in enumerate(cands)
        )
        _set_pending(
            user_id, channel_id,
            {
                "step": "awaiting_record_choice",
                "pending_action": action,
                "fields": fields,
                "candidates": [row["id"] for row in cands],
                "user_name": user_name,
                "applied": False,
            },
            ["record"], q,
        )
        return q
    owned = fetch_owned_work_log(user_id, record_id)
    if owned is None:
        return NO_POINTER
    before = row_to_fields(owned)
    if action == ACTION_DELETE:
        q = _preview_delete(record_id, before)
        _set_pending(
            user_id, channel_id,
            {
                "step": "awaiting_confirmation",
                "pending_action": ACTION_DELETE,
                "target_id": record_id,
                "before": before,
                "applied": False,
                "user_name": user_name,
            },
            ["confirm"], q,
        )
        return q
    patch, err = validate_update_fields(fields)
    if err:
        return f"❌ {sanitize_user_error(err)}"
    patch = patch or {}
    if not patch:
        q = f"직전 작업일지 #{record_id}예요. 어떤 값을 바꿀까요?"
        _set_pending(
            user_id, channel_id,
            {
                "step": "awaiting_confirmation",
                "pending_action": ACTION_UPDATE,
                "target_id": record_id,
                "before": before,
                "after": before,
                "fields": {},
                "applied": False,
                "user_name": user_name,
            },
            ["fields"], q,
        )
        return q
    after = merge_record_fields(before, patch)
    q = _preview_update(record_id, before, after)
    _set_pending(
        user_id, channel_id,
        {
            "step": "awaiting_confirmation",
            "pending_action": ACTION_UPDATE,
            "target_id": record_id,
            "before": before,
            "after": after,
            "fields": patch,
            "applied": False,
            "user_name": user_name,
        },
        ["confirm"], q,
    )
    return q


def _start_selected(
    user_id: str,
    channel_id: Optional[str],
    action: str,
    fields: Dict[str, Any],
    user_name: Optional[str],
    record_id: int,
) -> str:
    if not _is_journal_mode(user_id, channel_id):
        return MODE_BLOCKED
    owned = fetch_owned_work_log(user_id, record_id)
    if owned is None:
        return NO_POINTER
    before = row_to_fields(owned)
    patch, err = validate_update_fields(fields)
    if err:
        return f"❌ {sanitize_user_error(err)}"
    patch = patch or {}
    if not patch:
        q = f"작업일지 #{record_id}예요. 어떤 값을 바꿀까요?"
        _set_pending(
            user_id, channel_id,
            {
                "step": "awaiting_confirmation",
                "pending_action": ACTION_UPDATE,
                "target_id": record_id,
                "target_source": "selected_record",
                "before": before,
                "after": before,
                "fields": {},
                "applied": False,
                "user_name": user_name,
            },
            ["fields"], q,
        )
        return q
    after = merge_record_fields(before, patch)
    q = _preview_update(record_id, before, after)
    _set_pending(
        user_id, channel_id,
        {
            "step": "awaiting_confirmation",
            "pending_action": ACTION_UPDATE,
            "target_id": record_id,
            "target_source": "selected_record",
            "before": before,
            "after": after,
            "fields": patch,
            "applied": False,
            "user_name": user_name,
        },
        ["confirm"], q,
    )
    return q


def _handle_confirm(
    user_id: str,
    channel_id: Optional[str],
    pending: Dict[str, Any],
    user_name: Optional[str],
    event_id: Optional[str],
) -> str:
    if not _is_journal_mode(user_id, channel_id):
        return MODE_BLOCKED
    step = pending.get("step")
    if step == "awaiting_price":
        pending["unit_price"] = pending.get("unit_price") or pending.get("suggested_price")
        pending["amount_type"] = "unit"
        return _continue_create(user_id, channel_id, pending, user_name, event_id)
    if step == "awaiting_new_vs_draft":
        pending.pop("conflict_new", None)
        pending["step"] = "awaiting_fields"
        return _continue_create(user_id, channel_id, pending, user_name, event_id)
    if step != "awaiting_confirmation":
        return ASK_ONCE
    if pending.get("applied"):
        return ALREADY
    action = pending.get("pending_action")
    record_id = pending.get("target_id")
    pointer = get_last_saved_id(user_id, channel_id)
    source = pending.get("target_source") or "last_saved"
    from backend.app.services.bot_target import listed_record_ids

    allowed = False
    if record_id and source == "selected_record":
        allowed = int(record_id) in listed_record_ids(user_id, channel_id, "journal")
    elif record_id and pointer is not None and int(pointer) == int(record_id):
        allowed = True
    if not allowed:
        _clear_pending(user_id, channel_id)
        return NO_POINTER
    owned = fetch_owned_work_log(user_id, int(record_id))
    if owned is None:
        _clear_pending(user_id, channel_id)
        return NO_POINTER
    if action == ACTION_DELETE:
        result = delete_owned_work_log(user_id, channel_id, int(record_id), user_name or pending.get("user_name"))
        if not result.get("success"):
            err = result.get("error")
            if err == "mode_not_journal":
                return MODE_BLOCKED
            return f"❌ {sanitize_user_error(err)}"
        pending["applied"] = True
        q = f"🗑️ 작업일지 #{record_id}를 삭제했어요."
        _set_pending(user_id, channel_id, pending, [], q)
        return q
    fields = pending.get("fields") or {}
    result = apply_owned_work_log_fields(
        user_id, channel_id, int(record_id), fields, user_name or pending.get("user_name"),
    )
    if not result.get("success"):
        err = result.get("error")
        if err == "mode_not_journal":
            return MODE_BLOCKED
        return f"❌ {sanitize_user_error(err)}"
    pending["applied"] = True
    q = f"✅ 작업일지 #{record_id}를 수정했어요.\n{preview_line(pending.get('after') or {})}"
    _set_pending(user_id, channel_id, pending, [], q)
    return q


def _handle_record_choice(
    user_id: str,
    channel_id: Optional[str],
    pending: Dict[str, Any],
    text: str,
    fields: Dict[str, Any],
    user_name: Optional[str],
) -> Optional[str]:
    cands = pending.get("candidates") or []
    raw = (text or "").strip()
    chosen = None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(cands):
            chosen = cands[idx - 1]
        elif idx in cands:
            chosen = idx
    if chosen is None and fields.get("qty") and not fields.get("vendor"):
        idx = int(fields["qty"])
        if 1 <= idx <= len(cands):
            chosen = cands[idx - 1]
    if chosen is None:
        return None
    from backend.app.services.journal_edit import remember_last_saved

    remember_last_saved(user_id, channel_id, int(chosen))
    action = pending.get("pending_action") or ACTION_UPDATE
    return _start_last_saved(user_id, channel_id, action, pending.get("fields") or fields, user_name)


async def handle_user_text(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str] = None,
    nlu_intent=None,
    event_id: Optional[str] = None,
) -> str:
    raw = (text or "").strip()
    from backend.app.services.bot_nlu import interpret_or_fallback, nlu_to_bot_intent, render_readonly_nlu

    if not _is_journal_mode(user_id, channel_id):
        return MODE_BLOCKED

    nlu = nlu_intent if nlu_intent is not None else await interpret_or_fallback(user_id, channel_id, raw)
    from backend.app.services.bot_nlu import is_read_action
    from backend.app.services.bot_query import handle_mode_read, looks_like_query_read, looks_like_write_request

    nlu_action = getattr(nlu, "action", None) if nlu else None
    if nlu_action in {"update", "delete", "confirm", "cancel", "provide_field"}:
        pass
    elif is_read_action(nlu) or (looks_like_query_read(raw) and not looks_like_write_request(raw)):
        return handle_mode_read(nlu, raw, user_id, channel_id, user_name, "journal")
    readonly = render_readonly_nlu(nlu, raw)
    if readonly:
        return readonly
    intent = nlu_to_bot_intent(nlu, raw)
    pending = _get_pending(user_id, channel_id)
    fields = journal_fields_only(intent.fields)
    entries = [journal_fields_only(e) for e in (getattr(nlu, "entries", None) or intent.entries or []) if e]
    action = intent.action
    target = intent.target

    if action == ACTION_CANCEL:
        if pending:
            _clear_pending(user_id, channel_id)
            return CANCELLED
        return "취소할 작성 중인 일지가 없어요."

    if pending.get("step") == "awaiting_record_choice" and action != ACTION_UNKNOWN:
        chosen = _handle_record_choice(user_id, channel_id, pending, raw, fields, user_name)
        if chosen:
            return chosen

    if action == ACTION_CONFIRM and pending:
        return _handle_confirm(user_id, channel_id, pending, user_name, event_id)

    if pending.get("step") == "awaiting_confirmation":
        if pending.get("applied") and action == ACTION_CONFIRM:
            return ALREADY
        if action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD) and fields and pending.get("pending_action") == ACTION_UPDATE:
            patch, err = validate_update_fields({**(pending.get("fields") or {}), **fields})
            if err:
                return f"❌ {sanitize_user_error(err)}"
            before = pending.get("before") or {}
            after = merge_record_fields(before, patch or {})
            pending["fields"] = patch or {}
            pending["after"] = after
            pending["applied"] = False
            q = _preview_update(int(pending["target_id"]), before, after)
            _set_pending(user_id, channel_id, pending, ["confirm"], q)
            return q
        if pending.get("applied"):
            _clear_pending(user_id, channel_id)
            pending = {}
        elif action not in (ACTION_CREATE,) and not entries:
            return pending.get("last_prompt") or _preview_update(
                int(pending.get("target_id") or 0),
                pending.get("before") or {},
                pending.get("after") or pending.get("before") or {},
            )

    if pending.get("step") == "awaiting_new_vs_draft":
        compact = raw.replace(" ", "")
        if any(k in compact for k in ("새작업", "새로", "새걸로")):
            incoming = pending.get("conflict_new") or fields
            _clear_pending(user_id, channel_id)
            return _continue_create(user_id, channel_id, {**incoming, "user_name": user_name}, user_name, event_id)
        if any(k in compact for k in ("이어서", "작성중", "기존")):
            pending.pop("conflict_new", None)
            return _continue_create(user_id, channel_id, pending, user_name, event_id)

    if pending.get("step") == "awaiting_amount_type":
        compact = raw.replace(" ", "")
        if "총" in compact:
            pending["amount_type"] = "total"
            if pending.get("unit_price") and not pending.get("total_amount"):
                pending["total_amount"] = pending.pop("unit_price")
            return _continue_create(user_id, channel_id, pending, user_name, event_id)
        if any(k in compact for k in ("개당", "단가", "건당")):
            pending["amount_type"] = "unit"
            return _continue_create(user_id, channel_id, pending, user_name, event_id)
        if fields.get("amount_type") in ("unit", "total"):
            pending["amount_type"] = fields["amount_type"]
            return _continue_create(user_id, channel_id, pending, user_name, event_id)

    if pending.get("step") == "awaiting_price_choice":
        cands = pending.get("price_candidates") or []
        picked = fields.get("work_type") or raw.strip()
        if picked in cands:
            pending["work_type"] = picked
            pending.pop("price_candidates", None)
            pending["step"] = "awaiting_fields"
            return _continue_create(user_id, channel_id, pending, user_name, event_id)

    if pending.get("step") == "awaiting_price":
        if not fields.get("unit_price"):
            from backend.app.services.journal_adapter import extract_journal_fields_local

            local_price = extract_journal_fields_local(raw, pending_step="unit_price", user_name=user_name or "")
            if local_price.get("unit_price"):
                fields["unit_price"] = local_price["unit_price"]
        if fields.get("unit_price"):
            pending["unit_price"] = fields["unit_price"]
            pending["amount_type"] = "unit"
            return _continue_create(user_id, channel_id, pending, user_name, event_id)
        if action == ACTION_CONFIRM:
            return _handle_confirm(user_id, channel_id, pending, user_name, event_id)

    draft_active = bool(pending) and pending.get("step") not in {
        "awaiting_confirmation",
        "awaiting_record_choice",
    }

    if target == TARGET_LAST_SAVED and action in (ACTION_UPDATE, ACTION_DELETE):
        if draft_active and pending.get("step") in {"awaiting_fields", "awaiting_price", "awaiting_amount_type"}:
            q = "작성 중인 일지를 고칠까요, 아니면 직전 저장 기록을 고칠까요?"
            return q
        return _start_last_saved(user_id, channel_id, action, fields, user_name)

    if action == ACTION_DELETE:
        return _start_last_saved(user_id, channel_id, ACTION_DELETE, fields, user_name)

    if action == ACTION_UPDATE and target == TARGET_SELECTED_RECORD:
        from backend.app.services.bot_target import resolve_update_target

        resolved = resolve_update_target(user_id, channel_id, "journal", raw, nlu)
        if not resolved.record_id:
            return resolved.message or NO_POINTER
        return _start_selected(user_id, channel_id, ACTION_UPDATE, fields, user_name, int(resolved.record_id))

    if entries and len(entries) > 1 and action in (ACTION_CREATE, ACTION_PROVIDE_FIELD, ACTION_UNKNOWN):
        shared_date = fields.get("date")
        shared_vendor = fields.get("vendor")
        prepared = []
        for item in entries:
            one = dict(item)
            if shared_vendor and not one.get("vendor"):
                one["vendor"] = shared_vendor
            if shared_date and not one.get("date"):
                one["date"] = shared_date
            if one.get("qty") in (None, ""):
                one["qty"] = 1
            if not one.get("date"):
                one["date"] = seoul_today()
            prepared.append(one)
        return _try_save(user_id, channel_id, prepared, user_name, event_id)

    incoming = fields
    if action == ACTION_UNKNOWN and not incoming:
        local = extract_journal_fields_local(raw) if getattr(nlu, "source", "") == "fallback" else {}
        if local:
            incoming = local
            action = ACTION_PROVIDE_FIELD if draft_active else ACTION_CREATE
        else:
            if pending:
                return _ask_missing(user_id, channel_id, pending)
            return intent.clarification or ASK_ONCE

    if draft_active and action in (ACTION_CREATE, ACTION_PROVIDE_FIELD, ACTION_UPDATE) and target != TARGET_LAST_SAVED:
        if action == ACTION_CREATE and _conflicts_with_draft(pending, incoming):
            q = (
                f"작성 중인 {pending.get('vendor') or ''} {pending.get('work_type') or ''}를 이어서 할까요, "
                "새 작업으로 할까요?"
            )
            _set_pending(
                user_id, channel_id,
                {**pending, "step": "awaiting_new_vs_draft", "conflict_new": incoming},
                [], q,
            )
            return q
        merged = _merge_draft(pending, incoming)
        merged["user_name"] = user_name or pending.get("user_name")
        merged["step"] = "awaiting_fields"
        return _continue_create(user_id, channel_id, merged, user_name, event_id)

    if action in (ACTION_CREATE, ACTION_PROVIDE_FIELD) or incoming:
        data = {**incoming, "user_name": user_name, "step": "awaiting_fields"}
        return _continue_create(user_id, channel_id, data, user_name, event_id)

    return intent.clarification or ASK_ONCE
