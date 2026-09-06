"""조회 후속 문맥. 웹훅부터 query context·SQL 조건·DB 불변을 검증한다."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.bot_dates import last_month_range, seoul_today_str, this_month_range
from backend.app.services.bot_mode import MODE_JOURNAL, MODE_REPAIR, get_mode, parse_mode_command, set_mode
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection


def _ids(suffix: str):
    return f"qfu-user-{suffix}", f"qfu-ch-{suffix}"


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


def _insert_work(user_id, **kwargs):
    payload = {
        "날짜": seoul_today_str(),
        "업체명": "틸리언",
        "분류": "하차",
        "단가": 30000,
        "수량": 2,
        "작성자": "장지훈",
        "works_user_id": user_id,
    }
    payload.update(kwargs)
    payload["합계"] = int(payload["단가"]) * int(payload["수량"])
    with get_connection() as con:
        cur = con.execute(
            """INSERT INTO work_log
               (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                payload["날짜"], payload["업체명"], payload["분류"], payload["단가"],
                payload["수량"], payload["합계"], payload.get("비고1") or "",
                payload["작성자"], datetime.now().isoformat(), "bot", payload["works_user_id"],
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def _ctx(uid, cid):
    return get_conversation_manager().get_query_context(uid, cid) or {}


def _repair_count():
    with get_connection() as con:
        return int(con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0])


def _work_count():
    with get_connection() as con:
        return int(con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0])


def _sql_repair_groups(start, end, metric="quantity"):
    order = "SUM(비용)" if metric == "amount" else "SUM(수량)"
    with get_connection() as con:
        return list(con.execute(
            f"""SELECT 업체명, COUNT(*), SUM(수량), SUM(비용)
                FROM repair_work_log
                WHERE 날짜 >= ? AND 날짜 <= ? AND 업체명 IS NOT NULL
                GROUP BY 업체명 ORDER BY {order} DESC""",
            (start, end),
        ).fetchall())


def _seed_month_repairs():
    start, end = this_month_range()
    _insert_repair(날짜=start, 업체명="틸리언", 수량=4, 비용=5000)
    _insert_repair(날짜=start, 업체명="틸리언", 수량=2, 비용=2000)
    _insert_repair(날짜=end, 업체명="로지킴", 수량=3, 비용=15000)
    _insert_repair(날짜=end, 업체명="에이원", 수량=1, 비용=800)
    _insert_repair(날짜=end, 업체명="비투", 수량=1, 비용=900)
    _insert_repair(날짜=end, 업체명="씨쓰리", 수량=1, 비용=1000)
    _insert_repair(날짜=end, 업체명="디포", 수량=1, 비용=1100)


def test_1_repair_dot_is_mode_command():
    uid, cid = _ids("1")
    for phrase in ("수선", "수선.", "수선 .", "수선!", "수선모드"):
        cmd = parse_mode_command(phrase)
        assert cmd and cmd.get("action") == "start" and cmd.get("mode") == MODE_REPAIR
    assert parse_mode_command("오늘 수선실적 알려줘") is None
    sent = _sent(uid, cid, "수선 .")
    assert get_mode(uid, cid) == MODE_REPAIR
    assert "수선모드" in sent


def test_2_this_month_repair_stats():
    uid, cid = _ids("2")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    before = _repair_count()
    sent = _sent(uid, cid, "이번달수선실적")
    ctx = _ctx(uid, cid)
    start, end = this_month_range()
    with get_connection() as con:
        row = con.execute(
            "SELECT COUNT(*), SUM(수량), SUM(비용) FROM repair_work_log WHERE 날짜 >= ? AND 날짜 <= ?",
            (start, end),
        ).fetchone()
    assert "수선일지" in sent
    assert f"{int(row[0])}개 기록" in sent
    assert f"총 {int(row[1])}건" in sent
    assert f"{int(row[2]):,}" in sent
    assert ctx.get("entity") == "repair_log"
    assert (ctx.get("filters") or {}).get("relative_date") == "this_month"
    assert (ctx.get("date_range") or {}).get("start") == start
    assert (ctx.get("date_range") or {}).get("end") == end
    assert "사진" not in sent
    assert _repair_count() == before


