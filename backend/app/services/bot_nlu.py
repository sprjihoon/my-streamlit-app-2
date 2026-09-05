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
    ACTION_CONFIRM,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_NONE,
    ACTION_PROVIDE_FIELD,
    ACTION_QUERY_CATALOG,
    ACTION_SHOW_HELP,
    ACTION_START_MODE,
    ACTION_UNKNOWN,
    ACTION_UPDATE,
    AMOUNT_TYPES,
    DOMAIN_JOURNAL,
    DOMAIN_REPAIR,
    JOURNAL_ALLOWED_FIELDS,
    TARGET_DRAFT,
    TARGET_LAST_SAVED,
    TARGET_NONE,
    TARGET_SELECTED_RECORD,
    BotIntent,
    allowed_fields_only,
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
from backend.app.services.conversation_state import get_conversation_manager

logger = logging.getLogger(__name__)

NLU_MODEL = "gpt-4o-mini"
NLU_TIMEOUT_SEC = 8.0
LOW_CONFIDENCE = 0.6
LAST_SAVED_CONFIDENCE = 0.8
LAST_REPLY_MAX = 500
NLU_DISABLE_ENV = "BOT_NLU_DISABLE"

DOMAINS = frozenset(("repair", "journal", "query", "none"))
ACTIONS = frozenset(
    (
        "start_mode",
        "create",
        "provide_field",
        "update",
        "delete",
        "confirm",
        "cancel",
        "show_help",
        "query_catalog",
        "unknown",
    )
)
TARGETS = frozenset(("draft", "last_saved", "selected_record", "none"))
MODE_FIELDS = frozenset(("journal", "repair", "query"))
TOPIC_FIELDS = frozenset(("all", "journal", "repair", "query", "repair_work_prices"))
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
    "unit_price", "remark", "date", "total_amount", "amount_type",
)
RECENT_TURN_MAX = 4
RECENT_TURN_CHARS = 160
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

NLU_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "domain",
        "action",
        "target",
        "fields",
        "entries",
        "confidence",
        "needs_confirmation",
        "clarification",
    ],
    "properties": {
        "domain": {"type": "string", "enum": ["repair", "journal", "query", "none"]},
        "action": {
            "type": "string",
            "enum": [
                "start_mode",
                "create",
                "provide_field",
                "update",
                "delete",
                "confirm",
                "cancel",
                "show_help",
                "query_catalog",
                "unknown",
            ],
        },
        "target": {"type": "string", "enum": ["draft", "last_saved", "selected_record", "none"]},
        "fields": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "unit_price",
                "qty",
                "defect",
                "work_type",
                "remark",
                "vendor",
                "product",
                "option",
                "mode",
                "topic",
                "date",
                "total_amount",
                "amount_type",
            ],
            "properties": {
                "unit_price": {"type": ["number", "null"]},
                "qty": {"type": ["number", "null"]},
                "defect": {"type": ["string", "null"]},
                "work_type": {"type": ["string", "null"]},
                "remark": {"type": ["string", "null"]},
                "vendor": {"type": ["string", "null"]},
                "product": {"type": ["string", "null"]},
                "option": {"type": ["string", "null"]},
                "date": {"type": ["string", "null"]},
                "total_amount": {"type": ["number", "null"]},
                "amount_type": {
                    "anyOf": [
                        {"type": "string", "enum": ["unit", "total", "unknown"]},
                        {"type": "null"},
                    ]
                },
                "mode": {
                    "anyOf": [
                        {"type": "string", "enum": ["journal", "repair", "query"]},
                        {"type": "null"},
                    ]
                },
                "topic": {
                    "anyOf": [
                        {
                            "type": "string",
                            "enum": ["all", "journal", "repair", "query", "repair_work_prices"],
                        },
                        {"type": "null"},
                    ]
                },
            },
        },
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "vendor",
                    "work_type",
                    "unit_price",
                    "qty",
                    "date",
                    "remark",
                    "total_amount",
                    "amount_type",
                ],
                "properties": {
                    "vendor": {"type": ["string", "null"]},
                    "work_type": {"type": ["string", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "qty": {"type": ["number", "null"]},
                    "date": {"type": ["string", "null"]},
                    "remark": {"type": ["string", "null"]},
                    "total_amount": {"type": ["number", "null"]},
                    "amount_type": {
                        "anyOf": [
                            {"type": "string", "enum": ["unit", "total", "unknown"]},
                            {"type": "null"},
                        ]
                    },
                },
            },
        },
        "confidence": {"type": "number"},
        "needs_confirmation": {"type": "boolean"},
        "clarification": {"type": ["string", "null"]},
    },
}

