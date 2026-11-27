"""알바는 이름과 주민번호로 등록하고, 신고자만 주휴수당을 받는다."""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.part_time.calc import daily_worker_tax, minimum_wage, settle_part_time_pay, weekly_holiday_pay
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
    assert reported_total["weekly_holiday_hours"] == 2
    assert reported_total["weekly_holiday_pay"] == 24000
    assert reported_total["total_pay"] == 144000
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
    assert reported_slip["taxable_pay"] == 144000
    assert reported_slip["nontaxable_pay"] == 0
    assert reported_slip["income_tax"] == 0
    assert reported_slip["employment_insurance"] == 1290
    assert reported_slip["pension"] == 0
    assert reported_slip["health"] == 0
    assert reported_slip["employer_industrial"] == 1150
    assert reported_slip["net_pay"] == 142710
    hidden_slip = next(item for item in slips.json()["slips"] if item["worker_id"] == hidden_id)
    assert hidden_slip["withholding_kind"] == "business_3_3"
    assert hidden_slip["income_tax"] == 3090
    assert hidden_slip["local_tax"] == 300
    assert hidden_slip["employment_insurance"] == 0
    assert hidden_slip["net_pay"] == 99810
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
    assert kim_block is not None
    start, origin = kim_block
    assert ledger.cell(start + 1, origin).value == "900101-1234567"
    assert ledger.cell(start + 2, origin).value == "2일"
    assert ledger.cell(start + 4, origin).value == 144000
    assert ledger.cell(start + 6, origin + 1).value == 5
    assert ledger.cell(start + 6, origin + 2).value == 5
    gong = book["공단"]
    kim_gong = None
    for sheet in book.worksheets:
        if not str(sheet.title).startswith("공단"):
            continue
        for coord in ("O21", "AE21", "AT21", "BM21"):
            if sheet[coord].value == "김알바":
                kim_gong = (sheet, coord[0] if coord[1].isdigit() else coord[:2])
                break
        if kim_gong:
            break
    assert kim_gong is not None
    gong_sheet, gong_col = kim_gong
    assert gong_sheet[f"{gong_col}21"].value == "김알바"
    assert gong_sheet[f"{gong_col}22"].value == "900101-1234567"
    assert gong_sheet[f"{gong_col}48"].value == "144,000 원 "
    assert gong_sheet[f"{gong_col}50"].value == "0 원 "

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
        json={"work_date": "2026-10-30", "entries": [{"worker_id": worker_id, "hours": 5, "start_time": "09:00"}]},
    )
    assert saved.status_code == 200, saved.text
    october = saved.json()
    october_total = next(row for row in october["totals"] if row["worker_id"] == worker_id)
    assert october_total["basic_hours"] == 5
    assert october_total["weekly_holiday_pay"] == 0

    november = client.get("/part-time/calendar", params={"token": "admin-tok", "year": 2026, "month": 11})
    assert november.status_code == 200
    total = next(row for row in november.json()["totals"] if row["worker_id"] == worker_id)
    assert total["basic_hours"] == 0
    assert total["weekly_holiday_hours"] == 1
    assert total["weekly_holiday_pay"] == 10320


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
    assert names == ["김수영", "김순화", "김정미", "복진해", "설희", "손아현", "조여진", "지영주", "최윤영"]
    jo = next(item for item in body["totals"] if item["name"] == "조여진")
    assert jo["basic_hours"] == 75
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
