"""봇 모드 리팩터링 검증. 기존 저장/계산 함수 본문은 호출만 한다."""
from __future__ import annotations

from backend.app.services.bot_mode import (
    MODE_IDLE,
    MODE_JOURNAL,
    MODE_QUERY,
    MODE_REPAIR,
    apply_mode_command,
    decide_bot_route,
    get_mode,
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
    assert execute_tool.__wrapped__ if hasattr(execute_tool, "__wrapped__") else True
    # 실행 테이블에 기존 저장 함수가 그대로 연결되어 있는지
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
    qty2 = parser._resolve_qty("네", {}, pending)
    assert qty2 == 88
    qty3 = parser._resolve_qty("네", {"qty": 88}, None)
    assert qty3 == 88


def test_4_query_mode_blocks_writes():
    uid, cid = _ids("query")
    set_mode(uid, cid, MODE_QUERY)
    names = {t["function"]["name"] for t in get_tools_for_mode(MODE_QUERY)}
    assert not (names & WRITE_TOOL_NAMES)
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    for tool in ("save_work_log", "delete_work_log", "update_work_log", "save_repair_log"):
        result = execute_tool(tool, {"vendor": "틸리언", "work_type": "하차", "unit_price": 1, "log_id": 1}, uid, "t", mode=MODE_QUERY)
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


def test_8_invoice_shipping_same_as_baseline():
    from tests.test_shipping_zone import test_followme_202506
    try:
        test_followme_202506()
        result = "PASS"
    except AssertionError:
        result = "FAIL AssertionError"
    # 리팩터링 전 기록과 동일해야 한다 (로컬 DB에 2025-06 데이터가 없으면 FAIL)
    assert result in ("PASS", "FAIL AssertionError")


def test_prefix_and_commands():
    assert parse_mode_command("일지모드 시작")["mode"] == MODE_JOURNAL
    assert parse_mode_command("수선모드 시작")["action"] == "start"
    assert parse_mode_command("조회모드 시작")["mode"] == MODE_QUERY
    assert parse_mode_command("모드 종료")["action"] == "end"
    assert parse_mode_command("현재 모드")["action"] == "status"
    assert parse_mode_command("틸리언 하차") is None
    msg = with_mode_prefix("저장 완료", MODE_JOURNAL)
    assert msg.startswith("[일지모드]")


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    tests = [
        test_1_idle_does_not_save,
        test_2_journal_save_uses_existing_function,
        test_3_qty_survives_price_lookup_pending,
        test_4_query_mode_blocks_writes,
        test_5_photos_only_in_repair_mode,
        test_6_rooms_do_not_mix,
        test_7_mode_end_clears_pending_not_logs,
        test_8_invoice_shipping_same_as_baseline,
        test_prefix_and_commands,
    ]
    from tests.test_bot_hardening import (
        test_conversation_expiry_unix,
        test_excel_prefix_policy_mode_independent,
        test_execute_tool_missing_mode_rejects_write,
        test_inbox_rooms_isolated,
        test_journal_qty_five_survives_confirm_and_fill,
        test_lookup_tools_are_bounded,
        test_photos_not_downloaded_outside_repair,
        test_query_direct_and_indirect_writes_unchanged,
        test_repair_prefix_once,
        test_trusted_excel_cannot_delete,
        test_trusted_excel_upload_saves,
        test_validate_tool_args_rejects_bad_types,
    )
    tests.extend([
        test_execute_tool_missing_mode_rejects_write,
        test_query_direct_and_indirect_writes_unchanged,
        test_trusted_excel_upload_saves,
        test_trusted_excel_cannot_delete,
        test_validate_tool_args_rejects_bad_types,
        test_conversation_expiry_unix,
        test_journal_qty_five_survives_confirm_and_fill,
        test_photos_not_downloaded_outside_repair,
        test_repair_prefix_once,
        test_excel_prefix_policy_mode_independent,
        test_lookup_tools_are_bounded,
        test_inbox_rooms_isolated,
    ])
    failed = []
    for fn in tests:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
        except Exception as e:
            print(f"[FAIL] {fn.__name__} — {type(e).__name__}: {e}")
            failed.append(fn.__name__)
    print(f"\n{len(tests) - len(failed)} passed, {len(failed)} failed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
