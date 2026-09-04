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


@dataclass
class BufferedPhoto:
    data: bytes
    name: str
    ext: str = ".jpg"


_flush_tasks: Dict[str, asyncio.Task] = {}


def is_image_filename(name: str) -> bool:
    return (name or "").lower().endswith(IMAGE_EXTS)


def is_repair_text(text: str) -> bool:
    t = (text or "").replace(" ", "")
    if any(s in t for s in LOGISTICS_SIGNALS):
        return False
    return any(s in t for s in REPAIR_SIGNALS)


def pending_is_repair(user_id: str) -> bool:
    state = get_conversation_manager().get_state(user_id)
    if state and (state.get("pending_data") or {}).get("entry_type") == "repair":
        return True
    return _inbox_count(user_id) > 0


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

    if CANCEL_RE.match(raw) and (data or _inbox_count(user_id) > 0):
        clear_photo_inbox(user_id)
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


def _inbox_dir() -> Path:
    path = Path(settings.UPLOAD_DIR) / "repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inbox_count(user_id: str) -> int:
    if not user_id:
        return 0
    ensure_repair_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM repair_photo_inbox_file WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return int(row[0] or 0) if row else 0


def clear_photo_inbox(user_id: str) -> None:
    if not user_id:
        return
    ensure_repair_tables()
    folder = _inbox_dir()
    with get_connection() as con:
        rows = con.execute(
            "SELECT filename FROM repair_photo_inbox_file WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        con.execute("DELETE FROM repair_photo_inbox_file WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM repair_photo_inbox WHERE user_id = ?", (user_id,))
        con.commit()
    for row in rows:
        try:
            (folder / row[0]).unlink(missing_ok=True)
        except Exception:
            pass
    task = _flush_tasks.pop(user_id, None)
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
    ensure_repair_tables()
    filename = save_image_bytes(data, ext)
    now = datetime.now().isoformat()
    flush_after = time.time() + PHOTO_WAIT_SEC
    with get_connection() as con:
        con.execute(
            """
            INSERT INTO repair_photo_inbox
                (user_id, channel_id, channel_type, user_name, extra_rounds, notified_n, flush_after, updated_at)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                channel_type = excluded.channel_type,
                user_name = COALESCE(excluded.user_name, repair_photo_inbox.user_name),
                extra_rounds = 0,
                flush_after = excluded.flush_after,
                updated_at = excluded.updated_at
            """,
            (user_id, channel_id, channel_type, user_name, flush_after, now),
        )
        con.execute(
            """
            INSERT INTO repair_photo_inbox_file (user_id, filename, name, ext, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, filename, name, ext, now),
        )
        count = con.execute(
            "SELECT COUNT(*) FROM repair_photo_inbox_file WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        con.commit()
    return int(count)


def _claim_inbox_photos(user_id: str, need: int = 3) -> Optional[dict]:
    """워커 여러 개가 동시에 비우지 않도록 3장을 한 번에 가져온다."""
    ensure_repair_tables()
    folder = _inbox_dir()
    now = datetime.now().isoformat()
    with get_connection() as con:
        meta = con.execute(
            """SELECT channel_id, channel_type, user_name, extra_rounds, notified_n, flush_after
               FROM repair_photo_inbox WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        files = con.execute(
            """SELECT id, filename, name, ext FROM repair_photo_inbox_file
               WHERE user_id = ? ORDER BY id""",
            (user_id,),
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
            """UPDATE repair_photo_inbox SET extra_rounds = -1, updated_at = ?
               WHERE user_id = ? AND extra_rounds >= 0
                 AND (SELECT COUNT(*) FROM repair_photo_inbox_file WHERE user_id = ?) >= ?""",
            (now, user_id, user_id, need),
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
            con.execute("DELETE FROM repair_photo_inbox_file WHERE id = ?", (_id,))
        left = con.execute(
            "SELECT COUNT(*) FROM repair_photo_inbox_file WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        if left == 0:
            con.execute("DELETE FROM repair_photo_inbox WHERE user_id = ?", (user_id,))
        con.commit()
    return {
        "ready": True,
        "count": n,
        "channel_id": meta[0],
        "channel_type": meta[1],
        "user_name": meta[2],
        "photos": photos,
    }


def _bump_inbox_wait(user_id: str) -> None:
    with get_connection() as con:
        con.execute(
            """UPDATE repair_photo_inbox
               SET extra_rounds = extra_rounds + 1, flush_after = ?
               WHERE user_id = ?""",
            (time.time() + PHOTO_EXTRA_WAIT_SEC, user_id),
        )
        con.commit()


def _mark_inbox_notified(user_id: str, n: int) -> None:
    with get_connection() as con:
        con.execute(
            "UPDATE repair_photo_inbox SET notified_n = ? WHERE user_id = ?",
            (n, user_id),
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
    """사진을 워커 공용 버퍼에 넣고 잠시 후 세트로 처리."""
    ext = ".jpg"
    lower = (name or "").lower()
    for e in IMAGE_EXTS:
        if lower.endswith(e):
            ext = e if e != ".jpeg" else ".jpg"
            break
    count = _append_inbox_photo(
        user_id, channel_id, channel_type, user_name, data, name or "photo.jpg", ext
    )
    logger.info("repair photo buffered user=%s count=%s", user_id, count)
    wait = 1.0 if count >= 3 else PHOTO_WAIT_SEC
    existing = _flush_tasks.get(user_id)
    if existing and not existing.done():
        existing.cancel()
    _flush_tasks[user_id] = asyncio.create_task(_flush_later(user_id, wait, send_fn))


async def _flush_later(user_id: str, wait: float, send_fn, depth: int = 0) -> None:
    try:
        await asyncio.sleep(wait)
        await _flush_inbox(user_id, send_fn, depth)
    except asyncio.CancelledError:
        return


async def _flush_inbox(user_id: str, send_fn, depth: int = 0) -> None:
    if depth > 6:
        return
    ensure_repair_tables()
    with get_connection() as con:
        meta = con.execute(
            """SELECT channel_id, channel_type, extra_rounds, notified_n, flush_after
               FROM repair_photo_inbox WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        n = con.execute(
            "SELECT COUNT(*) FROM repair_photo_inbox_file WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
    if not meta or n == 0:
        return

    flush_after = float(meta[4] or 0)
    remain = flush_after - time.time()
    if remain > 0.05:
        await _flush_later(user_id, remain, send_fn, depth + 1)
        return

    if n < 3:
        extra = int(meta[2] or 0)
        if extra < PHOTO_MAX_EXTRA_ROUNDS:
            _bump_inbox_wait(user_id)
            await _flush_later(user_id, PHOTO_EXTRA_WAIT_SEC, send_fn, depth + 1)
            return
        notified = int(meta[3] or 0)
        if send_fn and notified != n:
            _mark_inbox_notified(user_id, n)
            await send_fn(
                meta[0],
                f"사진 {n}장 받았어요. 바코드·수선 전·후 포함해서 한 장 더 보내주세요.",
                meta[1],
            )
        return

    claimed = _claim_inbox_photos(user_id, 3)
    if not claimed or not claimed.get("ready"):
        if claimed and claimed.get("count", 0) < 3:
            await _flush_later(user_id, PHOTO_EXTRA_WAIT_SEC, send_fn, depth + 1)
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
        user_id=user_id,
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
