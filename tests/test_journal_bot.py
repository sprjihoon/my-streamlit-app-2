"""일지 NLU + 상태 머신. 실제 OpenAI는 호출하지 않고 임시 DB만 사용한다."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from backend.app.api.naver_works_webhook import process_message
from backend.app.services.bot_mode import MODE_JOURNAL, MODE_QUERY, MODE_REPAIR, set_mode
from backend.app.services.bot_nlu import NluIntent
from backend.app.services.bot_tools import TRUSTED_EXCEL_UPLOAD, execute_tool
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.journal_adapter import seoul_today
from backend.app.services.journal_bot import handle_user_text
from backend.app.services.journal_edit import get_last_saved_id, remember_last_saved
from logic.db import get_connection


SEOUL = ZoneInfo("Asia/Seoul")


def _ids(suffix: str):
    return f"jnl-user-{suffix}", f"jnl-ch-{suffix}"


def _nlu(**kwargs) -> NluIntent:
    body = {
        "domain": "journal",
        "action": "create",
        "target": "none",
        "fields": {},
        "confidence": 0.95,
        "needs_confirmation": False,
        "source": "nlu",
    }
    body.update(kwargs)
    return NluIntent(**body)


def _count(user_id=None) -> int:
    with get_connection() as con:
        if user_id:
            return con.execute(
                "SELECT COUNT(*) FROM work_log WHERE works_user_id = ?", (user_id,)
            ).fetchone()[0]
        return con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]


def _rows(user_id=None):
    with get_connection() as con:
        sql = "SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, works_user_id FROM work_log"
        params = []
        if user_id:
            sql += " WHERE works_user_id = ?"
            params.append(user_id)
        sql += " ORDER BY id"
        return con.execute(sql, params).fetchall()


def _insert_log(user_id, vendor="틸리언", work="하차", price=30000, qty=1, date="2026-09-01", remark="", name="테스터"):
    with get_connection() as con:
        cur = con.execute(
            """INSERT INTO work_log
               (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, vendor, work, price, qty, price * qty, remark, name, datetime.now().isoformat(), "bot", user_id),
        )
        con.commit()
        return cur.lastrowid


async def _talk(uid, cid, text, intent, event_id=None, name="테스터"):
    set_mode(uid, cid, MODE_JOURNAL)
    return await handle_user_text(uid, cid, text, name, nlu_intent=intent, event_id=event_id)


def test_1_complete_one_sentence_saves():
    uid, cid = _ids("full")
    before = _count()
    reply = asyncio.run(_talk(uid, cid, "어제 틸리언 하차 다섯 개 건당 3만원, 야간", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "qty": 5, "unit_price": 30000,
        "date": "2026-09-04", "remark": "야간", "amount_type": "unit",
    })))
    assert "✅" in reply
    assert _count() == before + 1
    row = _rows(uid)[-1]
    assert row[2] == "틸리언" and row[3] == "하차"
    assert row[4] == 30000 and row[5] == 5 and row[7] == "야간"
    assert get_last_saved_id(uid, cid) == row[0]


def test_2_alias_vendor_resolves():
    uid, cid = _ids("alias")
    reply = asyncio.run(_talk(uid, cid, "틸 하차 다섯 건 3만원", _nlu(fields={
        "vendor": "틸", "work_type": "하차", "qty": 5, "unit_price": 30000, "amount_type": "unit",
    })))
    assert "✅" in reply
    assert _rows(uid)[-1][2] == "틸리언"


def test_3_korean_qty_hana_and_daseot():
    uid, cid = _ids("qty")
    asyncio.run(_talk(uid, cid, "틸리언 하차 하나 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "qty": 1, "unit_price": 30000,
    })))
    asyncio.run(_talk(uid, cid, "틸리언 입고 다섯 개 1000원", _nlu(fields={
        "vendor": "틸리언", "work_type": "입고", "qty": 5, "unit_price": 1000,
    })))
    rows = _rows(uid)
    assert rows[0][5] == 1
    assert rows[1][5] == 5


