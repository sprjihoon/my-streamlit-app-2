"""알바는 이름과 주민번호로 등록하고, 신고자만 주휴수당을 받는다."""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.part_time.calc import (
    choose_pay_regime,
    daily_worker_tax,
    minimum_wage,
    settle_part_time_pay,
    weekly_holiday_pay,
)
from backend.app.services.part_time.calendar_actions import (
    date_from_point_target,
    drop_worker_onto_date,
    shift_times,
    workers_available_on_date,
)


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
    assert weekly_holiday_pay(5, 10320, True) == (0, 0)
    assert weekly_holiday_pay(13, 10320, True) == (0, 0)
    assert weekly_holiday_pay(14, 10320, True) == (2.8, 28896)
    assert weekly_holiday_pay(15, 10320, True) == (3, 30960)
    assert weekly_holiday_pay(40, 10320, True) == (8, 82560)
    assert weekly_holiday_pay(40, 10320, False) == (8, 82560)
    month_end = date(2026, 11, 30)
    assert choose_pay_regime(date(2026, 11, 2), month_end, 10, 10) == "short"
    assert choose_pay_regime(date(2026, 8, 1), month_end, 10, 10) == "short_long"
    assert choose_pay_regime(date(2026, 11, 2), month_end, 15, 15) == "daily"
    assert choose_pay_regime(date(2026, 8, 1), month_end, 15, 40) == "regular"
    cheap = settle_part_time_pay(120_000, 2, 10, True, 2026, 11, regime="short")
    assert cheap["employment_insurance"] == 0
    assert cheap["income_tax"] == 0
    assert cheap["employer_industrial"] == 960
    assert cheap["company_cost"] == 120_960
    longer = settle_part_time_pay(120_000, 2, 10, True, 2026, 11, regime="short_long")
    assert longer["employment_insurance"] == 1_080
    assert longer["employer_employment"] == 1_380
    assert longer["company_cost"] == 122_340
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
    short = settle_part_time_pay(144_000, 2, 10, True, 2026, 11, "900101-1234567")
    assert short["withholding_kind"] == "daily"
    assert short["employment_insurance"] == 1290
    assert short["pension"] == 0
    assert short["net_pay"] == 142_710
    covered = settle_part_time_pay(2_200_000, 8, 60, True, 2026, 11, "900101-1234567")
    assert covered["pension_base"] == 2_200_000
    assert covered["pension"] == 104_500
    assert covered["health"] == 79_090
    assert covered["care"] == 10_390
    assert covered["employment_insurance"] == 19_800
    assert covered["employer_industrial"] == 17_600
    assert covered["net_pay"] == 2_200_000 - covered["deduction_total"]
    assert covered["employer_industrial"] not in (covered["deduction_total"],)
    low = settle_part_time_pay(300_000, 8, 40, True, 2026, 11, "900101-1234567")
    assert low["pension_base"] == 410_000
    assert low["pension"] == 19_470
    older = settle_part_time_pay(2_200_000, 8, 60, True, 2026, 11, "600101-1234567")
    assert older["pension"] == 0
    assert older["employment_insurance"] == 0
    freelance = settle_part_time_pay(103_200, 2, 10, False, 2026, 11, "910101-2234567")
    assert freelance["income_tax"] == 3090
    assert freelance["local_tax"] == 300
    assert freelance["pension"] == 0
    assert freelance["employer_industrial"] == 0
    assert freelance["net_pay"] == 99_810
    small = settle_part_time_pay(30_000, 1, 3, False, 2026, 11, "910101-2234567")
    assert small["withholding_kind"] == "business_3_3"
    assert small["income_tax"] == 900
    assert small["local_tax"] == 90
    assert small["net_pay"] == 29_010
    assert small["employment_insurance"] == 0


