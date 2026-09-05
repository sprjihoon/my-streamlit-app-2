"""수정 대상 기록 resolver. draft와 저장 완료 기록을 섞지 않는다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.services.bot_intent import TARGET_LAST_SAVED, TARGET_SELECTED_RECORD, parse_result_index
from backend.app.services.conversation_state import get_conversation_manager

NO_TARGET = "수정할 기록이 없어요. 목록을 본 뒤 번호로 지목하거나, 방금 저장한 기록을 지정해주세요."
NO_INDEX = "그 번호의 기록이 없어요. 목록에서 번호를 다시 골라주세요."
NO_LAST = "이 방에서 방금 저장한 기록을 찾지 못했어요."
PICK_CANDIDATES = "여러 기록이 있어요. 번호를 골라주세요."


@dataclass
class UpdateTarget:
    source: str = "none"
    record_id: Optional[int] = None
    candidates: List[int] = field(default_factory=list)
    message: str = ""


def listed_record_ids(user_id: str, channel_id: Optional[str], domain: str) -> List[int]:
    return _query_ids(user_id, channel_id, domain)


def _query_ids(user_id: str, channel_id: Optional[str], domain: str) -> List[int]:
    ctx = get_conversation_manager().get_query_context(user_id, channel_id) or {}
    entity = ctx.get("entity")
    if domain == "journal" and entity not in {None, "", "work_log", "work_price"}:
        return []
    if domain == "repair" and entity not in {None, "", "repair_log", "repair_price"}:
        return []
    out: List[int] = []
    for raw in ctx.get("record_ids") or []:
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            continue
    return out


def _last_saved_id(user_id: str, channel_id: Optional[str], domain: str) -> Optional[int]:
    if domain == "journal":
        from backend.app.services.journal_edit import get_last_saved_id

        return get_last_saved_id(user_id, channel_id)
    from backend.app.services.repair_edit import get_last_saved_id as get_repair_last

    return get_repair_last(user_id, channel_id)


def _has_last_cue(text: str, nlu=None) -> bool:
    compact = "".join((text or "").split())
    if any(c in compact for c in ("방금", "직전", "아까")):
        return True
    target = getattr(nlu, "target", None) if nlu else None
    explicit = bool(getattr(nlu, "explicit_last_saved", False)) if nlu else False
    return target == TARGET_LAST_SAVED and explicit


def resolve_update_target(
    user_id: str,
    channel_id: Optional[str],
    domain: str,
    text: str,
    nlu=None,
) -> UpdateTarget:
    """last_saved → 조회 순번 → 단건 필터 → 후보. 추측하지 않는다."""
    idx = parse_result_index(text)
    if idx is None and getattr(nlu, "target", None) == TARGET_SELECTED_RECORD:
        raw_idx = (getattr(nlu, "fields", None) or {}).get("index")
        try:
            idx = int(raw_idx) if raw_idx is not None else None
        except (TypeError, ValueError):
            idx = None
    ids = _query_ids(user_id, channel_id, domain)
    if idx is not None:
        if 1 <= idx <= len(ids):
            return UpdateTarget(source="selected_record", record_id=int(ids[idx - 1]))
        return UpdateTarget(source="none", message=NO_INDEX)

    if _has_last_cue(text, nlu):
        pointer = _last_saved_id(user_id, channel_id, domain)
        if pointer is None:
            return UpdateTarget(source="none", message=NO_LAST)
        return UpdateTarget(source="last_saved", record_id=int(pointer))

    filters = dict(getattr(nlu, "filters", None) or {}) if nlu else {}
    has_filter = any(
        filters.get(k) not in (None, "", "none")
        for k in ("vendor", "product", "work_type", "defect", "barcode", "worker")
    )
    if has_filter:
        rows = _search_filter_ids(domain, filters, user_id)
        if len(rows) == 1:
            return UpdateTarget(source="by_filter", record_id=int(rows[0]))
        if 2 <= len(rows) <= 5:
            return UpdateTarget(source="clarify", candidates=rows, message=PICK_CANDIDATES)
        if len(rows) > 5:
            return UpdateTarget(source="clarify", candidates=rows[:5], message=PICK_CANDIDATES)
        return UpdateTarget(source="none", message=NO_TARGET)

    pointer = _last_saved_id(user_id, channel_id, domain)
    if pointer is not None:
        return UpdateTarget(source="last_saved", record_id=int(pointer))
    if len(ids) == 1:
        return UpdateTarget(source="selected_record", record_id=int(ids[0]))
    if 2 <= len(ids) <= 5:
        return UpdateTarget(source="clarify", candidates=ids, message=PICK_CANDIDATES)
    return UpdateTarget(source="none", message=NO_TARGET)


def _search_filter_ids(domain: str, filters: Dict[str, Any], user_id: str) -> List[int]:
    from backend.app.services.bot_tools import execute_tool

    args = {k: v for k, v in filters.items() if v not in (None, "", "none") and k != "scope"}
    args["limit"] = 5
    name = "search_work_logs" if domain == "journal" else "search_repair_logs"
    result = execute_tool(name, args, user_id, None, mode="query")
    rows = result.get("rows") or result.get("logs") or []
    out: List[int] = []
    for row in rows:
        if row.get("id") is None:
            continue
        try:
            out.append(int(row["id"]))
        except (TypeError, ValueError):
            continue
    return out