SYSTEM_PROMPT = """당신은 물류·수선 업무봇의 의도 분류기입니다.
사용자 문장을 허용된 JSON만으로 구조화하세요. DB 쓰기, SQL, 권한, 기록 ID 확정은 하지 마세요.
환경변수, API 키, 비밀번호, 파일 경로, 전체 DB는 요청·응답에 넣지 마세요.

입력 컨텍스트 키만 사용하세요: mode, pending_step, missing_fields, draft_fields, has_last_saved, last_question, last_assistant_reply, recent_turns, user_message.

규칙:
1. action/target/fields/domain은 schema enum만 사용합니다.
2. 작성 중 draft가 있으면 기본 target은 draft입니다.
3. 저장이 끝난 직전 기록을 명시적으로 가리킬 때만 target=last_saved 입니다.
4. last_saved 수정은 needs_confirmation=true 입니다. option은 last_saved에 넣지 마세요.
5. 모드를 시작하려는 의미면 action=start_mode 이고 fields.mode 또는 domain에 journal/repair/query를 넣습니다.
6. 지금 물어본 칸에 값을 채우는 말이면 action=provide_field 입니다. 추출한 값만 fields에 넣으세요.
7. 새 수선/일지를 시작하는 말이면 action=create 입니다.
8. 확정은 confirm, 포기는 cancel 입니다.
9. 봇이 무엇을 할 수 있는지 묻는 의미면 action=show_help, fields.topic=all 입니다. 모드를 고르라고 되묻지 마세요.
10. 수선 작업 종류·가격 목록을 보려는 의미면 action=query_catalog, fields.topic=repair_work_prices 입니다.
11. last_question·last_assistant_reply·recent_turns를 보고 후속 질문을 같은 주제로 연결하세요.
12. show_help와 query_catalog는 읽기 전용입니다. 기본상태에서도 이 action을 고르세요.
13. 한 문장에 업체·제품·옵션·작업·가격·수량이 있으면 있는 값만 fields에 모두 넣습니다.
14. 일지모드에서 여러 작업을 한 문장에 나열하면 entries에 항목별로 넣습니다.
15. 금액이 개당이면 amount_type=unit, 총액이면 total, 불명확하면 unknown 입니다.
16. 직전 저장 기록을 지우려면 action=delete, target=last_saved 입니다.
17. 자신이 없거나 대상이 섞이면 action=unknown 이고 clarification에 질문 하나만 넣습니다.
18. 아래는 문장 사전이 아니라 의미 예시입니다. 같은 뜻의 다른 말도 같은 action으로 접으세요.

의미 예시:
- 수선 업무를 시작함 → start_mode / repair
- 작업일지를 시작함 → start_mode / journal
- 조회만 함 → start_mode / query
- 기능을 물어봄 → show_help / topic=all
- 수선 작업과 가격을 물어봄 → query_catalog / topic=repair_work_prices
- 직전 안내 뒤 가격만 이어서 물어봄 → query_catalog / topic=repair_work_prices
- 지금 묻는 수량에 1을 답함 → provide_field / qty=1
- 방금 저장이 끝난 기록을 고침 → update / last_saved
- 방금 저장한 기록을 지움 → delete / last_saved
- 가격을 2000원으로 바꿈 → unit_price=2000
- 총액으로 말했음 → amount_type=total
- 불량/작업을 다른 값으로 정정함 → 해당 field만 채움
"""


@dataclass
class NluIntent:
    domain: str = "none"
    action: str = ACTION_UNKNOWN
    target: str = TARGET_NONE
    fields: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_confirmation: bool = False
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
        content = sanitize_last_reply(item.get("content") or "")[:RECENT_TURN_CHARS]
        if not content:
            continue
        turns.append({"role": role, "content": content})
    return turns