def test_3_vendor_followup_keeps_month_and_skips_photo():
    uid, cid = _ids("3")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    before = _repair_count()
    _sent(uid, cid, "이번달수선실적")
    mgr = get_conversation_manager()
    draft_before = (mgr.get_state(uid, cid) or {}).get("pending_data") or {}
    sent = _sent(uid, cid, "업체명")
    ctx = _ctx(uid, cid)
    start, end = this_month_range()
    groups = _sql_repair_groups(start, end, "quantity")
    assert "업체별" in sent
    assert "1." in sent
    assert groups[0][0] in sent
    assert ctx.get("action") == "group"
    assert ctx.get("group_by") == "vendor"
    assert (ctx.get("filters") or {}).get("relative_date") == "this_month"
    assert ctx.get("metric") == "quantity"
    assert (ctx.get("group_names") or [])[0] == groups[0][0]
    assert "사진" not in sent
    assert _repair_count() == before
    draft_after = (mgr.get_state(uid, cid) or {}).get("pending_data") or {}
    assert draft_after.get("entry_type") != "repair" or draft_after == draft_before


def test_4_top5_vendors_by_qty():
    uid, cid = _ids("4")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    before = _repair_count()
    sent = _sent(uid, cid, "수선실적 탑5 업체명")
    ctx = _ctx(uid, cid)
    start, end = this_month_range()
    groups = _sql_repair_groups(start, end, "quantity")[:5]
    assert "수량 기준" in sent
    assert "1." in sent
    assert groups[0][0] in sent
    assert ctx.get("action") == "group"
    assert ctx.get("group_by") == "vendor"
    assert ctx.get("limit") == 5
    assert ctx.get("sort") == "desc"
    assert ctx.get("metric") == "quantity"
    assert (ctx.get("filters") or {}).get("relative_date") == "this_month"
    assert (ctx.get("group_names") or [])[:5] == [row[0] for row in groups]
    assert "사진" not in sent
    assert _repair_count() == before


def test_5_resort_by_amount():
    uid, cid = _ids("5")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    _sent(uid, cid, "수선실적 탑5 업체명")
    before = _repair_count()
    sent = _sent(uid, cid, "금액순")
    ctx = _ctx(uid, cid)
    start, end = this_month_range()
    groups = _sql_repair_groups(start, end, "amount")[:5]
    assert "금액 기준" in sent
    assert groups[0][0] in sent.split("1.", 1)[-1]
    assert ctx.get("metric") == "amount"
    assert ctx.get("sort") == "desc"
    assert ctx.get("limit") == 5
    assert ctx.get("group_by") == "vendor"
    assert (ctx.get("filters") or {}).get("relative_date") == "this_month"
    assert (ctx.get("group_names") or [])[0] == groups[0][0]
    assert _repair_count() == before


def test_6_last_month_keeps_group_and_amount_sort():
    uid, cid = _ids("6")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    last_start, last_end = last_month_range()
    _insert_repair(날짜=last_start, 업체명="지난틸리언", 수량=1, 비용=40000)
    _insert_repair(날짜=last_end, 업체명="지난로지킴", 수량=8, 비용=3000)
    _sent(uid, cid, "수선실적 탑5 업체명")
    _sent(uid, cid, "금액순")
    before = _repair_count()
    sent = _sent(uid, cid, "지난달은")
    ctx = _ctx(uid, cid)
    groups = _sql_repair_groups(last_start, last_end, "amount")
    assert "지난달" in sent
    assert "지난틸리언" in sent
    assert ctx.get("metric") == "amount"
    assert ctx.get("group_by") == "vendor"
    assert ctx.get("sort") == "desc"
    assert (ctx.get("filters") or {}).get("relative_date") == "last_month"
    assert (ctx.get("filters") or {}).get("scope") != "self"
    assert (ctx.get("date_range") or {}).get("start") == last_start
    assert (ctx.get("date_range") or {}).get("end") == last_end
    assert (ctx.get("group_names") or [])[0] == groups[0][0]
    assert "1. 틸리언 —" not in sent
    assert _repair_count() == before


