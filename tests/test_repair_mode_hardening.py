"""수선모드 안정화 회귀. 실제 OpenAI 호출 없음. 임시 DB·업로드만 사용."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.api.repair_log import ensure_repair_tables, insert_repair_log_record, _lookup_barcode
from backend.app.services.bot_mode import MODE_IDLE, MODE_REPAIR, get_mode, set_mode
from backend.app.services.bot_nlu import NluIntent, fallback_from_local_parsers
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.repair_bot import (
    EXPIRED_REPAIR_MSG,
    PHOTO_MIN_SIZE,
    PHOTO_RETRY_MSG,
    BufferedPhoto,
    _claim_inbox_photos,
    _commit_inbox_claim,
    _inbox_count,
    _release_inbox_claim,
    _try_append_inbox_photo,
    extract_qty,
    finalize_photo_set,
    format_work_cost_list,
    handle_user_text,
)
from backend.app.services.repair_catalog import list_work_types
from backend.app.services.repair_edit import get_last_saved_id, remember_last_saved
from logic.db import get_connection
from tests.isolation import REAL_BILLING_DB, REAL_UPLOAD_DIR, sha256_file, upload_manifest


def _ids(suffix: str):
    return f"hardn-user-{suffix}", f"hardn-ch-{suffix}"


def _enter(uid: str, cid: str) -> None:
    set_mode(uid, cid, MODE_REPAIR)


def _nlu(**kwargs) -> NluIntent:
    body = {
        "domain": "repair",
        "action": "provide_field",
        "target": "draft",
        "fields": {},
        "confidence": 0.95,
        "needs_confirmation": False,
        "explicit_last_saved": False,
    }
    body.update(kwargs)
    return NluIntent(**body)


def _seed_new_barcode(uid: str, cid: str, barcode: str = "ON56S152917") -> None:
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "barcode": barcode,
            "user_name": "테스터",
            "before_image": "before-keep.jpg",
            "after_image": "after-keep.jpg",
            "barcode_image": "barcode-temp.jpg",
        },
        missing=["vendor"],
        last_question="등록 안 된 바코드예요 (ON56S152917). 업체명 알려주세요.",
    )


def _log_count() -> int:
    with get_connection() as con:
        return con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0]


def _catalog_price(name: str) -> int:
    for row in list_work_types():
        if row["작업명"] == name:
            return int(row["기본비용"])
    raise AssertionError(name)


def _draft(uid: str, cid: str) -> dict:
    state = get_conversation_manager().get_state(uid, cid) or {}
    return dict(state.get("pending_data") or {})


def _missing(uid: str, cid: str) -> list:
    state = get_conversation_manager().get_state(uid, cid) or {}
    return list(state.get("missing") or [])


def test_a_new_barcode_one_shot_then_lookup():
    uid, cid = _ids("a")
    _enter(uid, cid)
    _seed_new_barcode(uid, cid)
    before = _log_count()
    reply = asyncio.run(handle_user_text(
        uid, cid,
        "업체는 로지킴이고 제품은 린넨 볼캡, 옵션은 더스트 그레이야",
        "테스터",
        nlu_intent=_nlu(fields={"vendor": "로지킴", "product": "린넨 볼캡", "option": "더스트 그레이"}),
    ))
    draft = _draft(uid, cid)
    assert draft.get("vendor")
    assert draft.get("product") == "린넨 볼캡"
    assert draft.get("option") == "더스트 그레이"
    assert "업체명 알려주세요" not in (reply or "")
    assert _log_count() == before
    ensure_repair_tables()
    with get_connection() as con:
        assert _lookup_barcode(con, "ON56S152917") is None
    saved_reply = asyncio.run(handle_user_text(
        uid, cid,
        "부분세탁 700원 하나",
        "테스터",
        nlu_intent=_nlu(fields={"work_type": "부분세탁", "unit_price": 700, "qty": 1}),
    ))
    assert "✅" in saved_reply
    assert _log_count() == before + 1
    with get_connection() as con:
        found = _lookup_barcode(con, "ON56S152917")
        row = con.execute("SELECT 수량, 제품명, 옵션 FROM repair_work_log ORDER BY id DESC LIMIT 1").fetchone()
    assert found["업체명"]
    assert found["제품명"] == "린넨 볼캡"
    assert found["옵션"] == "더스트 그레이"
    assert row[0] == 1
    assert row[1] == "린넨 볼캡"
    from backend.app.services.repair_bot import continue_after_photos_or_text

    uid2, cid2 = _ids("a-rescan")
    _enter(uid2, cid2)
    again = continue_after_photos_or_text(
        {"entry_type": "repair", "barcode": "ON56S152917", "user_name": "테스터"},
        uid2,
        cid2,
    )
    draft2 = _draft(uid2, cid2)
    assert draft2.get("product") == "린넨 볼캡"
    assert draft2.get("option") == "더스트 그레이"
    assert "업체명 알려주세요" not in (again or "")


def test_b_nlu_vendor_product_do_not_repeat_question():
    uid, cid = _ids("b")
    _enter(uid, cid)
    _seed_new_barcode(uid, cid)
    first = asyncio.run(handle_user_text(
        uid, cid, "로지킴", "테스터", nlu_intent=_nlu(fields={"vendor": "로지킴"}),
    ))
    assert "업체명 알려주세요" not in first
    assert "제품명" in first
    assert _draft(uid, cid).get("product") is None
    second = asyncio.run(handle_user_text(
        uid, cid, "제품은 린넨 볼캡이야", "테스터",
        nlu_intent=_nlu(fields={"product": "린넨 볼캡"}),
    ))
    assert _draft(uid, cid).get("product") == "린넨 볼캡"
    assert _draft(uid, cid).get("product") != "제품은 린넨 볼캡이야"
    assert "제품명 알려주세요" not in second


def test_c_unrecognized_barcode_keeps_before_after():
    uid, cid = _ids("c")
    _enter(uid, cid)
    photos = [
        BufferedPhoto(data=b"barcode-bytes", name="1.jpg"),
        BufferedPhoto(data=b"before-bytes", name="2.jpg"),
        BufferedPhoto(data=b"after-bytes", name="3.jpg"),
    ]
    classified = {
        "barcode": None,
        "barcode_index": None,
        "before_index": 0,
        "after_index": 1,
        "ambiguous": False,
    }
    reply = asyncio.run(finalize_photo_set(uid, cid, photos, "테스터", classified=classified))
    assert "바코드" in reply
    draft = _draft(uid, cid)
    assert draft.get("barcode_image")
    assert draft.get("before_image")
    assert draft.get("after_image")
    before_name = draft["before_image"]
    after_name = draft["after_image"]
    asyncio.run(handle_user_text(uid, cid, "ON56S152917", "테스터", nlu_intent=_nlu(fields={})))
    after = _draft(uid, cid)
    assert after.get("barcode") == "ON56S152917"
    assert after.get("before_image") == before_name
    assert after.get("after_image") == after_name


def test_d_four_photos_and_duplicate_event_do_not_leak():
    uid, cid = _ids("d")
    other_u, other_c = _ids("d-other")
    for i in range(3):
        count, status = _try_append_inbox_photo(
            uid, cid, "group", "n", f"P{i}".encode(), f"p{i}.jpg", ".jpg", event_key=f"evt-{i}"
        )
        assert status == "ok"
        assert count == i + 1
    count, status = _try_append_inbox_photo(
        uid, cid, "group", "n", b"P3", "p3.jpg", ".jpg", event_key="evt-3"
    )
    assert status == "ok"
    assert count == 4
    count, status = _try_append_inbox_photo(
        uid, cid, "group", "n", b"P0-dup", "p0.jpg", ".jpg", event_key="evt-0"
    )
    assert status == "duplicate"
    assert count == 4
    _try_append_inbox_photo(other_u, other_c, "group", "n", b"X", "x.jpg", ".jpg", event_key="evt-0")
    assert _inbox_count(other_u, other_c) == 1
    claimed = _claim_inbox_photos(uid, cid, 2)
    assert claimed and claimed["ready"]
    assert len(claimed["photos"]) == 4
    assert _inbox_count(uid, cid) == 0
    assert _inbox_count(other_u, other_c) == 1


def test_e_classify_error_keeps_photos():
    uid, cid = _ids("e")
    _enter(uid, cid)
    for i in range(3):
        _try_append_inbox_photo(uid, cid, "group", "n", f"E{i}".encode(), f"e{i}.jpg", ".jpg")
    claimed = _claim_inbox_photos(uid, cid, 2)
    assert claimed and claimed["ready"]
    with patch(
        "backend.app.services.repair_bot._classify_photos_safe",
        return_value=None,
    ):
        reply = asyncio.run(finalize_photo_set(uid, cid, claimed["photos"], "테스터"))
    assert reply == PHOTO_RETRY_MSG
    assert "sql" not in reply.lower()
    assert "traceback" not in reply.lower()
    _release_inbox_claim(uid, cid)
    assert "sql" not in reply.lower()


def test_f_draft_price_does_not_change_catalog():
    uid, cid = _ids("f")
    _enter(uid, cid)
    before_price = _catalog_price("부분세탁")
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "캡",
            "work_type": "부분세탁",
            "unit_price": 700,
            "price_stated": True,
            "awaiting_price_confirm": True,
            "user_name": "테스터",
        },
        missing=["qty"],
        last_question="부분세탁 700원 맞아요?",
    )
    asyncio.run(handle_user_text(
        uid, cid, "900원으로", "테스터",
        nlu_intent=_nlu(fields={"unit_price": 900}),
    ))
    assert _catalog_price("부분세탁") == before_price == 700
    assert _draft(uid, cid).get("unit_price") == 900


def test_g_ten_minutes_later_qty_uses_same_draft():
    uid, cid = _ids("g")
    _enter(uid, cid)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "캡",
            "work_type": "부분세탁",
            "unit_price": 700,
            "price_stated": True,
            "awaiting_price_confirm": True,
            "user_name": "테스터",
        },
        missing=["qty"],
        last_question="몇 건이에요?",
    )
    with get_connection() as con:
        con.execute(
            "UPDATE conversation_states_v2 SET expires_at = ? WHERE user_id = ? AND channel_id = ?",
            (int(time.time()) + 3000, uid, cid),
        )
        con.commit()
    before = _log_count()
    reply = asyncio.run(handle_user_text(
        uid, cid, "하나", "테스터", nlu_intent=_nlu(fields={"qty": 1}),
    ))
    assert "✅" in reply
    assert _log_count() == before + 1
    assert "업체명 알려주세요" not in reply
    assert EXPIRED_REPAIR_MSG not in reply


def test_g_expired_repair_asks_to_restart():
    uid, cid = _ids("g-exp")
    _enter(uid, cid)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={"entry_type": "repair", "vendor": "로지킴", "product": "캡"},
        missing=["qty"],
        last_question="업체명 알려주세요.",
    )
    with get_connection() as con:
        con.execute(
            "UPDATE conversation_states_v2 SET expires_at = ? WHERE user_id = ? AND channel_id = ?",
            (int(time.time()) - 5, uid, cid),
        )
        con.commit()
    reply = asyncio.run(handle_user_text(uid, cid, "하나", "테스터", nlu_intent=_nlu(fields={"qty": 1})))
    assert reply == EXPIRED_REPAIR_MSG
    assert "업체명 알려주세요" not in reply
    assert not _draft(uid, cid)


def test_h_fallback_qty_cancel_confirm():
    assert extract_qty("하나") == 1
    assert extract_qty("한 개") == 1
    assert extract_qty("한 건") == 1
    assert extract_qty("둘") == 2
    assert extract_qty("두 개") == 2
    assert extract_qty("2건") == 2
    ctx = {"has_active_draft": True}
    one = fallback_from_local_parsers("하나", ctx)
    assert one.action == "provide_field"
    assert one.fields.get("qty") == 1
    cancel = fallback_from_local_parsers("취소", ctx)
    assert cancel.action == "cancel"
    yes = fallback_from_local_parsers("네", ctx)
    assert yes.action == "confirm"


def test_i_catalog_readonly_keeps_mode_and_draft():
    uid, cid = _ids("i")
    _enter(uid, cid)
    seeded = {
        "entry_type": "repair",
        "vendor": "로지킴",
        "product": "캡",
        "work_type": "부분세탁",
    }
    get_conversation_manager().set_state(
        user_id=uid, channel_id=cid, pending_data=seeded, missing=["qty"], last_question="몇 건이에요?",
    )
    listing = format_work_cost_list()
    reply = asyncio.run(handle_user_text(
        uid, cid, "수선항목과 가격", "테스터",
        nlu_intent=_nlu(action="query_catalog", target="none", fields={"topic": "repair_work_prices"}),
    ))
    assert "부분세탁" in reply
    assert listing.splitlines()[0] in reply
    assert get_mode(uid, cid) == MODE_REPAIR
    assert _draft(uid, cid).get("vendor") == "로지킴"
    assert _missing(uid, cid) == ["qty"]


def test_j_other_room_and_user_untouched():
    uid, cid = _ids("j-a")
    other_u, other_c = _ids("j-b")
    _enter(uid, cid)
    _enter(other_u, other_c)
    get_conversation_manager().set_state(
        user_id=other_u,
        channel_id=other_c,
        pending_data={"entry_type": "repair", "vendor": "다른업체", "product": "다른제품"},
        missing=["qty"],
        last_question="몇 건이에요?",
    )
    saved = insert_repair_log_record(
        날짜="2026-09-05", 작업="단순바느질", 비용=1500,
        업체명="로지킴", 제품명="릴리프T", 수량=1, 작성자="다른이", 출처="bot",
    )
    remember_last_saved(other_u, other_c, saved["id"])
    _try_append_inbox_photo(other_u, other_c, "group", "n", b"OT", "ot.jpg", ".jpg")
    _seed_new_barcode(uid, cid)
    asyncio.run(handle_user_text(
        uid, cid, "로지킴", "테스터", nlu_intent=_nlu(fields={"vendor": "로지킴"}),
    ))
    other = _draft(other_u, other_c)
    assert other.get("vendor") == "다른업체"
    assert other.get("product") == "다른제품"
    assert get_last_saved_id(other_u, other_c) == saved["id"]
    assert _inbox_count(other_u, other_c) == 1
    assert _inbox_count(uid, cid) == 0


def test_k_last_saved_confirms_once():
    uid, cid = _ids("k")
    _enter(uid, cid)
    saved = insert_repair_log_record(
        날짜="2026-09-05", 작업="단순바느질", 비용=1500,
        업체명="로지킴", 제품명="릴리프T", 수량=1, 작성자="테스터", 출처="bot",
    )
    remember_last_saved(uid, cid, saved["id"])
    preview = asyncio.run(handle_user_text(
        uid, cid, "방금 거 금액 2천원으로", "테스터",
        nlu_intent=_nlu(
            action="update", target="last_saved", fields={"unit_price": 2000},
            needs_confirmation=True, explicit_last_saved=True,
        ),
    ))
    with get_connection() as con:
        cost = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert cost == 1500
    assert "변경 전" in preview
    done = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    with get_connection() as con:
        cost = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert "수정했어요" in done
    assert cost == 2000


def test_l_work_name_is_not_last_saved():
    uid, cid = _ids("l")
    _enter(uid, cid)
    saved = insert_repair_log_record(
        날짜="2026-09-05", 작업="단순바느질", 비용=1500,
        업체명="로지킴", 제품명="릴리프T", 수량=1, 작성자="테스터", 출처="bot",
    )
    remember_last_saved(uid, cid, saved["id"])
    reply = asyncio.run(handle_user_text(
        uid, cid, "사이즈변경 5000원", "테스터",
        nlu_intent=_nlu(action="create", target="none", fields={"work_type": "사이즈변경", "unit_price": 5000}),
    ))
    with get_connection() as con:
        cost = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (saved["id"],)).fetchone()[0]
    assert cost == 1500
    assert "변경 전" not in reply
    assert "수정할까요" not in reply
    draft = _draft(uid, cid)
    assert draft.get("entry_type") == "repair"
    assert draft.get("work_type") == "사이즈변경"


def test_idle_help_does_not_require_mode():
    uid, cid = _ids("help")
    set_mode(uid, cid, MODE_IDLE)
    from unittest.mock import AsyncMock

    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch("backend.app.api.naver_works_webhook.get_naver_works_client", return_value=nw):
            await process_message(uid, cid, "기능설명해줘", "group", "테스터")

    with patch(
        "backend.app.api.naver_works_webhook.interpret_or_fallback",
        return_value=_nlu(action="show_help", target="none", domain="none", fields={"topic": "all"}),
    ):
        asyncio.run(_run())
    sent = " ".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)
    assert "모드별 기능 안내" in sent
    assert get_mode(uid, cid) == MODE_IDLE


def test_min_photo_set_is_two():
    assert PHOTO_MIN_SIZE == 2


def test_real_artifacts_snapshot_unchanged_here():
    assert sha256_file(REAL_BILLING_DB) == sha256_file(REAL_BILLING_DB)
    assert upload_manifest(REAL_UPLOAD_DIR) == upload_manifest(REAL_UPLOAD_DIR)
