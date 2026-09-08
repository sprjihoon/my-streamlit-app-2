"""
불량모드 봇 흐름
사진 버퍼(바코드/사진) → 바코드 조회 → 불량명 확인 → 저장.
수선모드와 달리 작업/비용 없음. 처리결과는 웹에서만 수동 입력.
repair_bot의 사진 인박스 인프라를 공유한다.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.api.repair_log import (
    _lookup_barcode,
    _resolve_vendor,
    save_image_bytes,
    ensure_repair_tables,
)
from backend.app.api.defect_log import ensure_defect_tables, insert_defect_log_record
from backend.app.services import repair_catalog
from backend.app.services.barcode_decode import looks_like_barcode
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.repair_bot import (
    PHOTO_RETRY_MSG,
    PHOTO_SET_HINT,
    BufferedPhoto,
    _assign_saved_photos,
    _classify_photos_safe,
    _positional_photo_slots,
    clear_photo_inbox,
)
from logic.db import get_connection

logger = logging.getLogger(__name__)

EXPIRED_DEFECT_MSG = "작성하던 불량이 만료됐어요. 다시 시작해주세요."
YES_RE = re.compile(r"^(네|넵|예|응|어|맞아|맞아요|그래|그래요|ㅇㅇ|ㅇㅋ|저장|저장해|좋아|ㅇ)$")
CANCEL_RE = re.compile(r"^(취소|그만|아니야|아니)$")
ASCII_BARCODE_RE = re.compile(r"^[A-Za-z0-9]{6,24}$")
QTY_RE = re.compile(r"(?:한\s*건)|(?:(\d+)\s*(?:건|개|장|벌))")
BARCODE_RETRY_RE = re.compile(r"다시\s*읽|다시읽|재인식|다시\s*봐")
COMMAND_HINTS = ("보여줘", "보여주", "리스트", "목록", "다시읽", "다시찍어", "알려줘", "알려주")


# ─────────────────────────────────────
# Conversation state helpers
# ─────────────────────────────────────

def _get_pending(user_id: str, channel_id: Optional[str] = None) -> Dict[str, Any]:
    state = get_conversation_manager().get_state(user_id, channel_id)
    if not state or state.get("expired"):
        return {}
    data = state.get("pending_data") or {}
    if data.get("entry_type") != "defect":
        return {}
    return data


def _set_pending(user_id: str, channel_id: str, data: Dict[str, Any], missing: List[str], question: str) -> None:
    data = {**data, "entry_type": "defect"}
    get_conversation_manager().set_state(
        user_id=user_id,
        channel_id=channel_id or "",
        pending_data=data,
        missing=missing,
        last_question=question,
    )


def _ask(user_id: str, channel_id: str, data: Dict[str, Any], missing: List[str], question: str) -> str:
    prev = (get_conversation_manager().get_state(user_id, channel_id) or {}).get("last_question")
    _set_pending(user_id, channel_id, data, missing, question)
    return "" if prev == question else question


def _clear_pending(user_id: str, channel_id: Optional[str] = None) -> None:
    get_conversation_manager().clear_state(user_id, channel_id)


def _consume_expired(user_id: str, channel_id: Optional[str] = None) -> bool:
    state = get_conversation_manager().get_state(user_id, channel_id)
    if not state or not state.get("expired"):
        return False
    if (state.get("pending_data") or {}).get("entry_type") != "defect":
        return False
    clear_photo_inbox(user_id, channel_id)
    _clear_pending(user_id, channel_id)
    return True


def pending_is_defect(user_id: str, channel_id: Optional[str] = None) -> bool:
    state = get_conversation_manager().get_state(user_id, channel_id)
    return bool(
        state
        and not state.get("expired")
        and (state.get("pending_data") or {}).get("entry_type") == "defect"
    )


# ─────────────────────────────────────
# Barcode / vendor helpers
# ─────────────────────────────────────

def _lookup(barcode: Optional[str]) -> Optional[dict]:
    if not barcode:
        return None
    ensure_repair_tables()
    with get_connection() as con:
        return _lookup_barcode(con, barcode)


def _attach_master(data: Dict[str, Any], found: dict) -> Dict[str, Any]:
    out = dict(data)
    out["barcode"] = found.get("바코드") or out.get("barcode")
    out["vendor"] = found.get("업체명") or out.get("vendor")
    out["product"] = found.get("제품명") or out.get("product")
    out["option"] = found.get("옵션") or out.get("option")
    return out


def _item_line(data: Dict[str, Any]) -> str:
    vendor = data.get("vendor") or "?"
    if vendor.startswith("자체제작_"):
        vendor = vendor.split("_", 1)[1]
    product = data.get("product") or "?"
    option = data.get("option")
    bits = [vendor, product]
    if option:
        bits.append(option)
    return " / ".join(bits)


def _is_manual_barcode(text: str) -> bool:
    s = re.sub(r"[\s\-]", "", text or "")
    if not ASCII_BARCODE_RE.fullmatch(s):
        return False
    return looks_like_barcode(s) or (s.isdigit() and 8 <= len(s) <= 14)


def _extract_barcode(text: str) -> Optional[str]:
    for token in re.findall(r"[A-Za-z0-9]{8,24}", text or ""):
        if looks_like_barcode(token) or (token.isdigit() and 8 <= len(token) <= 14):
            return token
    return None


def _extract_qty(text: str) -> Optional[int]:
    if not text:
        return None
    compact = re.sub(r"\s+", "", text.strip())
    if compact in {"하나", "한개", "한건"} or re.search(r"한\s*(?:건|개)", text):
        return 1
    m = QTY_RE.search(text)
    if m:
        n = int(m.group(1)) if m.group(1) else 1
        return n if n > 0 else None
    return None


def _is_command(text: str) -> bool:
    t = (text or "").replace(" ", "")
    return any(k in t for k in COMMAND_HINTS) or bool(BARCODE_RETRY_RE.search(text or ""))


# ─────────────────────────────────────
# Save
# ─────────────────────────────────────

def _save(data: Dict[str, Any], user_name: Optional[str]) -> Dict[str, Any]:
    return insert_defect_log_record(
        날짜=data.get("date") or datetime.now().strftime("%Y-%m-%d"),
        업체명=data.get("vendor"),
        제품명=data.get("product"),
        옵션=data.get("option"),
        바코드=data.get("barcode"),
        불량명=data.get("defect_name"),
        수량=int(data.get("qty") or 1),
        비고=data.get("remark"),
        작성자=user_name,
        출처="bot",
        before_image=data.get("before_image"),
        after_image=data.get("after_image"),
        extra_images=data.get("extra_images"),
    )


# ─────────────────────────────────────
# Conversation driver
# ─────────────────────────────────────

def _continue(data: Dict[str, Any], user_id: str, channel_id: str) -> str:
    """현재 데이터 상태를 기준으로 다음 질문 또는 저장 확인을 반환."""
    # 바코드로 업체/제품 조회
    if data.get("barcode") and not data.get("vendor"):
        found = _lookup(data["barcode"])
        if found:
            data = _attach_master(data, found)
        else:
            return _ask(
                user_id, channel_id, data, ["vendor"],
                f"등록 안 된 바코드예요 ({data['barcode']}). 업체명 알려주세요.",
            )

    if not data.get("vendor"):
        return _ask(user_id, channel_id, data, ["vendor"], "업체명 알려주세요.")
    if not data.get("product"):
        return _ask(user_id, channel_id, data, ["product"], "제품명 알려주세요.")

    if not data.get("defect_name"):
        return _ask(
            user_id, channel_id, data, ["defect_name"],
            f"{_item_line(data)} 맞아요. 불량명 알려주세요. (예: 구멍, 열펜, 올풀림)",
        )

    # 모든 필수값 확보 → 확인 요청
    item = _item_line(data)
    defect = data["defect_name"]
    qty = int(data.get("qty") or 1)
    remark = (data.get("remark") or "").strip()
    extra = f" (비고: {remark})" if remark else ""
    q = f"{item} / {defect} {qty}건{extra} 저장할까요?"
    data["awaiting_confirm"] = True
    return _ask(user_id, channel_id, data, [], q)


# ─────────────────────────────────────
# Text handler (봇 라우터가 호출)
# ─────────────────────────────────────

async def handle_user_text(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str] = None,
    nlu_intent=None,
) -> str:
    raw = (text or "").strip()

    if _consume_expired(user_id, channel_id):
        return EXPIRED_DEFECT_MSG

    data = _get_pending(user_id, channel_id)
    missing = (get_conversation_manager().get_state(user_id, channel_id) or {}).get("missing") or []
    data.setdefault("user_name", user_name)

    # 취소
    if CANCEL_RE.match(raw):
        if data:
            clear_photo_inbox(user_id, channel_id)
            _clear_pending(user_id, channel_id)
            return "🚫 불량 입력을 취소했어요."

    # 확인 대기 중 → 수량/yes/no 처리
    if data.get("awaiting_confirm"):
        qty = _extract_qty(raw)
        if qty:
            data["qty"] = qty
        if YES_RE.match(raw) or (nlu_intent and getattr(nlu_intent, "action", None) == "confirm"):
            data["qty"] = data.get("qty") or 1
            result = _save(data, user_name or data.get("user_name"))
            _clear_pending(user_id, channel_id)
            return f"✅ {result['message']}"
        if CANCEL_RE.match(raw):
            _clear_pending(user_id, channel_id)
            return "🚫 불량 입력을 취소했어요."
        if qty:
            return _continue(data, user_id, channel_id)
        return _continue(data, user_id, channel_id)

    # 바코드 수동 입력 대기
    if "barcode" in missing and raw:
        token = _extract_barcode(raw)
        compact = re.sub(r"[\s\-]", "", raw)
        if not token and _is_manual_barcode(compact):
            token = compact
        if token:
            data["barcode"] = token
            found = _lookup(token)
            if found:
                data = _attach_master(data, found)
            return _continue(data, user_id, channel_id)
        if BARCODE_RETRY_RE.search(raw) or _is_command(raw):
            return _ask(user_id, channel_id, data, ["barcode"], "바코드 숫자를 직접 입력해 주세요. 예: ON56S152917")
        return _ask(user_id, channel_id, data, ["barcode"], "바코드로 안 보여요. ON56S152917처럼 숫자·영문을 입력해 주세요.")

    # 업체명 대기
    if "vendor" in missing and not data.get("vendor") and raw:
        if _is_command(raw):
            return _ask(user_id, channel_id, data, ["vendor"], "업체명만 알려주세요. 예: 로지킴")
        with get_connection() as con:
            data["vendor"] = _resolve_vendor(con, raw.strip())
        return _continue(data, user_id, channel_id)

    if "vendor" in missing and data.get("vendor"):
        return _continue(data, user_id, channel_id)

    # 제품명 대기
    if "product" in missing and not data.get("product") and raw:
        if _is_command(raw):
            return _ask(user_id, channel_id, data, ["product"], "제품명만 알려주세요.")
        data["product"] = raw.strip()
        return _continue(data, user_id, channel_id)

    if "product" in missing and data.get("product"):
        return _continue(data, user_id, channel_id)

    # 불량명 대기
    if "defect_name" in missing and raw:
        defect = raw.strip()
        resolved = repair_catalog.resolve_defect(defect)
        data["defect_name"] = resolved["불량명"] if resolved else defect
        return _continue(data, user_id, channel_id)

    # 새 입력: 텍스트에서 바코드/불량명 파싱 시도
    if not data:
        data = {"entry_type": "defect", "user_name": user_name}
        token = _extract_barcode(raw)
        if token:
            data["barcode"] = token
            found = _lookup(token)
            if found:
                data = _attach_master(data, found)
        resolved = repair_catalog.resolve_defect(raw)
        if resolved:
            data["defect_name"] = resolved["불량명"]
        if data.get("vendor") or data.get("barcode"):
            return _continue(data, user_id, channel_id)
        # 텍스트만으로 판단 불가 → 사진 요청
        q = f"사진 2장 이상({PHOTO_SET_HINT})을 보내주세요."
        _set_pending(user_id, channel_id, data, ["photos"], q)
        return q

    return _continue(data, user_id, channel_id)


# ─────────────────────────────────────
# 사진 세트 완료 처리 (repair_bot._flush_inbox 에서 호출)
# ─────────────────────────────────────

async def finalize_defect_photo_set(
    user_id: str,
    channel_id: str,
    photos: List[BufferedPhoto],
    user_name: Optional[str] = None,
    classified: Optional[dict] = None,
) -> str:
    ensure_defect_tables()

    if classified is None:
        classified = await _classify_photos_safe(photos)
        if classified is None:
            return PHOTO_RETRY_MSG

    classified = _positional_photo_slots(photos, classified)
    saved_names = [
        save_image_bytes(p.data, p.ext) if p.data else None for p in photos
    ]

    data = _get_pending(user_id, channel_id)
    data.setdefault("user_name", user_name)
    data["entry_type"] = "defect"
    _assign_saved_photos(data, classified, saved_names)

    if classified.get("ambiguous"):
        data["barcode"] = classified.get("barcode") or data.get("barcode")
        q = "바코드가 여러 장에서 읽혔어요. 맞는 바코드를 적어주세요."
        _set_pending(user_id, channel_id, data, ["barcode"], q)
        return q

    if classified.get("barcode"):
        data["barcode"] = classified["barcode"]
        found = _lookup(data["barcode"])
        if found:
            data = _attach_master(data, found)
    else:
        q = "바코드를 못 읽었어요. 바코드 숫자를 직접 입력해 주세요."
        _set_pending(user_id, channel_id, data, ["barcode"], q)
        return q

    return _continue(data, user_id, channel_id)