def test_4_manwon_cheonwon_via_nlu():
    uid, cid = _ids("won")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    asyncio.run(_talk(uid, cid, "틸리언 입고 천원", _nlu(fields={
        "vendor": "틸리언", "work_type": "입고", "unit_price": 1000,
    })))
    rows = _rows(uid)
    assert rows[0][4] == 30000
    assert rows[1][4] == 1000


def test_5_date_and_remark_survive_missing_price():
    uid, cid = _ids("keep")
    asyncio.run(_talk(uid, cid, "어제 틸리언 하차 야간", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "date": "2026-09-04", "remark": "야간", "qty": 2,
    })))
    pending = get_conversation_manager().get_state(uid, cid)
    assert pending["pending_data"]["date"] == "2026-09-04"
    assert pending["pending_data"]["remark"] == "야간"
    assert pending["pending_data"]["qty"] == 2
    reply = asyncio.run(_talk(uid, cid, "삼만원", _nlu(action="provide_field", target="draft", fields={"unit_price": 30000})))
    assert "✅" in reply
    row = _rows(uid)[-1]
    assert row[1] == "2026-09-04" and row[7] == "야간" and row[5] == 2


def test_6_price_history_keeps_qty():
    uid, cid = _ids("hist")
    _insert_log(uid, work="하차", price=25000, qty=1)
    reply = asyncio.run(_talk(uid, cid, "틸리언 하차 다섯 건", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "qty": 5,
    })))
    assert "25,000원" in reply or "25000" in reply.replace(",", "")
    pending = get_conversation_manager().get_state(uid, cid)
    assert pending["pending_data"]["qty"] == 5
    reply = asyncio.run(_talk(uid, cid, "그 가격으로 해", _nlu(action="confirm")))
    assert "✅" in reply
    row = _rows(uid)[-1]
    assert row[4] == 25000 and row[5] == 5


def test_7_split_missing_answers_merge():
    uid, cid = _ids("split")
    asyncio.run(_talk(uid, cid, "일지 적을게", _nlu(action="create", fields={})))
    state = get_conversation_manager().get_state(uid, cid)
    assert state is not None
    asyncio.run(_talk(uid, cid, "틸리언", _nlu(action="provide_field", target="draft", fields={"vendor": "틸리언"})))
    asyncio.run(_talk(uid, cid, "하차", _nlu(action="provide_field", target="draft", fields={"work_type": "하차"})))
    pending = get_conversation_manager().get_state(uid, cid)
    assert pending["pending_data"]["vendor"] == "틸리언"
    assert pending["pending_data"]["work_type"] == "하차"
    reply = asyncio.run(_talk(uid, cid, "3만원", _nlu(action="provide_field", target="draft", fields={"unit_price": 30000})))
    assert "✅" in reply
    assert _count(uid) == 1


def test_8_mid_draft_correction():
    uid, cid = _ids("fix")
    asyncio.run(_talk(uid, cid, "틸 하차", _nlu(fields={"vendor": "틸", "work_type": "하차"})))
    asyncio.run(_talk(uid, cid, "업체는 틸 말고 팔로우미", _nlu(
        action="provide_field", target="draft", fields={"vendor": "팔로우미"}
    )))
    asyncio.run(_talk(uid, cid, "5건 아니고 3건", _nlu(
        action="provide_field", target="draft", fields={"qty": 3}
    )))
    reply = asyncio.run(_talk(uid, cid, "3만원", _nlu(action="provide_field", target="draft", fields={"unit_price": 30000})))
    assert "✅" in reply
    row = _rows(uid)[-1]
    assert row[2] == "팔로우미코스메틱"
    assert row[5] == 3


