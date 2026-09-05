"""수선 직전 기록 수정. 임시 DB·업로드만 사용."""
from __future__ import annotations

import asyncio

from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.bot_intent import (
    ACTION_UPDATE,
    TARGET_LAST_SAVED,
    extract_update_fields,
    parse_bot_intent,
)
from backend.app.services.repair_bot import handle_user_text
from backend.app.services.repair_edit import (
    ALREADY,
    ASK_FIELDS,
    NO_RECORD,
    get_last_saved_id,
    remember_last_saved,
)
from logic.db import get_connection


def _ids(suffix: str):
    return f"edit-user-{suffix}", f"edit-ch-{suffix}"


def _insert(vendor="로지킴", product="릴리프T", work="단순바느질", defect="구멍", qty=1, cost=1500, author="테스터"):
    return insert_repair_log_record(
        날짜="2026-09-05",
        작업=work,
        비용=cost,
        업체명=vendor,
        제품명=product,
        불량명=defect,
        수량=qty,
        작성자=author,
        출처="bot",
    )


def test_synonyms_map_to_update_last_saved():
    for text in ("직전내용수정", "방금 거 수정", "아까 저장한 거 바꿔"):
        intent = parse_bot_intent(text)
        assert intent.action == ACTION_UPDATE, text
        assert intent.target == TARGET_LAST_SAVED, text


def test_field_complements():
    price = extract_update_fields("금액 2천원으로 바꿔")
    assert price["unit_price"] == 2000
    defect = extract_update_fields("구멍 아니고 지퍼")
    assert defect.get("defect") in ("지퍼", "구멍") or "지퍼" in str(defect.values())
    # 아니고 뒤의 값이 우선
    assert defect.get("defect") == "지퍼" or "지퍼" in (defect.get("defect") or "")
    qty = extract_update_fields("1건 말고 3건")
    assert qty["qty"] == 3


def test_ask_fields_when_no_patch():
    uid, cid = _ids("ask")
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    reply = asyncio.run(handle_user_text(uid, cid, "직전내용수정", "테스터"))
    assert ASK_FIELDS in reply
    assert f"#{saved['id']}" in reply
    with get_connection() as con:
        cost = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert cost == 1500


def test_confirm_then_apply_once():
    uid, cid = _ids("apply")
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    assert "변경 전" in preview and "변경 후" in preview
    assert "2,000원" in preview
    with get_connection() as con:
        before = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert before == 1500
    done = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert "수정했어요" in done
    with get_connection() as con:
        after = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert after == 2000
    again = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert ALREADY in again
    with get_connection() as con:
        still = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert still == 2000


def test_cancel_does_not_write():
    uid, cid = _ids("cancel")
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    asyncio.run(handle_user_text(uid, cid, "1건 말고 3건", "테스터"))
    reply = asyncio.run(handle_user_text(uid, cid, "취소", "테스터"))
    assert "취소" in reply
    with get_connection() as con:
        qty = con.execute("SELECT 수량 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert qty == 1


def test_room_and_user_isolation():
    uid, cid = _ids("iso")
    other_uid, other_cid = _ids("iso-other")
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    assert get_last_saved_id(other_uid, cid) is None
    assert get_last_saved_id(uid, other_cid) is None
    other_room = asyncio.run(handle_user_text(uid, other_cid, "직전내용수정", "테스터"))
    other_user = asyncio.run(handle_user_text(other_uid, cid, "금액 2천원으로 바꿔", "다른사람"))
    assert NO_RECORD in other_room
    assert NO_RECORD in other_user
    with get_connection() as con:
        cost = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert cost == 1500


def test_no_record_does_not_guess():
    uid, cid = _ids("empty")
    _insert(author="다른작성자")
    reply = asyncio.run(handle_user_text(uid, cid, "방금 거 수정", "테스터"))
    assert NO_RECORD in reply


def test_plain_repair_text_still_asks_photos():
    uid, cid = _ids("photos")
    reply = asyncio.run(handle_user_text(uid, cid, "구멍 바느질 1500원", "테스터"))
    assert "사진 3장" in reply


def test_defect_correction_keeps_other_fields():
    uid, cid = _ids("defect")
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(uid, cid, "구멍 아니고 지퍼", "테스터"))
    assert "변경 전" in preview
    asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    with get_connection() as con:
        row = con.execute(
            "SELECT 불량명, 작업, 수량, 비용 FROM repair_work_log WHERE id = ?",
            (saved["id"],),
        ).fetchone()
    assert row[0] == "지퍼"
    assert row[1] == "단순바느질"
    assert row[2] == 1
    assert row[3] == 1500
