"""직원 퇴사처리는 계정을 남기고, 퇴사일부터 로그인을 막으며 다음 달 급여대장에서 뺀다."""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from backend.app.api.auth import hash_password
from backend.app.main import app
from tests.test_employment_contracts import _prepare, _sample, _worker_confirms


def _names(payload: dict) -> list[str]:
    return [line["employee_name"] for line in payload["lines"]]


def _employ(client: TestClient, staff_id: int) -> None:
    body = _sample()
    drafted = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=body,
    )
    assert drafted.status_code == 200
    _worker_confirms(client, staff_id)
    completed = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=body,
    )
    assert completed.status_code == 200


def _set_password(db_path, username: str, password: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(password), username),
        )
        con.commit()


def test_resignation_keeps_history_and_drops_the_next_payroll(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    _set_password(isolated_runtime["db"], "staff", "pw")
    client = TestClient(app)
    _employ(client, staff_id)

    november = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})
    assert november.status_code == 200
    assert "홍길동" in _names(november.json())
    hong_pay = next(line["net_pay"] for line in november.json()["lines"] if line["employee_name"] == "홍길동")

    resigned = client.post(
        f"/auth/users/{staff_id}/resign",
        params={"token": "admin-tok"},
        json={"resigned_on": "2026-11-15"},
    )
    assert resigned.status_code == 200
    assert resigned.json()["resigned_on"] == "2026-11-15"

    blocked = client.get("/auth/me", params={"token": "staff-tok"})
    assert blocked.status_code == 401
    assert blocked.json()["detail"] == "유효하지 않은 토큰입니다."
    wrong = client.post("/auth/login", json={"username": "staff", "password": "nope"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "잘못된 아이디 또는 비밀번호입니다."
    login = client.post("/auth/login", json={"username": "staff", "password": "pw"})
    assert login.status_code == 401
    assert login.json()["detail"] == "퇴사 처리된 계정입니다."

    opened = client.get("/employment-contracts", params={"token": "admin-tok", "view": "open"})
    assert all(row["user_id"] != staff_id for row in opened.json()["employees"])
    archived = client.get("/employment-contracts", params={"token": "admin-tok", "view": "completed"})
    assert any(row["employee_name"] == "홍길동" for row in archived.json()["contracts"])

    kept = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})
    assert kept.json()["existed"] is True
    assert "홍길동" in _names(kept.json())
    assert next(line["net_pay"] for line in kept.json()["lines"] if line["employee_name"] == "홍길동") == hong_pay

    december = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 12})
    assert december.status_code == 200
    assert "홍길동" not in _names(december.json())
    assert "장성령" in _names(december.json())

    listed = client.get("/auth/users", params={"token": "admin-tok"})
    staff = next(row for row in listed.json() if row["user_id"] == staff_id)
    assert staff["resigned_on"] == "2026-11-15"

    restored = client.post(f"/auth/users/{staff_id}/reinstate", params={"token": "admin-tok"})
    assert restored.status_code == 200
    again = client.post("/auth/login", json={"username": "staff", "password": "pw"})
    assert again.status_code == 200
    rebuilt = client.post(
        "/payroll-ledgers",
        params={"token": "admin-tok"},
        json={"year": 2026, "month": 12, "replace": True},
    )
    assert rebuilt.status_code == 200
    assert "홍길동" in _names(rebuilt.json())
    assert next(line["net_pay"] for line in rebuilt.json()["lines"] if line["employee_name"] == "홍길동") == hong_pay


def test_future_resignation_waits_until_that_date(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    _set_password(isolated_runtime["db"], "staff", "pw")
    client = TestClient(app)
    _employ(client, staff_id)
    client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})

    scheduled = client.post(
        f"/auth/users/{staff_id}/resign",
        params={"token": "admin-tok"},
        json={"resigned_on": "2026-12-31"},
    )
    assert scheduled.status_code == 200
    assert client.get("/auth/me", params={"token": "staff-tok"}).status_code == 200
    login = client.post("/auth/login", json={"username": "staff", "password": "pw"})
    assert login.status_code == 200

    december = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 12})
    assert "홍길동" in _names(december.json())
    january = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2027, "month": 1})
    assert january.status_code == 200
    assert "홍길동" not in _names(january.json())

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("UPDATE users SET resigned_on = '2026-11-01' WHERE user_id = ?", (staff_id,))
        con.commit()
    due = client.get("/auth/me", params={"token": "staff-tok"})
    assert due.status_code == 401
    assert due.json()["detail"] == "퇴사 처리된 계정입니다."
    gone = client.get("/auth/me", params={"token": "staff-tok"})
    assert gone.status_code == 401
    assert gone.json()["detail"] == "유효하지 않은 토큰입니다."


def test_resignation_rejects_bad_targets_and_dates(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    client = TestClient(app)
    with sqlite3.connect(isolated_runtime["db"]) as con:
        admin_id = con.execute("SELECT user_id FROM users WHERE username = 'admin'").fetchone()[0]
        con.execute(
            """
            INSERT INTO users (username, password_hash, nickname, is_admin, department, position, join_date)
            VALUES ('hr', 'x', '인사', 1, '인사과', '인사과장', '2020-01-01')
            """
        )
        hr_id = con.execute("SELECT user_id FROM users WHERE username = 'hr'").fetchone()[0]
        con.execute("INSERT INTO sessions (token, user_id) VALUES ('hr-tok', ?)", (hr_id,))
        con.execute(
            """
            INSERT INTO users (username, password_hash, nickname, is_admin, department, position, join_date)
            VALUES ('other', 'x', '다른팀', 0, '패션팀', '사원', '2026-01-01')
            """
        )
        other_id = con.execute("SELECT user_id FROM users WHERE username = 'other'").fetchone()[0]
        con.execute(
            """
            INSERT INTO users (username, password_hash, nickname, is_admin, department, position)
            VALUES ('clerk', 'x', '사원', 0, '수선팀', '사원')
            """
        )
        clerk_id = con.execute("SELECT user_id FROM users WHERE username = 'clerk'").fetchone()[0]
        con.execute("INSERT INTO sessions (token, user_id) VALUES ('clerk-tok', ?)", (clerk_id,))
        con.commit()

    self_resign = client.post(
        f"/auth/users/{admin_id}/resign",
        params={"token": "admin-tok"},
        json={"resigned_on": "2026-11-15"},
    )
    assert self_resign.status_code == 400
    system = client.post(
        f"/auth/users/{admin_id}/resign",
        params={"token": "hr-tok"},
        json={"resigned_on": "2026-11-15"},
    )
    assert system.status_code == 400
    assert "시스템 계정" in system.json()["detail"]

    early = client.post(
        f"/auth/users/{staff_id}/resign",
        params={"token": "admin-tok"},
        json={"resigned_on": "2020-01-01"},
    )
    assert early.status_code == 400
    bad_date = client.post(
        f"/auth/users/{staff_id}/resign",
        params={"token": "admin-tok"},
        json={"resigned_on": "2026/11/15"},
    )
    assert bad_date.status_code == 400

    other_team = client.post(
        f"/auth/users/{other_id}/resign",
        params={"token": "staff-tok"},
        json={"resigned_on": "2026-11-15"},
    )
    assert other_team.status_code == 403
    denied = client.post(
        f"/auth/users/{staff_id}/resign",
        params={"token": "clerk-tok"},
        json={"resigned_on": "2026-11-15"},
    )
    assert denied.status_code == 403

    active = client.post(f"/auth/users/{staff_id}/reinstate", params={"token": "admin-tok"})
    assert active.status_code == 400
