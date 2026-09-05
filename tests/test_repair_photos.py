"""수선 사진 정책: 바코드만 찾고, 2장 이상 여러 장을 저장한다."""
from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.barcode_decode import classify_photos
from backend.app.services import repair_bot as rb
from backend.app.services.repair_bot import (
    BufferedPhoto,
    finalize_photo_set,
    handle_user_text,
)
from logic.db import get_connection


def _ids(suffix: str):
    return f"photo-user-{suffix}", f"photo-ch-{suffix}"


def test_classify_no_barcode_uses_send_order(monkeypatch):
    async def no_vision(photos):
        return [None] * len(photos)

    monkeypatch.setattr("backend.app.services.barcode_decode.decode_local", lambda data: None)
    monkeypatch.setattr("backend.app.services.barcode_decode.decode_set_vision", no_vision)
    result = asyncio.run(classify_photos([b"a", b"b", b"c"]))
    assert result["barcode"] is None
    assert result["barcode_index"] == 0
    assert result["before_index"] == 1
    assert result["after_index"] == 2
    assert result["order_fallback"] is True


def test_classify_barcode_rest_in_send_order(monkeypatch):
    async def no_vision(photos):
        return [None] * len(photos)

    def local(data):
        if data == b"BAR":
            return ("ON56S152917", 0.95)
        return None

    monkeypatch.setattr("backend.app.services.barcode_decode.decode_local", local)
    monkeypatch.setattr("backend.app.services.barcode_decode.decode_set_vision", no_vision)
    result = asyncio.run(classify_photos([b"one", b"BAR", b"two"]))
    assert result["barcode"] == "ON56S152917"
    assert result["barcode_index"] == 1
    assert result["before_index"] == 0
    assert result["after_index"] == 2
    assert result["order_fallback"] is False


def test_finalize_keeps_all_three_photos():
    uid, cid = _ids("keep")
    photos = [
        BufferedPhoto(data=b"bar-bytes", name="barcode.jpg"),
        BufferedPhoto(data=b"p1-bytes", name="p1.jpg"),
        BufferedPhoto(data=b"p2-bytes", name="p2.jpg"),
    ]
    asyncio.run(finalize_photo_set(
        user_id=uid,
        channel_id=cid,
        photos=photos,
        user_name="테스터",
        classified={
            "barcode": "ON56S152917",
            "barcode_index": 0,
            "before_index": 1,
            "after_index": 2,
            "ambiguous": False,
            "order_fallback": False,
        },
    ))
    data = rb._get_pending(uid, cid)
    assert data.get("barcode_image")
    assert data.get("before_image")
    assert data.get("after_image")
    assert data["barcode_image"] != data["before_image"]
    assert data["before_image"] != data["after_image"]
    root = Path(rb._inbox_dir())
    for key in ("barcode_image", "before_image", "after_image"):
        assert (root / data[key]).is_file()


def test_unread_barcode_keeps_first_three_in_send_order():
    uid, cid = _ids("unread")
    photos = [
        BufferedPhoto(data=b"tmp-bar", name="tmp.jpg"),
        BufferedPhoto(data=b"save-1", name="one.jpg"),
        BufferedPhoto(data=b"save-2", name="two.jpg"),
    ]
    reply = asyncio.run(finalize_photo_set(
        user_id=uid,
        channel_id=cid,
        photos=photos,
        user_name="테스터",
        classified={
            "barcode": None,
            "barcode_index": 0,
            "before_index": 1,
            "after_index": 2,
            "ambiguous": False,
            "order_fallback": True,
        },
    ))
    assert "직접 입력" in reply
    data = rb._get_pending(uid, cid)
    root = Path(rb._inbox_dir())
    assert (root / data["barcode_image"]).read_bytes() == b"tmp-bar"
    assert (root / data["before_image"]).read_bytes() == b"save-1"
    assert (root / data["after_image"]).read_bytes() == b"save-2"


def test_manual_barcode_does_not_delete_photos():
    uid, cid = _ids("manual")
    asyncio.run(finalize_photo_set(
        user_id=uid,
        channel_id=cid,
        photos=[
            BufferedPhoto(data=b"keep-bar", name="b.jpg"),
            BufferedPhoto(data=b"keep-1", name="1.jpg"),
            BufferedPhoto(data=b"keep-2", name="2.jpg"),
        ],
        classified={
            "barcode": None,
            "barcode_index": 0,
            "before_index": 1,
            "after_index": 2,
            "ambiguous": False,
            "order_fallback": True,
        },
    ))
    before = rb._get_pending(uid, cid)
    names = [before["barcode_image"], before["before_image"], before["after_image"]]
    asyncio.run(handle_user_text(uid, cid, "ON56S152917", "테스터"))
    after = rb._get_pending(uid, cid)
    assert after.get("barcode") == "ON56S152917"
    assert after.get("barcode_image") == names[0]
    assert after.get("before_image") == names[1]
    assert after.get("after_image") == names[2]
    root = Path(rb._inbox_dir())
    for name in names:
        assert (root / name).is_file()


