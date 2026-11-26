"""완료한 근로계약서는 PDF로 남고, 작성 목록에서는 빠진다."""
from __future__ import annotations

import base64
import sqlite3

import fitz
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.employment_contract.calc import calculate_contract_pay


def _sample(**overrides):
    data = {
        "employee_name": "홍길동",
        "job_title": "수선",
        "rank_title": "팀장",
        "resident_id": "900101-1234567",
        "address": "대구광역시",
        "phone": "010-0000-0000",
        "hire_date": "2026-10-01",
        "contract_start": "2026-10-01",
        "contract_end": "2027-09-30",
        "base_hours": 209,
        "overtime_hours": 0,
        "holiday_hours": 0,
        "night_hours": 0,
        "net_pay": 1966730,
        "vehicle_allowance": 200000,
        "meal_allowance": 0,
        "position_allowance": 0,
        "income_tax": 20000,
        "weekday_hours": "09:00~18:00",
        "break_time": "1시간 (12~13)",
        "work_days": "주중 평균 5일 근무",
        "pay_day": 15,
    }
    data.update(overrides)
    return data


def _prepare(db_path):
    from backend.app.api.auth import ensure_users_table
    from backend.app.api.employment_contracts import ensure_contract_tables

    ensure_users_table()
    ensure_contract_tables()
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
            INSERT INTO users (username, password_hash, nickname, is_admin, department, position, join_date)
            VALUES ('staff', 'x', '홍길동', 0, '수선팀', '팀장', '2026-10-01')
            """
        )
        staff_id = con.execute("SELECT user_id FROM users WHERE username = 'staff'").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('admin-tok', ?)", (admin_id,))
        con.execute("INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('staff-tok', ?)", (staff_id,))
        con.commit()
    return staff_id


def test_sample_pay_matches_contract_sheet():
    calc = calculate_contract_pay(_sample())

    assert calc["taxable"] == 1981220
    assert calc["deduction_total"] == 214490
    assert calc["pension"] == 94090
    assert calc["health"] == 71220
    assert calc["care"] == 9350
    assert calc["local_tax"] == 2000
    assert calc["employment"] == 17830
    assert calc["gross"] == 2181220
    assert calc["net"] == 1966730
    assert calc["annual"] == 26174640
    assert calc["base_pay"] == 1981220
    assert calc["vehicle_allowance"] == 200000
    assert calc["hourly"] == 10436
    parts = (
        calc["base_pay"] + calc["overtime_pay"] + calc["holiday_pay"] + calc["night_pay"]
        + calc["meal_allowance"] + calc["vehicle_allowance"] + calc["position_allowance"]
    )
    assert parts == calc["gross"]


def test_meal_stays_out_of_taxable_pay_and_lines_still_sum():
    plain = calculate_contract_pay(_sample())
    with_meal = calculate_contract_pay(_sample(meal_allowance=100000))

    assert with_meal["net"] == 1966730
    assert with_meal["taxable"] < plain["taxable"]
    assert with_meal["meal_allowance"] == 100000
    parts = (
        with_meal["base_pay"] + with_meal["overtime_pay"] + with_meal["holiday_pay"] + with_meal["night_pay"]
        + with_meal["meal_allowance"] + with_meal["vehicle_allowance"] + with_meal["position_allowance"]
    )
    assert parts == with_meal["gross"]


def test_completed_contract_is_hidden_until_admin_reactivates(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    client = TestClient(app)
    body = _sample()

    denied = client.get("/employment-contracts", params={"token": "staff-tok", "view": "open"})
    assert denied.status_code == 403

    sheets = client.post(
        "/employment-contracts/preview-pages",
        params={"token": "admin-tok"},
        json=body,
    )
    assert sheets.status_code == 200
    preview_pages = sheets.json()["pages"]
    assert preview_pages
    first_page = base64.b64decode(preview_pages[0])
    assert first_page.startswith(b"\x89PNG")

    opened = client.get("/employment-contracts", params={"token": "admin-tok", "view": "open"})
    assert opened.status_code == 200
    assert any(row["user_id"] == staff_id for row in opened.json()["employees"])

    completed = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=body,
    )
    assert completed.status_code == 200
    contract_id = completed.json()["id"]

    hidden = client.get("/employment-contracts", params={"token": "admin-tok", "view": "open"})
    assert all(row["user_id"] != staff_id for row in hidden.json()["employees"])

    archived = client.get("/employment-contracts", params={"token": "admin-tok", "view": "completed"})
    stored = archived.json()["contracts"]
    assert stored[0]["id"] == contract_id
    assert stored[0]["can_reactivate"] is True
    assert "resident_id" not in stored[0]

    pdf = client.get(f"/employment-contracts/{contract_id}/pdf", params={"token": "admin-tok"})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    text = "".join(page.get_text() for page in fitz.open(stream=pdf.content, filetype="pdf"))
    assert "근로계약서" in text.replace(" ", "")
    assert "홍길동" in text
    assert "포괄임금제" in text
    assert "1,966,730" in text
    assert "900101-1234567" in text
    sealed = fitz.open(stream=pdf.content, filetype="pdf")
    assert any(page.get_images() for page in sealed)

    blocked = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=body,
    )
    assert blocked.status_code == 400

    again = client.post(f"/employment-contracts/users/{staff_id}/reactivate", params={"token": "admin-tok"})
    assert again.status_code == 200
    visible = client.get("/employment-contracts", params={"token": "admin-tok", "view": "open"})
    assert any(row["user_id"] == staff_id and row["state"] == "draft" for row in visible.json()["employees"])

    paged = client.get(f"/employment-contracts/{contract_id}/pages", params={"token": "admin-tok"})
    assert paged.status_code == 200
    assert paged.json()["pages"]

    kept = client.get(f"/employment-contracts/{contract_id}/pdf", params={"token": "admin-tok"})
    assert kept.status_code == 200
    assert kept.content.startswith(b"%PDF")
