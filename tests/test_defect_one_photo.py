"""바코드 번호+제품 사진 1장, 그리고 바코드 사진+제품 사진."""
from __future__ import annotations

import asyncio

from backend.app.api.repair_log import ensure_repair_tables
from backend.app.services.bot_mode import MODE_DEFECT, MODE_REPAIR, set_mode
from backend.app.services.defect_bot import (
    DEFECT_ONE_PHOTO_MSG,
    finalize_defect_photo_set,
)
from backend.app.services.defect_bot import _get_pending
from backend.app.services.defect_bot import handle_user_text as handle_defect_text
from backend.app.services.repair_bot import finalize_photo_set
from backend.app.services.repair_bot import handle_user_text as handle_repair_text
from backend.app.services.repair_bot import _get_pending as repair_pending
from backend.app.services.repair_bot import (
    PHOTO_MAX_EXTRA_ROUNDS,
    PHOTO_MIN_SIZE,
    BufferedPhoto,
    _append_inbox_photo,
    _flush_inbox,
    _inbox_count,
    photo_set_need,
)
from logic.db import get_connection

BARCODE = "ON56S152917"


def _ids(suffix: str):
    return f"defect-one-{suffix}", f"defect-ch-{suffix}"


def _seed_barcode():
    ensure_repair_tables()
    with get_connection() as con:
        con.execute(
            "INSERT OR REPLACE INTO repair_barcode (바코드, 업체명, 제품명, 옵션) VALUES (?, ?, ?, ?)",
            (BARCODE, "로지킴", "릴리프T", "블랙"),
        )
        con.commit()


def test_photo_need_is_one_only_after_defect_barcode():
    uid, cid = _ids("need")
    _seed_barcode()
    set_mode(uid, cid, MODE_REPAIR)
    assert PHOTO_MIN_SIZE == 2
    assert photo_set_need(uid, cid) == 2
    set_mode(uid, cid, MODE_DEFECT)
    assert photo_set_need(uid, cid) == 2
    reply = asyncio.run(handle_defect_text(uid, cid, BARCODE, "테스터"))
    assert "제품 사진 1장" in reply
    assert photo_set_need(uid, cid) == 1


def test_typed_barcode_keeps_single_product_photo():
    uid, cid = _ids("keep")
    _seed_barcode()
    set_mode(uid, cid, MODE_DEFECT)
    asyncio.run(handle_defect_text(uid, cid, BARCODE, "테스터"))
    reply = asyncio.run(finalize_defect_photo_set(
        uid,
        cid,
        [BufferedPhoto(data=b"product-photo", name="shirt.jpg")],
        "테스터",
        classified={
            "barcode": "OTHER1CODE",
            "barcode_index": 0,
            "ambiguous": False,
        },
    ))
    data = _get_pending(uid, cid)
    assert data["barcode"] == BARCODE
    assert data["vendor"] == "로지킴"
    assert data.get("before_image")
    assert "불량명" in reply
    assert "저장할까요" not in reply


def test_photo_waiting_then_barcode_text_attaches_it():
    uid, cid = _ids("order")
    _seed_barcode()
    set_mode(uid, cid, MODE_DEFECT)
    _append_inbox_photo(uid, cid, "group", "테스터", b"shirt-bytes", "shirt.jpg", ".jpg")
    reply = asyncio.run(handle_defect_text(uid, cid, BARCODE, "테스터"))
    assert _inbox_count(uid, cid) == 0
    data = _get_pending(uid, cid)
    assert data["barcode"] == BARCODE
    assert data.get("before_image")
    assert "불량명" in reply


def test_barcode_then_one_photo_then_save():
    uid, cid = _ids("save")
    _seed_barcode()
    set_mode(uid, cid, MODE_DEFECT)
    asyncio.run(handle_defect_text(uid, cid, BARCODE, "테스터"))
    _append_inbox_photo(uid, cid, "group", "테스터", b"shirt-bytes", "shirt.jpg", ".jpg")
    with get_connection() as con:
        con.execute(
            "UPDATE repair_photo_inbox_v2 SET flush_after = 0 WHERE user_id = ? AND channel_id = ?",
            (uid, cid),
        )
        con.commit()
    sent = []

    async def send_fn(ch, msg, typ="group"):
        sent.append((ch, msg))

    asyncio.run(_flush_inbox(uid, cid, send_fn))
    assert sent and sent[0][0] == cid
    assert "불량명" in sent[0][1]
    assert _inbox_count(uid, cid) == 0
    confirm = asyncio.run(handle_defect_text(uid, cid, "구멍", "테스터"))
    assert "저장할까요" in confirm
    saved = asyncio.run(handle_defect_text(uid, cid, "네", "테스터"))
    assert "저장" in saved
    with get_connection() as con:
        row = con.execute(
            "SELECT 바코드, 불량명, before_image, 업체명 FROM defect_log"
        ).fetchone()
    assert row[0] == BARCODE
    assert row[1] == "구멍"
    assert row[2]
    assert row[3] == "로지킴"


