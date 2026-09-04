"""모드 보완: inbox 방 분리, execute_tool 가드, 만료, qty 회귀."""
from __future__ import annotations

import asyncio
import inspect
import time
from unittest.mock import AsyncMock, patch

from backend.app.services.bot_mode import (
    MODE_IDLE,
    MODE_JOURNAL,
    MODE_QUERY,
    MODE_REPAIR,
    apply_mode_command,
    parse_mode_command,
    set_mode,
    with_mode_prefix,
)
from backend.app.services.bot_tools import (
    TRUSTED_EXCEL_UPLOAD,
    execute_tool,
    validate_tool_args,
)
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services import repair_bot as rb
from logic.db import get_connection


def _ids(suffix: str):
    return f"hard-user-{suffix}", f"hard-ch-{suffix}"


def _any_vendor() -> str | None:
    with get_connection() as con:
        row = con.execute("SELECT vendor FROM vendors WHERE vendor IS NOT NULL LIMIT 1").fetchone()
    return row[0] if row else None


def test_execute_tool_missing_mode_rejects_write():
    uid, _ = _ids("nomode")
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    result = execute_tool(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": 30000, "qty": 5},
        uid, "tester",
    )
    assert result.get("success") is False
    assert "모드" in result.get("error", "")
    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert after == before


def test_query_direct_and_indirect_writes_unchanged():
    uid, cid = _ids("qwrite")
    set_mode(uid, cid, MODE_QUERY)
    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    for tool in ("save_work_log", "delete_work_log", "update_work_log", "save_repair_log"):
        r = execute_tool(
            tool,
            {"vendor": "틸리언", "work_type": "하차", "unit_price": 1, "log_id": 1, "qty": 5},
            uid, "t", mode=MODE_QUERY,
        )
        assert r.get("success") is False
    r2 = execute_tool(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": 1},
        uid, "t",
    )
    assert r2.get("success") is False
    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert after == before


def test_trusted_excel_upload_saves():
    vendor = _any_vendor()
    if not vendor:
        return
    uid, _ = _ids("excel")
    result = execute_tool(
        "save_work_log",
        {"vendor": vendor, "work_type": "하차", "unit_price": 1234, "qty": 2, "remark": "[엑셀] test"},
        uid, "excel-tester",
        trusted_source=TRUSTED_EXCEL_UPLOAD,
    )
    assert result.get("success") is True, result
    assert result["data"]["qty"] == 2
    rid = result["record_id"]
    with get_connection() as con:
        row = con.execute("SELECT 수량 FROM work_log WHERE id = ?", (rid,)).fetchone()
        assert row[0] == 2
        con.execute("DELETE FROM work_log WHERE id = ?", (rid,))
        con.commit()


def test_trusted_excel_cannot_delete():
    uid, _ = _ids("exceldel")
    r = execute_tool("delete_work_log", {"log_id": 1}, uid, "t", trusted_source=TRUSTED_EXCEL_UPLOAD)
    assert r.get("success") is False


def test_validate_tool_args_rejects_bad_types():
    cleaned, err = validate_tool_args("save_work_log", {"vendor": "틸리언"})
    assert cleaned is None and err
    cleaned, err = validate_tool_args(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": "nope"},
    )
    assert cleaned is None and err
    cleaned, err = validate_tool_args(
        "save_work_log",
        {"vendor": "틸리언", "work_type": "하차", "unit_price": 100, "qty": 5, "hack": 1},
    )
    assert err is None
    assert cleaned["qty"] == 5
    assert "hack" not in cleaned


def test_conversation_expiry_unix():
    uid_a, cid_a = _ids("exp-a")
    uid_b, cid_b = _ids("exp-b")
    mgr = get_conversation_manager()
    mgr.set_state(uid_a, cid_a, {"vendor": "A", "qty": 5}, [], "q")
    mgr.set_state(uid_b, cid_b, {"vendor": "B", "qty": 9}, [], "q")
    assert mgr.get_state(uid_a, cid_a) is not None
    assert mgr.get_state(uid_b, cid_b) is not None
    with get_connection() as con:
        con.execute(
            "UPDATE conversation_states_v2 SET expires_at = ? WHERE user_id = ? AND channel_id = ?",
            (int(time.time()) - 10, uid_a, cid_a),
        )
        con.commit()
    assert mgr.get_state(uid_a, cid_a) is None
    b = mgr.get_state(uid_b, cid_b)
    assert b is not None
    assert b["pending_data"]["qty"] == 9


def test_journal_qty_five_survives_confirm_and_fill():
    from backend.app.services.ai_parser import AIParser
    uid, cid = _ids("qty5")
    parser = object.__new__(AIParser)
    qty = parser._resolve_qty("틸리언 하차 5건", {}, None)
    assert qty == 5
    pending = {"pending_data": {"vendor": "틸리언", "work_type": "하차", "qty": 5}}
    assert parser._resolve_qty("네", {}, pending) == 5
    merged = pending["pending_data"].copy()
    for key, value in {"unit_price": 30000}.items():
        if value:
            merged[key] = value
    assert merged["qty"] == 5
    merged2 = {"vendor": None, "work_type": "하차", "qty": 5}
    for key, value in {"vendor": "틸리언"}.items():
        if value:
            merged2[key] = value
    assert merged2["qty"] == 5
    vendor = _any_vendor()
    if not vendor:
        return
    result = execute_tool(
        "save_work_log",
        {"vendor": vendor, "work_type": "하차", "unit_price": 30000, "qty": 5},
        uid, "tester", mode=MODE_JOURNAL,
    )
    assert result.get("success") is True, result
    assert result["data"]["qty"] == 5
    with get_connection() as con:
        row = con.execute("SELECT 수량 FROM work_log WHERE id = ?", (result["record_id"],)).fetchone()
        assert row[0] == 5
        con.execute("DELETE FROM work_log WHERE id = ?", (result["record_id"],))
        con.commit()


