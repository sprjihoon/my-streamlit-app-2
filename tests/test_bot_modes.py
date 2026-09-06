"""봇 모드 리팩터링 검증. 실제 billing.db / 업로드 폴더는 사용하지 않는다."""
from __future__ import annotations

from backend.app.services.bot_mode import (
    MODE_IDLE,
    MODE_JOURNAL,
    MODE_QUERY,
    MODE_REPAIR,
    apply_mode_command,
    decide_bot_route,
    get_mode,
    idle_guide,
    parse_mode_command,
    set_mode,
    should_accept_repair_photo,
    with_mode_prefix,
)
from backend.app.services.bot_tools import (
    WRITE_TOOL_NAMES,
    execute_tool,
    get_tools_for_mode,
    _save_work_log,
)
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection
from tests.isolation import seed_shipping_fixture


def _ids(suffix: str):
    return f"mode-test-user-{suffix}", f"mode-test-ch-{suffix}"


def test_1_idle_does_not_save():
    uid, cid = _ids("idle")
    set_mode(uid, cid, MODE_IDLE)
    assert decide_bot_route(uid, cid, "틸리언 하차 3만원") == "idle"
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    blocked = execute_tool(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": 30000},
        uid, "tester", mode=MODE_IDLE,
    )
    assert blocked.get("success") is False
    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert after == before


def test_2_journal_save_uses_existing_function():
    uid, cid = _ids("journal")
    set_mode(uid, cid, MODE_JOURNAL)
    assert decide_bot_route(uid, cid, "틸리언 하차 3만원") == "journal"
    names = {t["function"]["name"] for t in get_tools_for_mode(MODE_JOURNAL)}
    assert "save_work_log" in names
    import backend.app.services.bot_tools as bt
    assert bt._save_work_log is _save_work_log
    allowed = execute_tool(
        "lookup_price_from_history",
        {"vendor": "틸리언", "work_type": "하차"},
        uid, "tester", mode=MODE_JOURNAL,
    )
    assert "error" not in allowed or allowed.get("success") is not False or "일지모드" not in str(allowed.get("error", ""))


def test_3_qty_survives_price_lookup_pending():
    from backend.app.services.ai_parser import AIParser
    uid, cid = _ids("qty")
    mgr = get_conversation_manager()
    mgr.clear_state(uid, cid)
    parser = object.__new__(AIParser)
    qty = parser._resolve_qty("나블리 양품화 88개", {}, None)
    assert qty == 88
    pending = {"pending_data": {"qty": 88, "vendor": "나블리", "work_type": "양품화"}}
    assert parser._resolve_qty("네", {}, pending) == 88
    assert parser._resolve_qty("네", {"qty": 88}, None) == 88


def test_4_query_mode_blocks_writes():
    uid, cid = _ids("query")
    set_mode(uid, cid, MODE_QUERY)
    names = {t["function"]["name"] for t in get_tools_for_mode(MODE_QUERY)}
    assert not (names & WRITE_TOOL_NAMES)
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    for tool in ("save_work_log", "delete_work_log", "update_work_log", "save_repair_log"):
        result = execute_tool(
            tool,
            {"vendor": "틸리언", "work_type": "하차", "unit_price": 1, "log_id": 1},
            uid, "t", mode=MODE_QUERY,
        )
        assert result.get("success") is False
        assert "조회모드" in result.get("error", "")
    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert after == before


def test_5_photos_only_in_repair_mode():
    uid, cid = _ids("photo")
    set_mode(uid, cid, MODE_IDLE)
    assert should_accept_repair_photo(uid, cid) is False
    set_mode(uid, cid, MODE_JOURNAL)
    assert should_accept_repair_photo(uid, cid) is False
    set_mode(uid, cid, MODE_QUERY)
    assert should_accept_repair_photo(uid, cid) is False
    set_mode(uid, cid, MODE_REPAIR)
    assert should_accept_repair_photo(uid, cid) is True
    assert decide_bot_route(uid, cid, "구멍 바느질") == "repair"


def test_6_rooms_do_not_mix():
    uid = "mode-test-user-rooms"
    personal = "dm-room"
    group = "group-room"
    set_mode(uid, personal, MODE_JOURNAL)
    set_mode(uid, group, MODE_QUERY)
    assert get_mode(uid, personal) == MODE_JOURNAL
    assert get_mode(uid, group) == MODE_QUERY
    assert decide_bot_route(uid, personal, "오늘 작업") == "journal"
    assert decide_bot_route(uid, group, "오늘 작업") == "query"


def test_7_mode_end_clears_pending_not_logs():
    uid, cid = _ids("end")
    mgr = get_conversation_manager()
    mgr.set_state(uid, cid, {"vendor": "틸리언", "work_type": "하차", "qty": 3}, ["unit_price"], "단가?")
    assert mgr.get_state(uid, cid) is not None
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    apply_mode_command(uid, cid, parse_mode_command("모드 종료"))
    assert get_mode(uid, cid) == MODE_IDLE
    assert mgr.get_state(uid, cid) is None
    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert after == before


def test_8_invoice_shipping_same_as_baseline(isolated_runtime):
    """고정 fixture로 기존 add_courier_fee_by_zone을 호출한다. 계산 본체는 수정하지 않는다."""
    seed_shipping_fixture(isolated_runtime["db"])
    from utils.utils_courier import add_courier_fee_by_zone

    items = []
    add_courier_fee_by_zone("팔로우미코스메틱", "2025-06-01", "2025-06-30", items_list=items)
    counts = {i["항목"]: i["수량"] for i in items}
    assert counts.get("택배요금 (극소)") == 3
    assert counts.get("택배요금 (중)") == 1
    assert counts.get("택배요금 (소)", 0) == 0


def test_prefix_and_commands():
    assert parse_mode_command("일지모드 시작")["mode"] == MODE_JOURNAL
    assert parse_mode_command("수선모드 시작")["action"] == "start"
    assert parse_mode_command("조회모드 시작")["mode"] == MODE_QUERY
    assert parse_mode_command("모드 종료")["action"] == "end"
    assert parse_mode_command("현재 모드")["action"] == "status"
    assert parse_mode_command("기능설명")["action"] == "help"
    assert parse_mode_command("기능 설명")["action"] == "help"
    assert parse_mode_command("틸리언 하차") is None
    msg = with_mode_prefix("저장 완료", MODE_JOURNAL)
    assert msg.startswith("[일지모드]")


def test_feature_guide_does_not_change_mode_or_pending():
    uid, cid = _ids("help")
    mgr = get_conversation_manager()
    set_mode(uid, cid, MODE_JOURNAL)
    mgr.set_state(uid, cid, {"vendor": "틸리언", "work_type": "하차", "qty": 3}, ["unit_price"], "단가?")
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert decide_bot_route(uid, cid, "기능설명") == "mode_command"
    reply = apply_mode_command(uid, cid, parse_mode_command("기능설명"))
    assert get_mode(uid, cid) == MODE_JOURNAL
    assert mgr.get_state(uid, cid) is not None
    assert "일지모드" in reply
    assert "수선모드" in reply
    assert "조회모드" in reply
    assert "조회만" in reply or "조회만 합니다" in reply
    assert "이번달 작업실적" in reply
    assert "이번달 수선실적" in reply
    assert "지난달" in reply
    assert "사진 2장" in reply
    assert "미리보기" in reply
    assert "기능설명" in idle_guide()
    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert after == before