def test_9_save_failure_keeps_draft():
    uid, cid = _ids("failkeep")
    asyncio.run(_talk(uid, cid, "없는업체 하차 3만원", _nlu(fields={
        "vendor": "없는업체", "work_type": "하차", "unit_price": 30000,
    })))
    pending = get_conversation_manager().get_state(uid, cid)
    assert pending is not None
    assert pending["pending_data"]["work_type"] == "하차"
    assert pending["pending_data"]["unit_price"] == 30000
    assert _count(uid) == 0
    reply = asyncio.run(_talk(uid, cid, "틸리언", _nlu(action="provide_field", target="draft", fields={"vendor": "틸리언"})))
    assert "✅" in reply
    assert _rows(uid)[-1][2] == "틸리언"


def test_10_cancel_leaves_db_unchanged():
    uid, cid = _ids("cancel")
    before = _count()
    asyncio.run(_talk(uid, cid, "틸리언 하차", _nlu(fields={"vendor": "틸리언", "work_type": "하차"})))
    reply = asyncio.run(_talk(uid, cid, "아니 취소", _nlu(action="cancel")))
    assert "취소" in reply
    assert _count() == before
    assert get_conversation_manager().get_state(uid, cid) is None


def test_11_unknown_vendor_shows_similar():
    uid, cid = _ids("unk")
    reply = asyncio.run(_talk(uid, cid, "틸리 하차 3만원", _nlu(fields={
        "vendor": "없는회사XYZ", "work_type": "하차", "unit_price": 30000,
    })))
    assert "등록되지 않은 업체" in reply
    assert _count(uid) == 0


def test_12_unit_vs_total_amount():
    uid, cid = _ids("amt")
    asyncio.run(_talk(uid, cid, "5개 개당 15만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "qty": 5, "unit_price": 150000, "amount_type": "unit",
    })))
    asyncio.run(_talk(uid, cid, "5개 총 15만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "입고", "qty": 5, "total_amount": 150000, "amount_type": "total",
    })))
    rows = _rows(uid)
    assert rows[0][4] == 150000 and rows[0][6] == 750000
    assert rows[1][4] == 30000 and rows[1][6] == 150000
    reply = asyncio.run(_talk(uid, cid, "3개 총 10만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "상차", "qty": 3, "total_amount": 100000, "amount_type": "total",
    })))
    assert "개당 단가" in reply
    assert _count(uid) == 2
    reply = asyncio.run(_talk(uid, cid, "5개 15만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "양품화", "qty": 5, "total_amount": 150000, "amount_type": "unknown",
    })))
    assert "개당" in reply and "총액" in reply


def test_13_multiple_works_one_sentence():
    uid, cid = _ids("multi")
    reply = asyncio.run(_talk(uid, cid, "틸 입고 3건 천원하고 하차 1건 3만원", _nlu(
        fields={"vendor": "틸"},
        entries=[
            {"vendor": "틸", "work_type": "입고", "qty": 3, "unit_price": 1000, "amount_type": "unit"},
            {"vendor": "틸", "work_type": "하차", "qty": 1, "unit_price": 30000, "amount_type": "unit"},
        ],
    )))
    assert "✅" in reply or "2건" in reply
    rows = _rows(uid)
    assert len(rows) == 2
    assert {rows[0][3], rows[1][3]} == {"입고", "하차"}


def test_14_all_fail_and_partial():
    uid, cid = _ids("part")
    reply = asyncio.run(_talk(uid, cid, "없는곳 하차 3만원", _nlu(
        fields={},
        entries=[
            {"vendor": "없는곳A", "work_type": "하차", "unit_price": 30000},
            {"vendor": "없는곳B", "work_type": "입고", "unit_price": 1000},
        ],
    )))
    assert "✅" not in reply
    assert "0건 저장완료" not in reply
    assert _count(uid) == 0
    reply = asyncio.run(_talk(uid, cid, "혼합", _nlu(
        fields={},
        entries=[
            {"vendor": "틸리언", "work_type": "하차", "unit_price": 30000},
            {"vendor": "없는곳C", "work_type": "입고", "unit_price": 1000},
        ],
    )))
    assert "부분" in reply or "실패" in reply
    assert _count(uid) == 1
    assert "0건 저장완료" not in reply


