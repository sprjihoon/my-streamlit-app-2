"""조회모드 읽기 adapter. 임시 DB만 사용하고 OpenAI는 호출하지 않는다."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from backend.app.api.naver_works_webhook import process_message
from backend.app.services.bot_dates import seoul_today_str
from backend.app.services.bot_mode import MODE_QUERY, set_mode
from backend.app.services.bot_nlu import NluIntent
from backend.app.services.bot_query import execute_query, looks_like_query_read
from backend.app.services.bot_tools import QUERY_TOOL_NAMES, execute_tool, get_tools_for_mode
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.repair_edit import remember_last_saved
from backend.app.api.repair_log import insert_repair_log_record
from logic.db import get_connection

SEOUL = ZoneInfo("Asia/Seoul")


def _ids(suffix: str):
    return f"qb-user-{suffix}", f"qb-ch-{suffix}"


def _today() -> str:
    return seoul_today_str()


def _insert_repair(**kwargs):
    payload = {
        "날짜": _today(),
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


def _sent(uid, cid, text, user_name="장지훈"):
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ):
            await process_message(uid, cid, text, "group", user_name)

    asyncio.run(_run())
    return "\n".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)


def test_query_tools_are_exactly_six():
    names = {t["function"]["name"] for t in get_tools_for_mode(MODE_QUERY)}
    assert names == QUERY_TOOL_NAMES
    assert names == {
        "search_work_logs",
        "get_work_log_stats",
        "search_repair_logs",
        "get_repair_log_stats",
        "lookup_work_price",
        "lookup_repair_price",
    }
    blocked = execute_tool("get_invoice_stats", {"top_n": 3}, "u", "t", mode=MODE_QUERY)
    assert blocked.get("success") is False


def test_today_repair_vendors_are_grouped_not_price_list():
    uid, cid = _ids("vendors")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(업체명="로지킴", 수량=2)
    _insert_repair(업체명="틸리언", 수량=4)
    sent = _sent(uid, cid, "오늘 수선작업한 업체")
    assert "로지킴" in sent and "틸리언" in sent
    assert "전체세탁" not in sent
    assert "등록된 수선 작업 비용" not in sent
    assert "기록" in sent


def test_today_repair_count_shows_rows_and_qty():
    uid, cid = _ids("count")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(수량=2, 작성자="A")
    _insert_repair(수량=4, 작성자="B")
    sent = _sent(uid, cid, "오늘 수선작업 몇건")
    assert "2개 기록" in sent
    assert "총 6건" in sent


def test_followup_all_clears_worker_keeps_repair_today():
    uid, cid = _ids("follow")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(수량=2, 작성자="장지훈")
    _insert_repair(수량=5, 작성자="다른사람")
    first = execute_query(
        NluIntent(entity="repair_log", action="count", filters={"relative_date": "today", "scope": "self", "worker": "장지훈"}),
        "오늘 수선작업 몇건",
        uid,
        cid,
        "장지훈",
    )
    assert "기록" in first
    second = _sent(uid, cid, "오늘 전체몇건")
    assert "2개 기록" in second
    assert "총 7건" in second


def test_today_repair_log_list():
    uid, cid = _ids("list")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(업체명="로지킴", 작업="봉제", 수량=1)
    sent = _sent(uid, cid, "오늘 수선일지조회")
    assert "로지킴" in sent
    assert "봉제" in sent
    assert "없습니다" not in sent


def test_last_saved_repair_uses_room_pointer():
    uid, cid = _ids("last")
    set_mode(uid, cid, MODE_QUERY)
    other = _insert_repair(업체명="다른방", 수량=9)
    mine = _insert_repair(업체명="내방", 수량=1)
    remember_last_saved(uid, cid, mine["id"])
    sent = _sent(uid, cid, "방금 저장된 수선항목")
    assert "내방" in sent
    assert str(mine["id"]) in sent
    assert "다른방" not in sent
    assert other["id"] != mine["id"]


def test_missing_last_saved_does_not_guess():
    uid, cid = _ids("nolast")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(업체명="아무거나", 수량=1)
    sent = _sent(uid, cid, "방금 저장된 수선항목")
    assert "찾지 못했어요" in sent
    assert "아무거나" not in sent


def test_sewing_filters_repair_work_type():
    uid, cid = _ids("sew")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(작업="봉제", 수량=2)
    _insert_repair(작업="스팀작업", 수량=8)
    sent = _sent(uid, cid, "봉제 몇건?")
    assert "1개 기록" in sent
    assert "총 2건" in sent
    assert "스팀" not in sent


def test_empty_result_states_filters():
    uid, cid = _ids("empty")
    set_mode(uid, cid, MODE_QUERY)
    sent = _sent(uid, cid, "오늘 수선작업 몇건")
    assert "없습니다" in sent
    assert "오늘" in sent
    assert "등록된 수선 작업 비용" not in sent


def test_no_select_star_in_query_readers():
    import inspect
    from backend.app.services import bot_tools

    for fn in (bot_tools._search_repair_logs, bot_tools._get_repair_log_stats, bot_tools._search_work_logs):
        src = inspect.getsource(fn)
        assert "SELECT *" not in src.upper().replace(" ", "")
        assert "INSERT " not in src
        assert "DELETE " not in src
        assert "DROP " not in src


def test_query_read_detector():
    assert looks_like_query_read("오늘 수선작업 몇 건이야")
    assert looks_like_query_read("오늘 수선일지조회")
    assert not looks_like_query_read("수선")
    assert not looks_like_query_read("수선할래")
