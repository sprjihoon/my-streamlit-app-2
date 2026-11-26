"""급여대장은 그 달에 적용되는 근로계약 급여로 만들고, 만든 달은 다시 덮지 않는다."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from backend.app.main import app
from tests.test_employment_contracts import _prepare, _sample


def test_monthly_ledger_uses_contract_pay_and_keeps_the_saved_month(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    client = TestClient(app)
    body = _sample()
    completed = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=body,
    )
    assert completed.status_code == 200

    denied = client.post("/payroll-ledgers", params={"token": "staff-tok"}, json={"year": 2026, "month": 10})
    assert denied.status_code == 403

    outside = dict(body)
    outside["contract_end"] = "2026-09-30"
    client.post(
        f"/employment-contracts/users/{staff_id}/reactivate",
        params={"token": "admin-tok"},
    )
    updated = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=outside,
    )
    assert updated.status_code == 200
    missing = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 9})
    assert missing.status_code == 400

    restored = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=body,
    )
    assert restored.status_code == 200

    created = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})
    assert created.status_code == 200
    payload = created.json()
    assert payload["period_label"] == "2026.11.01~2026.11.30"
    names = [line["employee_name"] for line in payload["lines"]]
    assert "홍길동" in names
    assert "장성령" in names
    line = next(item for item in payload["lines"] if item["employee_name"] == "홍길동")
    assert line["net_pay"] == 1966730
    assert line["vehicle_allowance"] == 200000
    assert line["gross_pay"] == line["net_pay"] + line["deduction_total"]
    assert "1234567" not in line["resident_id"]

    again = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})
    assert again.status_code == 200
    assert again.json()["existed"] is True
    assert "홍길동" in [item["employee_name"] for item in again.json()["lines"]]

    sheet = client.get("/payroll-ledgers/2026/11/xlsx", params={"token": "admin-tok"})
    assert sheet.status_code == 200
    book = load_workbook(filename=__import__("io").BytesIO(sheet.content))
    assert set(book.sheetnames) >= {"급여대장", "급여명세서", "2023년 조견표", "급여명세서 수령 확인"}
    ws = book["급여대장"]
    assert ws["H1"].value == "급여대장"
    assert ws["A1"].value.month == 11
    assert "2026.11.01" in str(ws["B3"].value)
    assert isinstance(ws["B8"].value, str) and str(ws["B8"].value).startswith("=")


def _sample_workbook() -> bytes:
    book = Workbook()
    ws = book.active
    ws.title = "급여대장"
    ws["A1"] = datetime(2026, 11, 1)
    ws["B3"] = "2026.11.01~2026.11.30"
    ws["L3"] = "틸리언"
    ws["B5"] = "성명"
    ws["A8"] = 1
    ws["B8"] = "장성령"
    ws["C8"] = "만근"
    ws["D8"] = 209
    ws["F8"] = 2914510
    ws["J8"] = 2914510
    ws["K8"] = 30000
    ws["L8"] = 136750
    ws["N8"] = 314510
    ws["O8"] = 2600000
    ws["A9"] = "패션총괄팀장"
    ws["B9"] = datetime(2026, 2, 2)
    ws["E9"] = 13945.02
    ws["K9"] = 3000
    ws["L9"] = 26230
    ws["A10"] = "900101-1234567"
    ws["K10"] = 104770
    ws["L10"] = 13760
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


def test_excel_file_replaces_the_month_with_its_own_figures(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    saved = client.post(
        "/payroll-ledgers/import",
        params={"token": "admin-tok"},
        files={"file": ("ledger.xlsx", _sample_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["origin"] == "excel"
    assert payload["month"] == 11
    assert payload["lines"][0]["employee_name"] == "장성령"
    assert payload["lines"][0]["affiliation"] == "패션총괄팀장"
    assert payload["lines"][0]["net_pay"] == 2600000
    assert payload["lines"][0]["base_pay"] == 2914510
    assert "1234567" not in payload["lines"][0]["resident_id"]

    denied = client.post(
        "/payroll-ledgers/import",
        params={"token": "staff-tok"},
        files={"file": ("ledger.xlsx", _sample_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert denied.status_code == 403


def test_october_workbook_keeps_the_given_headcount_and_total():
    path = Path(r"C:\Users\one\Documents\카카오톡 받은 파일\틸리언 급여대장 2026년 10월.xlsx")
    if not path.exists():
        return
    from backend.app.services.payroll_ledger.excel import parse_payroll_xlsx

    parsed = parse_payroll_xlsx(path.read_bytes())
    assert (parsed["year"], parsed["month"]) == (2026, 10)
    assert len(parsed["lines"]) == 8
    assert [line["employee_name"] for line in parsed["lines"]] == [
        "장성령", "장명찬", "신윤미", "태찬기", "신경주", "윤혜준", "전은정", "김민정",
    ]
    assert sum(line["net_pay"] for line in parsed["lines"]) == 16400190
    assert sum(line["gross_pay"] for line in parsed["lines"]) == 18270640
    assert parsed["lines"][6]["vehicle_allowance"] == 200000
    assert parsed["lines"][7]["base_hours"] == 84


def test_official_workbook_keeps_the_october_form_for_the_labor_office():
    from backend.app.services.payroll_ledger.excel import fill_official_xlsx
    from backend.app.services.payroll_ledger.october_2026 import october_2026_lines

    book = load_workbook(BytesIO(fill_official_xlsx({
        "year": 2026,
        "month": 11,
        "company_name": "틸리언",
        "period_label": "2026.11.01~2026.11.30",
        "lines": october_2026_lines(),
    })))
    assert {"급여대장", "급여명세서", "2023년 조견표", "급여명세서 수령 확인", "수선팀장 전은정"} <= set(book.sheetnames)
    assert book["급여대장"]["A1"].value == datetime(2026, 11, 1)
    assert "2026.11.01~2026.11.30" == book["급여대장"]["B3"].value
    assert book["수선팀장 전은정"]["H20"].value == 1966730
    assert book["수선팀장 전은정"]["D20"].value == 200000
    assert str(book["수선팀장 전은정"]["B24"].value).startswith("=")
    assert str(book["급여대장"]["B8"].value).startswith("=")
    assert book["급여명세서 수령 확인"]["B4"].value == "장성령"
    assert book["급여명세서 수령 확인"]["B11"].value == "김민정"
    assert book["급여명세서 수령 확인"]["B12"].value in (None, "")


def test_official_workbook_keeps_only_this_month_people_and_monthly_changes():
    from backend.app.services.payroll_ledger.excel import fill_official_xlsx
    from backend.app.services.payroll_ledger.october_2026 import october_2026_lines

    first = dict(october_2026_lines()[0])
    first["overtime_hours"] = 10
    first["annual_leave_pay"] = 50000
    extra = dict(first)
    extra["employee_name"] = "홍길동"
    extra["affiliation"] = "테스트"
    extra["seq"] = 2
    extra["net_pay"] = 1500000
    extra["overtime_hours"] = 0
    extra["annual_leave_pay"] = 0
    book = load_workbook(BytesIO(fill_official_xlsx({
        "year": 2026,
        "month": 11,
        "company_name": "틸리언",
        "period_label": "2026.11.01~2026.11.30",
        "lines": [first, extra],
    })))
    person_names = [
        book[name]["B3"].value
        for name in book.sheetnames
        if name not in {"급여대장", "급여명세서", "2023년 조견표", "급여명세서 수령 확인"}
    ]
    assert person_names == ["장성령", "홍길동"]
    assert book["패션팀장 장성령"]["C13"].value == 10
    assert book["패션팀장 장성령"]["I39"].value == 50000
    hong = next(name for name in book.sheetnames if book[name]["B3"].value == "홍길동")
    assert book[hong]["H20"].value == 1500000
    assert "전은정" in str(book["급여대장"]["B8"].value) or "장성령" in str(book["급여대장"]["B8"].value)
    assert "장성령" in str(book["급여대장"]["B8"].value)
    assert "홍길동" in str(book["급여대장"]["B11"].value)
    assert book["급여명세서 수령 확인"]["B4"].value == "장성령"
    assert book["급여명세서 수령 확인"]["B5"].value == "홍길동"
    assert book["급여명세서 수령 확인"]["B6"].value in (None, "")


def test_october_2026_is_seeded_from_the_given_workbook_values(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    saved = client.get("/payroll-ledgers/2026/10", params={"token": "admin-tok"})
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["origin"] == "excel"
    assert payload["period_label"] == "2026.10.01~2026.10.31"
    assert [line["employee_name"] for line in payload["lines"]] == [
        "장성령", "장명찬", "신윤미", "태찬기", "신경주", "윤혜준", "전은정", "김민정",
    ]
    assert payload["totals"]["net_pay"] == 16400190
    assert payload["totals"]["gross_pay"] == 18270640
    assert payload["lines"][0]["net_pay"] == 2600000
    assert payload["lines"][6]["vehicle_allowance"] == 200000
    assert payload["lines"][7]["base_hours"] == 84
    assert "1234567" not in "".join(line["resident_id"] for line in payload["lines"])


def test_payroll_file_fills_matching_employment_contract(isolated_runtime):
    import sqlite3

    _prepare(isolated_runtime["db"])
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            """
            INSERT INTO users (username, password_hash, nickname, is_admin, department, position, join_date)
            VALUES ('jang', 'x', '장성령', 0, '패션팀', '팀장', '')
            """
        )
        user_id = con.execute("SELECT user_id FROM users WHERE username = 'jang'").fetchone()[0]
        con.commit()
    client = TestClient(app)
    saved = client.post(
        "/payroll-ledgers/import",
        params={"token": "admin-tok"},
        files={"file": ("ledger.xlsx", _sample_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["contracts"]["updated"] == [{"user_id": user_id, "employee_name": "장성령"}]
    draft = client.get(f"/employment-contracts/users/{user_id}", params={"token": "admin-tok"})
    assert draft.status_code == 200
    fields = draft.json()["input"]
    assert fields["job_title"] == "패션총괄팀장"
    assert fields["rank_title"] == "팀장"
    assert fields["hire_date"] == "2026-02-02"
    assert fields["contract_start"] == "2026-02-02"
    assert fields["contract_end"] == "2027-02-01"
    assert fields["base_hours"] == 209
    assert fields["net_pay"] == 2600000
    assert fields["income_tax"] > 0
    assert fields["vehicle_allowance"] == 0
    assert fields["weekday_hours"] == "09:00~18:00"
    assert fields["address"] == ""
    assert len("".join(ch for ch in fields["resident_id"] if ch.isdigit())) == 13


def test_month_changes_are_saved_and_filled_in_the_official_workbook(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    created = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})
    assert created.status_code == 200
    lines = created.json()["lines"]
    target = next(line for line in lines if line["employee_name"] == "장성령")
    dropped = next(line for line in lines if line["employee_name"] == "김민정")
    saved = client.put(
        "/payroll-ledgers/2026/11/lines",
        params={"token": "admin-tok"},
        json={
            "lines": [
                {
                    "seq": line["seq"],
                    "keep": line["seq"] != dropped["seq"],
                    "overtime_hours": 10 if line["seq"] == target["seq"] else line.get("overtime_hours") or 0,
                    "annual_leave_pay": 50000 if line["seq"] == target["seq"] else 0,
                    "net_pay": line["net_pay"],
                    "work_days": line.get("work_days") or "만근",
                    "base_hours": line.get("base_hours") or 209,
                }
                for line in lines
            ]
        },
    )
    assert saved.status_code == 200
    names = [line["employee_name"] for line in saved.json()["lines"]]
    assert "장성령" in names
    assert "김민정" not in names
    changed = next(line for line in saved.json()["lines"] if line["employee_name"] == "장성령")
    assert changed["overtime_hours"] == 10
    assert changed["annual_leave_pay"] == 50000
    sheet = client.get("/payroll-ledgers/2026/11/xlsx", params={"token": "admin-tok"})
    assert sheet.status_code == 200
    book = load_workbook(BytesIO(sheet.content))
    assert book["패션팀장 장성령"]["C13"].value == 10
    assert book["패션팀장 장성령"]["I39"].value == 50000
    assert "단시간 김민정" not in book.sheetnames
    assert book["급여명세서 수령 확인"]["B4"].value == "장성령"