def test_7_query_context_is_scoped():
    a_uid, a_cid = _ids("7a")
    b_uid, b_cid = _ids("7b")
    set_mode(a_uid, a_cid, MODE_REPAIR)
    set_mode(b_uid, b_cid, MODE_REPAIR)
    _seed_month_repairs()
    _sent(a_uid, a_cid, "이번달수선실적")
    _sent(a_uid, a_cid, "업체명")
    a_ctx = _ctx(a_uid, a_cid)
    assert a_ctx.get("group_by") == "vendor"
    sent_b = _sent(b_uid, b_cid, "업체명")
    b_ctx = _ctx(b_uid, b_cid)
    assert b_ctx.get("group_by") != "vendor" or not b_ctx
    assert "1." not in sent_b or "사진" in sent_b or "수선" in sent_b
    assert _ctx(a_uid, a_cid).get("group_names") == a_ctx.get("group_names")


def test_8_followup_does_not_write():
    uid, cid = _ids("8")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    before_repair = _repair_count()
    before_work = _work_count()
    _sent(uid, cid, "이번달수선실적")
    _sent(uid, cid, "업체명")
    _sent(uid, cid, "수선실적 탑5 업체명")
    _sent(uid, cid, "금액순")
    mgr = get_conversation_manager()
    draft = (mgr.get_state(uid, cid) or {}).get("pending_data") or {}
    assert _repair_count() == before_repair
    assert _work_count() == before_work
    assert draft.get("entry_type") != "repair"


def test_9_waiting_vendor_draft_keeps_real_name():
    uid, cid = _ids("9")
    set_mode(uid, cid, MODE_REPAIR)
    _seed_month_repairs()
    _sent(uid, cid, "이번달수선실적")
    mgr = get_conversation_manager()
    mgr.set_state(uid, cid, {"entry_type": "repair", "barcode": "ON56S152917"}, ["vendor"], "업체명 알려주세요.")
    before = _repair_count()
    sent = _sent(uid, cid, "틸리언")
    state = mgr.get_state(uid, cid) or {}
    draft = state.get("pending_data") or {}
    assert draft.get("vendor") == "틸리언"
    assert draft.get("entry_type") == "repair"
    assert "업체별" not in sent
    assert _repair_count() == before


def test_10_journal_month_stats_then_vendor_group():
    uid, cid = _ids("10")
    set_mode(uid, cid, MODE_JOURNAL)
    start, end = this_month_range()
    _insert_work(uid, 날짜=start, 업체명="틸리언", 수량=2, 단가=10000)
    _insert_work(uid, 날짜=end, 업체명="로지킴", 수량=5, 단가=3000)
    before = _work_count()
    first = _sent(uid, cid, "이번달 작업실적")
    ctx = _ctx(uid, cid)
    assert ctx.get("entity") == "work_log"
    assert (ctx.get("filters") or {}).get("relative_date") == "this_month"
    assert "작업일지" in first
    sent = _sent(uid, cid, "업체별로")
    ctx = _ctx(uid, cid)
    with get_connection() as con:
        groups = list(con.execute(
            """SELECT 업체명, COUNT(*), SUM(수량), SUM(합계)
               FROM work_log WHERE 날짜 >= ? AND 날짜 <= ?
               GROUP BY 업체명 ORDER BY SUM(수량) DESC""",
            (start, end),
        ).fetchall())
    assert "업체별" in sent
    assert groups[0][0] in sent
    assert ctx.get("action") == "group"
    assert ctx.get("group_by") == "vendor"
    assert ctx.get("metric") == "quantity"
    assert (ctx.get("filters") or {}).get("relative_date") == "this_month"
    assert _work_count() == before
    assert get_mode(uid, cid) == MODE_JOURNAL
