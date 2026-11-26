"""급여명세서는 그달 대장 자료로 만들고, 제공된 뒤 본인만 받는다."""
from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.test_employment_contracts import _prepare, _sample, _worker_confirms


def test_worker_receives_only_own_released_payslip(isolated_runtime):
    staff_id = _prepare(isolated_runtime["db"])
    client = TestClient(app)
    body = _sample()
    drafted = client.put(
        f"/employment-contracts/users/{staff_id}",
        params={"token": "admin-tok"},
        json=body,
    )
    assert drafted.status_code == 200
    _worker_confirms(client, staff_id)
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
    assert "산재보험" in text.replace(" ", "")
    assert "15,840" in text
    assert "회사" in text


def test_slip_numbers_and_dates_stay_inside_page():
    from backend.app.services.payroll_ledger.slip import render_slip_pdf

    pdf = render_slip_pdf(
        {
            "company_name": "틸리언",
            "period_label": "2026.11.01~2026.11.30",
            "year": 2026,
            "month": 11,
        },
        {
            "employee_name": "홍길동",
            "affiliation": "수선팀",
            "hourly": 12345,
            "base_pay": 1966730,
            "gross_pay": 26174640,
            "deduction_total": 412340,
            "net_pay": 1966730,
            "work_days": "2026.11.01~2026.11.30",
            "base_hours": 209,
            "overtime_hours": 12.5,
            "holiday_hours": 8,
            "night_hours": 4,
        },
        masked_rrn="900101-1******",
    )
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    text = page.get_text()
    assert "2026.11.01~11.30" in text.replace(" ", "")
    assert "1,966,730" in text
    assert "26,174,640" in text
    for x0, _y0, x1, _y1, word, *_rest in page.get_text("words"):
        assert x0 >= 33, word
        assert x1 <= 562, (word, round(x0, 1), round(x1, 1))


def test_slip_list_filters_by_month_and_pages(isolated_runtime):
    _prepare(isolated_runtime["db"])
    client = TestClient(app)

    listed = client.get("/payroll-slips", params={"token": "admin-tok", "year": 2026, "month": 10})
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 8
    assert payload["page"] == 1
    assert all(row["year"] == 2026 and row["month"] == 10 for row in payload["slips"])
    assert any(row["year"] == 2026 and row["month"] == 10 for row in payload["months"])

    first = client.get(
        "/payroll-slips",
        params={"token": "admin-tok", "year": 2026, "month": 10, "page": 1, "page_size": 3},
    )
    assert first.status_code == 200
    assert first.json()["page_size"] == 3
    assert len(first.json()["slips"]) == 3
    assert first.json()["total"] == 8

    last = client.get(
        "/payroll-slips",
        params={"token": "admin-tok", "year": 2026, "month": 10, "page": 3, "page_size": 3},
    )
    assert last.status_code == 200
    assert len(last.json()["slips"]) == 2
    names = {row["employee_name"] for row in first.json()["slips"]} | {row["employee_name"] for row in last.json()["slips"]}
    assert len(names) == 5

    empty = client.get("/payroll-slips", params={"token": "admin-tok", "year": 2026, "month": 12})
    assert empty.status_code == 200
    assert empty.json()["slips"] == []
    assert empty.json()["total"] == 0

    bad = client.get("/payroll-slips", params={"token": "admin-tok", "month": 13})
    assert bad.status_code == 400

    staff = client.get("/payroll-slips", params={"token": "staff-tok", "year": 2026, "month": 10})
    assert staff.status_code == 200
    assert staff.json()["slips"] == []