def test_15_last_saved_update_preview_and_confirm():
    uid, cid = _ids("upd")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000, "qty": 1,
    })))
    row_id = _rows(uid)[-1][0]
    reply = asyncio.run(_talk(uid, cid, "좀 전 거 2만원으로", _nlu(
        action="update", target="last_saved", fields={"unit_price": 20000}, needs_confirmation=True,
    )))
    assert "변경 전" in reply and "변경 후" in reply
    assert _rows(uid)[-1][4] == 30000
    reply = asyncio.run(_talk(uid, cid, "네", _nlu(action="confirm")))
    assert "✅" in reply
    assert _rows(uid)[-1][4] == 20000
    assert get_last_saved_id(uid, cid) == row_id


def test_16_last_saved_delete_preview_and_confirm():
    uid, cid = _ids("del")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    reply = asyncio.run(_talk(uid, cid, "그거 지워", _nlu(
        action="delete", target="last_saved", needs_confirmation=True,
    )))
    assert "삭제할까요" in reply
    assert _count(uid) == 1
    reply = asyncio.run(_talk(uid, cid, "네", _nlu(action="confirm")))
    assert "삭제" in reply
    assert _count(uid) == 0


def test_17_same_confirm_runs_once():
    uid, cid = _ids("once")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    asyncio.run(_talk(uid, cid, "2만원으로", _nlu(
        action="update", target="last_saved", fields={"unit_price": 20000}, needs_confirmation=True,
    )))
    asyncio.run(_talk(uid, cid, "네", _nlu(action="confirm")))
    reply = asyncio.run(_talk(uid, cid, "네", _nlu(action="confirm")))
    assert "이미" in reply
    assert _count(uid) == 1
    assert _rows(uid)[-1][4] == 20000


def test_18_other_user_log_id_rejected():
    owner, cid = _ids("own")
    other, ocid = _ids("oth")
    log_id = _insert_log(owner)
    set_mode(other, ocid, MODE_JOURNAL)
    upd = execute_tool("update_work_log", {"log_id": log_id, "new_unit_price": 1}, other, "x", mode=MODE_JOURNAL)
    dele = execute_tool("delete_work_log", {"log_id": log_id}, other, "x", mode=MODE_JOURNAL)
    memo = execute_tool("add_memo", {"log_id": log_id, "memo": "hack"}, other, "x", mode=MODE_JOURNAL)
    assert upd.get("success") is False
    assert dele.get("success") is False
    assert memo.get("success") is False
    with get_connection() as con:
        row = con.execute("SELECT 단가, 비고1 FROM work_log WHERE id = ?", (log_id,)).fetchone()
    assert row[0] == 30000
    assert not row[1]


