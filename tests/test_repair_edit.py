"""수선 직전 기록 수정. 임시 DB·업로드만 사용."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.bot_intent import (
    ACTION_NONE,
    ACTION_UPDATE,
    DOMAIN_REPAIR,
    TARGET_LAST_SAVED,
    extract_update_fields,
    parse_bot_intent,
)
from backend.app.services.bot_mode import MODE_JOURNAL, MODE_REPAIR, set_mode
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.repair_bot import _save_repair_entry, handle_user_text
from backend.app.services.repair_edit import (
    ALREADY,
    ASK_FIELDS,
    DRAFT_BLOCKED,
    MODE_BLOCKED,
    NO_RECORD,
    apply_owned_repair_fields,
    get_last_saved_id,
    handle_repair_edit,
    remember_last_saved,
)
from logic.db import get_connection


def _ids(suffix: str):
    return f"edit-user-{suffix}", f"edit-ch-{suffix}"


def _enter_repair(uid: str, cid: str) -> None:
    set_mode(uid, cid, MODE_REPAIR)


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


def _cost(record_id: int):
    with get_connection() as con:
        return con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (record_id,)).fetchone()[0]


def _row(record_id: int):
    with get_connection() as con:
        return con.execute(
            "SELECT 업체명, 제품명, 불량명, 작업, 수량, 비용 FROM repair_work_log WHERE id = ?",
            (record_id,),
        ).fetchone()


def _seed_draft(uid: str, cid: str, **extra):
    data = {
        "entry_type": "repair",
        "vendor": "로지킴",
        "product": "릴리프T",
        "defect": "구멍",
        "work_type": "단순바느질",
        "qty": 1,
        "unit_price": 1800,
        **extra,
    }
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data=data,
        missing=["photos"],
        last_question="사진 3장 보내주세요.",
    )
    return dict(data)


def _draft(uid: str, cid: str):
    state = get_conversation_manager().get_state(uid, cid) or {}
    return dict(state.get("pending_data") or {})


def _missing(uid: str, cid: str):
    state = get_conversation_manager().get_state(uid, cid) or {}
    return list(state.get("missing") or [])


def _last_q(uid: str, cid: str):
    state = get_conversation_manager().get_state(uid, cid) or {}
    return state.get("last_question") or ""


def _log_count():
    with get_connection() as con:
        return con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0]


def test_synonyms_map_to_update_last_saved():
    for text in ("직전내용수정", "방금 거 수정", "아까 저장한 거 바꿔"):
        intent = parse_bot_intent(text)
        assert intent.action == ACTION_UPDATE, text
        assert intent.target == TARGET_LAST_SAVED, text
        assert intent.domain == DOMAIN_REPAIR, text
        assert intent.needs_confirmation is True, text
        assert intent.confidence == 1.0, text
        assert intent.explicit_last_saved is True, text


def test_last_saved_hint_plus_fields_intent():
    cases = (
        ("방금 거 금액 2천원으로", {"unit_price": 2000}),
        ("직전 거 1건 말고 3건", {"qty": 3}),
        ("아까 저장한 거 구멍 아니고 지퍼", {"defect": "지퍼"}),
    )
    for text, fields in cases:
        intent = parse_bot_intent(text)
        assert intent.action == ACTION_UPDATE, text
        assert intent.target == TARGET_LAST_SAVED, text
        assert intent.domain == DOMAIN_REPAIR, text
        assert intent.needs_confirmation is True, text
        assert intent.confidence == 1.0, text
        assert intent.fields == fields, (text, intent.fields)
        assert intent.missing_fields == []


def test_missing_fields_when_last_saved_has_no_patch():
    intent = parse_bot_intent("직전내용수정")
    assert intent.fields == {}
    assert intent.missing_fields == ["fields"]
    assert intent.needs_confirmation is True
    assert intent.confidence == 1.0


def test_work_name_with_sujeong_is_not_last_saved_update():
    for text in (
        "기장수정 5000원",
        "사이즈수정 1건 5000원",
        "사이즈변경 5000원",
        "지퍼 바꾸기 5000원",
        "소매 고쳐 3000원",
    ):
        intent = parse_bot_intent(text)
        assert intent.action == ACTION_NONE, text
        assert intent.target != TARGET_LAST_SAVED, text


def test_explicit_change_phrases_still_update_last_saved():
    for text in ("금액 2천원으로 바꿔", "2천원으로 변경", "1건 말고 3건", "방금 거 금액 2천원으로", "직전내용수정"):
        intent = parse_bot_intent(text)
        assert intent.action == ACTION_UPDATE, text
        assert intent.target == TARGET_LAST_SAVED, text


def test_field_complements():
    price = extract_update_fields("금액 2천원으로 바꿔")
    assert price["unit_price"] == 2000
    defect = extract_update_fields("구멍 아니고 지퍼")
    assert defect.get("defect") == "지퍼"
    qty = extract_update_fields("1건 말고 3건")
    assert qty["qty"] == 3


def test_ask_fields_when_no_patch():
    uid, cid = _ids("ask")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    reply = asyncio.run(handle_user_text(uid, cid, "직전내용수정", "테스터"))
    assert ASK_FIELDS in reply
    assert f"#{saved['id']}" in reply
    assert _cost(saved["id"]) == 1500


def test_confirm_then_apply_once():
    uid, cid = _ids("apply")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    assert "변경 전" in preview and "변경 후" in preview
    assert "2,000원" in preview
    assert _cost(saved["id"]) == 1500
    done = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert "수정했어요" in done
    assert _cost(saved["id"]) == 2000
    again = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert ALREADY in again
    assert _cost(saved["id"]) == 2000


def test_cancel_does_not_write():
    uid, cid = _ids("cancel")
    _enter_repair(uid, cid)
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
    _enter_repair(uid, cid)
    _enter_repair(uid, other_cid)
    _enter_repair(other_uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    assert get_last_saved_id(other_uid, cid) is None
    assert get_last_saved_id(uid, other_cid) is None
    other_room = asyncio.run(handle_user_text(uid, other_cid, "직전내용수정", "테스터"))
    other_user = asyncio.run(handle_user_text(other_uid, cid, "금액 2천원으로 바꿔", "다른사람"))
    assert NO_RECORD in other_room
    assert NO_RECORD in other_user
    assert _cost(saved["id"]) == 1500


def test_no_record_does_not_guess():
    uid, cid = _ids("empty")
    _enter_repair(uid, cid)
    _insert(author="다른작성자")
    reply = asyncio.run(handle_user_text(uid, cid, "방금 거 수정", "테스터"))
    assert NO_RECORD in reply


def test_plain_repair_text_still_asks_photos():
    uid, cid = _ids("photos")
    reply = asyncio.run(handle_user_text(uid, cid, "구멍 바느질 1500원", "테스터"))
    assert "사진 3장" in reply


def test_defect_correction_keeps_other_fields():
    uid, cid = _ids("defect")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(uid, cid, "구멍 아니고 지퍼", "테스터"))
    assert "변경 전" in preview
    asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    row = _row(saved["id"])
    assert row[0] == "로지킴"
    assert row[1] == "릴리프T"
    assert row[2] == "지퍼"
    assert row[3] == "단순바느질"
    assert row[4] == 1
    assert row[5] == 1500


def test_draft_field_fix_does_not_touch_last_saved():
    uid, cid = _ids("draft-fix")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    _seed_draft(uid, cid)
    reply = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    assert "변경 전" not in reply
    assert DRAFT_BLOCKED not in reply
    assert _cost(saved["id"]) == 1500
    after = _draft(uid, cid)
    assert after.get("entry_type") == "repair"


def test_handle_user_text_applies_price_to_existing_draft():
    uid, cid = _ids("draft-e2e")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    before_row = _row(saved["id"])
    _seed_draft(uid, cid, unit_price=1500, work_type="단순바느질", qty=1)
    before_q = _last_q(uid, cid)
    reply = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    after = _draft(uid, cid)
    assert after.get("unit_price") == 2000
    assert after.get("work_type") == "단순바느질"
    assert after.get("qty") == 1
    assert after.get("entry_type") == "repair"
    assert _missing(uid, cid) == ["photos"]
    assert _last_q(uid, cid) == before_q
    assert _row(saved["id"]) == before_row
    assert _cost(saved["id"]) == 1500
    assert "사진 3장" in reply
    assert "2,000원" in reply
    assert "변경 전" not in reply
    assert "저장할까요" not in reply


def test_explicit_last_saved_blocked_while_draft_exists():
    uid, cid = _ids("draft-block")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    before_draft = _seed_draft(uid, cid)
    reply = asyncio.run(handle_user_text(uid, cid, "직전내용수정", "테스터"))
    assert reply == DRAFT_BLOCKED
    assert _cost(saved["id"]) == 1500
    assert _draft(uid, cid) == before_draft
    assert handle_repair_edit(uid, cid, "방금 저장한 일지 수정", "테스터") == DRAFT_BLOCKED
    assert _draft(uid, cid) == before_draft
    assert _cost(saved["id"]) == 1500


def test_hint_plus_fields_previews_last_saved_without_draft():
    uid, cid = _ids("hint-preview")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(uid, cid, "방금 거 금액 2천원으로", "테스터"))
    assert "변경 전" in preview and "변경 후" in preview
    assert "2,000원" in preview
    assert _cost(saved["id"]) == 1500


def test_confirm_yes_updates_amount_once():
    uid, cid = _ids("yes-once")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    asyncio.run(handle_user_text(uid, cid, "방금 거 금액 2천원으로", "테스터"))
    assert _cost(saved["id"]) == 1500
    done = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert "수정했어요" in done
    assert _cost(saved["id"]) == 2000
    again = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert ALREADY in again
    assert _cost(saved["id"]) == 2000


def test_mode_change_during_confirm_rejects_update():
    uid, cid = _ids("mode-guard")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    assert "변경 전" in preview
    set_mode(uid, cid, MODE_JOURNAL)
    reply = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert MODE_BLOCKED in reply
    assert _cost(saved["id"]) == 1500
    pending = get_conversation_manager().get_state(uid, cid)
    assert not pending or (pending.get("pending_data") or {}).get("entry_type") != "repair_update"


def test_non_allowlist_field_rejected():
    uid, cid = _ids("allowlist")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    result = apply_owned_repair_fields(
        uid, cid, saved["id"], {"secret_note": "hack", "unit_price": 2000}, "테스터"
    )
    assert result.get("success") is False
    assert result.get("error") == "field_not_allowed"
    assert _cost(saved["id"]) == 1500
    assert _row(saved["id"])[5] == 1500


def test_existing_photo_intake_and_repair_save_regression():
    uid, cid = _ids("regress")
    _enter_repair(uid, cid)
    reply = asyncio.run(handle_user_text(uid, cid, "구멍 바느질 1500원", "테스터"))
    assert "사진 3장" in reply
    with get_connection() as con:
        before_count = con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0]
    saved = _save_repair_entry(
        {
            "vendor": "로지킴",
            "product": "릴리프T",
            "defect": "구멍",
            "work_type": "단순바느질",
            "qty": 1,
            "unit_price": 1500,
            "entry_type": "repair",
        },
        "테스터",
        True,
        uid,
        cid,
    )
    assert saved.get("success")
    assert get_last_saved_id(uid, cid) == saved["id"]
    with get_connection() as con:
        after_count = con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0]
    assert after_count == before_count + 1
    assert _cost(saved["id"]) == 1500


def test_applied_yes_then_new_repair_text_starts_photos():
    uid, cid = _ids("applied-new")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    done = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert "수정했어요" in done
    assert _cost(saved["id"]) == 2000
    reply = asyncio.run(handle_user_text(uid, cid, "구멍 바느질 1500원", "테스터"))
    assert ALREADY not in reply
    assert "사진 3장" in reply
    assert _cost(saved["id"]) == 2000


def test_applied_yes_then_yes_again_is_already():
    uid, cid = _ids("applied-yes")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    asyncio.run(handle_user_text(uid, cid, "직전내용수정", "테스터"))
    asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert _cost(saved["id"]) == 2000
    again = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert ALREADY in again
    assert _cost(saved["id"]) == 2000


def test_first_input_price_fix_keeps_photos_missing():
    uid, cid = _ids("first-price")
    _enter_repair(uid, cid)
    first = asyncio.run(handle_user_text(uid, cid, "구멍 바느질 1500원", "테스터"))
    assert "사진 3장" in first
    before = _draft(uid, cid)
    assert before.get("unit_price") == 1500
    assert not before.get("vendor")
    assert not before.get("product")
    assert "photos" in _missing(uid, cid)
    before_count = _log_count()
    reply = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    after = _draft(uid, cid)
    assert after.get("unit_price") == 2000
    assert after.get("work_type") == before.get("work_type")
    assert after.get("qty") == before.get("qty")
    assert after.get("defect") == before.get("defect")
    assert "photos" in _missing(uid, cid)
    assert not after.get("vendor")
    assert not after.get("product")
    assert "사진 3장" in reply
    assert "저장할까요" not in reply
    assert _log_count() == before_count


def test_second_price_edit_uses_current_db_before():
    uid, cid = _ids("second-price")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert _cost(saved["id"]) == 2000
    preview = asyncio.run(handle_user_text(uid, cid, "금액 3천원으로 바꿔", "테스터"))
    assert "변경 전" in preview and "변경 후" in preview
    assert "2,000원" in preview
    assert "3,000원" in preview
    before_line = preview.split("변경 후")[0]
    assert "2,000원" in before_line
    assert "1,500원" not in before_line
    assert _cost(saved["id"]) == 2000


def test_remember_last_saved_failure_keeps_save_success():
    uid, cid = _ids("pointer-fail")
    _enter_repair(uid, cid)
    before_count = _log_count()
    with patch(
        "backend.app.services.repair_edit.remember_last_saved",
        side_effect=RuntimeError("pointer fail"),
    ):
        saved = _save_repair_entry(
            {
                "vendor": "로지킴",
                "product": "릴리프T",
                "defect": "구멍",
                "work_type": "단순바느질",
                "qty": 1,
                "unit_price": 1500,
                "entry_type": "repair",
            },
            "테스터",
            True,
            uid,
            cid,
        )
    assert saved.get("success")
    assert saved.get("id")
    assert _log_count() == before_count + 1
    assert _cost(saved["id"]) == 1500
    assert get_last_saved_id(uid, cid) is None


def test_plain_price_answer_follows_existing_draft_flow():
    uid, cid = _ids("plain-price")
    _enter_repair(uid, cid)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "릴리프T",
            "defect": "구멍",
            "work_type": "단순바느질",
        },
        missing=["unit_price"],
        last_question="금액이 얼마예요?",
    )
    assert handle_repair_edit(uid, cid, "1500원", "테스터") is None
    reply = asyncio.run(handle_user_text(uid, cid, "1500원", "테스터"))
    assert _draft(uid, cid).get("unit_price") == 1500
    assert "변경 전" not in reply
    assert "바꿨어요" not in reply
    assert "몇 건" in reply or "저장할까요" in reply


def test_plain_qty_answer_saves_during_price_confirm():
    uid, cid = _ids("plain-qty")
    _enter_repair(uid, cid)
    before_count = _log_count()
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "릴리프T",
            "defect": "구멍",
            "work_type": "단순바느질",
            "unit_price": 1500,
            "price_stated": True,
            "awaiting_price_confirm": True,
            "user_name": "테스터",
        },
        missing=["qty"],
        last_question="구멍 / 단순바느질 1,500원 맞아요? 몇 건이에요?",
    )
    assert handle_repair_edit(uid, cid, "1건", "테스터") is None
    reply = asyncio.run(handle_user_text(uid, cid, "1건", "테스터"))
    assert "변경 전" not in reply
    assert "바꿨어요" not in reply
    assert "✅" in reply
    assert _log_count() == before_count + 1


def test_awaiting_confirm_rebuilds_question_with_new_price():
    uid, cid = _ids("rebuild-q")
    _enter_repair(uid, cid)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "릴리프T",
            "defect": "구멍",
            "work_type": "단순바느질",
            "unit_price": 1500,
            "qty": 1,
            "price_stated": True,
            "awaiting_price_confirm": True,
        },
        missing=["qty"],
        last_question="구멍 / 단순바느질 1,500원 1건으로 저장할까요?",
    )
    before_count = _log_count()
    reply = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    after = _draft(uid, cid)
    assert after.get("unit_price") == 2000
    assert after.get("awaiting_price_confirm") is True
    assert after.get("qty") == 1
    assert "photos" not in _missing(uid, cid)
    assert "2,000원" in reply
    assert "1,500원" not in reply
    assert "1,500원" not in _last_q(uid, cid)
    assert "저장할까요" in reply
    assert _log_count() == before_count


def test_work_name_sujeong_starts_new_repair_not_last_saved():
    uid, cid = _ids("gijang")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    reply = asyncio.run(handle_user_text(uid, cid, "기장수정 5000원", "테스터"))
    assert "변경 전" not in reply
    assert ASK_FIELDS not in reply
    assert "수정할까요" not in reply
    assert "사진 3장" in reply or "업체명" in reply or "제품명" in reply
    assert _cost(saved["id"]) == 1500
    other = asyncio.run(handle_user_text(*_ids("size-mod"), "사이즈수정 1건 5000원", "테스터"))
    assert "변경 전" not in other
    assert "수정할까요" not in other
    assert "사진 3장" in other or "업체명" in other or "제품명" in other


def _assert_new_repair_reply(reply: str) -> None:
    assert "변경 전" not in reply
    assert ASK_FIELDS not in reply
    assert "수정할까요" not in reply
    assert "사진 3장" in reply or "업체명" in reply or "제품명" in reply


def test_handle_user_text_work_names_are_new_repair():
    for i, text in enumerate(("기장수정 5000원", "사이즈변경 5000원", "지퍼 바꾸기 5000원", "소매 고쳐 3000원")):
        uid, cid = _ids(f"new-work-{i}")
        _enter_repair(uid, cid)
        saved = _insert()
        remember_last_saved(uid, cid, saved["id"])
        reply = asyncio.run(handle_user_text(uid, cid, text, "테스터"))
        _assert_new_repair_reply(reply)
        assert _cost(saved["id"]) == 1500


def test_handle_user_text_keeps_existing_last_saved_phrases():
    cases = (
        ("금액 2천원으로 바꿔", "2,000원"),
        ("2천원으로 변경", "2,000원"),
        ("1건 말고 3건", "3건"),
        ("방금 거 금액 2천원으로", "2,000원"),
    )
    for i, (text, marker) in enumerate(cases):
        uid, cid = _ids(f"keep-upd-{i}")
        _enter_repair(uid, cid)
        saved = _insert()
        remember_last_saved(uid, cid, saved["id"])
        reply = asyncio.run(handle_user_text(uid, cid, text, "테스터"))
        assert "변경 전" in reply, text
        assert marker in reply, text
        assert _cost(saved["id"]) == 1500
    uid, cid = _ids("keep-explicit")
    _enter_repair(uid, cid)
    saved = _insert()
    remember_last_saved(uid, cid, saved["id"])
    reply = asyncio.run(handle_user_text(uid, cid, "직전내용수정", "테스터"))
    assert ASK_FIELDS in reply
    assert _cost(saved["id"]) == 1500


def test_draft_price_question_advances_after_explicit_change():
    uid, cid = _ids("price-next")
    _enter_repair(uid, cid)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "릴리프T",
            "defect": "구멍",
            "work_type": "단순바느질",
        },
        missing=["unit_price"],
        last_question="금액이 얼마예요?",
    )
    reply = asyncio.run(handle_user_text(uid, cid, "금액 2천원으로 바꿔", "테스터"))
    assert _draft(uid, cid).get("unit_price") == 2000
    assert "금액이 얼마예요?" not in reply
    assert "금액이 얼마예요?" not in _last_q(uid, cid)
    assert "몇 건" in reply or "저장할까요" in reply
    assert "unit_price" not in _missing(uid, cid)
    assert "변경 전" not in reply
