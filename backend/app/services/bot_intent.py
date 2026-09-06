"""공통 봇 대화 intent. 문장별 if/elif가 아니라 action·target·fields로 본다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ACTION_NONE = "none"
ACTION_UPDATE = "update"
ACTION_CONFIRM = "confirm"
ACTION_CANCEL = "cancel"
ACTION_PROVIDE_FIELD = "provide_field"
ACTION_CREATE = "create"
ACTION_START_MODE = "start_mode"
ACTION_SHOW_HELP = "show_help"
ACTION_QUERY_CATALOG = "query_catalog"
ACTION_DELETE = "delete"
ACTION_UNKNOWN = "unknown"
ACTION_LIST = "list"
ACTION_LATEST = "latest"
ACTION_COUNT = "count"
ACTION_STATS = "stats"
ACTION_GROUP = "group"
ACTION_LOOKUP_PRICE = "lookup_price"
ACTION_HELP = "help"
ACTION_CLARIFY = "clarify"

READ_ACTIONS = frozenset(
    (ACTION_LIST, ACTION_LATEST, ACTION_COUNT, ACTION_STATS, ACTION_GROUP, ACTION_LOOKUP_PRICE)
)

TARGET_NONE = "none"
TARGET_LAST_SAVED = "last_saved"
TARGET_DRAFT = "draft"
TARGET_SELECTED_RECORD = "selected_record"

DOMAIN_REPAIR = "repair"
DOMAIN_JOURNAL = "journal"

_SPACE = re.compile(r"\s+")
_CHEON_RE = re.compile(r"(\d+(?:\.\d+)?)\s*천\s*원?")
_CORRECTION_RE = re.compile(r"(?:아니고|말고)\s*(.+)$")

UPDATE_SYNONYMS = (
    "직전내용수정",
    "직전수정",
    "직전거수정",
    "방금거수정",
    "방금내용수정",
    "방금수정",
    "아까저장한거바꿔",
    "아까저장한거바꾸",
    "아까저장한거수정",
    "방금저장한거바꿔",
    "방금저장한거바꾸",
    "방금저장한거수정",
    "아까저장한거변경",
)

UPDATE_VERBS = ("수정", "바꿔", "바꾸", "변경", "고쳐")
UPDATE_VERBS_FREE = ("바꿔", "변경", "고쳐")
LAST_SAVED_HINTS = ("직전", "방금", "아까", "저장한", "저장된")
CORRECTION_MARKERS = ("아니고", "말고")
EXPLICIT_RECORD_MARKERS = ("저장한", "저장된", "내용", "일지", "항목")
EXPLICIT_VERBS = ("수정", "변경")
FIELD_HINTS = ("금액", "가격", "단가", "건수", "수량", "불량", "작업", "업체", "제품", "비고", "메모")
_REMARK_LEAD_RE = re.compile(r"(?:비고|메모)\s*(?:에|은|는|를|을|:)?\s*")
_REMARK_LEAD_VERB_RE = re.compile(
    r"^(?:추가(?:해(?:요|줘|주세요)?)?|남겨(?:요|줘|주세요)?|넣(?:어(?:요|줘|주세요)?)?)\s*"
)
_REMARK_TRAIL_RE = re.compile(
    r"(?:으로|로)?\s*(?:바꿔(?:요|줘|주세요)?|바꾸(?:세요)?|변경(?:해(?:요|줘|주세요)?)?|"
    r"고쳐(?:요|줘|주세요)?|수정(?:해(?:요|줘|주세요)?)?|"
    r"추가(?:해(?:요|줘|주세요)?)?|남겨(?:요|줘|주세요)?|넣(?:어(?:요|줘|주세요)?)?)\s*$"
)
_REMARK_SAID_RE = re.compile(r"(.+?)\s*(?:이라고|라고)\s*(?:메모|비고)\s*$")
_REMARK_CLAUSE_RE = re.compile(r"(?:비고|메모)\s*(?:에|은|는|를|을|:)?\s*.+$")
_CREATE_FIELD_KEYS = frozenset(("unit_price", "qty", "work_type", "defect", "vendor", "product"))
_MOD_COMMAND_RE = re.compile(
    r"(?:내용|직전|방금|아까|일지|금액|가격|건수|거|것|으로|로|를|을|만|해)수정"
    r"|(?:^|[^가-힣])수정"
)
_VALUE_TO_CHANGE_RE = re.compile(
    r"(?:\d+(?:\.\d+)?천원?|\d+(?:\.\d+)?만원?|(?:\d{1,3}(?:,\d{3})+|\d+)원|\d+(?:건|개|장|벌))"
    r"(?:으로|로)(?:바꿔|바꾸|변경|고쳐|수정)"
)
_ORDINAL_WORDS = {
    "첫번째": 1, "첫번": 1, "첫번째거": 1, "첫번째꺼": 1,
    "두번째": 2, "두번째거": 2, "두번째꺼": 2,
    "세번째": 3, "세번째거": 3, "세번째꺼": 3,
    "네번째": 4, "네번째거": 4,
    "다섯번째": 5, "다섯번째거": 5,
}
_ORDINAL_RE = re.compile(r"(?<!\d)([1-5])\s*(?:번(?:째)?|번째)")


def parse_result_index(text: str) -> Optional[int]:
    compact = _norm(text)
    for key, idx in _ORDINAL_WORDS.items():
        if key in compact:
            return idx
    match = _ORDINAL_RE.search(text or "")
    if match:
        return int(match.group(1))
    return None

ALLOWED_FIELDS = frozenset(
    ("unit_price", "qty", "defect", "work_type", "remark", "vendor", "product")
)
DRAFT_ALLOWED_FIELDS = ALLOWED_FIELDS | frozenset(("option",))
JOURNAL_ALLOWED_FIELDS = frozenset(
    ("vendor", "work_type", "unit_price", "qty", "date", "remark", "total_amount", "amount_type")
)
AMOUNT_TYPES = frozenset(("unit", "total", "unknown"))
FIELD_KEYS = tuple(ALLOWED_FIELDS)


@dataclass
class BotIntent:
    action: str = ACTION_NONE
    target: str = TARGET_NONE
    fields: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    domain: str = DOMAIN_REPAIR
    needs_confirmation: bool = False
    missing_fields: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    explicit_last_saved: bool = False
    clarification: Optional[str] = None
    entries: List[Dict[str, Any]] = field(default_factory=list)


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "").strip())


def _has_update_verb(norm: str) -> bool:
    """작업명에 붙은 수정·변경·바꾸기는 변경 동사로 보지 않는다."""
    if "바꾸기" in norm and "바꿔" not in norm:
        has_free = any(v in norm for v in ("변경", "고쳐"))
    else:
        has_free = any(v in norm for v in UPDATE_VERBS_FREE) or ("바꾸" in norm)
    if has_free:
        return True
    return bool(_MOD_COMMAND_RE.search(norm))


def _has_named_field(norm: str) -> bool:
    return any(h in norm for h in FIELD_HINTS)


def _has_value_to_change(norm: str) -> bool:
    return bool(_VALUE_TO_CHANGE_RE.search(norm))


def allowed_fields_only(fields: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {k: v for k, v in (fields or {}).items() if k in ALLOWED_FIELDS and v not in (None, "")}


def draft_fields_only(fields: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {k: v for k, v in (fields or {}).items() if k in DRAFT_ALLOWED_FIELDS and v not in (None, "")}


def journal_fields_only(fields: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if key not in JOURNAL_ALLOWED_FIELDS or value in (None, ""):
            continue
        if key == "amount_type":
            if value in AMOUNT_TYPES:
                out[key] = value
            continue
        out[key] = value
    return out


def rejected_field_names(fields: Optional[Dict[str, Any]]) -> List[str]:
    return [k for k in (fields or {}) if k not in ALLOWED_FIELDS]


def rejected_draft_field_names(fields: Optional[Dict[str, Any]]) -> List[str]:
    return [k for k in (fields or {}) if k not in DRAFT_ALLOWED_FIELDS]


def extract_bare_qty(text: str) -> Optional[int]:
    compact = _norm(text)
    compact = compact.replace("항목", "").replace("건수", "").replace("수량", "")
    if compact in {"1", "하나", "한개", "한건", "한"}:
        return 1
    m = re.fullmatch(r"(\d+)(?:건|개|장|벌)?", compact)
    if m:
        qty = int(m.group(1))
        return qty if qty > 0 else None
    return None


def extract_remark(text: str) -> Optional[str]:
    """비고/메모 표지가 있을 때만 값을 읽는다. 필수값이 아니다."""
    raw = (text or "").strip()
    if not raw:
        return None
    said = _REMARK_SAID_RE.search(raw)
    if said:
        value = said.group(1).strip(" ,./")
        return value[:200] if value else None
    lead = _REMARK_LEAD_RE.search(raw)
    if not lead:
        return None
    value = raw[lead.end():].strip()
    value = _REMARK_LEAD_VERB_RE.sub("", value)
    value = _REMARK_TRAIL_RE.sub("", value).strip(" ,./")
    if not value:
        return None
    return value[:200]


def strip_remark_clause(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = _REMARK_SAID_RE.sub("", raw)
    cleaned = _REMARK_CLAUSE_RE.sub("", cleaned)
    return cleaned.strip(" ,./")


def extract_korean_amount(text: str) -> Optional[int]:
    """저장용 extract_price는 그대로 두고, 수정 intent만 천 단위를 보완한다."""
    from backend.app.services.repair_bot import extract_price

    if not text:
        return None
    priced = extract_price(text)
    if priced is not None:
        return priced
    m = _CHEON_RE.search(text)
    if m:
        return int(float(m.group(1)) * 1000)
    return None


def extract_update_fields(text: str) -> Dict[str, Any]:
    from backend.app.services.repair_bot import extract_qty, parse_repair_text

    raw = (text or "").strip()
    focus = raw
    corr = _CORRECTION_RE.search(raw)
    if corr:
        focus = corr.group(1).strip() or raw

    parsed = parse_repair_text(focus)
    fields: Dict[str, Any] = {}
    amount = extract_korean_amount(focus) or extract_korean_amount(raw)
    if amount is not None:
        fields["unit_price"] = amount
    qty = parsed.get("qty") or extract_qty(focus)
    if not qty:
        qty = extract_bare_qty(focus)
    if qty:
        fields["qty"] = qty
    work = parsed.get("work")
    if work and _norm(str(work)) in {"항목", "수선항목"}:
        work = None
    if work:
        fields["work_type"] = work
    if parsed.get("defect"):
        fields["defect"] = parsed["defect"]
    if corr and "defect" not in fields and "work_type" not in fields and amount is None and not qty:
        leftover = re.sub(r"(원|건|개|장|벌)$", "", focus).strip()
        leftover = re.sub(r"^\d+\s*", "", leftover).strip()
        leftover = strip_remark_clause(leftover)
        if leftover and leftover not in UPDATE_VERBS:
            fields["defect"] = leftover
    remark = parsed.get("remark") or extract_remark(focus) or extract_remark(raw)
    if remark:
        fields["remark"] = remark
    return allowed_fields_only(fields)


def parse_bot_intent(text: str) -> BotIntent:
    from backend.app.services.repair_bot import CANCEL_RE, YES_RE

    raw = (text or "").strip()
    if not raw:
        return BotIntent(raw=raw)
    if YES_RE.match(raw):
        return BotIntent(action=ACTION_CONFIRM, raw=raw, confidence=1.0)
    if CANCEL_RE.match(raw):
        return BotIntent(action=ACTION_CANCEL, raw=raw, confidence=1.0)

    norm = _norm(raw)
    fields = extract_update_fields(raw)
    has_synonym = any(s in norm for s in UPDATE_SYNONYMS)
    has_verb = _has_update_verb(norm)
    has_last = any(h in norm for h in LAST_SAVED_HINTS)
    has_correction = any(m in raw for m in CORRECTION_MARKERS)
    has_field = _has_named_field(norm)
    has_value_change = _has_value_to_change(norm)
    explicit = has_synonym or (
        has_last
        and any(v in norm for v in EXPLICIT_VERBS)
        and any(m in norm for m in EXPLICIT_RECORD_MARKERS)
    )
    named_field_change = has_field and bool(fields) and (has_verb or has_value_change or "으로" in norm)
    remark_only = "remark" in fields and not (set(fields) & _CREATE_FIELD_KEYS)
    matched = (
        explicit
        or (has_last and bool(fields))
        or (has_verb and has_last)
        or (has_correction and bool(fields))
        or named_field_change
        or has_value_change
        or remark_only
    )
    if not matched:
        return BotIntent(fields=fields, raw=raw)

    missing = [] if fields else ["fields"]
    idx = parse_result_index(raw)
    target = TARGET_SELECTED_RECORD if idx else TARGET_LAST_SAVED
    return BotIntent(
        action=ACTION_UPDATE,
        target=target,
        fields=fields,
        raw=raw,
        domain=DOMAIN_REPAIR,
        needs_confirmation=True,
        missing_fields=missing,
        confidence=1.0,
        explicit_last_saved=explicit and idx is None,
    )