def test_fifteen_hours_uses_daily_tax_and_three_months_adds_employment_insurance(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    daily = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "일용알바", "resident_id": "900101-1234567", "hourly_wage": 10320},
    )
    lasting = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "장기알바", "resident_id": "910101-2234567", "hourly_wage": 10320},
    )
    assert daily.status_code == 200 and lasting.status_code == 200
    daily_id = daily.json()["id"]
    lasting_id = lasting.json()["id"]
    for work_date, hours, worker_id in (
        ("2026-11-02", 8, daily_id),
        ("2026-11-03", 7, daily_id),
        ("2026-08-03", 5, lasting_id),
        ("2026-11-02", 5, lasting_id),
    ):
        saved = client.put(
            "/part-time/days",
            params={"token": "admin-tok"},
            json={"work_date": work_date, "entries": [{"worker_id": worker_id, "hours": hours, "start_time": "09:00"}]},
        )
        assert saved.status_code == 200, saved.text
    slips = client.get("/part-time/slips", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert slips.status_code == 200, slips.text
    daily_slip = next(item for item in slips.json()["slips"] if item["worker_id"] == daily_id)
    lasting_slip = next(item for item in slips.json()["slips"] if item["worker_id"] == lasting_id)
    assert daily_slip["pay_regime"] == "daily"
    assert daily_slip["taxable_pay"] == 185760
    assert lasting_slip["pay_regime"] == "short_long"
    assert lasting_slip["employment_insurance"] == 460
    assert lasting_slip["employer_industrial"] == 410
    sheet = client.get("/part-time/xlsx", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert sheet.status_code == 200
    from io import BytesIO
    from openpyxl import load_workbook
    book = load_workbook(BytesIO(sheet.content))
    names = [
        book["11월"].cell(row, col).value
        for row in range(1, (book["11월"].max_row or 1) + 1)
        for col in range(1, 16)
    ]
    assert "일용알바" in names
    assert "장기알바" not in names


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
        json={
            "name": "김알바",
            "resident_id": "900101-1234567",
            "reported": True,
            "phone": "01012345678",
            "bank_name": "농협",
            "account_number": "351-1207-8919-53",
        },
    )
    assert reported.status_code == 200, reported.text
    reported_body = reported.json()
    assert reported_body["phone"] == "010-1234-5678"
    assert reported_body["bank_name"] == "농협"
    assert reported_body["account_number"] == "351-1207-8919-53"
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
    assert raised.json()["bank_name"] == "농협"
    assert raised.json()["account_number"] == "351-1207-8919-53"
    account = client.put(
        f"/part-time/workers/{reported_body['id']}",
        params={"token": "admin-tok"},
        json={"bank_name": "카카오뱅크", "account_number": "3333-30-7784236"},
    )
    assert account.status_code == 200, account.text
    assert account.json()["bank_name"] == "카카오뱅크"
    assert account.json()["account_number"] == "3333-30-7784236"

    # 2026-11-02는 월요일, 11-08은 일요일. 다섯 시간씩 이틀은 10시간이라 주휴가 없다.
    for work_date in ("2026-11-02", "2026-11-03"):
        saved = client.put(
            "/part-time/days",
            params={"token": "admin-tok"},
            json={
                "work_date": work_date,
                "entries": [
                    {"worker_id": reported_body["id"], "hours": 5, "start_time": "09:00"},
                    {"worker_id": hidden_id, "hours": 5, "start_time": "13:00"},
                ],
            },
        )
        assert saved.status_code == 200, saved.text

    calendar = saved.json()
    reported_total = next(row for row in calendar["totals"] if row["worker_id"] == reported_body["id"])
    hidden_total = next(row for row in calendar["totals"] if row["worker_id"] == hidden_id)
    assert reported_total["basic_hours"] == 10
    assert reported_total["base_pay"] == 120000
    assert reported_total["weekly_holiday_hours"] == 0
    assert reported_total["weekly_holiday_pay"] == 0
    assert reported_total["total_pay"] == 120000
    day_entry = next(item for item in calendar["days"]["2026-11-03"] if item["worker_id"] == reported_body["id"])
    assert day_entry["pay"] == 60000
    assert day_entry["start_time"] == "09:00"
    assert day_entry["end_time"] == "14:00"
    assert day_entry["shift_label"] == "09:00~14:00"
    assert hidden_total["basic_hours"] == 10
    assert hidden_total["weekly_holiday_hours"] == 0
    assert hidden_total["weekly_holiday_pay"] == 0
    slips = client.get("/part-time/slips", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert slips.status_code == 200, slips.text
    reported_slip = next(item for item in slips.json()["slips"] if item["worker_id"] == reported_body["id"])
    assert reported_slip["work_days"] == 2
    assert reported_slip["taxable_pay"] == 120000
    assert reported_slip["nontaxable_pay"] == 0
    assert reported_slip["pay_regime"] == "short"
    assert reported_slip["income_tax"] == 0
    assert reported_slip["employment_insurance"] == 0
    assert reported_slip["pension"] == 0
    assert reported_slip["health"] == 0
    assert reported_slip["employer_industrial"] == 960
    assert reported_slip["net_pay"] == 120000
    assert reported_slip["company_cost"] == 120960
    hidden_slip = next(item for item in slips.json()["slips"] if item["worker_id"] == hidden_id)
    assert hidden_slip["pay_regime"] == "short"
    assert hidden_slip["withholding_kind"] == "short"
    assert hidden_slip["income_tax"] == 0
    assert hidden_slip["local_tax"] == 0
    assert hidden_slip["employment_insurance"] == 0
    assert hidden_slip["employer_industrial"] == 820
    assert hidden_slip["net_pay"] == 103200
    denied_slip = client.get("/part-time/slips", params={"token": "staff-tok", "year": 2026, "month": 11})
    assert denied_slip.status_code == 403

    sheet = client.get("/part-time/xlsx", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert sheet.status_code == 200
    assert sheet.content[:2] == b"PK"
    from io import BytesIO
    from openpyxl import load_workbook
    book = load_workbook(BytesIO(sheet.content))
    assert book.sheetnames[:2] == ["11월", "공단"]
    ledger = book["11월"]
    assert ledger["A1"].value == "2026년 11월 일용근로대장"
    kim_block = None
    for start in range(7, (ledger.max_row or 7) + 1, 19):
        for origin in (2, 8):
            if ledger.cell(start, origin).value == "김알바":
                kim_block = (start, origin)
                break
        if kim_block:
            break
    assert kim_block is None

    left = client.put(
        f"/part-time/workers/{reported_body['id']}",
        params={"token": "admin-tok"},
        json={"active": False},
    )
    assert left.status_code == 200, left.text
    assert left.json()["active"] is False
    parked = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert parked.status_code == 200
    parked_worker = next(item for item in parked.json()["workers"] if item["id"] == reported_body["id"])
    assert parked_worker["active"] is False
    brought_back = client.put(
        f"/part-time/workers/{reported_body['id']}",
        params={"token": "admin-tok"},
        json={"active": True},
    )
    assert brought_back.status_code == 200, brought_back.text
    assert brought_back.json()["active"] is True
    restored = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    restored_worker = next(item for item in restored.json()["workers"] if item["id"] == reported_body["id"])
    assert restored_worker["active"] is True

    sunday = next(week for week in calendar["weeks"] if week["sunday"] == "2026-11-08")
    assert any(person["weekly_holiday_pay"] == 0 and person["basic_hours"] == 10 for person in sunday["workers"])

    cleared = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={"work_date": "2026-11-03", "entries": [{"worker_id": reported_body["id"], "hours": 0}]},
    )
    assert cleared.status_code == 200
    after = next(row for row in cleared.json()["totals"] if row["worker_id"] == reported_body["id"])
    assert after["basic_hours"] == 5
    assert after["weekly_holiday_pay"] == 0

    duplicated = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={
            "work_date": "2026-11-04",
            "entries": [
                {"worker_id": reported_body["id"], "hours": 3, "start_time": "10:00"},
                {"worker_id": reported_body["id"], "hours": 9, "start_time": "12:00"},
            ],
        },
    )
    assert duplicated.status_code == 200, duplicated.text
    once = [item for item in duplicated.json()["days"]["2026-11-04"] if item["worker_id"] == reported_body["id"]]
    assert len(once) == 1
    assert once[0]["hours"] == 3
    assert once[0]["start_time"] == "10:00"
    assert once[0]["end_time"] == "13:00"


def test_calendar_drop_and_date_click_rules():
    workers = [
        {"id": 1, "name": "김알바", "active": True},
        {"id": 2, "name": "박알바", "active": True},
        {"id": 3, "name": "이알바", "active": False},
    ]
    empty: list[dict] = []
    with_kim = [{"worker_id": 1, "name": "김알바"}]

    assert drop_worker_onto_date(workers, empty, 1) == {"kind": "hours", "worker_id": 1, "name": "김알바"}
    assert drop_worker_onto_date(workers, with_kim, 1) == {"kind": "duplicate", "name": "김알바"}
    assert drop_worker_onto_date(workers, with_kim, 2) == {"kind": "hours", "worker_id": 2, "name": "박알바"}
    assert drop_worker_onto_date(workers, empty, 3) == {"kind": "ignore"}
    assert drop_worker_onto_date(workers, empty, 99) == {"kind": "ignore"}

    available = workers_available_on_date(workers, with_kim)
    assert [item["id"] for item in available] == [2]
    assert workers_available_on_date(workers, empty)[0]["id"] == 1
    assert date_from_point_target("2026-11-03") == "2026-11-03"
    assert date_from_point_target("") is None
    assert date_from_point_target(None) is None
    assert shift_times("09:00", 5) == {"start_time": "09:00", "end_time": "14:00", "next_day": False, "label": "09:00~14:00"}
    assert shift_times("09:00", 5.5)["end_time"] == "14:30"
    assert shift_times("22:00", 4) == {"start_time": "22:00", "end_time": "02:00", "next_day": True, "label": "22:00~익일 02:00"}


def test_date_add_and_drag_save_put_hours_on_that_day(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    kim = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "김알바", "resident_id": "900101-1234567", "reported": True, "hourly_wage": 10320},
    )
    park = client.post(
        "/part-time/workers",
        params={"token": "admin-tok"},
        json={"name": "박알바", "resident_id": "910101-2234567", "reported": False, "hourly_wage": 10320},
    )
    assert kim.status_code == 200 and park.status_code == 200
    kim_id = kim.json()["id"]
    park_id = park.json()["id"]

    first = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={"work_date": "2026-11-03", "entries": [{"worker_id": kim_id, "hours": 5, "start_time": "09:00"}]},
    )
    assert first.status_code == 200, first.text
    day = first.json()["days"]["2026-11-03"]
    assert [(item["worker_id"], item["hours"]) for item in day] == [(kim_id, 5)]
    assert day[0]["start_time"] == "09:00"
    assert day[0]["end_time"] == "14:00"
    assert day[0]["shift_label"] == "09:00~14:00"

    second = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={"work_date": "2026-11-03", "entries": [{"worker_id": park_id, "hours": 4, "start_time": "13:30"}]},
    )
    assert second.status_code == 200, second.text
    names = sorted(item["name"] for item in second.json()["days"]["2026-11-03"])
    assert names == ["김알바", "박알바"]
    park_entry = next(item for item in second.json()["days"]["2026-11-03"] if item["worker_id"] == park_id)
    assert park_entry["start_time"] == "13:30"
    assert park_entry["end_time"] == "17:30"

    calendar = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert calendar.status_code == 200
    remaining = workers_available_on_date(calendar.json()["workers"], calendar.json()["days"]["2026-11-03"])
    remaining_ids = {item["id"] for item in remaining}
    assert kim_id not in remaining_ids
    assert park_id not in remaining_ids
    other_day = workers_available_on_date(calendar.json()["workers"], calendar.json()["days"].get("2026-11-04", []))
    assert {kim_id, park_id} <= {item["id"] for item in other_day}

    missing = client.put(
        "/part-time/days",
        params={"token": "admin-tok"},
        json={"work_date": "2026-11-04", "entries": [{"worker_id": kim_id, "hours": 5}]},
    )
    assert missing.status_code == 400
    assert "시작시간" in missing.json()["detail"]


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
        json={"work_date": "2026-10-30", "entries": [{"worker_id": worker_id, "hours": 15, "start_time": "09:00"}]},
    )
    assert saved.status_code == 200, saved.text
    october = saved.json()
    october_total = next(row for row in october["totals"] if row["worker_id"] == worker_id)
    assert october_total["basic_hours"] == 15
    assert october_total["weekly_holiday_pay"] == 0

    november = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert november.status_code == 200
    total = next(row for row in november.json()["totals"] if row["worker_id"] == worker_id)
    assert total["basic_hours"] == 0
    assert total["weekly_holiday_hours"] == 3
    assert total["weekly_holiday_pay"] == 30960


