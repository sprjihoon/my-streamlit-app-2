from __future__ import annotations

import sqlite3

import fitz
import pytest
from fastapi import HTTPException

from backend.app.api.domestic_shipping import (
    DomesticSubmitRequest,
    DomesticVendorRequest,
    cancel_domestic,
    create_domestic,
    create_vendor,
    delete_domestic,
    domestic_label,
    preview_domestic,
)


def _seed_user(db_path, token="tok-domestic", admin=0):
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                department TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin, department) VALUES (?,?,?,?,?)",
            ("staff", "x", "물류담당", admin, "물류팀"),
        )
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, 1)", (token,))
        con.commit()
    return token


def _vendor(**overrides) -> DomesticVendorRequest:
    data = {
        "name": "테스트업체",
        "office_ser": "260940699",
        "sender_name": "스프링풀필먼트",
        "sender_phone": "01027239490",
        "sender_zip": "41142",
        "sender_addr1": "대구광역시 동구 동촌로 1",
        "sender_addr2": "2층",
    }
    data.update(overrides)
    return DomesticVendorRequest(**data)


def _submit(vendor_id: int, **overrides) -> DomesticSubmitRequest:
    data = {
        "vendor_id": vendor_id,
        "print_sender_name": "출력용상점",
        "print_sender_phone": "01099998888",
        "print_sender_zip": "04524",
        "print_sender_addr1": "서울특별시 중구 세종대로 110",
        "print_sender_addr2": "1층",
        "recipient_name": "홍길동",
        "recipient_phone": "01012345678",
        "recipient_zip": "06236",
        "recipient_addr1": "서울특별시 강남구 테헤란로 152",
        "recipient_addr2": "강남파이낸스센터",
        "goods_name": "의류",
        "box_size": "SMALL",
        "confirm": True,
        "test_mode": True,
    }
    data.update(overrides)
    return DomesticSubmitRequest(**data)


def test_vendor_requires_office_ser(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    with pytest.raises(HTTPException) as exc:
        create_vendor(_vendor(office_ser=""), token)
    assert exc.value.status_code == 400


def test_preview_does_not_write_and_splits_sender(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    preview = preview_domestic(_submit(vendor_id, confirm=False), token)
    assert preview["preview"]["api_sender"]["name"] == "스프링풀필먼트"
    assert preview["preview"]["print_sender"]["name"] == "출력용상점"
    assert preview["preview"]["office_ser"] == "260940699"
    with sqlite3.connect(isolated_runtime["db"]) as con:
        assert con.execute("SELECT COUNT(*) FROM domestic_shipments").fetchone()[0] == 0


def test_create_requires_confirm(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    with pytest.raises(HTTPException) as exc:
        create_domestic(_submit(vendor_id, confirm=False), token)
    assert exc.value.status_code == 400


def test_create_sends_saved_sender_and_prints_input(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    captured = {}

    def fake_insert(params):
        captured.update(params)
        return {
            "reqNo": "REQ1",
            "resNo": "RES1",
            "regiNo": "1234567890123",
            "regiPoNm": "동대구",
            "resDate": "20261002",
            "price": "3500",
            "vTelNo": "",
        }

    monkeypatch.setattr("backend.app.api.domestic_shipping.has_epost_credentials", lambda: True)
    monkeypatch.setattr("backend.app.api.domestic_shipping.insert_order", fake_insert)
    created = create_domestic(_submit(vendor_id, test_mode=False), token)
    assert created["is_test"] is False
    assert captured["officeSer"] == "260940699"
    assert captured["ordNm"] == "스프링풀필먼트"
    assert captured["reqType"] == "1"
    assert captured["qty"] == 1
    assert "출력용상점" not in captured.values()
    with sqlite3.connect(isolated_runtime["db"]) as con:
        row = con.execute(
            "SELECT api_sender_name, print_sender_name, tracking_no, is_test FROM domestic_shipments WHERE id=?",
            (created["id"],),
        ).fetchone()
    assert row == ("스프링풀필먼트", "출력용상점", "1234567890123", 0)
    pdf = domestic_label(created["id"], token, format="pdf")
    text = fitz.open(stream=pdf.body, filetype="pdf")[0].get_text()
    assert "출력용상점" in text
    assert "홍길동" in text
    assert "12345-6789-0123" in text
    page = fitz.open(stream=pdf.body, filetype="pdf")[0]
    assert abs(page.rect.width - 484.72) < 0.2
    assert abs(page.rect.height - 314.65) < 0.2


def test_second_box_is_not_blocked_after_the_double_submit_window(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    first = create_domestic(_submit(vendor_id), token)
    again = create_domestic(_submit(vendor_id), token)
    assert again.get("duplicate_guard") is True
    assert again["id"] == first["id"]
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "UPDATE domestic_shipments SET created_at='2020-01-01T00:00:00' WHERE id=?",
            (first["id"],),
        )
        con.commit()
    second = create_domestic(_submit(vendor_id), token)
    assert second.get("duplicate_guard") is not True
    assert second["id"] != first["id"]


def test_cancel_requires_confirm_then_marks_label(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    created = create_domestic(_submit(vendor_id), token)
    with pytest.raises(HTTPException) as exc:
        cancel_domestic(created["id"], token, confirm=False)
    assert exc.value.status_code == 400
    called = {}

    def fake_cancel(**kwargs):
        called.update(kwargs)
        return {"canceledYn": "Y"}

    monkeypatch.setattr("backend.app.api.domestic_shipping.cancel_order", fake_cancel)
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("UPDATE domestic_shipments SET is_test=0, req_no='REQ', res_no='RES' WHERE id=?", (created["id"],))
        con.commit()
    result = cancel_domestic(created["id"], token, confirm=True)
    assert result["success"] is True
    assert called["req_type"] == "1"
    text = fitz.open(stream=domestic_label(created["id"], token, format="pdf").body, filetype="pdf")[0].get_text()
    assert "취소된 접수" in text


def test_admin_delete_rejects_staff(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    created = create_domestic(_submit(vendor_id), token)
    with pytest.raises(HTTPException) as exc:
        delete_domestic(created["id"], token)
    assert exc.value.status_code == 403
