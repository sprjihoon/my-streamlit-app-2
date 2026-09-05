"""GPT 자연어 해석 계층. DB에 쓰지 않고 action·target·fields만 구조화한다."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.services.bot_intent import (
    ACTION_CANCEL,
    ACTION_CLARIFY,
    ACTION_CONFIRM,
    ACTION_COUNT,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_GROUP,
    ACTION_HELP,
    ACTION_LATEST,
    ACTION_LIST,
    ACTION_LOOKUP_PRICE,
    ACTION_NONE,
    ACTION_PROVIDE_FIELD,
    ACTION_QUERY_CATALOG,
    ACTION_SHOW_HELP,
    ACTION_START_MODE,
    ACTION_STATS,
    ACTION_UNKNOWN,
    ACTION_UPDATE,
    AMOUNT_TYPES,
    DOMAIN_JOURNAL,
    DOMAIN_REPAIR,
    JOURNAL_ALLOWED_FIELDS,
    READ_ACTIONS,
    TARGET_DRAFT,
    TARGET_LAST_SAVED,
    TARGET_NONE,
    TARGET_SELECTED_RECORD,
    BotIntent,
    allowed_fields_only,
    extract_bare_qty,
    journal_fields_only,
    parse_bot_intent,
)
from backend.app.services.bot_mode import (
    MODE_JOURNAL,
    MODE_QUERY,
    MODE_REPAIR,
    get_mode,
    parse_mode_command,
)
from backend.app.services.conversation_state import get_conversation_manager, strip_history_name_prefix

logger = logging.getLogger(__name__)

NLU_MODEL = (os.getenv("BOT_NLU_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
NLU_TIMEOUT_SEC = 8.0
LOW_CONFIDENCE = 0.6
LAST_SAVED_CONFIDENCE = 0.8
LAST_REPLY_MAX = 500
NLU_DISABLE_ENV = "BOT_NLU_DISABLE"
SCHEMA_VERSION = "2.0"
QUERY_LIMIT_MAX = 50

MODE_ACTIONS = frozenset(("none", "start", "end", "status"))
REQUESTED_MODES = frozenset(("idle", "journal", "repair", "query", "none"))
ENTITIES = frozenset(("work_log", "repair_log", "work_price", "repair_price", "none"))
NEW_ACTIONS = frozenset(
    (
        "create",
        "provide_field",
        "update",
        "delete",
        "confirm",
        "cancel",
        "list",
        "latest",
        "count",
        "stats",
        "group",
        "lookup_price",
        "help",
        "clarify",
        "unknown",
    )
)
LEGACY_ACTIONS = frozenset(
    (
        "start_mode",
        "show_help",
        "query_catalog",
        "query_logs",
        "show_last",
    )
)
ACTIONS = NEW_ACTIONS | LEGACY_ACTIONS
TARGETS = frozenset(("draft", "last_saved", "selected_record", "by_filter", "none"))
DOMAINS = frozenset(("repair", "journal", "query", "none"))
MODE_FIELDS = frozenset(("journal", "repair", "query"))
TOPIC_FIELDS = frozenset(
    ("all", "journal", "repair", "query", "repair_work_prices", "last_saved", "repair_logs", "work_logs", "work_prices")
)
RELATIVE_DATES = frozenset(("today", "yesterday", "this_week", "this_month", "none"))
SCOPES = frozenset(("all", "self", "named", "none"))
GROUP_BYS = frozenset(("vendor", "work_type", "worker", "product", "none"))
FILTER_KEYS = (
    "relative_date",
    "start_date",
    "end_date",
    "vendor",
    "product",
    "work_type",
    "defect",
    "worker",
    "barcode",
    "remark",
    "scope",
    "group_by",
    "limit",
)
WRITE_FIELD_KEYS = (
    "vendor",
    "product",
    "work_type",
    "defect",
    "unit_price",
    "qty",
    "barcode",
    "remark",
)
SECRET_MARKERS = (
    "sk-",
    "openai_api_key",
    "api_key",
    "database_path",
    "billing.db",
    "-----begin",
)
SAFE_DRAFT_KEYS = (
    "vendor", "product", "option", "work_type", "defect", "qty",
    "unit_price", "remark", "date", "total_amount", "amount_type", "barcode",
)
RECENT_TURN_MAX = 4
RECENT_TURN_CHARS = 160
COMMAND_WORK_TYPES = frozenset(
    ("조회", "조회모드", "기능", "기능설명", "도움", "종료", "끝", "모드종료", "사용법")
)
DOMAIN_TO_MODE = {
    "journal": MODE_JOURNAL,
    "repair": MODE_REPAIR,
    "query": MODE_QUERY,
}
MODE_TO_DOMAIN = {
    MODE_JOURNAL: "journal",
    MODE_REPAIR: "repair",
    MODE_QUERY: "query",
}
ENTITY_TO_DOMAIN = {
    "work_log": "journal",
    "work_price": "journal",
    "repair_log": "repair",
    "repair_price": "repair",
}
ACTION_TO_LEGACY = {
    ACTION_HELP: ACTION_SHOW_HELP,
    ACTION_LOOKUP_PRICE: ACTION_QUERY_CATALOG,
    ACTION_CLARIFY: ACTION_UNKNOWN,
}

NLU_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "mode_action",
        "requested_mode",
        "entity",
        "action",
        "target",
        "filters",
        "fields",
        "confidence",
        "missing_fields",
        "needs_confirmation",
        "clarification_reason",
    ],
    "properties": {
        "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
        "mode_action": {"type": "string", "enum": ["none", "start", "end", "status"]},
        "requested_mode": {"type": "string", "enum": ["idle", "journal", "repair", "query", "none"]},
        "entity": {
            "type": "string",
            "enum": ["work_log", "repair_log", "work_price", "repair_price", "none"],
        },
        "action": {
            "type": "string",
            "enum": [
                "create",
                "provide_field",
                "update",
                "delete",
                "confirm",
                "cancel",
                "list",
                "latest",
                "count",
                "stats",
                "group",
                "lookup_price",
                "help",
                "clarify",
                "unknown",
            ],
        },
        "target": {
            "type": "string",
            "enum": ["draft", "last_saved", "selected_record", "by_filter", "none"],
        },
        "filters": {
            "type": "object",
            "additionalProperties": False,
            "required": list(FILTER_KEYS),
            "properties": {
                "relative_date": {
                    "anyOf": [
                        {"type": "string", "enum": ["today", "yesterday", "this_week", "this_month", "none"]},
                        {"type": "null"},
                    ]
                },
                "start_date": {"type": ["string", "null"]},
                "end_date": {"type": ["string", "null"]},
                "vendor": {"type": ["string", "null"]},
                "product": {"type": ["string", "null"]},
                "work_type": {"type": ["string", "null"]},
                "defect": {"type": ["string", "null"]},
                "worker": {"type": ["string", "null"]},
                "barcode": {"type": ["string", "null"]},
                "remark": {"type": ["string", "null"]},
                "scope": {
                    "anyOf": [
                        {"type": "string", "enum": ["all", "self", "named", "none"]},
                        {"type": "null"},
                    ]
                },
                "group_by": {
                    "anyOf": [
                        {"type": "string", "enum": ["vendor", "work_type", "worker", "product", "none"]},
                        {"type": "null"},
                    ]
                },
                "limit": {"type": ["integer", "null"]},
            },
        },
        "fields": {
            "type": "object",
            "additionalProperties": False,
            "required": list(WRITE_FIELD_KEYS),
            "properties": {
                "vendor": {"type": ["string", "null"]},
                "product": {"type": ["string", "null"]},
                "work_type": {"type": ["string", "null"]},
                "defect": {"type": ["string", "null"]},
                "unit_price": {"type": ["number", "null"]},
                "qty": {"type": ["number", "null"]},
                "barcode": {"type": ["string", "null"]},
                "remark": {"type": ["string", "null"]},
            },
        },
        "confidence": {"type": "number"},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "needs_confirmation": {"type": "boolean"},
        "clarification_reason": {"type": ["string", "null"]},
    },
}

SYSTEM_PROMPT = """당신은 물류·수선 업무봇의 의도 분류기입니다.
사용자 문장을 허용된 JSON만으로 구조화하세요. DB 쓰기, SQL, 권한, 기록 ID 확정은 하지 마세요.
환경변수, API 키, 비밀번호, 파일 경로, 전체 DB는 요청·응답에 넣지 마세요.

