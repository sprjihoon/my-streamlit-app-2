"""
수선작업일지 봇 흐름
사진 3장 버퍼 + 바코드 조회 + 작업/비용 확인.
기존 work_log Function Calling과 분리한다.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config import settings

from backend.app.api.repair_log import (
    _lookup_barcode,
    _resolve_vendor,
    ensure_repair_tables,
    insert_repair_log_record,
    save_image_bytes,
    _delete_image,
    upsert_repair_barcode_record,
)
from backend.app.services import repair_catalog
from backend.app.services.barcode_decode import classify_photos, looks_like_barcode
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection

logger = logging.getLogger(__name__)

PHOTO_WAIT_SEC = 5.0
PHOTO_EXTRA_WAIT_SEC = 2.5
PHOTO_MAX_EXTRA_ROUNDS = 2
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
QTY_RE = re.compile(r"(?:한\s*건)|(?:(\d+)\s*(?:건|개|장|벌))")
VENDOR_MENTION_RE = re.compile(r"업체명\s*(?:은|는|:)?\s*([가-힣A-Za-z0-9_]+)")
BARCODE_RETRY_RE = re.compile(r"다시\s*읽|다시읽|재인식|다시\s*봐")
ASCII_BARCODE_RE = re.compile(r"^[A-Za-z0-9]{6,24}$")
COMMAND_HINTS = (
    "보여줘", "보여주", "리스트", "목록", "다시읽", "다시찍어",
    "상관없이", "알려줘", "알려주", "작업당", "비용목록",
)
DEFECT_DEFAULT_WORK = {
    "구멍": "단순바느질",
    "올풀림": "단순바느질",
    "봉제 불량": "단순바느질",
    "열펜": "열펜제거",
    "잡사": "잡사제거",
    "오염": "부분세탁",
    "기름얼룩": "부분세탁",
    "넥라인불량": "손뜨개작업",
}


@dataclass
class BufferedPhoto:
    data: bytes
    name: str
    ext: str = ".jpg"


_flush_tasks: Dict[str, asyncio.Task] = {}


def is_image_filename(name: str) -> bool:
    return (name or "").lower().endswith(IMAGE_EXTS)


def is_cost_catalog_query(text: str, *, pending_repair: bool = False) -> bool:
    t = (text or "").replace(" ", "")
    if not t or any(s in t for s in LOGISTICS_SIGNALS):
        return False
    has_list = any(k in t for k in ("목록", "리스트", "보여"))
    if not has_list:
        return False
    if "작업당" in t and "비용" in t:
        return True
    if "수선" in t and ("비용" in t or "작업" in t):
        return True
    if "등록" in t and "작업" in t and "비용" in t:
        return True
    return pending_repair and ("비용" in t or "작업" in t)


def is_repair_text(text: str) -> bool:
    t = (text or "").replace(" ", "")
    if any(s in t for s in LOGISTICS_SIGNALS):
        return False
    if is_cost_catalog_query(text):
        return True
    return any(s in t for s in REPAIR_SIGNALS)


def pending_is_repair(user_id: str, channel_id: Optional[str] = None) -> bool:
    state = get_conversation_manager().get_state(user_id, channel_id)
    if state and (state.get("pending_data") or {}).get("entry_type") == "repair":
        return True
    return _inbox_count(user_id, channel_id) > 0


def should_handle_repair(user_id: str, text: str, channel_id: Optional[str] = None) -> bool:
    """키워드 자동 분기는 웹훅에서 수선모드일 때만 호출한다."""
    return pending_is_repair(user_id, channel_id) or is_repair_text(text)


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
        if looks_like_barcode(token) or (token.isdigit() and 8 <= len(token) <= 14):
            return token
    return None


def extract_vendor_mention(text: str) -> Optional[str]:
    m = VENDOR_MENTION_RE.search(text or "")
    if not m:
        return None
    name = m.group(1).strip()
    if not name or name in ("알려주세요", "뭐예요", "뭐야"):
        return None
    return name


def is_conversational_command(text: str) -> bool:
    t = (text or "").replace(" ", "")
    return any(k in t for k in COMMAND_HINTS) or bool(BARCODE_RETRY_RE.search(text or ""))


def is_manual_barcode(text: str) -> bool:
    """한글 문장은 바코드가 아니다. Python isalnum()은 한글도 True라 쓰면 안 된다."""
    s = re.sub(r"[\s\-]", "", text or "")
    if not ASCII_BARCODE_RE.fullmatch(s):
        return False
    return looks_like_barcode(s) or (s.isdigit() and 8 <= len(s) <= 14)


def format_work_cost_list() -> str:
    rows = repair_catalog.list_work_types()
    if not rows:
        return "등록된 작업 비용이 없어요."
    lines = ["등록된 수선 작업 비용이에요."]
    for r in rows:
        alias = f" ({r['별칭']})" if r.get("별칭") else ""
        lines.append(f"• {r['작업명']}{alias} — {int(r['기본비용']):,}원")
    return "\n".join(lines)


def extract_qty(text: str) -> Optional[int]:
    if not text:
        return None
    if re.search(r"한\s*건", text):
        return 1
    m = re.search(r"(\d+)\s*(?:건|개|장|벌)", text)
    if m:
        n = int(m.group(1))
        return n if n > 0 else None
    return None


def parse_repair_text(text: str) -> Dict[str, Any]:
    price = extract_price(text)
    barcode = extract_barcode_token(text)
    qty = extract_qty(text)
    work = repair_catalog.resolve_work_type(text)
    defect = repair_catalog.resolve_defect(text)
    return {
        "price": price,
        "price_stated": price is not None,
        "barcode": barcode,
        "qty": qty,
        "work": work["작업명"] if work else None,
        "defect": defect["불량명"] if defect else None,
    }


def _get_pending(user_id: str, channel_id: Optional[str] = None) -> Dict[str, Any]:
    state = get_conversation_manager().get_state(user_id, channel_id)
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


def _ask(user_id: str, channel_id: str, data: Dict[str, Any], missing: List[str], question: str) -> str:
    """같은 질문을 워커가 여러 번 보내지 않는다."""
    prev = (get_conversation_manager().get_state(user_id, channel_id) or {}).get("last_question")
    _set_pending(user_id, channel_id, data, missing, question)
    return "" if prev == question else question


def _clear_pending(user_id: str, channel_id: Optional[str] = None) -> None:
    get_conversation_manager().clear_state(user_id, channel_id)


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
    if parsed.get("qty"):
        out["qty"] = parsed["qty"]
    return out


def _infer_work(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(data)
    if out.get("work_type"):
        return out
    defect = out.get("defect")
    if defect and defect in DEFECT_DEFAULT_WORK:
        out["work_type"] = DEFECT_DEFAULT_WORK[defect]
    return out


def _job_label(data: Dict[str, Any]) -> str:
    defect = data.get("defect")
    work = data.get("work_type")
    if defect and work and defect != work:
        return f"{defect} / {work}"
    return defect or work or "수선"


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


def _save_repair_entry(
    data: Dict[str, Any],
    user_name: Optional[str],
    price_stated: bool,
    user_id: str,
    channel_id: str,
) -> Dict[str, Any]:
    """기존 저장 본체를 호출한 뒤 이 방의 직전 기록 id만 기억한다."""
    saved = _try_save(data, user_name, price_stated)
    rid = saved.get("id")
    if saved.get("success") and rid:
        try:
            from backend.app.services.repair_edit import remember_last_saved
            remember_last_saved(user_id, channel_id, int(rid))
        except Exception:
            logger.exception(
                "remember_last_saved failed user=%s channel=%s record=%s",
                user_id, channel_id, rid,
            )
    return saved


def _confirm_cost_qty(data: Dict[str, Any], user_id: str, channel_id: str) -> str:
    price = int(data.get("unit_price") or 0)
    label = _job_label(data)
    qty = data.get("qty")
    if qty:
        q = f"{label} {price:,}원 {int(qty)}건으로 저장할까요?"
    else:
        q = f"{label} {price:,}원 맞아요? 몇 건이에요?"
    data["awaiting_price_confirm"] = True
    return _ask(user_id, channel_id, data, ["qty"], q)


def continue_after_photos_or_text(data: Dict[str, Any], user_id: str, channel_id: str) -> str:
    """사진/텍스트가 합쳐진 뒤 다음에 할 말."""
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

    data = _infer_work(data)
    if not data.get("work_type") and not data.get("defect"):
        return _ask(
            user_id, channel_id, data, ["work_type"],
            f"{_item_line(data)} 맞아요. 작업이랑 금액 알려주세요.",
        )
    if not data.get("work_type"):
        return _ask(
            user_id, channel_id, data, ["work_type"],
            f"{_item_line(data)} / {data.get('defect')} 맞아요. 작업은 뭐로 할까요?",
        )

    if not data.get("unit_price"):
        price_info = repair_catalog.lookup_repair_price(data.get("vendor"), data.get("work_type"))
        if price_info.get("found") and price_info.get("비용"):
            data["unit_price"] = price_info["비용"]
            data["work_type"] = price_info.get("작업명") or data["work_type"]
            data["price_stated"] = False
            return _confirm_cost_qty(data, user_id, channel_id)
        return _ask(user_id, channel_id, data, ["unit_price"], "금액이 얼마예요?")

    if data.get("qty") and data.get("price_stated") and data.get("awaiting_price_confirm") is not True:
        # 작업·금액·건수를 한 번에 말한 경우만 바로 저장
        saved = _save_repair_entry(data, data.get("user_name"), True, user_id, channel_id)
        _clear_pending(user_id, channel_id)
        return f"✅ {saved['message']}"

    return _confirm_cost_qty(data, user_id, channel_id)


def _merge_nlu_fields(parsed: Dict[str, Any], fields: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(parsed or {})
    if not fields:
        return out
    if fields.get("unit_price") is not None:
        out["price"] = int(fields["unit_price"])
        out["price_stated"] = True
    if fields.get("qty"):
        out["qty"] = int(fields["qty"])
    if fields.get("work_type"):
        out["work"] = fields["work_type"]
    if fields.get("defect"):
        out["defect"] = fields["defect"]
    if fields.get("vendor"):
        out["vendor"] = fields["vendor"]
    if fields.get("product"):
        out["product"] = fields["product"]
    return out


async def handle_user_text(
    user_id: str,
    channel_id: str,
    text: str,
    user_name: Optional[str] = None,
    nlu_intent=None,
) -> str:
    raw = (text or "").strip()
    from backend.app.services.bot_nlu import interpret_or_fallback, nlu_to_bot_intent
    from backend.app.services.repair_edit import handle_repair_edit

    nlu = nlu_intent if nlu_intent is not None else await interpret_or_fallback(user_id, channel_id, raw)
    intent = nlu_to_bot_intent(nlu, raw)
    edited = handle_repair_edit(user_id, channel_id, raw, user_name, intent=intent)
    if edited is not None:
        return edited

    data = _get_pending(user_id, channel_id)
    data.setdefault("user_name", user_name)
    missing = (get_conversation_manager().get_state(user_id, channel_id) or {}).get("missing") or []

    if (nlu and getattr(nlu, "action", None) == "unknown" and nlu.clarification
            and not data and not missing and _inbox_count(user_id, channel_id) == 0):
        return nlu.clarification

    cancelled = bool(CANCEL_RE.match(raw) or (nlu and getattr(nlu, "action", None) == "cancel"))
    if cancelled and (data or _inbox_count(user_id, channel_id) > 0):
        clear_photo_inbox(user_id, channel_id)
        _clear_pending(user_id, channel_id)
        return "🚫 수선 입력을 취소했어요."

    if is_cost_catalog_query(raw, pending_repair=bool(data or missing)):
        listing = format_work_cost_list()
        last_q = (get_conversation_manager().get_state(user_id, channel_id) or {}).get("last_question") or ""
        if last_q and last_q not in listing:
            return f"{listing}\n\n{last_q}"
        return listing

    parsed = parse_repair_text(raw)
    nlu_action = getattr(nlu, "action", None) if nlu else None
    nlu_target = getattr(nlu, "target", None) if nlu else None
    nlu_fields = getattr(nlu, "fields", None) if nlu else None
    if nlu_action in ("provide_field", "create", "update") and nlu_target != "last_saved":
        parsed = _merge_nlu_fields(parsed, nlu_fields)
    vendor_mention = extract_vendor_mention(raw) or (parsed.get("vendor") if parsed.get("vendor") else None)
    if vendor_mention and not data.get("vendor"):
        with get_connection() as con:
            data["vendor"] = _resolve_vendor(con, vendor_mention)

    if data.get("awaiting_price_confirm"):
        prev_price = data.get("unit_price")
        if parsed.get("qty"):
            data["qty"] = parsed["qty"]
        if parsed.get("price") is not None:
            data["unit_price"] = parsed["price"]
            data["price_stated"] = True
            if data.get("work_type"):
                try:
                    repair_catalog.upsert_work_type(data["work_type"], parsed["price"])
                except Exception:
                    pass
        if parsed.get("work"):
            data["work_type"] = parsed["work"]
        if parsed.get("defect"):
            data["defect"] = parsed["defect"]
            data = _infer_work(data)
        if YES_RE.match(raw) or nlu_action == "confirm":
            data["qty"] = data.get("qty") or 1
            saved = _save_repair_entry(
                data, user_name or data.get("user_name"), bool(data.get("price_stated")),
                user_id, channel_id,
            )
            _clear_pending(user_id, channel_id)
            return f"✅ {saved['message']}"
        if data.get("qty") and data.get("unit_price"):
            saved = _save_repair_entry(
                data, user_name or data.get("user_name"), bool(data.get("price_stated")),
                user_id, channel_id,
            )
            _clear_pending(user_id, channel_id)
            return f"✅ {saved['message']}"
        if parsed.get("price") is not None and parsed["price"] != prev_price:
            return _confirm_cost_qty(data, user_id, channel_id)
        return _ask(user_id, channel_id, data, ["qty"], "몇 건인지 숫자로 알려주세요. 예: 1건")

    if "barcode" in missing and raw:
        token = extract_barcode_token(raw)
        compact = re.sub(r"[\s\-]", "", raw)
        if not token and is_manual_barcode(compact):
            token = compact
        if token:
            data["barcode"] = token
            if data.get("barcode_image"):
                _delete_image(data["barcode_image"])
                data["barcode_image"] = None
            found = _lookup(token)
            if found:
                data = _attach_master(data, found)
            return continue_after_photos_or_text(data, user_id, channel_id)
        if vendor_mention or BARCODE_RETRY_RE.search(raw) or is_conversational_command(raw):
            q = "바코드 숫자를 직접 입력해 주세요. 예: ON56S152917"
            if data.get("vendor"):
                q = (
                    f"{display_vendor(data['vendor'])} 업체로 받을게요. "
                    "바코드 숫자를 직접 입력해 주세요. 예: ON56S152917"
                )
            return _ask(user_id, channel_id, data, ["barcode"], q)
        return _ask(
            user_id, channel_id, data, ["barcode"],
            "바코드로 안 보여요. ON56S152917처럼 숫자·영문을 입력해 주세요.",
        )

    if "vendor" in missing and raw:
        if is_conversational_command(raw) and not vendor_mention:
            return _ask(user_id, channel_id, data, ["vendor"], "업체명만 알려주세요. 예: 로지킴")
        vendor_text = vendor_mention or raw.strip()
        with get_connection() as con:
            data["vendor"] = _resolve_vendor(con, vendor_text)
        return continue_after_photos_or_text(data, user_id, channel_id)

    if "product" in missing and raw:
        if is_conversational_command(raw):
            return _ask(user_id, channel_id, data, ["product"], "제품명만 알려주세요.")
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
        elif (
            raw
            and not parsed.get("price")
            and not parsed.get("qty")
            and not YES_RE.match(raw)
            and not is_conversational_command(raw)
            and "vendor" not in missing
        ):
            leftover = raw
            leftover = PRICE_RE.sub("", leftover).strip()
            leftover = QTY_RE.sub("", leftover).strip()
            leftover = leftover.replace("원", "").strip()
            if leftover and leftover not in REPAIR_SIGNALS:
                if not parsed.get("defect") or leftover != parsed.get("defect"):
                    data["work_type"] = leftover
                    if parsed.get("price"):
                        repair_catalog.upsert_work_type(leftover, parsed["price"])

    data = _merge_parsed(data, parsed)
    data = _infer_work(data)

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


INBOX_STALE_SEC = 6 * 3600


def _inbox_dir() -> Path:
    path = Path(settings.UPLOAD_DIR) / "repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _room_key(user_id: str, channel_id: Optional[str] = None) -> tuple[str, str]:
    uid = (user_id or "").strip()
    cid = (channel_id or "").strip() or uid
    return uid, cid


def _task_key(user_id: str, channel_id: Optional[str] = None) -> str:
    uid, cid = _room_key(user_id, channel_id)
    return f"{uid}\x1f{cid}"


def ensure_inbox_v2_tables() -> None:
    """임시 세션용 v2 inbox. 기존 repair_photo_inbox PK는 변경하지 않는다."""
    ensure_repair_tables()
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS repair_photo_inbox_v2 (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_type TEXT,
                user_name TEXT,
                extra_rounds INTEGER DEFAULT 0,
                notified_n INTEGER DEFAULT 0,
                flush_after REAL,
                updated_at TEXT,
                PRIMARY KEY (user_id, channel_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS repair_photo_inbox_file_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                name TEXT,
                ext TEXT,
                created_at TEXT
            )
            """
        )
        con.commit()