def test_insert_keeps_barcode_image_column():
    saved = insert_repair_log_record(
        날짜="2026-09-05",
        작업="단순바느질",
        비용=1500,
        업체명="로지킴",
        제품명="릴리프T",
        바코드="ON56S152917",
        barcode_image="bar-keep.jpg",
        before_image="before-keep.jpg",
        after_image="after-keep.jpg",
        작성자="테스터",
        출처="bot",
    )
    with get_connection() as con:
        row = con.execute(
            "SELECT barcode_image, before_image, after_image FROM repair_work_log WHERE id = ?",
            (saved["id"],),
        ).fetchone()
    assert row == ("bar-keep.jpg", "before-keep.jpg", "after-keep.jpg")


def test_claim_takes_all_photos_when_ready():
    uid, cid = _ids("claim")
    rb.clear_photo_inbox(uid, cid)
    for i in range(5):
        rb._append_inbox_photo(uid, cid, "group", "n", f"P{i}".encode(), f"p{i}.jpg", ".jpg")
    claimed = rb._claim_inbox_photos(uid, cid, 2)
    assert claimed and claimed["ready"]
    assert [p.data for p in claimed["photos"]] == [b"P0", b"P1", b"P2", b"P3", b"P4"]
    assert rb._inbox_count(uid, cid) == 0


def test_read_error_keeps_readable_photos():
    uid, cid = _ids("readerr")
    rb.clear_photo_inbox(uid, cid)
    rb._append_inbox_photo(uid, cid, "group", "n", b"good-a", "a.jpg", ".jpg")
    rb._append_inbox_photo(uid, cid, "group", "n", b"good-b", "b.jpg", ".jpg")
    rb._append_inbox_photo(uid, cid, "group", "n", b"gone", "c.jpg", ".jpg")
    with get_connection() as con:
        row = con.execute(
            """SELECT filename FROM repair_photo_inbox_file_v2
               WHERE user_id = ? AND channel_id = ? ORDER BY id""",
            (uid, cid),
        ).fetchall()
    gone = Path(rb._inbox_dir()) / row[2][0]
    gone.unlink()
    claimed = rb._claim_inbox_photos(uid, cid, 2)
    assert claimed and not claimed["ready"]
    assert claimed.get("read_error") is True
    assert rb._inbox_count(uid, cid) == 2


def test_two_photos_are_enough():
    uid, cid = _ids("two")
    asyncio.run(finalize_photo_set(
        user_id=uid,
        channel_id=cid,
        photos=[
            BufferedPhoto(data=b"bar-2", name="b.jpg"),
            BufferedPhoto(data=b"p1-2", name="1.jpg"),
        ],
        classified={
            "barcode": "ON56S152917",
            "barcode_index": 0,
            "before_index": 1,
            "after_index": None,
            "ambiguous": False,
        },
    ))
    data = rb._get_pending(uid, cid)
    assert data.get("barcode_image")
    assert data.get("before_image")
    assert not data.get("after_image")
    assert not data.get("extra_images")


def test_four_photos_keep_extras():
    uid, cid = _ids("four")
    asyncio.run(finalize_photo_set(
        user_id=uid,
        channel_id=cid,
        photos=[
            BufferedPhoto(data=b"bar-4", name="b.jpg"),
            BufferedPhoto(data=b"p1-4", name="1.jpg"),
            BufferedPhoto(data=b"p2-4", name="2.jpg"),
            BufferedPhoto(data=b"p3-4", name="3.jpg"),
        ],
        classified={
            "barcode": "ON56S152917",
            "barcode_index": 0,
            "before_index": 1,
            "after_index": 2,
            "ambiguous": False,
        },
    ))
    data = rb._get_pending(uid, cid)
    extras = data.get("extra_images") or []
    assert len(extras) == 1
    root = Path(rb._inbox_dir())
    assert (root / extras[0]).read_bytes() == b"p3-4"


def test_insert_keeps_extra_images():
    saved = insert_repair_log_record(
        날짜="2026-09-05",
        작업="단순바느질",
        비용=1500,
        업체명="로지킴",
        제품명="릴리프T",
        extra_images=["extra-a.jpg", "extra-b.jpg"],
        작성자="테스터",
        출처="bot",
    )
    with get_connection() as con:
        row = con.execute(
            "SELECT extra_images FROM repair_work_log WHERE id = ?",
            (saved["id"],),
        ).fetchone()
    assert "extra-a.jpg" in (row[0] or "")
    assert "extra-b.jpg" in (row[0] or "")


def test_late_photos_attach_to_current_case():
    uid, cid = _ids("late")
    rb.clear_photo_inbox(uid, cid)
    asyncio.run(finalize_photo_set(
        user_id=uid,
        channel_id=cid,
        photos=[
            BufferedPhoto(data=b"b", name="b.jpg"),
            BufferedPhoto(data=b"1", name="1.jpg"),
        ],
        classified={
            "barcode": "ON56S152917",
            "barcode_index": 0,
            "before_index": 1,
            "after_index": None,
            "ambiguous": False,
        },
    ))
    rb._append_inbox_photo(uid, cid, "group", "n", b"late", "late.jpg", ".jpg")
    rb._keep_overflow_off_next_case(uid, cid)
    assert rb._inbox_count(uid, cid) == 0
    data = rb._get_pending(uid, cid)
    extras = data.get("extra_images") or []
    assert len(extras) == 1
    assert (Path(rb._inbox_dir()) / extras[0]).is_file()