def collect_nlu_context(user_id: str, channel_id: Optional[str], text: str) -> Dict[str, Any]:
    """GPT에 넣을 최소 컨텍스트. 비밀·파일경로·전체 DB는 넣지 않는다."""
    mode = get_mode(user_id, channel_id)
    state = get_conversation_manager().get_state(user_id, channel_id) or {}
    expired = bool(state.get("expired"))
    pending = {} if expired else (state.get("pending_data") or {})
    missing = [] if expired else [str(x) for x in (state.get("missing") or []) if x]
    pending_step = missing[0] if missing else ""
    entry_type = pending.get("entry_type")
    journal_draft = entry_type == "journal"
    has_active_draft = ((not expired) and entry_type == "repair") or journal_draft
    draft_fields: Dict[str, Any] = {}
    if has_active_draft:
        for key in SAFE_DRAFT_KEYS:
            value = pending.get(key)
            if value not in (None, ""):
                draft_fields[key] = value
    has_last_saved = False
    try:
        from backend.app.services.repair_edit import get_last_saved_id

        has_last_saved = get_last_saved_id(user_id, channel_id) is not None
    except Exception:
        has_last_saved = False
    if not has_last_saved:
        try:
            from backend.app.services.journal_edit import get_last_saved_id as get_journal_last_saved_id

            has_last_saved = get_journal_last_saved_id(user_id, channel_id) is not None
        except Exception:
            pass
    last_question = "" if expired else sanitize_last_reply(state.get("last_question") or "")
    return {
        "mode": mode,
        "pending_step": pending_step,
        "missing_fields": missing,
        "draft_fields": draft_fields,
        "has_last_saved": bool(has_last_saved),
        "has_active_draft": has_active_draft,
        "expired_repair_draft": expired and (state.get("pending_data") or {}).get("entry_type") == "repair",
        "last_question": last_question,
        "last_assistant_reply": last_assistant_reply(user_id, channel_id),
        "recent_turns": recent_turns(user_id, channel_id),
        "user_message": (text or "").strip(),
    }