def cleanup_stale_inbox_v2(max_age_sec: int = INBOX_STALE_SEC) -> int:
    """만료된 v2 inbox 임시 파일만 정리. 저장된 수선일지 사진은 건드리지 않는다."""
    ensure_inbox_v2_tables()
    cutoff = time.time() - max_age_sec
    folder = _inbox_dir()
    removed = 0
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT id, filename, created_at FROM repair_photo_inbox_file_v2
            """
        ).fetchall()
        stale_ids = []
        for _id, filename, created in rows:
            ts = 0.0
            if created:
                try:
                    ts = datetime.fromisoformat(str(created)).timestamp()
                except ValueError:
                    ts = 0.0
            if ts and ts > cutoff:
                continue
            stale_ids.append((_id, filename))
        for _id, filename in stale_ids:
            con.execute("DELETE FROM repair_photo_inbox_file_v2 WHERE id = ?", (_id,))
            if filename:
                try:
                    (folder / filename).unlink(missing_ok=True)
                except Exception:
                    pass
            removed += 1
        con.execute(
            """
            DELETE FROM repair_photo_inbox_v2
            WHERE NOT EXISTS (
                SELECT 1 FROM repair_photo_inbox_file_v2 f
                WHERE f.user_id = repair_photo_inbox_v2.user_id
                  AND f.channel_id = repair_photo_inbox_v2.channel_id
            )
            """
        )
        con.commit()
    return removed


def _inbox_count(user_id: str, channel_id: Optional[str] = None) -> int:
    uid, cid = _room_key(user_id, channel_id)
    if not uid:
        return 0
    ensure_inbox_v2_tables()
    with get_connection() as con:
        row = con.execute(
            """
            SELECT COUNT(*) FROM repair_photo_inbox_file_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()
    return int(row[0] or 0) if row else 0