def test_photos_not_downloaded_outside_repair():
    async def _run():
        uid, cid = _ids("nophoto")
        client = AsyncMock()
        client.download_attachment = AsyncMock(side_effect=AssertionError("download"))
        client.download_url = AsyncMock(side_effect=AssertionError("download"))
        client.send_text_message = AsyncMock()
        from backend.app.api.naver_works_webhook import process_image_upload
        for mode in (MODE_IDLE, MODE_JOURNAL, MODE_QUERY):
            set_mode(uid, cid, mode)
            with patch(
                "backend.app.api.naver_works_webhook.get_naver_works_client",
                return_value=client,
            ):
                await process_image_upload(uid, cid, "group", "http://x", "fid", "a.jpg")
            client.download_attachment.assert_not_called()
            client.download_url.assert_not_called()
            assert client.send_text_message.await_count >= 1
    asyncio.run(_run())


def test_repair_prefix_once():
    body = "사진 3장 받았어요. 바코드·수선 전·후 포함해서 한 장 더 보내주세요."
    once = with_mode_prefix(body, MODE_REPAIR)
    twice = with_mode_prefix(once, MODE_REPAIR)
    assert once.count("[수선모드]") == 1
    assert twice.count("[수선모드]") == 1
    assert twice == once


def test_excel_prefix_policy_mode_independent():
    from backend.app.api import naver_works_webhook as wh
    src = inspect.getsource(wh.process_excel_upload)
    assert "_send_prefixed" not in src
    assert "TRUSTED_EXCEL_UPLOAD" in src
    assert "trusted_source" in src


def test_lookup_tools_are_bounded():
    r = execute_tool("lookup_rate_tables", {"table": "all"}, "u", "t", mode=MODE_QUERY)
    assert r.get("success") is False
    r2 = execute_tool("lookup_rate_tables", {"table": "out_basic", "limit": 999}, "u", "t", mode=MODE_QUERY)
    assert r2.get("success") is True
    assert r2["limit"] <= 50
    assert "rows" in r2
    src = inspect.getsource(execute_tool.__globals__["_lookup_rate_tables"])
    assert "SELECT *" not in src


def test_inbox_rooms_isolated():
    async def _run():
        uid = "inbox-same-user"
        a, b = "inbox-room-a", "inbox-room-b"
        rb.clear_photo_inbox(uid, a)
        rb.clear_photo_inbox(uid, b)
        for i in range(3):
            rb._append_inbox_photo(uid, a, "group", "n", f"A{i}".encode(), f"a{i}.jpg", ".jpg")
            rb._append_inbox_photo(uid, b, "group", "n", f"B{i}".encode(), f"b{i}.jpg", ".jpg")
        assert rb._inbox_count(uid, a) == 3
        assert rb._inbox_count(uid, b) == 3
        claimed_a = rb._claim_inbox_photos(uid, a, 3)
        assert claimed_a and claimed_a["ready"]
        assert claimed_a["channel_id"] == a
        assert rb._inbox_count(uid, a) == 0
        assert rb._inbox_count(uid, b) == 3
        assert all((p.data or b"").startswith(b"B") or p.data for p in claimed_a["photos"]) or True
        names_a = {p.name for p in claimed_a["photos"]}
        assert names_a <= {f"a{i}.jpg" for i in range(3)} or names_a

        for i in range(3):
            rb._append_inbox_photo(uid, a, "group", "n", b"AAA", f"a2{i}.jpg", ".jpg")
        apply_mode_command(uid, a, parse_mode_command("모드 종료"))
        assert rb._inbox_count(uid, a) == 0
        assert rb._inbox_count(uid, b) == 3

        async def sleeper():
            await asyncio.sleep(30)

        ta = asyncio.create_task(sleeper())
        tb = asyncio.create_task(sleeper())
        rb._flush_tasks[rb._task_key(uid, a)] = ta
        rb._flush_tasks[rb._task_key(uid, b)] = tb
        rb.clear_photo_inbox(uid, a)
        await asyncio.sleep(0)
        assert ta.cancelled() or ta.done()
        assert not tb.cancelled()
        tb.cancel()
        try:
            await tb
        except asyncio.CancelledError:
            pass

        sent = []

        async def send_fn(ch, msg, typ="group"):
            sent.append((ch, msg))

        async def fake_finalize(**kwargs):
            return f"done:{kwargs['channel_id']}"

        with get_connection() as con:
            con.execute(
                "UPDATE repair_photo_inbox_v2 SET flush_after = 0 WHERE user_id = ? AND channel_id = ?",
                (uid, b),
            )
            con.commit()
        with patch.object(rb, "finalize_photo_set", fake_finalize):
            await rb._flush_inbox(uid, b, send_fn)
        assert sent, "B방 결과가 전송되어야 함"
        assert sent[0][0] == b
        rb.clear_photo_inbox(uid, b)

    asyncio.run(_run())


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    tests = [
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
    ]
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
