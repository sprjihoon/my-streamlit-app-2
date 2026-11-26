"""알바는 이름과 주민번호로 등록하고, 신고자만 주휴수당을 받는다."""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.part_time.calc import daily_worker_tax, minimum_wage, weekly_holiday_pay


def _prepare(db_path):
    from backend.app.api.auth import ensure_users_table

    ensure_users_table()
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        admin_id = con.execute("SELECT user_id FROM users WHERE username = 'admin'").fetchone()[0]
        con.execute(
            """
            INSERT INTO users (username, password_hash, nickname, is_admin)
            VALUES ('staff', 'x', '직원', 0)
            """
        )
        staff_id = con.execute("SELECT user_id FROM users WHERE username = 'staff'").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('admin-tok', ?)", (admin_id,))
        con.execute("INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('staff-tok', ?)", (staff_id,))
        con.commit()


def test_weekly_holiday_follows_the_sheet_formula():
    hours, pay = weekly_holiday_pay(5, 10320, True)
    assert hours == 1
    assert pay == 10320
    assert weekly_holiday_pay(40, 10320, True) == (8, 82560)
    assert weekly_holiday_pay(40, 10320, False) == (0, 0)
    assert minimum_wage(2026) == 10320
    assert minimum_wage(2027) == 10700
    taxed = daily_worker_tax(4_000_000, 20)
    assert taxed["tax_base"] == 1_000_000
    assert taxed["calculated_tax"] == 60_000
    assert taxed["tax_credit"] == 33_000
    assert taxed["income_tax"] == 27_000
    assert taxed["local_tax"] == 2_700
    assert daily_worker_tax(700_000, 7)["income_tax"] == 0
    assert daily_worker_tax(3_030_000, 20)["income_tax"] == 0


def test_reported_worker_gets_weekly_holiday_and_unreported_does_not(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)

    denied = client.post(
        "/part-time/workers",
        params={"token": "staff-tok"},
        json={"name": "김알바", "resident_id": "900101-1234567", "reported": True},
    )
    assert denied.status_code == 403

    default_wage = client.get("/part-time/wage-default", params={"token": "admin-tok", "year": 2026})
    assert default_wage.status_code == 200
    assert default_wage.json()["hourly_wage"] == 10320

    reported = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "김알바", "resident_id": "900101-1234567", "reported": True},
    )
    assert reported.status_code == 200, reported.text
    reported_body = reported.json()
    assert reported_body["hourly_wage"] == minimum_wage(date.today().year)
    assert reported_body["resident_id"] == "900101-1******"
    assert "234567" not in reported_body["resident_id"]

    duplicate = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "김알바2", "resident_id": "9001011234567", "reported": True, "hourly_wage": 11000},
    )
    assert duplicate.status_code == 400

    hidden = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "박알바", "resident_id": "910101-2234567", "reported": False, "hourly_wage": 10320},
    )
    assert hidden.status_code == 200
    hidden_id = hidden.json()["id"]

    raised = client.put(
        f"/part-time/workers/{reported_body['id']}",
        params={"token": "admin-tok"},
        json={"hourly_wage": 12000},
    )
    assert raised.status_code == 200
    assert raised.json()["hourly_wage"] == 12000

    # 2026-11-02는 월요일, 11-08은 일요일. 다섯 시간씩 이틀이면 주휴 2시간.
    for work_date in ("2026-11-02", "2026-11-03"):
        saved = client.put(
            "/part-time/days",
            params={"token": "admin-tok"},
            json={
                "work_date": work_date,
                "entries": [
                    {"worker_id": reported_body["id"], "hours": 5},
                    {"worker_id": hidden_id, "hours": 5},
                ],
            },
        )
        assert saved.status_code == 200, saved.text

    calendar = saved.json()
    reported_total = next(row for row in calendar["totals"] if row["worker_id"] == reported_body["id"])
    hidden_total = next(row for row in calendar["totals"] if row["worker_id"] == hidden_id)
    assert reported_total["basic_hours"] == 10
    assert reported_total["base_pay"] == 120000
    assert reported_total["weekly_holiday_hours"] == 2
    assert reported_total["weekly_holiday_pay"] == 24000
    assert reported_total["total_pay"] == 144000
    day_entry = next(item for item in calendar["days"]["2026-11-03"] if item["worker_id"] == reported_body["id"])
    assert day_entry["pay"] == 60000
    assert hidden_total["basic_hours"] == 10
    assert hidden_total["weekly_holiday_hours"] == 0
    assert hidden_total["weekly_holiday_pay"] == 0
    slips = client.get("/part-time/slips", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert slips.status_code == 200, slips.text
    reported_slip = next(item for item in slips.json()["slips"] if item["worker_id"] == reported_body["id"])
    assert reported_slip["work_days"] == 2
    assert reported_slip["taxable_pay"] == 144000
    assert reported_slip["nontaxable_pay"] == 0
    assert reported_slip["income_tax"] == 0
    assert reported_slip["net_pay"] == 144000
    denied_slip = client.get("/part-time/slips", params={"token": "staff-tok", "year": 2026, "month": 11})
    assert denied_slip.status_code == 403

    sunday = next(week for week in calendar["weeks"] if week["sunday"] == "2026-11-08")
    assert any(person["weekly_holiday_pay"] == 24000 for person in sunday["workers"])

    cleared = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={"work_date": "2026-11-03", "entries": [{"worker_id": reported_body["id"], "hours": 0}]},
    )
    assert cleared.status_code == 200
    after = next(row for row in cleared.json()["totals"] if row["worker_id"] == reported_body["id"])
    assert after["basic_hours"] == 5
    assert after["weekly_holiday_pay"] == 12000

    duplicated = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={
            "work_date": "2026-11-04",
            "entries": [
                {"worker_id": reported_body["id"], "hours": 3},
                {"worker_id": reported_body["id"], "hours": 9},
            ],
        },
    )
    assert duplicated.status_code == 200, duplicated.text
    once = [item for item in duplicated.json()["days"]["2026-11-04"] if item["worker_id"] == reported_body["id"]]
    assert len(once) == 1
    assert once[0]["hours"] == 3


def test_weekly_holiday_uses_the_sunday_month_when_the_week_crosses(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    created = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "이알바", "resident_id": "880101-1234567", "reported": True, "hourly_wage": 10320},
    )
    assert created.status_code == 200, created.text
    worker_id = created.json()["id"]
    # 2026-10-26 월요일부터 2026-11-01 일요일. 주휴는 11월에만 잡힌다.
    saved = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={"work_date": "2026-10-30", "entries": [{"worker_id": worker_id, "hours": 5}]},
    )
    assert saved.status_code == 200, saved.text
    october = saved.json()
    assert october["totals"][0]["basic_hours"] == 5
    assert october["totals"][0]["weekly_holiday_pay"] == 0

    november = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert november.status_code == 200
    total = november.json()["totals"][0]
    assert total["basic_hours"] == 0
    assert total["weekly_holiday_hours"] == 1
    assert total["weekly_holiday_pay"] == 10320