def test_19_room_pointers_isolated():
    uid, a = _ids("room-a")
    _, b = "jnl-user-room-a", "jnl-ch-room-b"
    asyncio.run(_talk(uid, a, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    asyncio.run(_talk(uid, b, "틸리언 입고 1000원", _nlu(fields={
        "vendor": "틸리언", "work_type": "입고", "unit_price": 1000,
    })))
    id_a = get_last_saved_id(uid, a)
    id_b = get_last_saved_id(uid, b)
    assert id_a and id_b and id_a != id_b
    asyncio.run(_talk(uid, a, "2만원으로", _nlu(
        action="update", target="last_saved", fields={"unit_price": 20000}, needs_confirmation=True,
    )))
    asyncio.run(_talk(uid, a, "네", _nlu(action="confirm")))
    with get_connection() as con:
        pa = con.execute("SELECT 단가 FROM work_log WHERE id = ?", (id_a,)).fetchone()[0]
        pb = con.execute("SELECT 단가 FROM work_log WHERE id = ?", (id_b,)).fetchone()[0]
    assert pa == 20000
    assert pb == 1000


def test_20_mode_change_rejects_confirm():
    uid, cid = _ids("mode")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    asyncio.run(_talk(uid, cid, "2만원으로", _nlu(
        action="update", target="last_saved", fields={"unit_price": 20000}, needs_confirmation=True,
    )))
    set_mode(uid, cid, MODE_QUERY)
    reply = asyncio.run(handle_user_text(uid, cid, "네", "테스터", nlu_intent=_nlu(action="confirm")))
    assert "일지모드" in reply
    assert _rows(uid)[-1][4] == 30000


def test_21_negative_zero_bad_date_rejected():
    cases = [
        ("bad-price", {"vendor": "틸리언", "work_type": "하차", "unit_price": -100}, "단가"),
        ("bad-qty", {"vendor": "틸리언", "work_type": "하차", "unit_price": 100, "qty": 0}, "수량"),
        ("bad-date", {"vendor": "틸리언", "work_type": "하차", "unit_price": 100, "date": "2026-02-30"}, "날짜"),
    ]
    before = _count()
    for suffix, fields, needle in cases:
        uid, cid = _ids(suffix)
        reply = asyncio.run(_talk(uid, cid, needle, _nlu(fields=fields)))
        assert needle in reply or "❌" in reply
        assert _count(uid) == 0
    assert _count() == before


def test_22_update_vendor_revalidated():
    uid, cid = _ids("reval")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    reply = asyncio.run(_talk(uid, cid, "업체를 없는곳으로", _nlu(
        action="update", target="last_saved", fields={"vendor": "없는곳XYZ"}, needs_confirmation=True,
    )))
    assert "등록되지 않은 업체" in reply
    assert _rows(uid)[-1][2] == "틸리언"


def test_23_ambiguous_price_history_lists_candidates():
    uid, cid = _ids("amb")
    _insert_log(uid, work="1톤하차", price=10000)
    _insert_log(uid, work="3톤하차", price=20000)
    reply = asyncio.run(_talk(uid, cid, "틸리언 하차", _nlu(fields={"vendor": "틸리언", "work_type": "하차"})))
    assert "1톤하차" in reply and "3톤하차" in reply
    assert _count(uid) == 2


def test_24_nlu_error_fallback_and_uncertain(monkeypatch):
    uid, cid = _ids("fb")
    set_mode(uid, cid, MODE_JOURNAL)
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    with patch("backend.app.services.bot_nlu.interpret_user_text", side_effect=TimeoutError("nlu timeout")):
        reply = asyncio.run(handle_user_text(uid, cid, "틸리언 하차 3만원", "테스터"))
    assert "✅" in reply
    assert _count(uid) == 1
    with patch("backend.app.services.bot_nlu.interpret_user_text", side_effect=RuntimeError("nlu down")):
        reply = asyncio.run(handle_user_text(uid, cid, "글쎄요", "테스터"))
    assert "업체" in reply
    assert "TimeoutError" not in reply
    assert "nlu down" not in reply


def test_25_duplicate_webhook_event_saves_once():
    uid, cid = _ids("idem")
    intent = _nlu(fields={"vendor": "틸리언", "work_type": "하차", "unit_price": 30000, "qty": 1})
    r1 = asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", intent, event_id="evt-dup-1"))
    r2 = asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", intent, event_id="evt-dup-1"))
    assert "✅" in r1
    assert _count(uid) == 1
    assert r2 == r1 or "이미" in r2 or "✅" in r2
    asyncio.run(_talk(uid, cid, "틸리언 입고 1000원", _nlu(fields={
        "vendor": "틸리언", "work_type": "입고", "unit_price": 1000,
    }), event_id="evt-dup-2"))
    assert _count(uid) == 2


def test_26_internal_error_not_exposed():
    uid, cid = _ids("leak")
    set_mode(uid, cid, MODE_JOURNAL)
    with patch(
        "backend.app.services.bot_tools._save_work_log",
        side_effect=Exception("sqlite3.OperationalError no such table work_log C:/secret/billing.db"),
    ):
        reply = asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
            "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
        })))
    assert "sqlite" not in reply.lower()
    assert "billing.db" not in reply
    assert "C:/" not in reply
    assert "OperationalError" not in reply


