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
    from backend.app.services.employment_contract.tax_table import lookup_simple_tax

    assert calc["income_tax"] == lookup_simple_tax(calc["taxable"], 1)
    assert calc["local_tax"] == int(calc["income_tax"] * 0.1 // 10 * 10)
    assert calc["pension"] == int(calc["pension_base"] * 0.0475 // 10 * 10)
    assert calc["net"] == 1966730
    assert calc["vehicle_allowance"] == 200000
    assert calc["gross"] == calc["taxable"] + calc["vehicle_allowance"]
    assert abs(calc["gross"] - calc["deduction_total"] - calc["net"]) <= 20
    parts = (
        calc["base_pay"] + calc["overtime_pay"] + calc["holiday_pay"] + calc["night_pay"]
        + calc["meal_allowance"] + calc["vehicle_allowance"] + calc["position_allowance"]
    )
    assert parts == calc["gross"]


def test_excel_insurance_formulas_fill_from_net_and_income_tax():
    from backend.app.services.employment_contract.calc import calculate_contract_pay
    from backend.app.services.employment_contract.tax_table import lookup_simple_tax

    assert lookup_simple_tax(1_981_220, 1) == 18880
    assert lookup_simple_tax(1_981_220, 4) == 2820

    formula = calculate_contract_pay(_sample())
    assert formula["income_tax"] == lookup_simple_tax(formula["taxable"], 1)
    assert formula["net"] == 1966730

    from_taxable = calculate_contract_pay({
        "net_pay": 0,
        "taxable_pay": 1981220,
        "annual_pay": 0,
        "meal_allowance": 0,
        "vehicle_allowance": 200000,
        "position_allowance": 0,
        "dependents": 1,
        "base_hours": 209,
        "overtime_hours": 0,
        "holiday_hours": 0,
        "night_hours": 0,
    })
    assert from_taxable["gross"] == 2181220
    assert from_taxable["annual"] == 26174640
    assert from_taxable["income_tax"] == 18880
    assert from_taxable["pension"] == 94090
    assert from_taxable["net"] == from_taxable["gross"] - from_taxable["deduction_total"]

    from_annual = calculate_contract_pay({
        "net_pay": 0,
        "taxable_pay": 0,
        "annual_pay": 26174640,
        "meal_allowance": 0,
        "vehicle_allowance": 200000,
        "position_allowance": 0,
        "dependents": 1,
        "base_hours": 209,
        "overtime_hours": 0,
        "holiday_hours": 0,
        "night_hours": 0,
    })
    assert from_annual["taxable"] == 1981220
    assert from_annual["income_tax"] == 18880


def test_meal_stays_out_of_taxable_pay_and_lines_still_sum():
    plain = calculate_contract_pay(_sample())
    with_meal = calculate_contract_pay(_sample(meal_allowance=100000))

    assert with_meal["net"] == with_meal["gross"] - with_meal["deduction_total"]
    assert with_meal["taxable"] < plain["taxable"]
    assert with_meal["meal_allowance"] == 100000
    parts = (
        with_meal["base_pay"] + with_meal["overtime_pay"] + with_meal["holiday_pay"] + with_meal["night_pay"]
        + with_meal["meal_allowance"] + with_meal["vehicle_allowance"] + with_meal["position_allowance"]
    )
    assert parts == with_meal["gross"]


def _worker_confirms(client: TestClient, staff_id: int):
    mark = client.put(
        f"/employment-contracts/users/{staff_id}/mark",
        params={"token": "staff-tok"},
        json={"kind": "grid"},
    )
    assert mark.status_code == 200, mark.text
    sealed = client.post(
        f"/employment-contracts/users/{staff_id}/worker-seal",
        params={"token": "staff-tok"},
    )
    assert sealed.status_code == 200, sealed.text


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
    assert client.get("/auth/me", params={"token": "staff-tok"}).json()["needs_contract"] is True

    blocked = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=body,
    )
    assert blocked.status_code == 400

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
    contract_id = completed.json()["id"]

    hidden = client.get("/employment-contracts", params={"token": "admin-tok", "view": "open"})
    assert all(row["user_id"] != staff_id for row in hidden.json()["employees"])

    archived = client.get("/employment-contracts", params={"token": "admin-tok", "view": "completed"})
    stored = archived.json()["contracts"]
    assert stored[0]["id"] == contract_id
    assert stored[0]["can_reactivate"] is True
    assert stored[0]["has_pdf"] is True
    assert stored[0]["resident_id"] == "900101-1******"
    assert "1234567" not in stored[0]["resident_id"]

    staff_me = client.get("/auth/me", params={"token": "staff-tok"})
    assert staff_me.status_code == 200
    assert staff_me.json()["needs_contract"] is False
    staff_get = client.get(f"/employment-contracts/users/{staff_id}", params={"token": "staff-tok"})
    assert staff_get.status_code == 400
    staff_pdf = client.get(f"/employment-contracts/{contract_id}/pdf", params={"token": "staff-tok"})
    assert staff_pdf.status_code == 403
    staff_pages = client.get(f"/employment-contracts/{contract_id}/pages", params={"token": "staff-tok"})
    assert staff_pages.status_code == 403
    staff_list = client.get("/employment-contracts", params={"token": "staff-tok", "view": "completed"})
    assert staff_list.status_code == 403

    pdf = client.get(f"/employment-contracts/{contract_id}/pdf", params={"token": "admin-tok"})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    sealed = fitz.open(stream=pdf.content, filetype="pdf")
    assert sealed.page_count == 3
    text = "".join(page.get_text() for page in sealed)
    assert "근로계약서" in text.replace(" ", "")
    assert "홍길동" in text
    assert "포괄임금제" in text
    assert "1,966,730" in text
    assert "900101-1234567" in text
    assert "임금지급방법" in text.replace(" ", "")
    assert "연장근로동의서" in text.replace(" ", "")
    assert "정보보호서약서" in text.replace(" ", "")
    consent = sealed[1].get_text()
    pledge = sealed[2].get_text()
    assert "2026" in consent and "10  월" in consent and "1  일" in consent
    assert "11  월" not in consent and "26  일" not in consent
    assert "2026년" in pledge and "10월" in pledge and "1일" in pledge
    assert "11월" not in pledge and "26일" not in pledge
    assert len(preview_pages) == 3
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

    draft = client.get(f"/employment-contracts/users/{staff_id}", params={"token": "admin-tok"})
    assert draft.status_code == 200
    copied = draft.json()["input"]
    assert copied["resident_id"] == "900101-1234567"
    assert copied["address"] == "대구광역시"
    assert draft.json()["rrn_locked"] is True
    assert draft.json()["renewal"] is True
    staff_after_renew = client.get(f"/employment-contracts/users/{staff_id}", params={"token": "staff-tok"})
    assert staff_after_renew.status_code == 200
    assert staff_after_renew.json()["rrn_locked"] is True
    assert staff_after_renew.json()["input"]["resident_id"] == "900101-1234567"
    assert client.get("/auth/me", params={"token": "staff-tok"}).json()["needs_contract"] is True

    worker_change = client.put(
        f"/employment-contracts/users/{staff_id}/worker",
        params={"token": "staff-tok"},
        json={
            "employee_name": "홍길동",
            "resident_id": "800101-1111111",
            "address": "서울특별시",
            "phone": "010-1111-2222",
        },
    )
    assert worker_change.status_code == 200
    after_worker = client.get(f"/employment-contracts/users/{staff_id}", params={"token": "admin-tok"}).json()["input"]
    assert after_worker["resident_id"] == "900101-1234567"
    assert after_worker["address"] == "서울특별시"
    assert after_worker["phone"] == "010-1111-2222"

    admin_change = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=_sample(resident_id="800101-1111111", net_pay=2100000, address="부산광역시", phone="010-3333-4444"),
    )
    assert admin_change.status_code == 200
    after_admin = client.get(f"/employment-contracts/users/{staff_id}", params={"token": "admin-tok"}).json()["input"]
    assert after_admin["resident_id"] == "900101-1234567"
    assert after_admin["address"] == "부산광역시"
    assert after_admin["phone"] == "010-3333-4444"

    _worker_confirms(client, staff_id)
    renewed = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=_sample(net_pay=2100000, contract_start="2027-10-01", contract_end="2028-09-30"),
    )
    assert renewed.status_code == 200
    new_id = renewed.json()["id"]
    assert new_id != contract_id
    archive = client.get("/employment-contracts", params={"token": "admin-tok", "view": "completed"}).json()["contracts"]
    ids = [row["id"] for row in archive]
    assert contract_id in ids and new_id in ids
    assert all(row["has_pdf"] for row in archive if row["id"] in {contract_id, new_id})
    old_pdf = client.get(f"/employment-contracts/{contract_id}/pdf", params={"token": "admin-tok"})
    new_pdf = client.get(f"/employment-contracts/{new_id}/pdf", params={"token": "admin-tok"})
    assert old_pdf.status_code == 200 and old_pdf.content.startswith(b"%PDF")
    assert new_pdf.status_code == 200 and new_pdf.content.startswith(b"%PDF")
    assert old_pdf.content != new_pdf.content