def test_one_photo_without_barcode_asks_for_number_in_defect_only():
    uid, cid = _ids("wait")
    set_mode(uid, cid, MODE_REPAIR)
    _append_inbox_photo(uid, cid, "group", "테스터", b"only", "only.jpg", ".jpg")
    with get_connection() as con:
        con.execute(
            """UPDATE repair_photo_inbox_v2
               SET flush_after = 0, extra_rounds = ?
               WHERE user_id = ? AND channel_id = ?""",
            (PHOTO_MAX_EXTRA_ROUNDS, uid, cid),
        )
        con.commit()
    sent = []

    async def send_fn(ch, msg, typ="group"):
        sent.append(msg)

    asyncio.run(_flush_inbox(uid, cid, send_fn))
    assert sent and "한 장 더" in sent[0]
    assert _inbox_count(uid, cid) == 1

    set_mode(uid, cid, MODE_DEFECT)
    with get_connection() as con:
        con.execute(
            """UPDATE repair_photo_inbox_v2
               SET flush_after = 0, extra_rounds = ?, notified_n = 0
               WHERE user_id = ? AND channel_id = ?""",
            (PHOTO_MAX_EXTRA_ROUNDS, uid, cid),
        )
        con.commit()
    sent.clear()
    asyncio.run(_flush_inbox(uid, cid, send_fn))
    assert sent == [DEFECT_ONE_PHOTO_MSG]
    assert _inbox_count(uid, cid) == 1


def test_two_photos_keep_barcode_from_image():
    uid, cid = _ids("pair")
    _seed_barcode()
    set_mode(uid, cid, MODE_DEFECT)
    reply = asyncio.run(finalize_defect_photo_set(
        uid,
        cid,
        [
            BufferedPhoto(data=b"barcode-photo", name="barcode.jpg"),
            BufferedPhoto(data=b"product-photo", name="shirt.jpg"),
        ],
        "테스터",
        classified={
            "barcode": BARCODE,
            "barcode_index": 0,
            "before_index": 1,
            "ambiguous": False,
        },
    ))
    data = _get_pending(uid, cid)
    assert data["barcode"] == BARCODE
    assert data["vendor"] == "로지킴"
    assert data.get("before_image")
    assert not data.get("barcode_image")
    assert "불량명" in reply


def test_repair_typed_barcode_then_one_photo():
    uid, cid = _ids("repair-one")
    _seed_barcode()
    set_mode(uid, cid, MODE_REPAIR)
    assert photo_set_need(uid, cid) == 2
    reply = asyncio.run(handle_repair_text(uid, cid, BARCODE, "테스터"))
    assert "제품 사진 1장" in reply
    assert photo_set_need(uid, cid) == 1
    reply = asyncio.run(finalize_photo_set(
        uid,
        cid,
        [BufferedPhoto(data=b"product-photo", name="shirt.jpg")],
        "테스터",
        classified={"barcode": "OTHER1CODE", "barcode_index": 0, "ambiguous": False},
    ))
    data = repair_pending(uid, cid)
    assert data["barcode"] == BARCODE
    assert data["vendor"] == "로지킴"
    assert data.get("before_image")
    assert "작업" in reply


def test_repair_two_photos_still_read_barcode_image():
    uid, cid = _ids("repair-pair")
    _seed_barcode()
    set_mode(uid, cid, MODE_REPAIR)
    asyncio.run(handle_repair_text(uid, cid, "ON00TYPED1", "테스터"))
    reply = asyncio.run(finalize_photo_set(
        uid,
        cid,
        [
            BufferedPhoto(data=b"barcode-photo", name="barcode.jpg"),
            BufferedPhoto(data=b"product-photo", name="shirt.jpg"),
        ],
        "테스터",
        classified={
            "barcode": BARCODE,
            "barcode_index": 0,
            "before_index": 1,
            "ambiguous": False,
        },
    ))
    data = repair_pending(uid, cid)
    assert data["barcode"] == BARCODE
    assert data["vendor"] == "로지킴"
    assert data.get("before_image")
    assert not data.get("barcode_image")
    assert "작업" in reply
