from __future__ import annotations

import sqlite3

import fitz
import pytest
from fastapi import HTTPException

from backend.app.api.domestic_shipping import (
    DomesticSavedRecipientRequest,
    DomesticSubmitRequest,
    DomesticVendorRequest,
    cancel_domestic,
    create_domestic,
    create_vendor,
    delete_domestic,
    delete_domestic_saved_recipient,
    domestic_label,
    ensure_domestic_tables,
    domestic_labels,
    list_domestic_saved_recipients,
    preview_domestic,
    save_domestic_recipient,
    update_domestic_saved_recipient,
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
            "vTelNo": "05056159873",
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
            "SELECT api_sender_name, print_sender_name, tracking_no, is_test, v_tel_no FROM domestic_shipments WHERE id=?",
            (created["id"],),
        ).fetchone()
    assert row == ("스프링풀필먼트", "출력용상점", "1234567890123", 0, "05056159873")
    pdf = domestic_label(created["id"], token, format="pdf")
    text = fitz.open(stream=pdf.body, filetype="pdf")[0].get_text()
    assert "출력용상점" in text
    assert "홍길동" in text
    assert "12345-6789-0123" in text
    assert "T: 0505-615-9873" in text
    assert "010-1234-5678" not in text
    assert "임시 가상번호" in text
    assert "QA2Ene" not in text
    assert "A1" in text
    assert "135" in text
    assert "동서울" in text
    assert "서울강남" in text
    assert "100" in text
    page = fitz.open(stream=pdf.body, filetype="pdf")[0]
    assert abs(page.rect.width - 484.72) < 0.2
    assert abs(page.rect.height - 314.65) < 0.2


def test_goods_qty_is_sent_and_several_labels_print(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    captured = []

    def fake_insert(params):
        captured.append(dict(params))
        n = len(captured)
        return {
            "reqNo": f"REQ{n}",
            "resNo": f"RES{n}",
            "regiNo": f"12345678901{n:02d}",
            "regiPoNm": "동대구우체국",
            "resDate": "20261003",
            "price": "2600",
            "vTelNo": "",
        }

    monkeypatch.setattr("backend.app.api.domestic_shipping.has_epost_credentials", lambda: True)
    monkeypatch.setattr("backend.app.api.domestic_shipping.insert_order", fake_insert)
    created = create_domestic(_submit(vendor_id, test_mode=False, goods_qty=3, label_count=2), token)
    assert created["partial"] is False
    assert len(created["ids"]) == 2
    assert len(captured) == 2
    assert {row["qty"] for row in captured} == {3}
    assert {row["goodsNm"] for row in captured} == {"의류"}
    assert captured[0]["orderNo"] != captured[1]["orderNo"]
    pdf = domestic_labels(token, ids=",".join(str(item) for item in created["ids"]))
    doc = fitz.open(stream=pdf.body, filetype="pdf")
    assert doc.page_count == 2
    assert "수량:3" in doc[0].get_text()
    assert "수량:3" in doc[1].get_text()
    with sqlite3.connect(isolated_runtime["db"]) as con:
        qty = con.execute("SELECT goods_qty FROM domestic_shipments WHERE id=?", (created["ids"][0],)).fetchone()[0]
    assert qty == 3


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


def _saved(**overrides) -> DomesticSavedRecipientRequest:
    data = {
        "label": "본사",
        "recipient_name": "홍길동",
        "recipient_phone": "010-1234-5678",
        "zipcode": "06236",
        "addr1": "서울특별시 강남구 테헤란로 123",
        "addr2": "201호",
    }
    data.update(overrides)
    return DomesticSavedRecipientRequest(**data)


def test_spring_vendor_is_seeded_once_from_pickup_center(isolated_runtime):
    ensure_domestic_tables()
    ensure_domestic_tables()
    with sqlite3.connect(isolated_runtime["db"]) as con:
        rows = con.execute(
            "SELECT name, office_ser, sender_name, sender_phone, sender_zip, sender_addr1, sender_addr2 FROM domestic_vendors"
        ).fetchall()
    assert rows == [(
        "스프링풀필먼트",
        "260940699",
        "스프링풀필먼트",
        "01027239490",
        "41142",
        "대구광역시 동구 동촌로 1",
        "동대구우체국 2층 소포실",
    )]


def test_domestic_saved_addresses_stay_separate_from_pickup(isolated_runtime):
    from backend.app.api.kpost_pickup.saved_recipients import list_saved_recipients, save_recipient
    from backend.app.api.kpost_pickup.saved_recipients import SavedRecipientRequest

    token = _seed_user(isolated_runtime["db"])
    save_recipient(SavedRecipientRequest(**{
        "label": "회수창고",
        "recipient_name": "회수고객",
        "recipient_phone": "01011112222",
        "zipcode": "04524",
        "addr1": "서울특별시 중구 세종대로 110",
        "addr2": "1층",
    }), token)

    assert list_domestic_saved_recipients(token)["items"] == []
    saved = save_domestic_recipient(_saved(), token)
    assert saved["recipient_phone"] == "01012345678"
    assert [row["label"] for row in list_domestic_saved_recipients(token)["items"]] == ["본사"]
    assert [row["label"] for row in list_saved_recipients(token)["items"]] == ["회수창고"]

    again = save_domestic_recipient(_saved(recipient_name="다른사람"), token)
    assert again["id"] == saved["id"]
    assert list_domestic_saved_recipients(token)["items"][0]["recipient_name"] == "홍길동"

    other = save_domestic_recipient(_saved(label="창고2"), token)
    with pytest.raises(HTTPException) as exc:
        update_domestic_saved_recipient(saved["id"], _saved(label="창고2"), token)
    assert exc.value.status_code == 400
    updated = update_domestic_saved_recipient(saved["id"], _saved(label="경기창고"), token)
    assert updated["label"] == "경기창고"
    delete_domestic_saved_recipient(saved["id"], token)
    delete_domestic_saved_recipient(other["id"], token)
    assert list_domestic_saved_recipients(token)["items"] == []
    assert [row["label"] for row in list_saved_recipients(token)["items"]] == ["회수창고"]


def test_domestic_saved_addresses_isolated_by_user(isolated_runtime):
    token_a = _seed_user(isolated_runtime["db"], token="tok-a")
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin, department) VALUES (?,?,?,?,?)",
            ("other", "x", "다른담당", 0, "물류팀"),
        )
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, 2)", ("tok-b",))
        con.commit()
    save_domestic_recipient(_saved(label="A창고"), token_a)
    assert list_domestic_saved_recipients("tok-b")["items"] == []
    other = save_domestic_recipient(_saved(label="B창고"), "tok-b")
    with pytest.raises(HTTPException) as exc:
        delete_domestic_saved_recipient(other["id"], token_a)
    assert exc.value.status_code == 403


def test_admin_delete_rejects_staff(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    vendor_id = create_vendor(_vendor(), token)["id"]
    created = create_domestic(_submit(vendor_id), token)
    with pytest.raises(HTTPException) as exc:
        delete_domestic(created["id"], token)
    assert exc.value.status_code == 403