def _same_png(left: bytes, right: bytes) -> bool:
    a = fitz.Pixmap(left)
    b = fitz.Pixmap(right)
    return a.width == b.width and a.height == b.height and a.samples == b.samples


def test_name_seal_uses_the_workers_own_name_and_is_stamped(isolated_runtime):
    from backend.app.services.employment_contract.seal import make_seal

    staff_id = _prepare(isolated_runtime["db"])
    client = TestClient(app)
    admin_id = sqlite3.connect(isolated_runtime["db"]).execute(
        "SELECT user_id FROM users WHERE username = 'admin'"
    ).fetchone()[0]

    forged = client.put(
        f"/employment-contracts/users/{staff_id}/mark",
        params={"token": "staff-tok"},
        json={"kind": "grid", "name": "장지훈"},
    )
    assert forged.status_code == 200
    assert forged.json()["name"] == "홍길동"
    assert _same_png(base64.b64decode(forged.json()["image"]), make_seal("홍길동", "grid"))
    assert not _same_png(base64.b64decode(forged.json()["image"]), make_seal("장지훈", "grid"))

    denied = client.get(
        f"/employment-contracts/users/{admin_id}/mark-samples",
        params={"token": "staff-tok"},
    )
    assert denied.status_code == 403

    named = client.put(
        f"/employment-contracts/users/{staff_id}/worker",
        params={"token": "staff-tok"},
        json={
            "employee_name": "김철수",
            "resident_id": "900101-1234567",
            "address": "대구광역시",
            "phone": "010-0000-0000",
        },
    )
    assert named.status_code == 200

    samples = client.get(
        f"/employment-contracts/users/{staff_id}/mark-samples",
        params={"token": "staff-tok"},
    )
    assert samples.status_code == 200
    assert samples.json()["name"] == "김철수"
    assert _same_png(base64.b64decode(samples.json()["ring"]), make_seal("김철수", "ring"))

    chosen = client.put(
        f"/employment-contracts/users/{staff_id}/mark",
        params={"token": "staff-tok"},
        json={"kind": "ring", "name": "장지훈"},
    )
    assert chosen.status_code == 200
    assert chosen.json()["name"] == "김철수"

    body = _sample(employee_name="김철수")
    drafted = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=body,
    )
    assert drafted.status_code == 200
    ready = client.post(
        f"/employment-contracts/users/{staff_id}/worker-seal",
        params={"token": "staff-tok"},
    )
    assert ready.status_code == 200
    completed = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=body,
    )
    assert completed.status_code == 200
    sealed = fitz.open(stream=client.get(
        f"/employment-contracts/{completed.json()['id']}/pdf",
        params={"token": "admin-tok"},
    ).content, filetype="pdf")
    assert len(sealed[0].get_images()) >= 2
    assert sealed[1].get_images()
    assert sealed[2].get_images()
