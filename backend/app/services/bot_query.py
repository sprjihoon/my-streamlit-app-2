"""조회모드 읽기 전용 adapter. AIParser를 호출하지 않고 서버가 사실을 렌더링한다."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services.bot_dates import business_date, resolve_relative_range, seoul_today_str
from backend.app.services.bot_intent import (
    ACTION_COUNT,
    ACTION_GROUP,
    ACTION_LATEST,
    ACTION_LIST,
    ACTION_LOOKUP_PRICE,
    ACTION_QUERY_CATALOG,
    ACTION_SHOW_HELP,
    ACTION_START_MODE,
    ACTION_STATS,
)
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.journal_edit import get_last_saved_id as get_journal_last_saved_id
from backend.app.services.repair_edit import fetch_owned_repair, get_last_saved_id as get_repair_last_saved_id

logger = logging.getLogger(__name__)

PRICE_CUES = ("가격", "단가", "얼마", "비용", "요금")
LOG_CUES = ("목록", "기록", "일지", "최근", "저장한", "저장된", "항목", "조회")
LAST_CUES = ("방금", "직전", "아까", "저장한", "저장된")
CHANGE_CUES = ("수정", "변경", "바꿔", "고치", "고쳐", "아니고", "말고")
COUNT_CUES = ("몇건", "몇 건", "몇개", "몇 개", "건수")
GROUP_CUES = ("업체별", "작업별", "작업자별", "제품별")
SELF_CUES = ("내가", "내작업", "내 작업", "나는", "난")
ALL_SCOPE_CUES = ("전체", "전원", "모두")
REPAIR_ENTITY_CUES = ("수선",)
WORK_ENTITY_CUES = ("작업일지", "하차", "상차", "입고", "양품")
QUERY_HINT_REPAIR = "수선일지는 수선모드나 조회모드에서 확인할 수 있어요."
QUERY_HINT_JOURNAL = "작업일지는 일지모드나 조회모드에서 확인할 수 있어요."
QUERY_WRITE_BLOCKED = "조회모드는 읽기 전용이에요. 작업일지는 일지모드, 수선일지는 수선모드에서 수정할 수 있어요."
SAFE_QUERY_ERROR = "조회 중 문제가 생겼어요. 조건을 바꿔 다시 요청해주세요."
GENERIC_WORK_TYPES = frozenset(("작업", "일지", "기록", "조회", "건", "몇건", "수선작업", "작업일지", "수선일지"))
_SPACE = re.compile(r"\s+")


def _compact(text: str) -> str:
    return _SPACE.sub("", (text or "").strip())


def looks_like_last_saved_update(text: str) -> bool:
    compact = _compact(text)
    if "바꾸기" in compact and "바꿔" not in compact:
        has_change = any(c in compact for c in ("수정", "변경", "고쳐", "고치", "아니고", "말고"))
    else:
        has_change = any(c in compact for c in CHANGE_CUES) or ("바꾸" in compact)
    has_last = any(c in compact for c in LAST_CUES)
    return bool(has_last and has_change)


def looks_like_last_saved_show(text: str) -> bool:
    compact = _compact(text)
    if looks_like_last_saved_update(text):
        return False
    if any(c in compact for c in PRICE_CUES):
        return False
    has_last = any(c in compact for c in LAST_CUES)
    has_item = any(c in compact for c in ("수선", "항목", "일지", "그거"))
    return bool(has_last and has_item)


def looks_like_repair_logs(text: str) -> bool:
    compact = _compact(text)
    if looks_like_last_saved_update(text) or looks_like_last_saved_show(text):
        return False
    if any(c in compact for c in PRICE_CUES) and not any(c in compact for c in COUNT_CUES):
        return False
    return "수선" in compact and any(
        c in compact for c in ("목록", "최근", "기록", "일지", "조회", "몇건", "몇개", "업체", "봉제")
    )


def looks_like_price_query(text: str) -> bool:
    compact = _compact(text)
    if looks_like_last_saved_update(text) or looks_like_last_saved_show(text):
        return False
    if any(c in compact for c in ("몇건", "목록", "일지조회", "업체별")):
        return False
    has_price = any(c in compact for c in PRICE_CUES)
    return has_price and ("수선" in compact or "항목" in compact or "작업" in compact or "세탁" in compact)


def looks_like_selected_update(text: str) -> bool:
    from backend.app.services.bot_intent import parse_result_index

    if parse_result_index(text) is None:
        return False
    compact = _compact(text)
    return any(c in compact for c in CHANGE_CUES) or ("바꾸" in compact)


def looks_like_write_request(text: str) -> bool:
    return looks_like_last_saved_update(text) or looks_like_selected_update(text)


def looks_like_work_logs(text: str) -> bool:
    compact = _compact(text)
    if looks_like_write_request(text) or "수선" in compact:
        return False
    return "작업일지" in compact or (
        "작업" in compact and any(c in compact for c in ("몇건", "몇개", "목록", "보여", "찾아", "조회"))
    )


def looks_like_specific_price_query(text: str) -> bool:
    if not looks_like_price_query(text):
        return False
    compact = _compact(text)
    if any(c in compact for c in ("항목", "목록", "리스트", "등록된")):
        return False
    from backend.app.services.repair_catalog import resolve_work_type

    return resolve_work_type(text) is not None


def looks_like_query_read(text: str) -> bool:
    compact = _compact(text)
    if compact in {"수선", "일지", "조회", "작업일지", "수선모드", "일지모드", "조회모드"}:
        return False
    if looks_like_write_request(text):
        return False
    if looks_like_last_saved_show(text) or looks_like_repair_logs(text) or looks_like_work_logs(text):
        return True
    if looks_like_specific_price_query(text):
        return True
    return any(
        c in compact
        for c in (
            "몇건", "몇개", "목록", "일지조회", "업체별", "작업한업체",
            "전체몇", "수선일지조회", "기록좀",
        )
    )


def should_skip_readonly(text: str, nlu=None) -> bool:
    if looks_like_specific_price_query(text):
        return True
    if looks_like_last_saved_update(text) or looks_like_last_saved_show(text) or looks_like_repair_logs(text):
        return True
    action = getattr(nlu, "action", None) if nlu else None
    entity = getattr(nlu, "entity", None) if nlu else None
    topic = (getattr(nlu, "fields", None) or {}).get("topic") if nlu else None
    if action in {ACTION_LIST, ACTION_LATEST, ACTION_COUNT, ACTION_STATS, ACTION_GROUP, ACTION_LOOKUP_PRICE}:
        return True
    if action == ACTION_SHOW_HELP and (looks_like_last_saved_show(text) or looks_like_repair_logs(text)):
        return True
    if action == ACTION_QUERY_CATALOG and topic in {"last_saved", "repair_logs", "work_logs"}:
        return True
    if action == ACTION_START_MODE and looks_like_query_read(text):
        return True
    if entity in {"work_log", "repair_log"} and action == ACTION_QUERY_CATALOG:
        return True
    return False


def _extract_vendor(text: str) -> Optional[str]:
    compact = _compact(text)
    if not compact:
        return None
    try:
        from logic.db import get_connection

        with get_connection() as con:
            rows = con.execute("SELECT vendor FROM vendors WHERE vendor IS NOT NULL").fetchall()
    except Exception:
        return None
    hits = [str(row[0]) for row in rows if row and row[0] and _compact(str(row[0])) in compact]
    if not hits:
        return None
    hits.sort(key=lambda name: len(_compact(name)), reverse=True)
    return hits[0]


def infer_query_fallback(text: str, context: Optional[Dict[str, Any]] = None) -> Any:
    from backend.app.services.bot_nlu import NluIntent

    context = context or {}
    prev = context.get("query_context") or {}
    compact = _compact(text)
    mode = context.get("mode")
    entity = prev.get("entity") or ("work_log" if mode == "journal" else "repair_log")
    if mode == "journal" and "수선" not in compact:
        entity = "work_log"
    if mode == "repair" and "작업일지" not in compact:
        entity = "repair_log"
    if any(c in compact for c in WORK_ENTITY_CUES) and "수선" not in compact:
        entity = "work_log"
    if "수선" in compact:
        entity = "repair_log"
    if "작업일지" in compact and "수선" not in compact:
        entity = "work_log"
    filters: Dict[str, Any] = {}
    if prev.get("filters"):
        filters.update(prev["filters"])
    if "오늘" in compact:
        filters["relative_date"] = "today"
    elif "어제" in compact:
        filters["relative_date"] = "yesterday"
    if any(c in compact for c in ALL_SCOPE_CUES):
        filters["scope"] = "all"
        filters.pop("worker", None)
    if any(c in compact for c in SELF_CUES):
        filters["scope"] = "self"
    if "봉제" in compact:
        filters["work_type"] = "봉제"
        entity = "repair_log"
    vendor = _extract_vendor(text)
    if vendor:
        filters["vendor"] = vendor
    action = ACTION_LIST
    if looks_like_last_saved_show(text):
        action = ACTION_LATEST
    elif any(c in compact for c in GROUP_CUES) or compact.endswith("업체") or "업체별" in compact or "작업한업체" in compact:
        action = ACTION_GROUP
        filters["group_by"] = "vendor" if "업체" in compact else filters.get("group_by") or "vendor"
    elif any(cue.replace(" ", "") in compact for cue in COUNT_CUES) or "몇건" in compact or "몇개" in compact:
        action = ACTION_COUNT
    elif looks_like_price_query(text):
        action = ACTION_LOOKUP_PRICE
        entity = "repair_price" if "수선" in compact or "세탁" in compact else "work_price"
        if entity == "repair_price":
            from backend.app.services.repair_catalog import resolve_work_type

            hit = resolve_work_type(text)
            if hit and hit.get("작업명"):
                filters["work_type"] = hit["작업명"]
    domain = {
        "work_log": "journal",
        "work_price": "journal",
        "repair_log": "repair",
        "repair_price": "repair",
    }.get(entity, "query")
    return NluIntent(
        entity=entity,
        domain=domain,
        action=action,
        target="last_saved" if action == ACTION_LATEST else "by_filter",
        filters=filters,
        confidence=0.7,
        source="fallback",
    )


def _safe_tool(name: str, args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    from backend.app.services.bot_tools import execute_tool

    try:
        return execute_tool(name, args, user_id, None, mode="query")
    except Exception:
        logger.exception("query_tool_failed name=%s", name)
        return {"success": False, "error": "lookup_failed"}


def _merge_filters(nlu, text: str, prev: Optional[Dict[str, Any]]) -> Tuple[str, str, Dict[str, Any]]:
    prev = prev or {}
    compact = _compact(text)
    mode = prev.get("mode") or getattr(nlu, "domain", None)
    domain = getattr(nlu, "domain", None)
    raw_entity = getattr(nlu, "entity", None)
    entity = raw_entity if raw_entity not in (None, "", "none") else prev.get("entity")
    if entity in (None, "", "none"):
        entity = "work_log" if mode in {"journal", "work_log"} else "repair_log"
    action = getattr(nlu, "action", None) or prev.get("action") or ACTION_LIST
    if action in {ACTION_SHOW_HELP, ACTION_START_MODE, ACTION_QUERY_CATALOG, "unknown", "clarify"} and looks_like_query_read(text):
        inferred = infer_query_fallback(text, {"query_context": prev, "mode": mode})
        entity = inferred.entity
        action = inferred.action
        filters_in = dict(inferred.filters or {})
        prev = {**prev, "filters": {**(prev.get("filters") or {}), **filters_in}}
    filters = dict(prev.get("filters") or {})
    incoming = dict(getattr(nlu, "filters", None) or {})
    fields = dict(getattr(nlu, "fields", None) or {})
    for key, value in incoming.items():
        if value not in (None, "", "none"):
            filters[key] = value
    for key in ("vendor", "product", "work_type", "defect", "barcode", "remark"):
        if fields.get(key) and key not in incoming:
            filters[key] = fields[key]
    if "오늘" in compact:
        filters["relative_date"] = "today"
    elif "어제" in compact:
        filters["relative_date"] = "yesterday"
    if any(c in compact for c in ALL_SCOPE_CUES):
        filters["scope"] = "all"
        filters.pop("worker", None)
    elif any(c in compact for c in SELF_CUES):
        filters["scope"] = "self"
    if "봉제" in compact:
        filters["work_type"] = filters.get("work_type") or "봉제"
        entity = "repair_log"
    vendor = _extract_vendor(text)
    if vendor:
        filters["vendor"] = vendor
    if filters.get("work_type") in GENERIC_WORK_TYPES:
        filters.pop("work_type", None)
    if "수선" in compact:
        entity = "repair_log"
    if looks_like_specific_price_query(text):
        action = ACTION_LOOKUP_PRICE
        entity = "repair_price"
    if looks_like_last_saved_show(text):
        action = ACTION_LATEST
        entity = "work_log" if "작업일지" in compact and "수선" not in compact else "repair_log"
    if any(c in compact for c in GROUP_CUES) or "작업한업체" in compact:
        action = ACTION_GROUP
        filters["group_by"] = "vendor" if "업체" in compact else filters.get("group_by") or "vendor"
    elif "몇건" in compact or "몇개" in compact or "전체몇" in compact:
        action = ACTION_COUNT
    if action == ACTION_QUERY_CATALOG and entity in {"work_log", "repair_log"}:
        action = ACTION_LIST
    if entity not in {"work_log", "repair_log", "work_price", "repair_price"}:
        entity = "repair_log" if "수선" in compact or prev.get("entity") == "repair_log" else "work_log"
    return entity, action, filters


def _date_bounds(filters: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    start, end = resolve_relative_range(filters.get("relative_date"))
    start = filters.get("start_date") or start
    end = filters.get("end_date") or end
    return start, end


def _worker_args(filters: Dict[str, Any], user_name: Optional[str]) -> Optional[str]:
    scope = filters.get("scope") or "all"
    if scope == "all":
        return None
    if scope == "self":
        return (user_name or "").strip() or None
    return (filters.get("worker") or "").strip() or None


def _used_conditions(entity: str, filters: Dict[str, Any]) -> str:
    labels = []
    rel = filters.get("relative_date")
    if rel == "today":
        labels.append(f"오늘({seoul_today_str()})")
    elif rel == "yesterday":
        labels.append("어제")
    elif filters.get("start_date") or filters.get("end_date"):
        labels.append(f"{filters.get('start_date') or ''}~{filters.get('end_date') or ''}".strip("~"))
    for key, title in (
        ("vendor", "업체"),
        ("work_type", "작업"),
        ("product", "제품"),
        ("defect", "불량"),
        ("worker", "작업자"),
        ("barcode", "바코드"),
        ("remark", "비고"),
    ):
        if filters.get(key):
            labels.append(f"{title} {filters[key]}")
    if filters.get("scope") == "all":
        labels.append("전체 작업자")
    entity_label = {
        "work_log": "작업일지",
        "repair_log": "수선일지",
        "work_price": "작업 단가",
        "repair_price": "수선 가격",
    }.get(entity, "기록")
    if not labels:
        return entity_label
    return f"{entity_label} / " + ", ".join(labels)


def _empty(entity: str, filters: Dict[str, Any]) -> str:
    return f"{_used_conditions(entity, filters)} 조건에 해당하는 기록이 없습니다."


def format_last_saved(user_id: str, channel_id: Optional[str], entity: str) -> str:
    if entity == "work_log":
        record_id = get_journal_last_saved_id(user_id, channel_id)
        if record_id is None:
            return "이 방에서 방금 저장한 작업일지를 찾지 못했어요."
        from logic.db import get_connection

        with get_connection() as con:
            row = con.execute(
                "SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계 FROM work_log WHERE id = ?",
                (record_id,),
            ).fetchone()
        if not row:
            return "이 방에서 방금 저장한 작업일지를 찾지 못했어요."
        return (
            f"방금 저장한 작업일지입니다.\n"
            f"#{row[0]} / {row[1] or '-'} / {row[2] or '-'} / {row[3] or '-'} / "
            f"{row[4] or 0}건 / {int(row[5] or 0):,}원"
        )
    record_id = get_repair_last_saved_id(user_id, channel_id)
    if record_id is None:
        return "이 방에서 방금 저장한 수선일지를 찾지 못했어요."
    row = fetch_owned_repair(user_id, channel_id, record_id)
    if not row:
        return "이 방에서 방금 저장한 수선일지를 찾지 못했어요."
    qty = row.get("수량") if row.get("수량") is not None else "?"
    price = row.get("비용")
    price_txt = f"{int(price):,}원" if price is not None else "-"
    return (
        f"방금 저장한 수선일지입니다.\n"
        f"#{row.get('id')} / {row.get('업체명') or '-'} / {row.get('제품명') or '-'}"
        f" / {row.get('작업') or row.get('불량명') or '-'} / {qty}건 / {price_txt}"
    )


def _tool_args(filters: Dict[str, Any], user_name: Optional[str]) -> Dict[str, Any]:
    start, end = _date_bounds(filters)
    args: Dict[str, Any] = {
        "vendor": filters.get("vendor"),
        "work_type": filters.get("work_type"),
        "product": filters.get("product"),
        "defect": filters.get("defect"),
        "barcode": filters.get("barcode"),
        "remark": filters.get("remark"),
        "worker": _worker_args(filters, user_name),
        "start_date": start,
        "end_date": end,
        "limit": filters.get("limit") or 20,
        "group_by": filters.get("group_by"),
        "include_amount": bool(filters.get("include_amount")),
    }
    return {k: v for k, v in args.items() if v not in (None, "", "none")}


def render_count(entity: str, result: Dict[str, Any], filters: Dict[str, Any], *, include_amount: bool) -> str:
    rows = int(result.get("count") or result.get("row_count") or 0)
    qty = int(result.get("qty") or result.get("qty_sum") or 0)
    amount = int(result.get("total") or result.get("amount") or 0)
    label = "수선일지" if entity == "repair_log" else "작업일지"
    when = "오늘 " if filters.get("relative_date") == "today" else ""
    text = f"{when}{label}는 {rows}개 기록이고, 수량 합계는 총 {qty}건입니다."
    if include_amount:
        text += f" 총금액은 {amount:,}원입니다."
    if rows == 0 and qty == 0:
        return _empty(entity, filters)
    return text


def render_group(entity: str, result: Dict[str, Any], filters: Dict[str, Any]) -> str:
    groups = result.get("groups") or []
    if not groups:
        return _empty(entity, filters)
    by = filters.get("group_by") or "vendor"
    title = {"vendor": "업체", "work_type": "작업", "worker": "작업자", "product": "제품"}.get(by, by)
    label = "수선일지" if entity == "repair_log" else "작업일지"
    when = "오늘 " if filters.get("relative_date") == "today" else ""
    lines = [f"{when}{label}를 {title}별로 집계했습니다."]
    for item in groups[:50]:
        name = item.get("name") or "-"
        rows = int(item.get("count") or 0)
        qty = int(item.get("qty") or 0)
        lines.append(f"• {name}: {rows}개 기록, 수량 {qty}건")
    return "\n".join(lines)


def render_list(entity: str, result: Dict[str, Any], filters: Dict[str, Any]) -> str:
    rows = result.get("rows") or result.get("logs") or []
    if not rows:
        return _empty(entity, filters)
    label = "수선일지" if entity == "repair_log" else "작업일지"
    lines = [f"{_used_conditions(entity, filters)} 목록입니다."]
    for i, row in enumerate(rows[:50], start=1):
        rid = row.get("id")
        prefix = f"{i}. #{rid} / " if rid is not None else f"{i}. "
        if entity == "repair_log":
            lines.append(
                f"{prefix}{row.get('date') or '-'} / {row.get('vendor') or '-'} / "
                f"{row.get('product') or '-'} / {row.get('work_type') or '-'} / "
                f"{row.get('qty') or 0}건 / {int(row.get('unit_price') or 0):,}원"
            )
        else:
            date = row.get("날짜") or row.get("date")
            vendor = row.get("업체명") or row.get("vendor")
            work = row.get("분류") or row.get("work_type")
            qty = row.get("수량") or row.get("qty") or 0
            total = row.get("합계") or row.get("total") or 0
            lines.append(f"{prefix}{date or '-'} / {vendor or '-'} / {work or '-'} / {qty}건 / {int(total):,}원")
    return "\n".join(lines)


def render_price(entity: str, result: Dict[str, Any], filters: Dict[str, Any]) -> str:
    if not result.get("success"):
        return SAFE_QUERY_ERROR
    if entity == "work_price":
        if result.get("found") and result.get("most_recent_price") is not None:
            vendor = result.get("vendor") or filters.get("vendor") or ""
            work = result.get("work_type") or filters.get("work_type") or ""
            return f"{vendor} {work} 최근 단가는 {int(result['most_recent_price']):,}원입니다."
        return _empty(entity, filters)
    if result.get("candidates"):
        names = [c.get("작업명") or c.get("name") for c in result["candidates"] if c]
        return "여러 작업이 맞아요. " + ", ".join(n for n in names if n) + " 중에서 골라주세요."
    if result.get("found") or result.get("price") is not None or result.get("unit_price") is not None:
        name = result.get("work_type") or result.get("작업명") or filters.get("work_type") or ""
        price = result.get("price") or result.get("unit_price") or result.get("기본비용")
        if price is not None:
            return f"{name} 가격은 {int(price):,}원입니다."
    if result.get("message") and "전체세탁" not in str(result.get("message")) or filters.get("work_type") != "부분세탁":
        msg = result.get("message") or ""
        if msg and "없습니다" not in msg:
            work = filters.get("work_type") or ""
            if work and work in msg:
                return msg
            if work and "전체세탁" in msg and "부분" in work:
                return _empty(entity, filters)
            return msg
    return _empty(entity, filters)


def _remember(user_id: str, channel_id: Optional[str], entity: str, action: str, filters: Dict[str, Any], summary: str, ids: List[int]) -> None:
    get_conversation_manager().set_query_context(
        user_id,
        channel_id,
        {
            "entity": entity,
            "action": action,
            "filters": filters,
            "scope": filters.get("scope") or "all",
            "group_by": filters.get("group_by"),
            "summary": summary[:300],
            "record_ids": ids[:20],
        },
    )


def execute_query(
    nlu,
    text: str,
    user_id: str,
    channel_id: Optional[str],
    user_name: Optional[str] = None,
) -> str:
    mgr = get_conversation_manager()
    prev = mgr.get_query_context(user_id, channel_id)
    from backend.app.services.bot_mode import get_mode

    mode = get_mode(user_id, channel_id)
    if prev is None:
        prev = {}
    entity, action, filters = _merge_filters(nlu, text, {**prev, "mode": mode})
    include_amount = any(k in _compact(text) for k in ("금액", "총액", "합계", "얼마"))
    filters["include_amount"] = include_amount
    args = _tool_args(filters, user_name)

    if action == ACTION_LATEST or looks_like_last_saved_show(text):
        last_entity = entity if entity in {"work_log", "repair_log"} else (
            "work_log" if mode == "journal" else "repair_log"
        )
        reply = format_last_saved(user_id, channel_id, last_entity)
        _remember(user_id, channel_id, entity, ACTION_LATEST, filters, reply, [])
        return reply

    if entity == "repair_price" or (action == ACTION_LOOKUP_PRICE and entity != "work_price"):
        from backend.app.services.repair_catalog import lookup_repair_price

        work = filters.get("work_type") or (getattr(nlu, "fields", None) or {}).get("work_type")
        try:
            result = lookup_repair_price(filters.get("vendor"), work or text, filters.get("product"))
            result.setdefault("success", True)
        except Exception:
            logger.exception("lookup_repair_price_failed")
            result = {"success": False}
        reply = render_price("repair_price", result, {**filters, "work_type": work or filters.get("work_type")})
        _remember(user_id, channel_id, "repair_price", ACTION_LOOKUP_PRICE, filters, reply, [])
        return reply
    if entity == "work_price" or action == ACTION_LOOKUP_PRICE:
        result = _safe_tool(
            "lookup_work_price",
            {"vendor": filters.get("vendor"), "work_type": filters.get("work_type")},
            user_id,
        )
        reply = render_price("work_price", result, filters)
        _remember(user_id, channel_id, "work_price", ACTION_LOOKUP_PRICE, filters, reply, [])
        return reply

    tool_search = "search_repair_logs" if entity == "repair_log" else "search_work_logs"
    tool_stats = "get_repair_log_stats" if entity == "repair_log" else "get_work_log_stats"
    if action == ACTION_GROUP:
        result = _safe_tool(tool_stats, {**args, "group_by": filters.get("group_by") or "vendor"}, user_id)
        if not result.get("success"):
            return SAFE_QUERY_ERROR
        reply = render_group(entity, result, filters)
        _remember(user_id, channel_id, entity, ACTION_GROUP, filters, reply, [])
        return reply
    if action in {ACTION_COUNT, ACTION_STATS}:
        result = _safe_tool(tool_stats, args, user_id)
        if not result.get("success"):
            return SAFE_QUERY_ERROR
        reply = render_count(entity, result, filters, include_amount=include_amount or action == ACTION_STATS)
        _remember(user_id, channel_id, entity, action, filters, reply, [])
        return reply

    result = _safe_tool(tool_search, args, user_id)
    if not result.get("success"):
        return SAFE_QUERY_ERROR
    reply = render_list(entity, result, filters)
    ids = [int(r.get("id")) for r in (result.get("rows") or result.get("logs") or []) if r.get("id") is not None]
    _remember(user_id, channel_id, entity, ACTION_LIST, filters, reply, ids)
    return reply


def render_query_read(nlu, text: str, user_id: str, channel_id: Optional[str], user_name: Optional[str] = None) -> str:
    if looks_like_write_request(text) or (
        nlu and getattr(nlu, "action", None) in {"create", "update", "delete"}
    ):
        note = getattr(nlu, "clarification", None) if nlu else None
        return note or QUERY_WRITE_BLOCKED
    return execute_query(nlu, text, user_id, channel_id, user_name)


def query_guard_reply(mode: str) -> str:
    if mode == "repair":
        return QUERY_HINT_JOURNAL
    return QUERY_HINT_REPAIR


def is_foreign_entity(mode: str, entity: Optional[str], text: str = "") -> bool:
    compact = _compact(text)
    if mode == "journal":
        return "수선일지" in compact or (
            "수선" in compact and any(c in compact for c in ("일지", "목록", "조회", "작업한업체"))
        )
    if mode == "repair":
        return "작업일지" in compact
    return False


def handle_mode_read(nlu, text: str, user_id: str, channel_id: Optional[str], user_name: Optional[str], mode: str) -> str:
    entity = getattr(nlu, "entity", None) if nlu else None
    if is_foreign_entity(mode, entity, text):
        return query_guard_reply(mode)
    return execute_query(nlu, text, user_id, channel_id, user_name)
