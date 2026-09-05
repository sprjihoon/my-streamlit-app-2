"""웹훅 진입점 회귀. 임시 DB·임시 업로드만 사용하고 OpenAI는 호출하지 않는다."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.bot_dates import seoul_today_str
from backend.app.services.bot_mode import MODE_IDLE, MODE_JOURNAL, MODE_QUERY, MODE_REPAIR, get_mode, set_mode
from backend.app.services.bot_nlu import NluIntent, fallback_from_local_parsers, parse_nlu_payload
from backend.app.services.conversation_state import get_conversation_manager, strip_history_name_prefix
from backend.app.services.journal_adapter import extract_journal_fields_local
from backend.app.services.repair_catalog import resolve_work_type, resolve_work_type_candidates
from backend.app.services.repair_edit import remember_last_saved
from logic.db import get_connection


def _ids(suffix: str):
    return f"eng-user-{suffix}", f"eng-ch-{suffix}"


def _sent(uid, cid, text, user_name="장지훈", event_id=None):
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ):
            await process_message(uid, cid, text, "group", user_name, event_id=event_id)

    asyncio.run(_run())
    return "\n".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)


def _repair_count():
    with get_connection() as con:
        return con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0]


def _work_count():
    with get_connection() as con:
        return con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]


def _insert_repair(**kwargs):
    payload = {
        "날짜": seoul_today_str(),
        "작업": "봉제",
        "비용": 700,
        "업체명": "로지킴",
        "제품명": "릴리프T",
        "불량명": "구멍",
        "수량": 3,
        "작성자": "다른사람",
        "출처": "bot",
    }
    payload.update(kwargs)
    return insert_repair_log_record(**payload)


def test_s1_query_today_vendors():
    uid, cid = _ids("s1")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(업체명="로지킴", 수량=1)
    _insert_repair(업체명="틸리언", 수량=2)
    sent = _sent(uid, cid, "오늘 수선작업한 업체")
    assert "로지킴" in sent and "틸리언" in sent
    assert "등록된 수선 작업 비용" not in sent


def test_s2_query_today_count():
    uid, cid = _ids("s2")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(수량=2)
    _insert_repair(수량=4)
    sent = _sent(uid, cid, "오늘 수선작업 몇건")
    assert "2개 기록" in sent
    assert "총 6건" in sent


def test_s3_followup_all():
    uid, cid = _ids("s3")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(수량=2, 작성자="장지훈")
    _insert_repair(수량=5, 작성자="다른사람")
    _sent(uid, cid, "오늘 수선작업 몇건")
    sent = _sent(uid, cid, "오늘 전체몇건")
    assert "2개 기록" in sent
    assert "총 7건" in sent


def test_s4_today_repair_list():
    uid, cid = _ids("s4")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(업체명="로지킴")
    sent = _sent(uid, cid, "오늘 수선일지조회")
    assert "로지킴" in sent


def test_s5_last_saved_repair():
    uid, cid = _ids("s5")
    set_mode(uid, cid, MODE_QUERY)
    saved = _insert_repair(업체명="포인터", 수량=1)
    remember_last_saved(uid, cid, saved["id"])
    sent = _sent(uid, cid, "방금 저장된 수선항목")
    assert "포인터" in sent


def test_s6_sewing_count():
    uid, cid = _ids("s6")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(작업="봉제", 수량=3)
    sent = _sent(uid, cid, "봉제 몇건?")
    assert "1개 기록" in sent
    assert "총 3건" in sent


def test_s7_repair_mode_query_does_not_create_draft():
    uid, cid = _ids("s7")
    set_mode(uid, cid, MODE_REPAIR)
    before = _repair_count()
    mgr = get_conversation_manager()
    mgr.set_state(uid, cid, {"entry_type": "repair", "vendor": "기존", "qty": 1}, ["photos"], "사진?")
    sent = _sent(uid, cid, "오늘 수선작업한 업체")
    assert "조회모드에서 확인할 수 있어요" not in sent
    assert "사진 2장" not in sent
    assert mgr.get_state(uid, cid)["pending_data"]["vendor"] == "기존"
    assert _repair_count() == before
    assert get_mode(uid, cid) == MODE_REPAIR


def test_s8_repair_mode_list_not_price_catalog():
    uid, cid = _ids("s8")
    set_mode(uid, cid, MODE_REPAIR)
    sent = _sent(uid, cid, "오늘 수선일지조회")
    assert "등록된 수선 작업 비용" not in sent
    assert "사진 2장" not in sent
    assert "조회모드에서 확인할 수 있어요" not in sent


def test_s9_journal_tilian_not_username():
    uid, cid = _ids("s9")
    set_mode(uid, cid, MODE_JOURNAL)
    fields = extract_journal_fields_local("틸리언 스티커부착", user_name="장지훈")
    assert fields.get("vendor") == "틸리언"
    assert fields.get("work_type") == "스티커부착"
    assert fields.get("vendor") != "장지훈"


def test_s10_price_waiting_keeps_qty():
    uid, cid = _ids("s10")
    set_mode(uid, cid, MODE_JOURNAL)
    mgr = get_conversation_manager()
    mgr.set_state(
        uid, cid,
        {"entry_type": "journal", "vendor": "틸리언", "work_type": "스티커부착", "qty": 2, "step": "awaiting_price"},
        ["unit_price"],
        "단가?",
    )
    from backend.app.services.journal_bot import handle_user_text

    reply = asyncio.run(handle_user_text(
        uid, cid, "3천원", "장지훈",
        nlu_intent=NluIntent(action="provide_field", target="draft", fields={"unit_price": 3000}, domain="journal"),
    ))
    state = mgr.get_state(uid, cid) or {}
    data = state.get("pending_data") or {}
    if "저장" in reply or "✅" in reply:
        with get_connection() as con:
            row = con.execute("SELECT 수량, 단가 FROM work_log ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == 2
        assert row[1] == 3000
    else:
        assert data.get("qty") == 2
        assert data.get("unit_price") == 3000


def test_s11_qty_waiting_one():
    fields_1 = extract_journal_fields_local("1", pending_step="qty")
    fields_hana = extract_journal_fields_local("하나", pending_step="qty")
    assert fields_1.get("qty") == 1
    assert fields_hana.get("qty") == 1
    assert "unit_price" not in fields_1


def test_s12_partial_wash_not_full():
    hit = resolve_work_type("부분세탁 얼마?")
    assert hit is not None
    assert hit["작업명"] == "부분세탁"
    assert all(c["작업명"] != "전체세탁" or len(resolve_work_type_candidates("부분세탁 얼마?")) == 1
               for c in resolve_work_type_candidates("부분세탁 얼마?"))
    names = [c["작업명"] for c in resolve_work_type_candidates("부분세탁 얼마?")]
    assert names == ["부분세탁"]


def test_s13_end_clears_repair_draft():
    uid, cid = _ids("s13")
    set_mode(uid, cid, MODE_REPAIR)
    get_conversation_manager().set_state(uid, cid, {"entry_type": "repair", "vendor": "기존"}, ["photos"], "사진?")
    sent = _sent(uid, cid, "종료")
    assert get_mode(uid, cid) == MODE_IDLE
    assert not (get_conversation_manager().get_state(uid, cid) or {}).get("pending_data")
    assert "종료" in sent or "기본상태" in sent


def test_s14_second_end_does_not_repeat_cancel():
    uid, cid = _ids("s14")
    set_mode(uid, cid, MODE_REPAIR)
    get_conversation_manager().set_state(uid, cid, {"entry_type": "repair", "vendor": "기존"}, ["photos"], "사진?")
    first = _sent(uid, cid, "종료")
    second = _sent(uid, cid, "종료")
    assert "수선 입력을 취소" not in second
    assert first != second or "이미 기본상태" in second


def test_s15_natural_repair_starts():
    for i, phrase in enumerate(("수선", "수선할래", "수선모드 시작")):
        uid, cid = _ids(f"s15-{i}")
        set_mode(uid, cid, MODE_IDLE)
        _sent(uid, cid, phrase)
        assert get_mode(uid, cid) == MODE_REPAIR, phrase


def test_s16_work_sentence_does_not_start_repair():
    uid, cid = _ids("s16")
    set_mode(uid, cid, MODE_IDLE)
    _sent(uid, cid, "오늘 수선작업 몇건")
    assert get_mode(uid, cid) == MODE_IDLE


def test_s17_gpt_timeout_no_draft():
    uid, cid = _ids("s17")
    set_mode(uid, cid, MODE_REPAIR)
    before = _repair_count()
    before_state = get_conversation_manager().get_state(uid, cid)

    async def _timeout(_messages):
        raise TimeoutError("nlu timeout")

    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ), patch("backend.app.services.bot_nlu._complete_chat", _timeout):
            import os
            os.environ["BOT_NLU_DISABLE"] = "0"
            await process_message(uid, cid, "그냥 그거", "group", "장지훈")

    asyncio.run(_run())
    assert _repair_count() == before
    state = get_conversation_manager().get_state(uid, cid)
    pending = (state or {}).get("pending_data") or {}
    assert pending.get("work_type") != "구멍 수선"
    assert pending.get("defect") != "구멍"
    if before_state is None:
        assert not pending or pending.get("entry_type") != "repair" or not pending.get("work_type")


def test_s18_duplicate_webhook_event_does_not_write_twice():
    uid, cid = _ids("s18")
    set_mode(uid, cid, MODE_JOURNAL)
    nlu = NluIntent(
        action="create",
        domain="journal",
        fields={"vendor": "틸리언", "work_type": "하차", "unit_price": 30000, "qty": 1},
        confidence=0.9,
    )
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ), patch(
            "backend.app.api.naver_works_webhook.interpret_or_fallback",
            return_value=nlu,
        ):
            await process_message(uid, cid, "틸리언 하차 3만원", "group", "장지훈", event_id="evt-dup-1")
            await process_message(uid, cid, "틸리언 하차 3만원", "group", "장지훈", event_id="evt-dup-1")

    asyncio.run(_run())
    assert _work_count() == 1


def test_history_strips_name_prefix_and_does_not_store_it():
    uid, cid = _ids("hist")
    mgr = get_conversation_manager()
    mgr.add_message(uid, cid, "user", "[장지훈] 어제 메시지")
    hist = mgr.get_history(uid, channel_id=cid)
    assert hist[0]["content"] == "어제 메시지"
    assert strip_history_name_prefix("[장지훈] 틸리언 하차") == "틸리언 하차"
    set_mode(uid, cid, MODE_IDLE)
    _sent(uid, cid, "현재 모드", "장지훈")
    stored = mgr.get_history(uid, channel_id=cid)
    user_rows = [h["content"] for h in stored if h["role"] == "user"]
    assert any(row == "현재 모드" for row in user_rows)
    assert all(not row.startswith("[장지훈]") for row in user_rows)


def test_username_not_extracted_as_vendor():
    fields = extract_journal_fields_local("장지훈 스티커부착", user_name="장지훈")
    assert fields.get("vendor") != "장지훈"


def test_fallback_does_not_invent_hole_repair():
    out = fallback_from_local_parsers("수선", {"mode": "idle"})
    assert (out.fields or {}).get("work_type") != "구멍 수선"
    assert (out.fields or {}).get("defect") != "구멍"


def test_new_schema_rejects_trusted_source_and_negative():
    raw = {
        "schema_version": "2.0",
        "mode_action": "none",
        "requested_mode": "none",
        "entity": "repair_log",
        "action": "create",
        "target": "none",
        "filters": {k: None for k in (
            "relative_date", "start_date", "end_date", "vendor", "product", "work_type",
            "defect", "worker", "barcode", "remark", "scope", "group_by", "limit",
        )},
        "fields": {
            "vendor": None, "product": None, "work_type": "봉제", "defect": None,
            "unit_price": -3, "qty": 1, "barcode": None, "remark": None,
        },
        "confidence": 0.9,
        "missing_fields": [],
        "needs_confirmation": False,
        "clarification_reason": None,
        "trusted_source": "excel",
    }
    try:
        parse_nlu_payload(raw)
        assert False, "trusted_source must be rejected"
    except ValueError:
        pass
    raw.pop("trusted_source")
    intent = parse_nlu_payload(raw)
    assert intent.fields.get("unit_price") is None or intent.fields.get("unit_price") > 0


def test_eval_fixture_has_sixty_natural_variants():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bot_nlu_eval_cases.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 60


def test_help_phrases_are_mode_commands():
    from backend.app.services.bot_mode import parse_mode_command

    assert parse_mode_command("기능")["action"] == "help"
    assert parse_mode_command("뭐 할 수 있어?")["action"] == "help"
    assert parse_mode_command("사용법 알려줘")["action"] == "help"