def test_part_time_permission_lets_a_non_admin_open_the_ledger(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            """
            INSERT INTO users (username, password_hash, nickname, is_admin, position, department)
            VALUES ('lead', 'x', '팀장', 0, '팀장', '패션팀')
            """
        )
        lead_id = con.execute("SELECT user_id FROM users WHERE username = 'lead'").fetchone()[0]
        staff_id = con.execute("SELECT user_id FROM users WHERE username = 'staff'").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('lead-tok', ?)", (lead_id,))
        con.commit()

    blocked = client.put(
        f"/auth/users/{staff_id}",
        params={"token": "lead-tok"},
        json={"can_manage_part_time": True},
    )
    assert blocked.status_code == 403

    still_denied = client.get("/part-time/calendar", params={"token": "staff-tok", "year": 2026, "month": 11})
    assert still_denied.status_code == 403

    granted = client.put(
        f"/auth/users/{staff_id}",
        params={"token": "admin-tok"},
        json={"can_manage_part_time": True},
    )
    assert granted.status_code == 200, granted.text

    me = client.get("/auth/me", params={"token": "staff-tok"})
    assert me.status_code == 200
    assert me.json()["is_admin"] is False
    assert me.json()["can_manage_part_time"] is True

    listed = client.get("/auth/users", params={"token": "admin-tok"})
    staff = next(row for row in listed.json() if row["username"] == "staff")
    assert staff["can_manage_part_time"] is True
    assert next(row for row in listed.json() if row["username"] == "admin")["can_manage_part_time"] is False

    created = client.post(
        "/part-time/workers",
        params={"token": "staff-tok"},
        json={"name": "권한알바", "resident_id": "910202-2234567", "reported": False},
    )
    assert created.status_code == 200, created.text

    revoked = client.put(
        f"/auth/users/{staff_id}",
        params={"token": "admin-tok"},
        json={"can_manage_part_time": False},
    )
    assert revoked.status_code == 200, revoked.text
    denied_again = client.get("/part-time/calendar", params={"token": "staff-tok", "year": 2026, "month": 11})
    assert denied_again.status_code == 403

    admin_calendar = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert admin_calendar.status_code == 200