def clear_photo_inbox(user_id: str, channel_id: Optional[str] = None) -> None:
    """해당 방 inbox만 비운다. 저장된 수선일지·사진은 삭제하지 않는다."""
    uid, cid = _room_key(user_id, channel_id)
    if not uid:
        return
    ensure_inbox_v2_tables()
    folder = _inbox_dir()
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT filename FROM repair_photo_inbox_file_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchall()
        con.execute(
            "DELETE FROM repair_photo_inbox_file_v2 WHERE user_id = ? AND channel_id = ?",
            (uid, cid),
        )
        con.execute(
            "DELETE FROM repair_photo_inbox_v2 WHERE user_id = ? AND channel_id = ?",
            (uid, cid),
        )
        con.commit()
    for row in rows:
        try:
            (folder / row[0]).unlink(missing_ok=True)
        except Exception:
            pass
    task = _flush_tasks.pop(_task_key(uid, cid), None)
    if task and not task.done():
        task.cancel()


def _append_inbox_photo(
    user_id: str,
    channel_id: str,
    channel_type: str,
    user_name: Optional[str],
    data: bytes,
    name: str,
    ext: str,
) -> int:
    uid, cid = _room_key(user_id, channel_id)
    ensure_inbox_v2_tables()
    cleanup_stale_inbox_v2()
    filename = save_image_bytes(data, ext)
    now = datetime.now().isoformat()
    flush_after = time.time() + PHOTO_WAIT_SEC
    with get_connection() as con:
        con.execute(
            """
            INSERT INTO repair_photo_inbox_v2
                (user_id, channel_id, channel_type, user_name, extra_rounds, notified_n, flush_after, updated_at)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?)
            ON CONFLICT(user_id, channel_id) DO UPDATE SET
                channel_type = excluded.channel_type,
                user_name = COALESCE(excluded.user_name, repair_photo_inbox_v2.user_name),
                extra_rounds = 0,
                flush_after = excluded.flush_after,
                updated_at = excluded.updated_at
            """,
            (uid, cid, channel_type, user_name, flush_after, now),
        )
        con.execute(
            """
            INSERT INTO repair_photo_inbox_file_v2
                (user_id, channel_id, filename, name, ext, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uid, cid, filename, name, ext, now),
        )
        count = con.execute(
            """
            SELECT COUNT(*) FROM repair_photo_inbox_file_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()[0]
        con.commit()
    return int(count)


def _claim_inbox_photos(user_id: str, channel_id: Optional[str] = None, need: int = 3) -> Optional[dict]:
    """워커 여러 개가 동시에 비우지 않도록 해당 방 3장만 한 번에 가져온다."""
    uid, cid = _room_key(user_id, channel_id)
    ensure_inbox_v2_tables()
    folder = _inbox_dir()
    now = datetime.now().isoformat()
    with get_connection() as con:
        meta = con.execute(
            """
            SELECT channel_id, channel_type, user_name, extra_rounds, notified_n, flush_after
            FROM repair_photo_inbox_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()
        files = con.execute(
            """
            SELECT id, filename, name, ext FROM repair_photo_inbox_file_v2
            WHERE user_id = ? AND channel_id = ?
            ORDER BY id
            """,
            (uid, cid),
        ).fetchall()
        if not meta or not files:
            return None
        n = len(files)
        if n < need:
            return {
                "ready": False,
                "count": n,
                "channel_id": meta[0],
                "channel_type": meta[1],
                "user_name": meta[2],
                "extra_rounds": int(meta[3] or 0),
                "notified_n": int(meta[4] or 0),
                "flush_after": float(meta[5] or 0),
            }
        claimed = con.execute(
            """
            UPDATE repair_photo_inbox_v2 SET extra_rounds = -1, updated_at = ?
            WHERE user_id = ? AND channel_id = ? AND extra_rounds >= 0
              AND (
                SELECT COUNT(*) FROM repair_photo_inbox_file_v2
                WHERE user_id = ? AND channel_id = ?
              ) >= ?
            """,
            (now, uid, cid, uid, cid, need),
        )
        if claimed.rowcount != 1:
            con.commit()
            return None
        taken = files[-need:] if n > need else files
        photos = []
        for _id, filename, name, ext in taken:
            path = folder / filename
            photos.append(BufferedPhoto(
                data=path.read_bytes() if path.exists() else b"",
                name=name or filename,
                ext=ext or ".jpg",
            ))
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            con.execute("DELETE FROM repair_photo_inbox_file_v2 WHERE id = ?", (_id,))
        left = con.execute(
            """
            SELECT COUNT(*) FROM repair_photo_inbox_file_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()[0]
        if left == 0:
            con.execute(
                "DELETE FROM repair_photo_inbox_v2 WHERE user_id = ? AND channel_id = ?",
                (uid, cid),
            )
        con.commit()
    return {
        "ready": True,
        "count": n,
        "channel_id": meta[0],
        "channel_type": meta[1],
        "user_name": meta[2],
        "photos": photos,
    }


def _bump_inbox_wait(user_id: str, channel_id: Optional[str] = None) -> None:
    uid, cid = _room_key(user_id, channel_id)
    with get_connection() as con:
        con.execute(
            """
            UPDATE repair_photo_inbox_v2
            SET extra_rounds = extra_rounds + 1, flush_after = ?
            WHERE user_id = ? AND channel_id = ?
            """,
            (time.time() + PHOTO_EXTRA_WAIT_SEC, uid, cid),
        )
        con.commit()


def _mark_inbox_notified(user_id: str, channel_id: Optional[str], n: int) -> None:
    uid, cid = _room_key(user_id, channel_id)
    with get_connection() as con:
        con.execute(
            """
            UPDATE repair_photo_inbox_v2 SET notified_n = ?
            WHERE user_id = ? AND channel_id = ?
            """,
            (n, uid, cid),
        )
        con.commit()


async def receive_photo(
    user_id: str,
    channel_id: str,
    channel_type: str,
    data: bytes,
    name: str,
    user_name: Optional[str] = None,
    send_fn=None,
) -> None:
    """사진을 해당 방 버퍼에 넣고 잠시 후 세트로 처리."""
    ext = ".jpg"
    lower = (name or "").lower()
    for e in IMAGE_EXTS:
        if lower.endswith(e):
            ext = e if e != ".jpeg" else ".jpg"
            break
    count = _append_inbox_photo(
        user_id, channel_id, channel_type, user_name, data, name or "photo.jpg", ext
    )
    logger.info("repair photo buffered user=%s channel=%s count=%s", user_id, channel_id, count)
    wait = 1.0 if count >= 3 else PHOTO_WAIT_SEC
    key = _task_key(user_id, channel_id)
    existing = _flush_tasks.get(key)
    if existing and not existing.done():
        existing.cancel()
    _flush_tasks[key] = asyncio.create_task(
        _flush_later(user_id, channel_id, wait, send_fn)
    )


async def _flush_later(user_id: str, channel_id: str, wait: float, send_fn, depth: int = 0) -> None:
    try:
        await asyncio.sleep(wait)
        await _flush_inbox(user_id, channel_id, send_fn, depth)
    except asyncio.CancelledError:
        return


async def _flush_inbox(user_id: str, channel_id: str, send_fn, depth: int = 0) -> None:
    if depth > 6:
        return
    uid, cid = _room_key(user_id, channel_id)
    ensure_inbox_v2_tables()
    with get_connection() as con:
        meta = con.execute(
            """
            SELECT channel_id, channel_type, extra_rounds, notified_n, flush_after
            FROM repair_photo_inbox_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()
        n = con.execute(
            """
            SELECT COUNT(*) FROM repair_photo_inbox_file_v2
            WHERE user_id = ? AND channel_id = ?
            """,
            (uid, cid),
        ).fetchone()[0]
    if not meta or n == 0:
        return

    flush_after = float(meta[4] or 0)
    remain = flush_after - time.time()
    if remain > 0.05:
        await _flush_later(uid, cid, remain, send_fn, depth + 1)
        return

    if n < 3:
        extra = int(meta[2] or 0)
        if extra < PHOTO_MAX_EXTRA_ROUNDS:
            _bump_inbox_wait(uid, cid)
            await _flush_later(uid, cid, PHOTO_EXTRA_WAIT_SEC, send_fn, depth + 1)
            return
        notified = int(meta[3] or 0)
        if send_fn and notified != n:
            _mark_inbox_notified(uid, cid, n)
            await send_fn(
                meta[0],
                f"사진 {n}장 받았어요. 바코드·수선 전·후 포함해서 한 장 더 보내주세요.",
                meta[1],
            )
        return

    claimed = _claim_inbox_photos(uid, cid, 3)
    if not claimed or not claimed.get("ready"):
        if claimed and claimed.get("count", 0) < 3:
            await _flush_later(uid, cid, PHOTO_EXTRA_WAIT_SEC, send_fn, depth + 1)
        return

    photos = [p for p in claimed["photos"] if p.data]
    if len(photos) < 3:
        if send_fn:
            await send_fn(
                claimed["channel_id"],
                "사진을 일부 읽지 못했어요. 바코드·수선 전·후 3장을 다시 보내주세요.",
                claimed["channel_type"],
            )
        return

    reply = await finalize_photo_set(
        user_id=uid,
        channel_id=claimed["channel_id"],
        photos=photos,
        user_name=claimed["user_name"],
    )
    if send_fn and reply:
        await send_fn(claimed["channel_id"], reply, claimed["channel_type"])


async def finalize_photo_set(
    user_id: str,
    channel_id: str,
    photos: List[BufferedPhoto],
    user_name: Optional[str] = None,
    classified: Optional[dict] = None,
) -> str:
    ensure_repair_tables()
    classified = classified or await classify_photos([p.data for p in photos])
    bi = classified.get("barcode_index")
    decoded = bool(classified.get("barcode")) and not classified.get("ambiguous")
    saved_names: List[Optional[str]] = [None] * len(photos)
    for i, p in enumerate(photos):
        if decoded and i == bi:
            continue
        saved_names[i] = save_image_bytes(p.data, p.ext)

    data = _get_pending(user_id, channel_id)
    data.setdefault("user_name", user_name)
    data["entry_type"] = "repair"
    if classified.get("before_index") is not None:
        data["before_image"] = saved_names[classified["before_index"]]
    if classified.get("after_index") is not None:
        data["after_image"] = saved_names[classified["after_index"]]
    data.pop("barcode_image", None)

    if classified.get("ambiguous"):
        data["barcode"] = classified.get("barcode") or data.get("barcode")
        if bi is not None and saved_names[bi]:
            data["barcode_image"] = saved_names[bi]
        q = "바코드가 여러 장에서 읽혔어요. 맞는 바코드를 적어주세요."
        _set_pending(user_id, channel_id, data, ["barcode"], q)
        return q

    if classified.get("barcode"):
        data["barcode"] = classified["barcode"]
        found = _lookup(data["barcode"])
        if found:
            data = _attach_master(data, found)
    else:
        if bi is not None and saved_names[bi]:
            data["barcode_image"] = saved_names[bi]
        q = "바코드를 못 읽었어요. 바코드 숫자를 직접 입력해 주세요."
        _set_pending(user_id, channel_id, data, ["barcode"], q)
        return q

    return continue_after_photos_or_text(data, user_id, channel_id)


def save_repair_from_tool(args: Dict[str, Any], user_id: str, user_name: str) -> Dict[str, Any]:
    """Function Calling용."""
    channel_id = args.get("channel_id")
    pending = _get_pending(user_id, channel_id)
    data = {**pending, **{k: v for k, v in args.items() if v not in (None, "")}}
    data["vendor"] = data.get("vendor") or args.get("vendor")
    data["work_type"] = data.get("work_type") or args.get("work_type")
    data["unit_price"] = data.get("unit_price") or args.get("unit_price") or args.get("price")
    data["product"] = data.get("product") or args.get("product")
    data["defect"] = data.get("defect") or args.get("defect")
    data["option"] = data.get("option") or args.get("option")
    data["barcode"] = data.get("barcode") or args.get("barcode")
    try:
        result = _save_repair_entry(
            data, user_name, bool(data.get("price_stated") or args.get("price_stated")),
            user_id, channel_id or user_id,
        )
        _clear_pending(user_id, channel_id)
        return result
    except ValueError as e:
        return {"success": False, "error": str(e)}
