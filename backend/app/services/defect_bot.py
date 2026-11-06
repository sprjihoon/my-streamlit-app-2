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
    ensure_repair_tables,
)
from backend.app.api.defect_log import ensure_defect_tables, insert_defect_log_record
from backend.app.services import repair_catalog
from backend.app.services.barcode_decode import looks_like_barcode
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.repair_bot import (
    PHOTO_RETRY_MSG,
    BufferedPhoto,
    _claim_inbox_photos,
    _commit_inbox_claim,
    _inbox_count,
    _release_inbox_claim,
    cancel_photo_flush,
    clear_photo_inbox,
)
from logic.db import get_connection

logger = logging.getLogger(__name__)

EXPIRED_DEFECT_MSG = "작성하던 불량이 만료됐어요. 다시 시작해주세요."
DEFECT_ONE_PHOTO_MSG = "제품 사진 1장을 받았어요. 바코드 번호를 입력해 주세요."
DEFECT_BARCODE_HINT = "바코드 번호를 입력해 주세요. 번호를 입력했다면 제품 사진 1장만 보내도 됩니다."
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


def pending_barcode(user_id: str, channel_id: Optional[str] = None) -> str:
    return (_get_pending(user_id, channel_id).get("barcode") or "").strip()


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
        hint = "" if data.get("before_image") else " 제품 사진 1장을 같이 보내도 됩니다."
        return _ask(
            user_id, channel_id, data, ["defect_name"],
            f"{_item_line(data)} 맞아요. 불량명 알려주세요. (예: 구멍, 열펜, 올풀림){hint}",
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


async def _apply_defect_photos(
    data: Dict[str, Any],
    photos: List[BufferedPhoto],
    classified: Optional[dict],
) -> Optional[Dict[str, Any]]:
    from backend.app.services.repair_bot import apply_labeled_photos

    return await apply_labeled_photos(data, photos, classified)


async def absorb_inbox_photos(
    user_id: str,
    channel_id: str,
    user_name: Optional[str] = None,
    force: bool = False,
) -> bool:
    """바코드 번호를 받은 뒤 대기 중인 제품 사진을 같은 불량 초안에 붙인다."""
    from backend.app.services.repair_bot import photo_flush_pending

    if _inbox_count(user_id, channel_id) < 1 or not pending_barcode(user_id, channel_id):
        return False
    if not force and photo_flush_pending(user_id, channel_id):
        return False
    cancel_photo_flush(user_id, channel_id)
    claimed = _claim_inbox_photos(user_id, channel_id, 1)
    if not claimed or not claimed.get("ready"):
        return False
    photos = [p for p in claimed["photos"] if p.data]
    if not photos:
        _release_inbox_claim(user_id, channel_id)
        return False
    data = _get_pending(user_id, channel_id)
    data.setdefault("user_name", user_name or claimed.get("user_name"))
    data["entry_type"] = "defect"
    applied = await _apply_defect_photos(data, photos, None)
    if applied is None:
        _release_inbox_claim(user_id, channel_id)
        return False
    applied.pop("_ask_barcode", None)
    _set_pending(user_id, channel_id, applied, [], "")
    _commit_inbox_claim(user_id, channel_id, claimed.get("file_ids"))
    return True


async def _after(
    data: Dict[str, Any],
    user_id: str,
    channel_id: str,
    user_name: Optional[str],
) -> str:
    if (data.get("barcode") or "").strip() and _inbox_count(user_id, channel_id) >= 1:
        _set_pending(user_id, channel_id, data, [], "")
        if await absorb_inbox_photos(user_id, channel_id, user_name):
            fresh = _get_pending(user_id, channel_id)
            if fresh:
                data = fresh
    return _continue(data, user_id, channel_id)


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
    fresh = not data
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
            if (data.get("barcode") or "").strip() and _inbox_count(user_id, channel_id) >= 1:
                _set_pending(user_id, channel_id, data, [], "")
                if await absorb_inbox_photos(user_id, channel_id, user_name, force=True):
                    fresh = _get_pending(user_id, channel_id)
                    if fresh:
                        fresh["qty"] = data.get("qty") or 1
                        data = fresh
            result = _save(data, user_name or data.get("user_name"))
            _clear_pending(user_id, channel_id)
            return f"✅ {result['message']}"
        if CANCEL_RE.match(raw):
            _clear_pending(user_id, channel_id)
            return "🚫 불량 입력을 취소했어요."
        if qty:
            return await _after(data, user_id, channel_id, user_name)
        return await _after(data, user_id, channel_id, user_name)

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
            return await _after(data, user_id, channel_id, user_name)
        if BARCODE_RETRY_RE.search(raw) or _is_command(raw):
            return _ask(user_id, channel_id, data, ["barcode"], "바코드 숫자를 직접 입력해 주세요. 예: ON56S152917")
        return _ask(user_id, channel_id, data, ["barcode"], "바코드로 안 보여요. ON56S152917처럼 숫자·영문을 입력해 주세요.")

    # 업체명 대기
    if "vendor" in missing and not data.get("vendor") and raw:
        if _is_command(raw):
            return _ask(user_id, channel_id, data, ["vendor"], "업체명만 알려주세요. 예: 로지킴")
        with get_connection() as con:
            data["vendor"] = _resolve_vendor(con, raw.strip())
        return await _after(data, user_id, channel_id, user_name)

    if "vendor" in missing and data.get("vendor"):
        return await _after(data, user_id, channel_id, user_name)

    # 제품명 대기
    if "product" in missing and not data.get("product") and raw:
        if _is_command(raw):
            return _ask(user_id, channel_id, data, ["product"], "제품명만 알려주세요.")
        data["product"] = raw.strip()
        return await _after(data, user_id, channel_id, user_name)

    if "product" in missing and data.get("product"):
        return await _after(data, user_id, channel_id, user_name)

    # 불량명 대기
    if "defect_name" in missing and raw:
        defect = raw.strip()
        resolved = repair_catalog.resolve_defect(defect)
        data["defect_name"] = resolved["불량명"] if resolved else defect
        return await _after(data, user_id, channel_id, user_name)

    # 새 입력: 텍스트에서 바코드/불량명 파싱 시도
    if fresh:
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
            return await _after(data, user_id, channel_id, user_name)
        q = DEFECT_BARCODE_HINT
        _set_pending(user_id, channel_id, data, ["photos"], q)
        return q

    return await _after(data, user_id, channel_id, user_name)


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

    data = _get_pending(user_id, channel_id)
    data.setdefault("user_name", user_name)
    data["entry_type"] = "defect"
    applied = await _apply_defect_photos(data, photos, classified)
    if applied is None:
        return PHOTO_RETRY_MSG

    ask = applied.pop("_ask_barcode", None)
    if ask == "ambiguous":
        q = "바코드가 여러 장에서 읽혔어요. 맞는 바코드를 적어주세요."
        _set_pending(user_id, channel_id, applied, ["barcode"], q)
        return q
    if ask == "missing":
        q = "바코드를 못 읽었어요. 바코드 숫자를 직접 입력해 주세요."
        _set_pending(user_id, channel_id, applied, ["barcode"], q)
        return q
    return _continue(applied, user_id, channel_id)