입력 컨텍스트 키만 사용하세요: mode, pending_step, missing_fields, draft_fields, has_last_saved, has_repair_last_saved, has_journal_last_saved, last_question, last_assistant_reply, recent_turns, user_message, user_name.

규칙:
1. enum 밖 값, trusted_source, mode 우회 인자는 만들지 마세요.
2. 현재 user_message는 한 번만 주어집니다. recent_turns의 마지막과 같아도 중복으로 쓰지 마세요.
3. user_name은 사람 이름입니다. 업체·제품·작업명으로 쓰지 마세요.
4. 작성 중 draft가 있으면 기본 target은 draft입니다.
5. 저장이 끝난 직전 기록을 명시적으로 가리킬 때만 target=last_saved 입니다.
6. last_saved 수정은 needs_confirmation=true 입니다.
7. 모드를 시작하려는 짧은 명령만 mode_action=start 입니다. 오늘 수선작업 몇 건처럼 업무 문장은 모드를 바꾸지 마세요.
8. 지금 물어본 칸에 값을 채우는 말이면 action=provide_field 입니다.
9. 새 수선/일지를 시작하는 말이면 action=create 입니다.
10. 확정은 confirm, 포기는 cancel 입니다.
11. 기능을 물으면 action=help 입니다.
12. 작업/수선 기록을 목록·건수·통계로 보면 list/count/stats/group 입니다. 가격표로 바꾸지 마세요.
13. 방금 저장된 수선항목은 entity=repair_log, action=latest, target=last_saved 입니다.
14. 오늘 수선작업한 업체는 entity=repair_log, action=group, group_by=vendor 입니다.
15. 몇 건은 action=count 입니다. 작업자를 말하지 않으면 scope=all 입니다. 전체는 작업자 필터를 제거합니다.
16. 봉제 몇 건은 수선일지 work_type=봉제 입니다.
17. 금액이 개당이면 fields에 unit_price만, 수량은 pending이 수량일 때만 qty로 넣습니다.
18. 자신이 없거나 대상이 섞이면 action=clarify 이고 clarification_reason에 질문 하나만 넣습니다.
19. 조회모드에서 create/update/delete를 고르지 마세요.