def gpt_payload(context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mode": context.get("mode") or "idle",
        "pending_step": context.get("pending_step") or "",
        "missing_fields": list(context.get("missing_fields") or []),
        "draft_fields": dict(context.get("draft_fields") or {}),
        "has_last_saved": bool(context.get("has_last_saved")),
        "last_question": context.get("last_question") or "",
        "last_assistant_reply": context.get("last_assistant_reply") or "",
        "recent_turns": list(context.get("recent_turns") or []),
        "user_message": context.get("user_message") or "",
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


def clean_nlu_fields(fields: Optional[Dict[str, Any]], *, action: str) -> Dict[str, Any]:
    raw = fields or {}
    cleaned: Dict[str, Any] = {}
    if action == ACTION_START_MODE:
        mode = raw.get("mode")
        if mode in MODE_FIELDS:
            cleaned["mode"] = mode
    if action in (ACTION_SHOW_HELP, ACTION_QUERY_CATALOG):
        topic = raw.get("topic")
        if topic in TOPIC_FIELDS:
            cleaned["topic"] = topic
    from backend.app.services.bot_intent import DRAFT_ALLOWED_FIELDS

    for key in DRAFT_ALLOWED_FIELDS | JOURNAL_ALLOWED_FIELDS:
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
        if text:
            cleaned[key] = text
    return cleaned


def _clean_entries(raw_entries: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_entries, list):
        return []
    entries: List[Dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        cleaned = journal_fields_only(clean_nlu_fields(item, action=ACTION_CREATE))
        if cleaned:
            entries.append(cleaned)
    return entries


def parse_nlu_payload(raw: Any) -> NluIntent:
    if not isinstance(raw, dict):
        raise ValueError("nlu_not_object")
    if raw.get("trusted_source") is not None:
        raise ValueError("nlu_trusted_source_rejected")
    domain = raw.get("domain") if raw.get("domain") in DOMAINS else "none"
    action = raw.get("action") if raw.get("action") in ACTIONS else ACTION_UNKNOWN
    target = raw.get("target") if raw.get("target") in TARGETS else TARGET_NONE
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    fields = clean_nlu_fields(raw.get("fields") if isinstance(raw.get("fields"), dict) else {}, action=action)
    entries = _clean_entries(raw.get("entries"))
    clarification = raw.get("clarification")
    if clarification is not None:
        clarification = str(clarification).strip() or None
    needs = bool(raw.get("needs_confirmation"))
    return NluIntent(
        domain=domain,
        action=action,
        target=target,
        fields=fields,
        confidence=confidence,
        needs_confirmation=needs,
        clarification=clarification,
        source="nlu",
        entries=entries,
    )


def enforce_nlu_policy(intent: NluIntent, context: Dict[str, Any]) -> NluIntent:
    """서버가 GPT 결과를 다시 검증한다. 쓰기는 여기서 하지 않는다."""
    has_draft = bool(context.get("has_active_draft"))
    if intent.action == ACTION_SHOW_HELP:
        intent.target = TARGET_NONE
        intent.needs_confirmation = False
        intent.fields = {"topic": intent.fields.get("topic") or "all"}
        return intent
    if intent.action == ACTION_QUERY_CATALOG:
        topic = intent.fields.get("topic") or "repair_work_prices"
        if topic not in TOPIC_FIELDS:
            topic = "repair_work_prices"
        intent.target = TARGET_NONE
        intent.needs_confirmation = False
        intent.fields = {"topic": topic}
        return intent
    if intent.action == ACTION_START_MODE:
        mode = intent.fields.get("mode") or (intent.domain if intent.domain in MODE_FIELDS else None)
        if mode in MODE_FIELDS:
            intent.domain = mode
            intent.fields = {"mode": mode}
            intent.target = TARGET_NONE
            intent.needs_confirmation = False
        else:
            intent.action = ACTION_UNKNOWN
            intent.clarification = intent.clarification or "어떤 모드를 시작할까요? 일지, 수선, 조회 중에서 골라주세요."
        return intent

    if intent.action in (ACTION_CONFIRM, ACTION_CANCEL):
        intent.target = TARGET_NONE
        intent.fields = {}
        intent.needs_confirmation = False
        return intent

    if intent.action == ACTION_DELETE:
        if has_draft and intent.target != TARGET_LAST_SAVED:
            intent.action = ACTION_UNKNOWN
            intent.target = TARGET_DRAFT
            intent.needs_confirmation = False
            intent.clarification = intent.clarification or (
                "작성 중인 내용을 취소할까요, 아니면 직전 저장 기록을 지울까요?"
            )
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
    }:
        intent.action = ACTION_UNKNOWN
        intent.target = TARGET_NONE
        intent.needs_confirmation = False
        intent.clarification = intent.clarification or (
            "한 가지만 확인할게요. 지금 작성 중인 내용을 이어서 할까요, 아니면 직전 저장 기록을 고칠까요?"
        )
        return intent

    if intent.action in (ACTION_UPDATE, ACTION_PROVIDE_FIELD, ACTION_CREATE):
        if has_draft:
            if intent.target == TARGET_LAST_SAVED:
                if intent.confidence >= LAST_SAVED_CONFIDENCE and intent.action == ACTION_UPDATE:
                    intent.explicit_last_saved = True
                    intent.needs_confirmation = True
                else:
                    intent.action = ACTION_UNKNOWN
                    intent.target = TARGET_DRAFT
                    intent.clarification = intent.clarification or (
                        "작성 중인 수선을 고칠까요, 아니면 직전 저장 기록을 고칠까요?"
                    )
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
    }:
        action = ACTION_NONE
    from backend.app.services.bot_intent import draft_fields_only

    target = (
        intent.target
        if intent.target in {TARGET_DRAFT, TARGET_LAST_SAVED, TARGET_SELECTED_RECORD, TARGET_NONE}
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
        missing_fields=[] if fields else (["fields"] if action in (ACTION_UPDATE, ACTION_DELETE) else []),
        confidence=intent.confidence,
        explicit_last_saved=bool(intent.explicit_last_saved),
        clarification=intent.clarification,
        entries=list(intent.entries or []),
    )


def nlu_to_mode_command(intent: Optional[NluIntent]) -> Optional[dict]:
    if not intent or intent.action != ACTION_START_MODE:
        return None
    mode = (intent.fields or {}).get("mode") or intent.domain
    resolved = DOMAIN_TO_MODE.get(mode)
    if not resolved:
        return None
    return {"action": "start", "mode": resolved}


