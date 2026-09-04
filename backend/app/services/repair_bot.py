"""
수선작업일지 봇 흐름
사진 3장 버퍼 + 바코드 조회 + 작업/비용 확인.
기존 work_log Function Calling과 분리한다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.api.repair_log import (
    _lookup_barcode,
    _resolve_vendor,
    ensure_repair_tables,
    insert_repair_log_record,
    save_image_bytes,
    upsert_repair_barcode_record,
)
from backend.app.services import repair_catalog
from backend.app.services.barcode_decode import classify_photos, looks_like_barcode
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection

logger = logging.getLogger(__name__)

PHOTO_WAIT_SEC = 2.5
PHOTO_EXTRA_WAIT_SEC = 1.5
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

REPAIR_SIGNALS = (
    "수선", "불량", "구멍", "열펜", "잡사", "세탁", "스팀", "바느질",
    "손뜨개", "보풀", "넥라인", "오염", "올풀림", "봉제", "기름",
)
LOGISTICS_SIGNALS = (
    "하차", "상차", "입고", "양품화", "발송", "대납", "이중라벨",
    "라벨작업", "톤하차", "톤상차", "화물비용",
)

PRICE_RE = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*만\s*원?)|((?:\d{1,3}(?:,\d{3})+|\d{3,}))\s*원?"
)
YES_RE = re.compile(r"^(네|넵|예|응|어|맞아|맞아요|그래|그래요|ㅇㅇ|ㅇㅋ|저장|저장해|그대로|좋아|ㅇ)$")
CANCEL_RE = re.compile(r"^(취소|그만|아니야|아니)$")


@dataclass
class BufferedPhoto:
    data: bytes
    name: str
    ext: str = ".jpg"


@dataclass
class PhotoSession:
    user_id: str
    channel_id: str
    channel_type: str
    user_name: Optional[str] = None
    photos: List[BufferedPhoto] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    extra_waited: bool = False


_sessions: Dict[str, PhotoSession] = {}


def is_image_filename(name: str) -> bool:
    return (name or "").lower().endswith(IMAGE_EXTS)


def is_repair_text(text: str) -> bool:
    t = (text or "").replace(" ", "")
    if any(s in t for s in LOGISTICS_SIGNALS):
        return False
    return any(s in t for s in REPAIR_SIGNALS)


def pending_is_repair(user_id: str) -> bool:
    state = get_conversation_manager().get_state(user_id)
    if not state:
        return False
    return (state.get("pending_data") or {}).get("entry_type") == "repair"


def should_handle_repair(user_id: str, text: str) -> bool:
    return pending_is_repair(user_id) or is_repair_text(text)


def display_vendor(name: Optional[str]) -> str:
    if not name:
        return ""
    if name.startswith("자체제작_"):
        return name.split("_", 1)[1]
    return name


def extract_price(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원?", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"((?:\d{1,3}(?:,\d{3})+)|\d{3,6})\s*원", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def extract_barcode_token(text: str) -> Optional[str]:
    for token in re.findall(r"[A-Za-z0-9]{8,24}", text or ""):
        if looks_like_barcode(token):
            return token
    return None


def parse_repair_text(text: str) -> Dict[str, Any]:
    price = extract_price(text)
    barcode = extract_barcode_token(text)
    work = repair_catalog.resolve_work_type(text)
    defect = repair_catalog.resolve_defect(text)
    return {
        "price": price,
        "price_stated": price is not None,
        "barcode": barcode,
        "work": work["작업명"] if work else None,
        "defect": defect["불량명"] if defect else None,
    }


def _get_pending(user_id: str) -> Dict[str, Any]:
    state = get_conversation_manager().get_state(user_id)
    if not state:
        return {}
    data = state.get("pending_data") or {}
    if data.get("entry_type") != "repair":
        return {}
    return data


def _set_pending(user_id: str, channel_id: str, data: Dict[str, Any], missing: List[str], question: str) -> None:
    data = {**data, "entry_type": "repair"}
    get_conversation_manager().set_state(
        user_id=user_id,
        channel_id=channel_id or "",
        pending_data=data,
        missing=missing,
        last_question=question,
    )


def _clear_pending(user_id: str) -> None:
    get_conversation_manager().clear_state(user_id)


def _merge_parsed(data: Dict[str, Any], parsed: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(data)
    if parsed.get("work"):
        out["work_type"] = parsed["work"]
    if parsed.get("defect"):
        out["defect"] = parsed["defect"]
    if parsed.get("barcode") and not out.get("barcode"):
        out["barcode"] = parsed["barcode"]
    if parsed.get("price") is not None:
        out["unit_price"] = parsed["price"]
        out["price_stated"] = True
    return out


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
    vendor = display_vendor(data.get("vendor")) or data.get("vendor") or "?"
    product = data.get("product") or "?"
    option = data.get("option")
    bits = [vendor, product]
    if option:
        bits.append(option)
    return " / ".join(bits)


def _try_save(data: Dict[str, Any], user_name: Optional[str], price_stated: bool) -> Dict[str, Any]:
    result = insert_repair_log_record(
        날짜=data.get("date") or datetime.now().strftime("%Y-%m-%d"),
        작업=data.get("work_type"),
        비용=int(data.get("unit_price")),
        업체명=data.get("vendor"),
        제품명=data.get("product"),
        옵션=data.get("option"),
        바코드=data.get("barcode"),
        불량명=data.get("defect"),
        수량=int(data.get("qty") or 1),
        비고=data.get("remark"),
        작성자=user_name,
        출처="bot",
        barcode_image=data.get("barcode_image"),
        before_image=data.get("before_image"),
        after_image=data.get("after_image"),
        price_stated=price_stated,
    )
    return result


def continue_after_photos_or_text(data: Dict[str, Any], user_id: str, channel_id: str) -> str:
    """사진/텍스트가 합쳐진 뒤 다음에 할 말."""
    if data.get("barcode") and not data.get("vendor"):
        found = _lookup(data["barcode"])
        if found:
            data = _attach_master(data, found)
        else:
            q = f"등록 안 된 바코드예요 ({data['barcode']}). 업체명 알려주세요."
            _set_pending(user_id, channel_id, data, ["vendor"], q)
            return q

    if not data.get("vendor"):
        q = "업체명 알려주세요."
        _set_pending(user_id, channel_id, data, ["vendor"], q)
        return q
    if not data.get("product"):
        q = "제품명 알려주세요."
        _set_pending(user_id, channel_id, data, ["product"], q)
        return q
    if not data.get("work_type"):
        q = f"{_item_line(data)} 맞아요. 작업이랑 금액 알려주세요."
        _set_pending(user_id, channel_id, data, ["work_type"], q)
        return q

    if data.get("unit_price"):
        if data.get("price_stated"):
            saved = _try_save(data, data.get("user_name"), True)
            _clear_pending(user_id)
            return f"✅ {saved['message']}"
        q = (
            f"{display_vendor(data.get('vendor')) or data.get('vendor')} "
            f"{data['work_type']} 최근 비용은 {int(data['unit_price']):,}원이었습니다. "
            f"그대로 저장할까요?"
        )
        data["awaiting_price_confirm"] = True
        _set_pending(user_id, channel_id, data, [], q)
        return q

    price_info = repair_catalog.lookup_repair_price(data.get("vendor"), data.get("work_type"))
    if price_info.get("found") and price_info.get("비용"):
        data["unit_price"] = price_info["비용"]
        data["work_type"] = price_info.get("작업명") or data["work_type"]
        q = price_info.get("message") or (
            f"{data.get('vendor')} {data['work_type']} 최근 비용은 {price_info['비용']:,}원이었습니다. 그대로 저장할까요?"
        )
        data["awaiting_price_confirm"] = True
        _set_pending(user_id, channel_id, data, [], q)
        return q

    q = "등록된 비용이 없어요. 금액을 알려주세요."
    _set_pending(user_id, channel_id, data, ["unit_price"], q)
    return q


async def handle_user_text(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str] = None,
) -> str:
    raw = (text or "").strip()
    data = _get_pending(user_id)
    data.setdefault("user_name", user_name)
    missing = (get_conversation_manager().get_state(user_id) or {}).get("missing") or []

    if data and CANCEL_RE.match(raw):
        _clear_pending(user_id)
        return "🚫 수선 입력을 취소했어요."

    if data.get("awaiting_price_confirm") and YES_RE.match(raw):
        saved = _try_save(data, user_name or data.get("user_name"), False)
        _clear_pending(user_id)
        return f"✅ {saved['message']}"

    parsed = parse_repair_text(raw)

    if data.get("awaiting_price_confirm") and parsed.get("price") is not None:
        data["unit_price"] = parsed["price"]
        data["price_stated"] = True
        if data.get("work_type"):
            try:
                repair_catalog.upsert_work_type(data["work_type"], parsed["price"])
            except Exception:
                pass
        saved = _try_save(data, user_name or data.get("user_name"), True)
        _clear_pending(user_id)
        return f"✅ {saved['message']}"

    if "barcode" in missing and raw:
        token = extract_barcode_token(raw) or re.sub(r"\s", "", raw)
        if looks_like_barcode(token) or (token.isalnum() and len(token) >= 6):
            data["barcode"] = token
            found = _lookup(token)
            if found:
                data = _attach_master(data, found)
            return continue_after_photos_or_text(data, user_id, channel_id)

    if "vendor" in missing and raw:
        with get_connection() as con:
            data["vendor"] = _resolve_vendor(con, raw)
        return continue_after_photos_or_text(data, user_id, channel_id)

    if "product" in missing and raw:
        data["product"] = raw
        if data.get("barcode") and data.get("vendor"):
            try:
                upsert_repair_barcode_record(
                    data["barcode"], data["vendor"], data["product"], data.get("option"), "bot"
                )
            except Exception:
                pass
        return continue_after_photos_or_text(data, user_id, channel_id)

    if "unit_price" in missing and parsed.get("price") is not None:
        data["unit_price"] = parsed["price"]
        data["price_stated"] = True
        return continue_after_photos_or_text(data, user_id, channel_id)

    if "work_type" in missing or not data.get("work_type"):
        if parsed.get("work"):
            data["work_type"] = parsed["work"]
        elif raw and not parsed.get("price") and "vendor" not in missing:
            # 마스터에 없는 새 작업명
            leftover = raw
            for token in ("원",):
                leftover = leftover.replace(token, "")
            leftover = PRICE_RE.sub("", leftover).strip()
            if leftover and leftover not in REPAIR_SIGNALS:
                if not parsed.get("defect") or leftover != parsed.get("defect"):
                    data["work_type"] = leftover
                    if parsed.get("price"):
                        repair_catalog.upsert_work_type(leftover, parsed["price"])

    data = _merge_parsed(data, parsed)

    if parsed.get("work") and not parsed.get("price") and data.get("vendor"):
        # 작업만 새로 온 경우 비용 조회
        data.pop("unit_price", None)
        data.pop("awaiting_price_confirm", None)

    if data.get("barcode") and not data.get("vendor"):
        found = _lookup(data["barcode"])
        if found:
            data = _attach_master(data, found)

    has_photos = bool(data.get("barcode_image") or data.get("before_image"))
    can_save_without_photos = bool(
        data.get("vendor") and data.get("product") and data.get("work_type") and data.get("unit_price")
    )
    if not has_photos and not can_save_without_photos and not data.get("barcode"):
        if data.get("work_type") or data.get("defect"):
            q = "사진 3장(바코드 / 수선 전 / 수선 후)을 한 번에 보내주세요."
            _set_pending(user_id, channel_id, data, ["photos"], q)
            return q

    return continue_after_photos_or_text(data, user_id, channel_id)


async def receive_photo(
    user_id: str,
    channel_id: str,
    channel_type: str,
    data: bytes,
    name: str,
    user_name: Optional[str] = None,
    send_fn=None,
) -> None:
    """사진을 버퍼에 넣고 잠시 후 세트로 처리."""
    sess = _sessions.get(user_id)
    if sess is None or sess.channel_id != channel_id:
        sess = PhotoSession(user_id=user_id, channel_id=channel_id, channel_type=channel_type, user_name=user_name)
        _sessions[user_id] = sess
    ext = ".jpg"
    lower = (name or "").lower()
    for e in IMAGE_EXTS:
        if lower.endswith(e):
            ext = e if e != ".jpeg" else ".jpg"
            break
    sess.photos.append(BufferedPhoto(data=data, name=name or "photo.jpg", ext=ext))
    sess.user_name = user_name or sess.user_name
    if sess.task and not sess.task.done():
        sess.task.cancel()
    wait = PHOTO_WAIT_SEC if len(sess.photos) < 3 else 1.0
    sess.task = asyncio.create_task(_flush_later(sess, wait, send_fn))


async def _flush_later(sess: PhotoSession, wait: float, send_fn) -> None:
    try:
        await asyncio.sleep(wait)
        await _flush_session(sess, send_fn)
    except asyncio.CancelledError:
        return


async def _flush_session(sess: PhotoSession, send_fn) -> None:
    n = len(sess.photos)
    if n == 0:
        return
    if n == 2 and not sess.extra_waited:
        sess.extra_waited = True
        sess.task = asyncio.create_task(_flush_later(sess, PHOTO_EXTRA_WAIT_SEC, send_fn))
        return
    if n < 3:
        msg = f"사진 {n}장 받았어요. 바코드·수선 전·후 포함해서 한 장 더 보내주세요."
        if send_fn:
            await send_fn(sess.channel_id, msg, sess.channel_type)
        return

    photos = sess.photos[:3]
    _sessions.pop(sess.user_id, None)
    reply = await finalize_photo_set(
        user_id=sess.user_id,
        channel_id=sess.channel_id,
        photos=photos,
        user_name=sess.user_name,
    )
    if send_fn and reply:
        await send_fn(sess.channel_id, reply, sess.channel_type)


async def finalize_photo_set(
    user_id: str,
    channel_id: str,
    photos: List[BufferedPhoto],
    user_name: Optional[str] = None,
    classified: Optional[dict] = None,
) -> str:
    ensure_repair_tables()
    classified = classified or await classify_photos([p.data for p in photos])
    saved_names = []
    for p in photos:
        saved_names.append(save_image_bytes(p.data, p.ext))

    data = _get_pending(user_id)
    data.setdefault("user_name", user_name)
    data["entry_type"] = "repair"
    bi = classified.get("barcode_index")
    if bi is not None:
        data["barcode_image"] = saved_names[bi]
    if classified.get("before_index") is not None:
        data["before_image"] = saved_names[classified["before_index"]]
    if classified.get("after_index") is not None:
        data["after_image"] = saved_names[classified["after_index"]]

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

    return continue_after_photos_or_text(data, user_id, channel_id)


def save_repair_from_tool(args: Dict[str, Any], user_id: str, user_name: str) -> Dict[str, Any]:
    """Function Calling용."""
    pending = _get_pending(user_id)
    data = {**pending, **{k: v for k, v in args.items() if v not in (None, "")}}
    data["vendor"] = data.get("vendor") or args.get("vendor")
    data["work_type"] = data.get("work_type") or args.get("work_type")
    data["unit_price"] = data.get("unit_price") or args.get("unit_price") or args.get("price")
    data["product"] = data.get("product") or args.get("product")
    data["defect"] = data.get("defect") or args.get("defect")
    data["option"] = data.get("option") or args.get("option")
    data["barcode"] = data.get("barcode") or args.get("barcode")
    try:
        result = _try_save(data, user_name, bool(data.get("price_stated") or args.get("price_stated")))
        _clear_pending(user_id)
        return result
    except ValueError as e:
        return {"success": False, "error": str(e)}
