"""공통 봇 대화 intent. 문장별 if/elif가 아니라 action·target·fields로 본다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

ACTION_NONE = "none"
ACTION_UPDATE = "update"
ACTION_CONFIRM = "confirm"
ACTION_CANCEL = "cancel"

TARGET_NONE = "none"
TARGET_LAST_SAVED = "last_saved"

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
LAST_SAVED_HINTS = ("직전", "방금", "아까", "저장한")
CORRECTION_MARKERS = ("아니고", "말고")

FIELD_KEYS = ("unit_price", "qty", "defect", "work_type", "remark", "vendor", "product")


@dataclass
class BotIntent:
    action: str = ACTION_NONE
    target: str = TARGET_NONE
    fields: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "").strip())


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
    if qty:
        fields["qty"] = qty
    if parsed.get("defect"):
        fields["defect"] = parsed["defect"]
    if parsed.get("work"):
        fields["work_type"] = parsed["work"]
    if corr and "defect" not in fields and "work_type" not in fields and amount is None and not qty:
        leftover = re.sub(r"(원|건|개|장|벌)$", "", focus).strip()
        leftover = re.sub(r"^\d+\s*", "", leftover).strip()
        if leftover and leftover not in UPDATE_VERBS:
            fields["defect"] = leftover
    return {k: v for k, v in fields.items() if v not in (None, "")}


def parse_bot_intent(text: str) -> BotIntent:
    from backend.app.services.repair_bot import CANCEL_RE, YES_RE

    raw = (text or "").strip()
    if not raw:
        return BotIntent(raw=raw)
    if YES_RE.match(raw):
        return BotIntent(action=ACTION_CONFIRM, raw=raw)
    if CANCEL_RE.match(raw):
        return BotIntent(action=ACTION_CANCEL, raw=raw)

    norm = _norm(raw)
    fields = extract_update_fields(raw)
    has_synonym = any(s in norm for s in UPDATE_SYNONYMS)
    has_verb = any(v in norm for v in UPDATE_VERBS)
    has_last = any(h in norm for h in LAST_SAVED_HINTS)
    has_correction = any(m in raw for m in CORRECTION_MARKERS)

    if has_synonym or (has_verb and has_last) or (has_verb and fields) or (has_correction and fields):
        return BotIntent(
            action=ACTION_UPDATE,
            target=TARGET_LAST_SAVED,
            fields=fields,
            raw=raw,
        )
    return BotIntent(fields=fields, raw=raw)