def test_october_2026_is_seeded_from_the_given_workbook(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    calendar = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 10})
    assert calendar.status_code == 200, calendar.text
    body = calendar.json()
    names = [item["name"] for item in body["workers"] if item["active"]]
    assert names == [
        "김수영", "김순화", "김정미", "문정숙", "박희숙", "복진해", "설희",
        "손아현", "이행자", "정현소", "조여진", "지영주", "최윤영", "황보화",
    ]
    cho_profile = next(item for item in body["workers"] if item["name"] == "조여진")
    assert cho_profile["resident_id"] == "050704-3******"
    assert cho_profile["phone"] == "010-8817-0199"
    assert cho_profile["bank_name"] == "kb은행"
    assert cho_profile["account_number"] == "940302-01-724971"
    moon = next(item for item in body["workers"] if item["name"] == "문정숙")
    assert moon["resident_id"] == "750716-2******"
    assert moon["bank_name"] == "카카오뱅크"
    assert moon["account_number"] == "3333-30-7784236"
    hwang = next(item for item in body["workers"] if item["name"] == "황보화")
    assert hwang["resident_id"] == "850227-2******"
    assert hwang["phone"] == "010-7353-7119"
    jo = next(item for item in body["totals"] if item["name"] == "조여진")
    assert jo["basic_hours"] == 75
    seolhee = next(item for item in body["totals"] if item["name"] == "설희")
    ji = next(item for item in body["totals"] if item["name"] == "지영주")
    assert seolhee["basic_hours"] == 10
    assert seolhee["weekly_holiday_pay"] == 0
    assert ji["basic_hours"] == 15
    assert ji["weekly_holiday_pay"] == 0
    assert jo["hourly_wage"] == 10320
    assert body["days"]["2026-10-02"][0]["hours"] == 5
    assert {item["name"] for item in body["days"]["2026-10-02"]} == {"조여진", "지영주"}
    cho = next(item for item in body["days"]["2026-10-02"] if item["name"] == "조여진")
    assert cho["start_time"] == "09:00"
    assert cho["end_time"] == "14:00"
    assert cho["shift_label"] == "09:00~14:00"
    assert len(body["days"]["2026-10-27"]) == 2
    assert {item["name"] for item in body["days"]["2026-10-27"]} == {"손아현", "최윤영"}
    assert body["days"]["2026-10-28"][0]["name"] == "김순화"
    entries = sum(len(items) for items in body["days"].values())
    assert entries == 29
    again = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 10})
    assert sum(len(items) for items in again.json()["days"].values()) == 29

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "UPDATE part_time_workers SET resident_id = ?, phone = '', bank_name = '', account_number = '' WHERE name = ?",
            ("111111-1111111", "조여진"),
        )
        con.commit()
    from backend.app.api.part_time import ensure_part_time_tables
    ensure_part_time_tables()
    filled = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 10})
    restored = next(item for item in filled.json()["workers"] if item["name"] == "조여진")
    assert restored["resident_id"] == "050704-3******"
    assert restored["phone"] == "010-8817-0199"
    assert restored["bank_name"] == "kb은행"
    assert restored["account_number"] == "940302-01-724971"
