"""급여대장은 그 달에 적용되는 근로계약 급여로 만들고, 만든 달은 다시 덮지 않는다."""
from __future__ import annotations

from fastapi.testclient import TestClient
from openpyxl import load_workbook

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
    missing = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 10})
    assert missing.status_code == 400

    restored = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=body,
    )
    assert restored.status_code == 200

    created = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 10})
    assert created.status_code == 200
    payload = created.json()
    assert payload["period_label"] == "2026.10.01~2026.10.31"
    assert len(payload["lines"]) == 1
    line = payload["lines"][0]
    assert line["employee_name"] == "홍길동"
    assert line["net_pay"] == 1966730
    assert line["gross_pay"] == 2181220
    assert line["pension"] == 94090
    assert line["vehicle_allowance"] == 200000
    assert "1234567" not in line["resident_id"]
    assert payload["totals"]["net_pay"] == 1966730

    again = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 10})
    assert again.status_code == 200
    assert again.json()["existed"] is True
    assert again.json()["lines"][0]["net_pay"] == 1966730

    sheet = client.get("/payroll-ledgers/2026/10/xlsx", params={"token": "admin-tok"})
    assert sheet.status_code == 200
    book = load_workbook(filename=__import__("io").BytesIO(sheet.content))
    ws = book["급여대장"]
    assert ws["H1"].value == "급여대장"
    assert ws["B8"].value == "홍길동"
    assert ws["O8"].value == 1966730
    assert ws["A10"].value == "900101-1234567"