def test_27_existing_repair_query_excel_invoice_smoke(isolated_runtime):
    uid, cid = _ids("reg")
    set_mode(uid, cid, MODE_REPAIR)
    from backend.app.services.repair_bot import handle_user_text as repair_text
    reply = asyncio.run(repair_text(uid, cid, "구멍 바느질 1500원", "테스터"))
    assert "사진" in reply or "수선" in reply or "불량" in reply or "작업" in reply
    excel = execute_tool(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": 1234, "qty": 2, "remark": "[엑셀] t"},
        uid, "excel", trusted_source=TRUSTED_EXCEL_UPLOAD,
    )
    assert excel.get("success") is True
    from tests.isolation import seed_shipping_fixture
    from utils.utils_courier import add_courier_fee_by_zone

    seed_shipping_fixture(isolated_runtime["db"])
    items = []
    add_courier_fee_by_zone("팔로우미코스메틱", "2025-06-01", "2025-06-30", items_list=items)
    counts = {i["항목"]: i["수량"] for i in items}
    assert counts.get("택배요금 (극소)") == 3
    set_mode(uid, cid, MODE_QUERY)
    blocked = execute_tool(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": 1},
        uid, "t", mode=MODE_QUERY,
    )
    assert blocked.get("success") is False


def test_webhook_journal_does_not_call_aiparser():
    uid, cid = _ids("wh")
    set_mode(uid, cid, MODE_JOURNAL)
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()
    parser = AsyncMock()

    async def _run():
        with patch("backend.app.api.naver_works_webhook.get_naver_works_client", return_value=nw), patch(
            "backend.app.api.naver_works_webhook.get_ai_parser", return_value=parser
        ), patch(
            "backend.app.api.naver_works_webhook.interpret_or_fallback",
            return_value=_nlu(fields={"vendor": "틸리언", "work_type": "하차", "unit_price": 30000}),
        ):
            await process_message(uid, cid, "오늘 작업 넣자", "group", "테스터", event_id="evt-wh-1")

    asyncio.run(_run())
    parser.process_message.assert_not_called()
    sent = " ".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)
    assert "일지모드" in sent
    assert _count(uid) == 1


def test_default_date_is_seoul_today():
    uid, cid = _ids("tz")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    assert _rows(uid)[-1][1] == seoul_today()
    assert seoul_today() == datetime.now(SEOUL).strftime("%Y-%m-%d")


def test_draft_update_does_not_touch_last_saved():
    uid, cid = _ids("draftonly")
    asyncio.run(_talk(uid, cid, "틸리언 하차 3만원", _nlu(fields={
        "vendor": "틸리언", "work_type": "하차", "unit_price": 30000,
    })))
    saved_price = _rows(uid)[-1][4]
    asyncio.run(_talk(uid, cid, "팔로우미 입고", _nlu(fields={"vendor": "팔로우미", "work_type": "입고"})))
    asyncio.run(_talk(uid, cid, "3건으로", _nlu(
        action="provide_field", target="draft", fields={"qty": 3},
    )))
    assert _rows(uid)[-1][4] == saved_price
    assert _count(uid) == 1
    pending = get_conversation_manager().get_state(uid, cid)
    assert pending["pending_data"]["qty"] == 3
    assert pending["pending_data"]["vendor"] == "팔로우미코스메틱"
