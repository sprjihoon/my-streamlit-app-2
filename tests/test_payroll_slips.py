"""급여명세서는 그달 대장 자료로 만들고, 제공된 뒤 본인만 받는다."""
from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.test_employment_contracts import _prepare, _sample


def test_worker_receives_only_own_released_payslip(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    client = TestClient(app)
    body = _sample()
    saved = client.post(
        f"/employment-contracts/users/{staff_id}/complete",
        params={"token": "admin-tok"},
        json=body,
    )
    assert saved.status_code == 200
    created = client.post("/payroll-ledgers", params={"token": "admin-tok"}, json={"year": 2026, "month": 11})
    assert created.status_code == 200
    assert "홍길동" in [line["employee_name"] for line in created.json()["lines"]]

    hidden = client.get("/payroll-slips", params={"token": "staff-tok"})
    assert hidden.status_code == 200
    assert hidden.json()["slips"] == []
    denied = client.get("/payroll-slips/2026/11/pdf", params={"token": "staff-tok"})
    assert denied.status_code == 404
    bundle = client.get("/payroll-slips/2026/11/bundle.pdf", params={"token": "staff-tok"})
    assert bundle.status_code == 403

    released = client.post("/payroll-ledgers/2026/11/release", params={"token": "admin-tok"})
    assert released.status_code == 200
    assert released.json()["released_at"]

    listed = client.get("/payroll-slips", params={"token": "staff-tok"})
    assert listed.status_code == 200
    slips = listed.json()["slips"]
    assert len(slips) == 1
    assert slips[0]["employee_name"] == "홍길동"
    assert slips[0]["month"] == 11
    assert slips[0]["net_pay"] == 1966730

    other = client.get(
        "/payroll-slips/2026/11/pdf",
        params={"token": "staff-tok", "employee_name": "장성령"},
    )
    assert other.status_code == 200
    mine = fitz.open(stream=other.content, filetype="pdf")
    text = "".join(page.get_text() for page in mine)
    assert "급여명세서" in text or "급 여 명 세 서" in text
    assert "홍길동" in text
    assert "장성령" not in text
    assert "1234567" not in text
    assert "1,966,730" in text
    assert mine.page_count == 1

    admin_all = client.get("/payroll-slips/2026/11/bundle.pdf", params={"token": "admin-tok"})
    assert admin_all.status_code == 200
    bundle_doc = fitz.open(stream=admin_all.content, filetype="pdf")
    assert bundle_doc.page_count == len(created.json()["lines"])
    bundle_text = "".join(page.get_text() for page in bundle_doc)
    assert "홍길동" in bundle_text
    assert "장성령" in bundle_text

    preview = client.get("/payroll-slips/2026/11/pages", params={"token": "staff-tok"})
    assert preview.status_code == 200
    assert preview.json()["pages"]


def test_admin_can_preview_slip_before_release(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)
    preview = client.get(
        "/payroll-slips/2026/10/pages",
        params={"token": "admin-tok", "employee_name": "전은정"},
    )
    assert preview.status_code == 200
    assert preview.json()["pages"]
    pdf = client.get(
        "/payroll-slips/2026/10/pdf",
        params={"token": "admin-tok", "employee_name": "전은정"},
    )
    assert pdf.status_code == 200
    text = fitz.open(stream=pdf.content, filetype="pdf")[0].get_text()
    assert "전은정" in text
    assert "1,966,730" in text
