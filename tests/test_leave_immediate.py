"""결재자 없이 신청한 연차는 대기 없이 해당 날짜가 바로 반영된다."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi import HTTPException

from backend.app.api.leave import (
    LeaveRequestCreate,
    bot_apply_leave,
    confirm_leave_on_calendar,
    create_leave_request,
    ensure_leave_tables,
    get_leave_calendar,
    get_leave_summary_data,
)


def _seed(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.commit()

    ensure_leave_tables()

    with sqlite3.connect(db_path) as con:
        con.execute(
            """INSERT INTO users
               (username, password_hash, nickname, join_date, leave_exempt, naver_works_id)
               VALUES (?,?,?,?,?,?)""",
            ("solo", "x", "단독", "2020-01-02", 0, "nw-solo"),
        )
        con.execute(
            """INSERT INTO users
               (username, password_hash, nickname, join_date, leave_exempt, naver_works_id)
               VALUES (?,?,?,?,?,?)""",
            ("boss", "x", "결재자", "2018-01-02", 0, "nw-boss"),
        )
        boss_id = con.execute("SELECT user_id FROM users WHERE username='boss'").fetchone()[0]
        con.execute(
            """INSERT INTO users
               (username, password_hash, nickname, join_date, leave_exempt, approver_id, naver_works_id)
               VALUES (?,?,?,?,?,?,?)""",
            ("staff", "x", "직원", "2020-01-02", 0, boss_id, "nw-staff"),
        )
        solo_id = con.execute("SELECT user_id FROM users WHERE username='solo'").fetchone()[0]
        staff_id = con.execute("SELECT user_id FROM users WHERE username='staff'").fetchone()[0]
        con.execute("INSERT INTO sessions (token, user_id) VALUES ('tok-solo', ?)", (solo_id,))
        con.execute("INSERT INTO sessions (token, user_id) VALUES ('tok-staff', ?)", (staff_id,))
        con.commit()
    return {"solo_id": solo_id, "staff_id": staff_id, "boss_id": boss_id}


def _status(db_path, request_id):
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            "SELECT status FROM leave_requests WHERE id=?", (request_id,)
        ).fetchone()
        approvals = con.execute(
            "SELECT COUNT(*) FROM leave_approvals WHERE request_id=?", (request_id,)
        ).fetchone()[0]
    return row[0], approvals


def test_no_approver_records_the_date_immediately(isolated_runtime):
    ids = _seed(isolated_runtime["db"])
    result = bot_apply_leave("nw-solo", "연차", "2026-10-21", "2026-10-21", "개인")

    assert result["auto_approved"] is True
    assert result["status"] == "approved"
    status, approvals = _status(isolated_runtime["db"], result["request_id"])
    assert status == "approved"
    assert approvals == 0

    summary = get_leave_summary_data(ids["solo_id"])
    assert summary["used_hours"] == 7
    assert summary["pending_hours"] == 0


def test_approver_keeps_the_request_pending(isolated_runtime):
    ids = _seed(isolated_runtime["db"])
    result = bot_apply_leave("nw-staff", "연차", "2026-10-22", "2026-10-22")

    assert result["auto_approved"] is False
    assert result["status"] == "pending"
    status, approvals = _status(isolated_runtime["db"], result["request_id"])
    assert status == "pending"
    assert approvals == 1

    summary = get_leave_summary_data(ids["staff_id"])
    assert summary["used_hours"] == 0
    assert summary["pending_hours"] == 7


def test_clearing_approvers_records_the_date_immediately(isolated_runtime, monkeypatch):
    ids = _seed(isolated_runtime["db"])

    def _swallow(coro):
        coro.close()
        return None

    monkeypatch.setattr("asyncio.create_task", _swallow)

    cleared = asyncio.run(
        create_leave_request(
            LeaveRequestCreate(
                leave_type="연차",
                start_date="2026-10-23",
                end_date="2026-10-23",
                custom_approvers=[],
            ),
            "tok-staff",
        )
    )
    assert cleared["auto_approved"] is True
    status, approvals = _status(isolated_runtime["db"], cleared["request_id"])
    assert status == "approved"
    assert approvals == 0

    pending = asyncio.run(
        create_leave_request(
            LeaveRequestCreate(
                leave_type="반차(오전)",
                start_date="2026-10-26",
                end_date="2026-10-26",
            ),
            "tok-staff",
        )
    )
    assert pending["auto_approved"] is False
    status, approvals = _status(isolated_runtime["db"], pending["request_id"])
    assert status == "pending"
    assert approvals == 1

    summary = get_leave_summary_data(ids["staff_id"])
    assert summary["used_hours"] == 7
    assert summary["pending_hours"] == 3.5


def test_existing_pending_request_stays_pending_until_admin_confirms(isolated_runtime):
    ids = _seed(isolated_runtime["db"])
    with sqlite3.connect(isolated_runtime["db"]) as con:
        cur = con.execute(
            """INSERT INTO leave_requests
               (user_id, leave_type, start_date, end_date, hours_requested, reason, status)
               VALUES (?, '반차(오후)', '2026-10-27', '2026-10-27', 3.5, '기존', 'pending')""",
            (ids["staff_id"],),
        )
        request_id = cur.lastrowid
        con.execute(
            """INSERT INTO leave_approvals (request_id, approver_id, step, status)
               VALUES (?, ?, 1, 'waiting')""",
            (request_id, ids["boss_id"]),
        )
        con.execute("UPDATE users SET is_admin=1 WHERE user_id=?", (ids["boss_id"],))
        con.execute("INSERT INTO sessions (token, user_id) VALUES ('tok-admin', ?)", (ids["boss_id"],))
        con.commit()

    ensure_leave_tables()
    status, _approvals = _status(isolated_runtime["db"], request_id)
    assert status == "pending"

    calendar = asyncio.run(get_leave_calendar("tok-admin", 2026, 10))
    day = calendar["days"]["2026-10-27"]
    assert calendar["is_admin"] is True
    assert day[0]["request_id"] == request_id
    assert day[0]["status"] == "pending"

    with pytest.raises(HTTPException) as denied:
        asyncio.run(confirm_leave_on_calendar(request_id, "tok-staff"))
    assert denied.value.status_code == 403

    result = asyncio.run(confirm_leave_on_calendar(request_id, "tok-admin"))
    assert result["status"] == "approved"
    status, _approvals = _status(isolated_runtime["db"], request_id)
    assert status == "approved"
    with sqlite3.connect(isolated_runtime["db"]) as con:
        approval_status = con.execute(
            "SELECT status, comment FROM leave_approvals WHERE request_id=?",
            (request_id,),
        ).fetchone()
    assert approval_status == ("skipped", "관리자 달력 확정")
    summary = get_leave_summary_data(ids["staff_id"])
    assert summary["used_hours"] == 3.5
    assert summary["pending_hours"] == 0