의미 예시:
- 수선 업무를 시작함 → mode_action=start / repair
- 오늘 수선작업 몇 건 → count / repair_log / scope=all
- 방금 저장된 수선항목 → latest / last_saved
- 기능을 물어봄 → help
"""


@dataclass
class NluIntent:
    schema_version: str = SCHEMA_VERSION
    mode_action: str = "none"
    requested_mode: str = "none"
    entity: str = "none"
    domain: str = "none"
    action: str = ACTION_UNKNOWN
    target: str = TARGET_NONE
    fields: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_confirmation: bool = False
    missing_fields: List[str] = field(default_factory=list)
    clarification_reason: Optional[str] = None
    clarification: Optional[str] = None
    source: str = "nlu"
    explicit_last_saved: bool = False
    entries: List[Dict[str, Any]] = field(default_factory=list)


def nlu_disabled() -> bool:
    return (os.getenv(NLU_DISABLE_ENV) or "").strip() in {"1", "true", "TRUE", "yes"}


def sanitize_last_reply(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if any(marker in lowered or marker in raw for marker in SECRET_MARKERS):
        return ""
    cleaned = re.sub(r"(?:[A-Za-z]:)?[\\/][^\s]{3,}", "", raw)
    return cleaned.strip()[:LAST_REPLY_MAX]


def last_assistant_reply(user_id: str, channel_id: Optional[str]) -> str:
    history = get_conversation_manager().get_history(user_id, limit=8, channel_id=channel_id)
    for item in reversed(history):
        if item.get("role") == "assistant":
            return sanitize_last_reply(item.get("content") or "")
    return ""


def recent_turns(user_id: str, channel_id: Optional[str]) -> List[Dict[str, str]]:
    history = get_conversation_manager().get_history(user_id, limit=RECENT_TURN_MAX, channel_id=channel_id)
    turns: List[Dict[str, str]] = []
    for item in history[-RECENT_TURN_MAX:]:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = sanitize_last_reply(strip_history_name_prefix(item.get("content") or ""))[:RECENT_TURN_CHARS]
        if not content:
            continue
        turns.append({"role": role, "content": content})
    return turns


def collect_nlu_context(
    user_id: str,
    channel_id: Optional[str],
    text: str,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """GPT에 넣을 최소 컨텍스트. 현재 문장 저장 전에 호출해야 한다."""
    mode = get_mode(user_id, channel_id)
    state = get_conversation_manager().get_state(user_id, channel_id) or {}
    expired = bool(state.get("expired"))
    pending = {} if expired else (state.get("pending_data") or {})
    missing = [] if expired else [str(x) for x in (state.get("missing") or []) if x]
    pending_step = missing[0] if missing else (pending.get("step") or "")
    entry_type = pending.get("entry_type")
    journal_draft = entry_type == "journal" or pending.get("step") in {
        "awaiting_fields", "awaiting_price", "awaiting_amount_type", "awaiting_price_choice",
    }
    has_active_draft = ((not expired) and entry_type == "repair") or journal_draft
    draft_fields: Dict[str, Any] = {}
    if has_active_draft:
        for key in SAFE_DRAFT_KEYS:
            value = pending.get(key)
            if value not in (None, ""):
                draft_fields[key] = value
    has_repair_last_saved = False
    has_journal_last_saved = False
    try:
        from backend.app.services.repair_edit import get_last_saved_id

        has_repair_last_saved = get_last_saved_id(user_id, channel_id) is not None
    except Exception:
        has_repair_last_saved = False
    try:
        from backend.app.services.journal_edit import get_last_saved_id as get_journal_last_saved_id

        has_journal_last_saved = get_journal_last_saved_id(user_id, channel_id) is not None
    except Exception:
        has_journal_last_saved = False
    last_question = "" if expired else sanitize_last_reply(state.get("last_question") or "")
    query_ctx = {}
    try:
        query_ctx = get_conversation_manager().get_query_context(user_id, channel_id)
    except Exception:
        query_ctx = {}
    return {
        "mode": mode,
        "pending_step": pending_step,
        "missing_fields": missing,
        "draft_fields": draft_fields,
        "has_last_saved": bool(has_repair_last_saved or has_journal_last_saved),
        "has_repair_last_saved": bool(has_repair_last_saved),
        "has_journal_last_saved": bool(has_journal_last_saved),
        "has_active_draft": has_active_draft,
        "expired_repair_draft": expired and (state.get("pending_data") or {}).get("entry_type") == "repair",
        "last_question": last_question,
        "last_assistant_reply": last_assistant_reply(user_id, channel_id),
        "recent_turns": recent_turns(user_id, channel_id),
        "user_message": (text or "").strip(),
        "user_name": (user_name or "").strip(),
        "query_context": query_ctx or {},
    }


def gpt_payload(context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mode": context.get("mode") or "idle",
        "pending_step": context.get("pending_step") or "",
        "missing_fields": list(context.get("missing_fields") or []),
        "draft_fields": dict(context.get("draft_fields") or {}),
        "has_last_saved": bool(context.get("has_last_saved")),
        "has_repair_last_saved": bool(context.get("has_repair_last_saved")),
        "has_journal_last_saved": bool(context.get("has_journal_last_saved")),
        "last_question": context.get("last_question") or "",
        "last_assistant_reply": context.get("last_assistant_reply") or "",
        "recent_turns": list(context.get("recent_turns") or []),
        "user_message": context.get("user_message") or "",
        "user_name": context.get("user_name") or "",
    }


def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return int(number)


def _as_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def clean_nlu_fields(fields: Optional[Dict[str, Any]], *, action: str, user_name: str = "") -> Dict[str, Any]:
    raw = fields or {}
    cleaned: Dict[str, Any] = {}
    if action == ACTION_START_MODE:
        mode = raw.get("mode")
        if mode in MODE_FIELDS:
            cleaned["mode"] = mode
    if action in (ACTION_SHOW_HELP, ACTION_QUERY_CATALOG, ACTION_HELP, ACTION_LOOKUP_PRICE):
        topic = raw.get("topic")
        if topic in TOPIC_FIELDS:
            cleaned["topic"] = topic
    from backend.app.services.bot_intent import DRAFT_ALLOWED_FIELDS

    display = (user_name or "").strip()
    for key in DRAFT_ALLOWED_FIELDS | JOURNAL_ALLOWED_FIELDS | {"barcode"}:
        if key not in raw or raw[key] in (None, ""):
            continue
        if key in ("unit_price", "qty", "total_amount"):
            number = _as_int(raw[key])
            if number is not None and number > 0:
                cleaned[key] = number
            continue
        if key == "amount_type":
            if raw[key] in AMOUNT_TYPES:
                cleaned[key] = raw[key]
            continue
        text = str(raw[key]).strip()
        if display and text.replace(" ", "") == display.replace(" ", "") and key in {"vendor", "product", "work_type"}:
            continue
        if key == "work_type" and text.replace(" ", "") in COMMAND_WORK_TYPES:
            continue
        if text:
            cleaned[key] = text
    return cleaned


def clean_filters(raw: Any) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    out: Dict[str, Any] = {}
    rel = data.get("relative_date")
    if rel in RELATIVE_DATES and rel != "none":
        out["relative_date"] = rel
    for key in ("start_date", "end_date"):
        value = _as_text(data.get(key))
        if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            out[key] = value
    for key in ("vendor", "product", "work_type", "defect", "worker", "barcode", "remark"):
        value = _as_text(data.get(key))
        if value:
            out[key] = value
    scope = data.get("scope")
    if scope in SCOPES and scope != "none":
        out["scope"] = scope
    group_by = data.get("group_by")
    if group_by in GROUP_BYS and group_by != "none":
        out["group_by"] = group_by
    limit = _as_int(data.get("limit"))
    if limit is not None:
        if limit < 1:
            limit = 1
        out["limit"] = min(limit, QUERY_LIMIT_MAX)
    return out


def _clean_entries(raw_entries: Any, user_name: str = "") -> List[Dict[str, Any]]:
    if not isinstance(raw_entries, list):
        return []
    entries: List[Dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        cleaned = journal_fields_only(clean_nlu_fields(item, action=ACTION_CREATE, user_name=user_name))
        if cleaned:
            entries.append(cleaned)
    return entries


def _legacy_to_new(raw: Dict[str, Any]) -> Dict[str, Any]:
    action = raw.get("action")
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    mode_action = "none"
    requested = "none"
    entity = "none"
    new_action = action if action in NEW_ACTIONS else ACTION_UNKNOWN
    if action == ACTION_START_MODE:
        mode_action = "start"
        requested = fields.get("mode") or raw.get("domain") or "none"
        if requested not in REQUESTED_MODES:
            requested = "none"
        new_action = ACTION_UNKNOWN
    elif action == ACTION_SHOW_HELP:
        new_action = ACTION_HELP
    elif action in {ACTION_QUERY_CATALOG, "query_logs"}:
        topic = fields.get("topic")
        if topic in {"last_saved"}:
            new_action = ACTION_LATEST
            entity = "repair_log"
        elif topic in {"repair_logs"}:
            new_action = ACTION_LIST
            entity = "repair_log"
        elif topic in {"work_logs"}:
            new_action = ACTION_LIST
            entity = "work_log"
        elif topic in {"work_prices"}:
            new_action = ACTION_LOOKUP_PRICE
            entity = "work_price"
        else:
            new_action = ACTION_LOOKUP_PRICE
            entity = "repair_price"
    elif action == "show_last":
        new_action = ACTION_LATEST
        entity = "repair_log"
    domain = raw.get("domain")
    if entity == "none":
        if domain == "journal":
            entity = "work_log"
        elif domain == "repair":
            entity = "repair_log"
        elif domain == "query":
            entity = "none"
    return {
        "schema_version": SCHEMA_VERSION,
        "mode_action": mode_action,
        "requested_mode": requested if requested in REQUESTED_MODES else "none",
        "entity": entity if entity in ENTITIES else "none",
        "action": new_action,
        "target": raw.get("target") if raw.get("target") in TARGETS else "none",
        "filters": raw.get("filters") if isinstance(raw.get("filters"), dict) else {},
        "fields": fields,
        "confidence": raw.get("confidence"),
        "missing_fields": raw.get("missing_fields") or [],
        "needs_confirmation": raw.get("needs_confirmation"),
        "clarification_reason": raw.get("clarification_reason") or raw.get("clarification"),
        "entries": raw.get("entries"),
        "domain": domain,
        "legacy_action": action,
    }


def _normalize_action(action: str, mode_action: str) -> str:
    if mode_action == "start":
        return ACTION_START_MODE
    if action == ACTION_HELP:
        return ACTION_SHOW_HELP
    if action == ACTION_LOOKUP_PRICE:
        return ACTION_QUERY_CATALOG
    if action == ACTION_CLARIFY:
        return ACTION_UNKNOWN
    if action in ACTIONS:
        return action
    return ACTION_UNKNOWN


def parse_nlu_payload(raw: Any, context: Optional[Dict[str, Any]] = None) -> NluIntent:
    if not isinstance(raw, dict):
        raise ValueError("nlu_not_object")
    if raw.get("trusted_source") is not None:
        raise ValueError("nlu_trusted_source_rejected")
    if raw.get("mode") in MODE_FIELDS and raw.get("mode_action") not in MODE_ACTIONS:
        # GPT가 상위 mode로 우회하지 못하게 한다.
        raise ValueError("nlu_mode_bypass_rejected")
    context = context or {}
    user_name = str(context.get("user_name") or "")
    is_new = "schema_version" in raw or "mode_action" in raw
    body = raw if is_new else _legacy_to_new(raw)
    if body.get("trusted_source") is not None:
        raise ValueError("nlu_trusted_source_rejected")

    mode_action = body.get("mode_action") if body.get("mode_action") in MODE_ACTIONS else "none"
    requested = body.get("requested_mode") if body.get("requested_mode") in REQUESTED_MODES else "none"
    entity = body.get("entity") if body.get("entity") in ENTITIES else "none"
    raw_action = body.get("action")
    if raw_action not in ACTIONS:
        raw_action = ACTION_UNKNOWN
    action = _normalize_action(raw_action, mode_action)
    if not is_new and body.get("legacy_action") in LEGACY_ACTIONS:
        action = _normalize_action(body.get("legacy_action"), mode_action)
        if body.get("legacy_action") == ACTION_START_MODE:
            action = ACTION_START_MODE
        elif body.get("legacy_action") == ACTION_SHOW_HELP:
            action = ACTION_SHOW_HELP
        elif body.get("legacy_action") == ACTION_QUERY_CATALOG:
            action = ACTION_QUERY_CATALOG
    target = body.get("target") if body.get("target") in TARGETS else TARGET_NONE
    try:
        confidence = float(body.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    fields = clean_nlu_fields(
        body.get("fields") if isinstance(body.get("fields"), dict) else {},
        action=action,
        user_name=user_name,
    )
    if action == ACTION_START_MODE and requested in MODE_FIELDS and "mode" not in fields:
        fields["mode"] = requested
    filters = clean_filters(body.get("filters"))
    entries = _clean_entries(body.get("entries"), user_name=user_name)
    missing = [str(x) for x in (body.get("missing_fields") or []) if x]
    reason = body.get("clarification_reason") or body.get("clarification")
    if reason is not None:
        reason = str(reason).strip() or None
    domain = body.get("domain") if body.get("domain") in DOMAINS else "none"
    if domain == "none":
        domain = ENTITY_TO_DOMAIN.get(entity, requested if requested in MODE_FIELDS else "none")
        if domain not in DOMAINS:
            domain = "none"
    return NluIntent(
        schema_version=SCHEMA_VERSION,
        mode_action=mode_action,
        requested_mode=requested if requested in REQUESTED_MODES else "none",
        entity=entity,
        domain=domain if domain in DOMAINS else "none",
        action=action,
        target=target,
        fields=fields,
        filters=filters,
        confidence=confidence,
        needs_confirmation=bool(body.get("needs_confirmation")),
        missing_fields=missing,
        clarification_reason=reason,
        clarification=reason,
        source="nlu",
        entries=entries,
    )


def is_read_action(intent: Optional[NluIntent]) -> bool:
    if not intent:
        return False
    if intent.action in {
        ACTION_LIST, ACTION_LATEST, ACTION_COUNT, ACTION_STATS, ACTION_GROUP,
    }:
        return True
    if intent.entity in {"work_log", "repair_log", "work_price", "repair_price"} and intent.action in {
        ACTION_UNKNOWN, ACTION_CLARIFY,
    }:
        return bool(intent.filters)
    return False


def enforce_nlu_policy(intent: NluIntent, context: Dict[str, Any]) -> NluIntent:
    """서버가 GPT 결과를 다시 검증한다. 쓰기는 여기서 하지 않는다."""
    mode = context.get("mode")
    has_draft = bool(context.get("has_active_draft"))
    user_name = str(context.get("user_name") or "")
    if user_name:
        for key in ("vendor", "product", "work_type"):
            value = str(intent.fields.get(key) or "").replace(" ", "")
            if value and value == user_name.replace(" ", ""):
                intent.fields.pop(key, None)
        for key in ("vendor", "product", "work_type", "worker"):
            value = str(intent.filters.get(key) or "").replace(" ", "")
            if value and value == user_name.replace(" ", "") and key != "worker":
                intent.filters.pop(key, None)

    for key in ("unit_price", "qty"):
        if key in intent.fields and intent.fields[key] is not None and intent.fields[key] < 0:
            intent.fields.pop(key, None)
            intent.action = ACTION_UNKNOWN
            intent.clarification = intent.clarification or "수량과 금액은 0보다 커야 해요."
            intent.clarification_reason = intent.clarification
            return intent
    if intent.filters.get("limit") is not None:
        intent.filters["limit"] = min(max(int(intent.filters["limit"]), 1), QUERY_LIMIT_MAX)

    if mode == MODE_QUERY and intent.action in {ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE, ACTION_PROVIDE_FIELD}:
        intent.action = ACTION_UNKNOWN
        intent.target = TARGET_NONE
        intent.fields = {}
        intent.needs_confirmation = False
        intent.clarification = "조회모드에서는 저장·수정·삭제를 할 수 없어요."
        intent.clarification_reason = intent.clarification
        return intent

    if intent.action in {ACTION_CREATE, ACTION_PROVIDE_FIELD, ACTION_UPDATE, ACTION_DELETE}:
        write_domain = intent.domain if intent.domain in {DOMAIN_JOURNAL, DOMAIN_REPAIR} else ENTITY_TO_DOMAIN.get(intent.entity)
        if mode == MODE_JOURNAL and write_domain == DOMAIN_REPAIR:
            intent.action = ACTION_UNKNOWN
            intent.clarification = intent.clarification or "지금은 일지모드입니다. 수선 저장은 수선모드에서 해주세요."
            intent.clarification_reason = intent.clarification
            return intent
        if mode == MODE_REPAIR and write_domain == DOMAIN_JOURNAL and intent.action in {ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE}:
            # 수선모드에서 작업일지 쓰기는 거부. 조회 안내는 별도 경로.
            if intent.entity == "work_log":
                intent.action = ACTION_UNKNOWN
                intent.clarification = intent.clarification or "작업일지 저장은 일지모드에서 해주세요."
                intent.clarification_reason = intent.clarification
                return intent

    if intent.action == ACTION_SHOW_HELP or (intent.action == ACTION_HELP):
        intent.action = ACTION_SHOW_HELP
        intent.target = TARGET_NONE
        intent.needs_confirmation = False
        intent.fields = {"topic": intent.fields.get("topic") or "all"}
        return intent
    if intent.action in {ACTION_QUERY_CATALOG, ACTION_LOOKUP_PRICE} and intent.entity in {"none", "repair_price"}:
        topic = intent.fields.get("topic") or "repair_work_prices"
        if topic not in TOPIC_FIELDS:
            topic = "repair_work_prices"
        if intent.action == ACTION_LOOKUP_PRICE and intent.entity == "work_price":
            intent.action = ACTION_QUERY_CATALOG
            intent.fields = {**intent.fields, "topic": "work_prices"}
            intent.target = TARGET_NONE
            intent.needs_confirmation = False
            return intent
        if intent.entity in {"work_log", "repair_log"}:
            return intent
        intent.action = ACTION_QUERY_CATALOG
        intent.target = TARGET_NONE
        intent.needs_confirmation = False
        intent.fields = {**{k: v for k, v in intent.fields.items() if k in WRITE_FIELD_KEYS}, "topic": topic}
        return intent
    if intent.action == ACTION_START_MODE or intent.mode_action == "start":
        mode_name = intent.fields.get("mode") or (
            intent.requested_mode if intent.requested_mode in MODE_FIELDS else None
        ) or (intent.domain if intent.domain in MODE_FIELDS else None)
        if mode_name in MODE_FIELDS:
            intent.action = ACTION_START_MODE
            intent.mode_action = "start"
            intent.domain = mode_name
            intent.requested_mode = mode_name
            intent.fields = {"mode": mode_name}
            intent.target = TARGET_NONE
            intent.needs_confirmation = False
        else:
            intent.action = ACTION_UNKNOWN
            intent.clarification = intent.clarification or "어떤 모드를 시작할까요? 일지, 수선, 조회 중에서 골라주세요."
            intent.clarification_reason = intent.clarification
        return intent

    if intent.action in (ACTION_CONFIRM, ACTION_CANCEL):
        intent.target = TARGET_NONE
        intent.fields = {}
        intent.needs_confirmation = False
        return intent

    if intent.action in READ_ACTIONS or intent.action in {ACTION_LIST, ACTION_LATEST, ACTION_COUNT, ACTION_STATS, ACTION_GROUP}:
        intent.needs_confirmation = False
        if intent.action == ACTION_LATEST and intent.target == TARGET_NONE:
            intent.target = TARGET_LAST_SAVED
        if intent.action != ACTION_LATEST:
            intent.target = intent.target if intent.target in {TARGET_LAST_SAVED, "by_filter"} else "by_filter"
        return intent

    if intent.action == ACTION_DELETE:
        if has_draft and intent.target != TARGET_LAST_SAVED:
            intent.action = ACTION_UNKNOWN
            intent.target = TARGET_DRAFT
            intent.needs_confirmation = False
            intent.clarification = intent.clarification or (
                "작성 중인 내용을 취소할까요, 아니면 직전 저장 기록을 지울까요?"
            )
            intent.clarification_reason = intent.clarification
            return intent
        intent.target = TARGET_LAST_SAVED
        intent.needs_confirmation = True
        intent.explicit_last_saved = True
        if not intent.domain or intent.domain == "none":
            intent.domain = MODE_TO_DOMAIN.get(context.get("mode"), DOMAIN_JOURNAL)
        return intent

    if intent.confidence < LOW_CONFIDENCE and intent.action not in {
        ACTION_UNKNOWN,
        ACTION_SHOW_HELP,
        ACTION_QUERY_CATALOG,
        ACTION_HELP,
        ACTION_LIST,
        ACTION_LATEST,
        ACTION_COUNT,
        ACTION_STATS,
        ACTION_GROUP,
    }:
        intent.action = ACTION_UNKNOWN
        intent.target = TARGET_NONE
        intent.needs_confirmation = False
        intent.clarification = intent.clarification or (
            "한 가지만 확인할게요. 지금 작성 중인 내용을 이어서 할까요, 아니면 직전 저장 기록을 고칠까요?"
        )
        intent.clarification_reason = intent.clarification
        return intent

    if intent.action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD, ACTION_CREATE):
        if has_draft:
            if intent.target == TARGET_LAST_SAVED:
                if intent.explicit_last_saved and intent.confidence >= LAST_SAVED_CONFIDENCE and intent.action == ACTION_UPDATE:
                    intent.needs_confirmation = True
                elif intent.action == ACTION_UPDATE and not intent.explicit_last_saved:
                    intent.action = ACTION_PROVIDE_FIELD
                    intent.target = TARGET_DRAFT
                    intent.needs_confirmation = False
                else:
                    intent.action = ACTION_UNKNOWN
                    intent.target = TARGET_DRAFT
                    intent.clarification = intent.clarification or (
                        "작성 중인 수선을 고칠까요, 아니면 직전 저장 기록을 고칠까요?"
                    )
                    intent.clarification_reason = intent.clarification
                    return intent
            else:
                intent.target = TARGET_DRAFT
                if intent.action == ACTION_UPDATE:
                    intent.action = ACTION_PROVIDE_FIELD
                intent.needs_confirmation = False
        elif intent.target == TARGET_LAST_SAVED or (
            intent.action == ACTION_UPDATE and bool(context.get("has_last_saved"))
        ):
            if intent.target != TARGET_LAST_SAVED and intent.action != ACTION_UPDATE:
                intent.target = TARGET_NONE
            if intent.target == TARGET_LAST_SAVED:
                intent.explicit_last_saved = True
                intent.needs_confirmation = True
                intent.action = ACTION_UPDATE
        elif intent.action == ACTION_CREATE:
            intent.target = TARGET_NONE
            intent.needs_confirmation = False
        elif intent.action == ACTION_PROVIDE_FIELD:
            intent.target = TARGET_DRAFT if has_draft else TARGET_NONE

    if intent.action == ACTION_UPDATE and intent.target == TARGET_LAST_SAVED:
        intent.needs_confirmation = True
        intent.explicit_last_saved = True
        if not intent.domain or intent.domain == "none":
            intent.domain = MODE_TO_DOMAIN.get(context.get("mode"), DOMAIN_REPAIR)
    if intent.target == TARGET_SELECTED_RECORD and intent.action in (ACTION_UPDATE, ACTION_DELETE, ACTION_PROVIDE_FIELD):
        intent.needs_confirmation = True
    return intent


def nlu_to_bot_intent(intent: Optional[NluIntent], raw: str = "") -> BotIntent:
    if intent is None:
        return parse_bot_intent(raw)
    action = intent.action
    if action not in {
        ACTION_UPDATE,
        ACTION_DELETE,
        ACTION_CONFIRM,
        ACTION_CANCEL,
        ACTION_PROVIDE_FIELD,
        ACTION_CREATE,
        ACTION_START_MODE,
        ACTION_SHOW_HELP,
        ACTION_QUERY_CATALOG,
        ACTION_UNKNOWN,
        ACTION_LIST,
        ACTION_LATEST,
        ACTION_COUNT,
        ACTION_STATS,
        ACTION_GROUP,
        ACTION_LOOKUP_PRICE,
        ACTION_HELP,
    }:
        action = ACTION_NONE
    from backend.app.services.bot_intent import draft_fields_only

    target = (
        intent.target
        if intent.target in {TARGET_DRAFT, TARGET_LAST_SAVED, TARGET_SELECTED_RECORD, TARGET_NONE, "by_filter"}
        else TARGET_NONE
    )
    domain = intent.domain if intent.domain in DOMAINS else DOMAIN_REPAIR
    if domain == DOMAIN_JOURNAL:
        fields = journal_fields_only(intent.fields)
    elif target == TARGET_LAST_SAVED:
        fields = allowed_fields_only(intent.fields)
    else:
        fields = draft_fields_only(intent.fields)
    return BotIntent(
        action=action,
        target=target,
        fields=fields,
        raw=raw,
        domain=domain,
        needs_confirmation=bool(intent.needs_confirmation),
        missing_fields=list(intent.missing_fields or ([] if fields else (["fields"] if action in (ACTION_UPDATE, ACTION_DELETE) else []))),
        confidence=intent.confidence,
        explicit_last_saved=bool(intent.explicit_last_saved),
        clarification=intent.clarification,
        entries=list(intent.entries or []),
    )


def nlu_to_mode_command(intent: Optional[NluIntent]) -> Optional[dict]:
    if not intent:
        return None
    if intent.mode_action == "end":
        return {"action": "end"}
    if intent.mode_action == "status":
        return {"action": "status"}
    if intent.action != ACTION_START_MODE and intent.mode_action != "start":
        return None
    mode = (intent.fields or {}).get("mode") or intent.requested_mode or intent.domain
    resolved = DOMAIN_TO_MODE.get(mode)
    if not resolved:
        return None
    return {"action": "start", "mode": resolved}


def fallback_from_local_parsers(text: str, context: Optional[Dict[str, Any]] = None) -> NluIntent:
    """GPT 실패 시 값을 임의 생성하지 않는다. 같은 서버 검증을 다시 통과한다."""
    from backend.app.services.bot_query import looks_like_query_read

    context = context or {}
    command = parse_mode_command(text)
    if command and command.get("action") == "help":
        return enforce_nlu_policy(
            NluIntent(action=ACTION_SHOW_HELP, target=TARGET_NONE, fields={"topic": "all"}, confidence=1.0, source="fallback"),
            context,
        )
    if command and command.get("action") == "end":
        return NluIntent(mode_action="end", action=ACTION_CANCEL, confidence=1.0, source="fallback")
    if command and command.get("action") == "status":
        return NluIntent(mode_action="status", action=ACTION_UNKNOWN, confidence=1.0, source="fallback")
    if command and command.get("action") == "start":
        domain = MODE_TO_DOMAIN.get(command["mode"], "none")
        return enforce_nlu_policy(
            NluIntent(
                domain=domain,
                action=ACTION_START_MODE,
                mode_action="start",
                requested_mode=domain if domain in REQUESTED_MODES else "none",
                target=TARGET_NONE,
                fields={"mode": domain} if domain in MODE_FIELDS else {},
                confidence=1.0,
                source="fallback",
            ),
            context,
        )

    pending_step = str(context.get("pending_step") or "")
    compact = re.sub(r"\s+", "", text or "")
    if looks_like_query_read(text) and not context.get("has_active_draft"):
        from backend.app.services.bot_query import infer_query_fallback

        inferred = infer_query_fallback(text, context)
        inferred.source = "fallback"
        return enforce_nlu_policy(inferred, context)
    if looks_like_query_read(text) and context.get("has_active_draft"):
        return NluIntent(
            action=ACTION_UNKNOWN,
            domain=MODE_TO_DOMAIN.get(context.get("mode"), "none"),
            confidence=0.4,
            source="fallback",
            clarification="조회모드에서 확인할 수 있어요. 현재 입력은 그대로 유지할까요?",
            clarification_reason="조회모드에서 확인할 수 있어요. 현재 입력은 그대로 유지할까요?",
        )

    if pending_step in {"qty", "수량"} or pending_step.endswith("qty"):
        qty = extract_bare_qty(text)
        if qty:
            return enforce_nlu_policy(
                NluIntent(
                    domain=MODE_TO_DOMAIN.get(context.get("mode"), DOMAIN_REPAIR),
                    action=ACTION_PROVIDE_FIELD,
                    target=TARGET_DRAFT,
                    fields={"qty": qty},
                    confidence=0.9,
                    source="fallback",
                ),
                context,
            )
    if pending_step in {"unit_price", "단가", "awaiting_price"} or "price" in pending_step:
        from backend.app.services.bot_intent import extract_korean_amount

        price = extract_korean_amount(text)
        if price:
            return enforce_nlu_policy(
                NluIntent(
                    domain=MODE_TO_DOMAIN.get(context.get("mode"), DOMAIN_JOURNAL),
                    action=ACTION_PROVIDE_FIELD,
                    target=TARGET_DRAFT,
                    fields={"unit_price": price, "amount_type": "unit"},
                    confidence=0.9,
                    source="fallback",
                ),
                context,
            )

    local = parse_bot_intent(text)
    if local.action == ACTION_CONFIRM:
        return NluIntent(action=ACTION_CONFIRM, confidence=1.0, source="fallback")
    if local.action == ACTION_CANCEL:
        return NluIntent(action=ACTION_CANCEL, confidence=1.0, source="fallback")
    if local.action == ACTION_UPDATE:
        use_last = bool(local.explicit_last_saved) or (
            local.target == TARGET_LAST_SAVED and not context.get("has_active_draft")
        )
        return enforce_nlu_policy(
            NluIntent(
                domain=local.domain or DOMAIN_REPAIR,
                action=ACTION_UPDATE if use_last else ACTION_PROVIDE_FIELD,
                target=TARGET_LAST_SAVED if use_last else TARGET_DRAFT,
                fields=dict(local.fields or {}),
                confidence=1.0,
                needs_confirmation=use_last,
                explicit_last_saved=bool(local.explicit_last_saved),
                source="fallback",
            ),
            context,
        )

    if context.get("mode") == MODE_JOURNAL:
        from backend.app.services.journal_adapter import extract_journal_fields_local

        jfields = extract_journal_fields_local(
            text,
            pending_step=pending_step,
            user_name=str(context.get("user_name") or ""),
        )
        if jfields and context.get("has_active_draft"):
            return enforce_nlu_policy(
                NluIntent(
                    domain=DOMAIN_JOURNAL,
                    action=ACTION_PROVIDE_FIELD,
                    target=TARGET_DRAFT,
                    fields=jfields,
                    confidence=0.85,
                    source="fallback",
                ),
                context,
            )
        if jfields.get("vendor") and jfields.get("work_type") and (
            jfields.get("unit_price") or jfields.get("total_amount")
        ):
            return enforce_nlu_policy(
                NluIntent(domain=DOMAIN_JOURNAL, action=ACTION_CREATE, fields=jfields, confidence=0.8, source="fallback"),
                context,
            )
        if jfields:
            return enforce_nlu_policy(
                NluIntent(domain=DOMAIN_JOURNAL, action=ACTION_CREATE, fields=jfields, confidence=0.55, source="fallback"),
                context,
            )
        return NluIntent(
            domain=DOMAIN_JOURNAL,
            action=ACTION_UNKNOWN,
            confidence=0.0,
            source="fallback",
            clarification="업체, 작업, 단가를 다시 알려주세요.",
            clarification_reason="업체, 작업, 단가를 다시 알려주세요.",
        )

    if compact in {"수선"}:
        return NluIntent(
            action=ACTION_UNKNOWN,
            confidence=0.0,
            source="fallback",
            clarification="수선모드를 시작할까요, 아니면 수선일지를 조회할까요?",
            clarification_reason="수선모드를 시작할까요, 아니면 수선일지를 조회할까요?",
        )

    from backend.app.services.repair_bot import extract_price, extract_qty, parse_repair_text

    if context.get("has_active_draft") and pending_step in {"qty", "수량"}:
        qty = extract_qty(text) or extract_bare_qty(text)
        if qty:
            return enforce_nlu_policy(
                NluIntent(
                    domain=DOMAIN_REPAIR,
                    action=ACTION_PROVIDE_FIELD,
                    target=TARGET_DRAFT,
                    fields={"qty": qty},
                    confidence=1.0,
                    source="fallback",
                ),
                context,
            )
    parsed = parse_repair_text(text)
    fields: Dict[str, Any] = {}
    if parsed.get("price") is not None:
        fields["unit_price"] = parsed["price"]
    if parsed.get("qty"):
        fields["qty"] = parsed["qty"]
    if parsed.get("work"):
        work_name = parsed["work"]
        if isinstance(work_name, dict):
            work_name = work_name.get("작업명")
        if work_name and str(work_name) not in {"구멍 수선", "구멍수선"} and compact != "수선":
            fields["work_type"] = work_name
    if parsed.get("defect"):
        defect = parsed["defect"]
        defect_name = defect.get("불량명") if isinstance(defect, dict) else defect
        if compact != "수선" and defect_name:
            fields["defect"] = defect_name
    if fields and context.get("has_active_draft"):
        return enforce_nlu_policy(
            NluIntent(
                domain=DOMAIN_REPAIR,
                action=ACTION_PROVIDE_FIELD,
                target=TARGET_DRAFT,
                fields=fields,
                confidence=1.0,
                source="fallback",
            ),
            context,
        )
    if fields:
        return enforce_nlu_policy(
            NluIntent(domain=DOMAIN_REPAIR, action=ACTION_CREATE, fields=fields, confidence=0.7, source="fallback"),
            context,
        )
    ask = "지금 진행할 내용을 한 가지만 알려주세요."
    if pending_step in {"qty", "수량"}:
        ask = "수량을 숫자로 알려주세요. 예: 1"
    elif pending_step in {"unit_price", "단가", "awaiting_price"}:
        ask = "단가를 알려주세요. 예: 3000원"
    elif context.get("mode") == MODE_REPAIR:
        ask = "수선 작업이나 수량을 알려주세요."
    return NluIntent(action=ACTION_UNKNOWN, confidence=0.0, source="fallback", clarification=ask, clarification_reason=ask)


def render_readonly_nlu(intent: Optional[NluIntent], text: str = "") -> Optional[str]:
    """도움말·가격표. 조회 문장을 가격표로 바꾸지 않는다."""
    if not intent:
        return None
    from backend.app.services.bot_query import looks_like_query_read, should_skip_readonly

    if should_skip_readonly(text, intent):
        return None
    if intent.action == ACTION_SHOW_HELP:
        from backend.app.services.bot_mode import mode_feature_guide

        return mode_feature_guide()
    if intent.action == ACTION_QUERY_CATALOG and intent.entity in {"work_log", "repair_log"}:
        return None
    if intent.action == ACTION_QUERY_CATALOG:
        topic = (intent.fields or {}).get("topic") or "repair_work_prices"
        if topic in {"repair_work_prices", "repair", "repair_price"} or intent.entity == "repair_price":
            if looks_like_query_read(text) and any(k in re.sub(r"\s+", "", text or "") for k in ("몇건", "목록", "일지", "업체")):
                return None
            from backend.app.services.repair_bot import format_work_cost_list

            return format_work_cost_list()
        if topic in {"all", "journal", "query"}:
            from backend.app.services.bot_mode import mode_feature_guide

            return mode_feature_guide()
    return None


async def _complete_chat(messages: List[Dict[str, str]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("nlu_no_key")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=NLU_MODEL,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "bot_nlu_intent",
                "strict": True,
                "schema": NLU_JSON_SCHEMA,
            },
        },
        timeout=NLU_TIMEOUT_SEC,
    )
    return (response.choices[0].message.content or "").strip()


async def interpret_user_text(text: str, context: Dict[str, Any]) -> NluIntent:
    payload = gpt_payload(context)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    content = await _complete_chat(messages)
    parsed = json.loads(content)
    intent = parse_nlu_payload(parsed, context)
    return enforce_nlu_policy(intent, context)


async def interpret_or_fallback(
    user_id: str,
    channel_id: Optional[str],
    text: str,
    context: Optional[Dict[str, Any]] = None,
) -> NluIntent:
    ctx = context or collect_nlu_context(user_id, channel_id, text)
    if nlu_disabled():
        return fallback_from_local_parsers(text, ctx)
    try:
        return await interpret_user_text(text, ctx)
    except Exception as exc:
        logger.warning("nlu_fallback reason=%s", type(exc).__name__)
        return fallback_from_local_parsers(text, ctx)