def fallback_from_local_parsers(text: str, context: Optional[Dict[str, Any]] = None) -> NluIntent:
    """GPT 실패 시 기존 로컬 파서만 사용한다. 새 단어 정규식은 추가하지 않는다."""
    context = context or {}
    command = parse_mode_command(text)
    if command and command.get("action") == "help":
        return NluIntent(
            action=ACTION_SHOW_HELP,
            target=TARGET_NONE,
            fields={"topic": "all"},
            confidence=1.0,
            source="fallback",
        )
    if command and command.get("action") == "start":
        domain = MODE_TO_DOMAIN.get(command["mode"], "none")
        return NluIntent(
            domain=domain,
            action=ACTION_START_MODE,
            target=TARGET_NONE,
            fields={"mode": domain} if domain in MODE_FIELDS else {},
            confidence=1.0,
            source="fallback",
        )
    local = parse_bot_intent(text)
    if local.action == ACTION_CONFIRM:
        return NluIntent(action=ACTION_CONFIRM, confidence=1.0, source="fallback")
    if local.action == ACTION_CANCEL:
        return NluIntent(action=ACTION_CANCEL, confidence=1.0, source="fallback")
    if local.action == ACTION_UPDATE:
        return NluIntent(
            domain=local.domain or DOMAIN_REPAIR,
            action=ACTION_UPDATE,
            target=TARGET_LAST_SAVED if local.target == TARGET_LAST_SAVED else TARGET_DRAFT,
            fields=dict(local.fields or {}),
            confidence=1.0,
            needs_confirmation=True,
            explicit_last_saved=bool(local.explicit_last_saved),
            source="fallback",
        )

    if context.get("mode") == MODE_JOURNAL:
        from backend.app.services.journal_adapter import extract_journal_fields_local

        jfields = extract_journal_fields_local(text)
        if jfields and context.get("has_active_draft"):
            return NluIntent(
                domain=DOMAIN_JOURNAL,
                action=ACTION_PROVIDE_FIELD,
                target=TARGET_DRAFT,
                fields=jfields,
                confidence=0.85,
                source="fallback",
            )
        if jfields.get("vendor") and jfields.get("work_type") and (
            jfields.get("unit_price") or jfields.get("total_amount")
        ):
            return NluIntent(
                domain=DOMAIN_JOURNAL,
                action=ACTION_CREATE,
                fields=jfields,
                confidence=0.8,
                source="fallback",
            )
        if jfields:
            return NluIntent(
                domain=DOMAIN_JOURNAL,
                action=ACTION_CREATE,
                fields=jfields,
                confidence=0.55,
                source="fallback",
            )
        return NluIntent(
            domain=DOMAIN_JOURNAL,
            action=ACTION_UNKNOWN,
            confidence=0.0,
            source="fallback",
            clarification="업체, 작업, 단가를 다시 알려주세요.",
        )

    from backend.app.services.repair_bot import parse_repair_text

    parsed = parse_repair_text(text)
    fields: Dict[str, Any] = {}
    if parsed.get("price") is not None:
        fields["unit_price"] = parsed["price"]
    if parsed.get("qty"):
        fields["qty"] = parsed["qty"]
    if parsed.get("work"):
        fields["work_type"] = parsed["work"]
    if parsed.get("defect"):
        fields["defect"] = parsed["defect"]
    if fields and context.get("has_active_draft"):
        return NluIntent(
            domain=DOMAIN_REPAIR,
            action=ACTION_PROVIDE_FIELD,
            target=TARGET_DRAFT,
            fields=fields,
            confidence=1.0,
            source="fallback",
        )
    if fields:
        return NluIntent(
            domain=DOMAIN_REPAIR,
            action=ACTION_CREATE,
            fields=fields,
            confidence=0.7,
            source="fallback",
        )
    return NluIntent(action=ACTION_UNKNOWN, confidence=0.0, source="fallback")


def render_readonly_nlu(intent: Optional[NluIntent]) -> Optional[str]:
    """도움말·카탈로그는 DB에 쓰지 않고 기존 안내 함수만 호출한다."""
    if not intent:
        return None
    if intent.action == ACTION_SHOW_HELP:
        from backend.app.services.bot_mode import mode_feature_guide

        return mode_feature_guide()
    if intent.action == ACTION_QUERY_CATALOG:
        topic = (intent.fields or {}).get("topic") or "repair_work_prices"
        if topic in {"repair_work_prices", "repair"}:
            from backend.app.services.repair_bot import format_work_cost_list

            return format_work_cost_list()
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
    intent = parse_nlu_payload(parsed)
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
