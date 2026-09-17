from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from backend.app.api.overseas_shipping import (
    OverseasSubmitRequest,
    cancel_overseas,
    create_overseas,
    list_overseas,
    preview_overseas,
)
from backend.app.services.ems.dimension_limits import validate_shipping_dimensions, validate_weight
from backend.app.services.ems.fields import build_ems_params, serialize_invoice_items, validate_apply_input


def _seed_user(db_path, token="tok-overseas"):
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
            ("staff", "x", "물류담당", 0, "물류팀"),
        )
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, 1)", (token,))
        con.commit()
    return token


def _req(**overrides) -> OverseasSubmitRequest:
    data = {
        "shipping_method": "EMS",
        "countrycd": "JP",
        "receivename": "Hong Gildong",
        "receivetelno": "+819012345678",
        "receivemail": "hong@example.com",
        "receivezipcode": "1500001",
        "receiveaddr1": "Tokyo",
        "receiveaddr2": "Shibuya-ku",
        "receiveaddr3": "1-2-3 Example Street",
        "totweight": 500,
        "boxlength": 30,
        "boxwidth": 25,
        "boxheight": 15,
        "items": [
            {
                "name_en": "Clothing",
                "quantity": 2,
                "unit_price_usd": 25,
                "hs_code": "610910",
                "origin_country": "KR",
            }
        ],
        "notes": "",
        "confirm": False,
        "test_mode": True,
    }
    data.update(overrides)
    return OverseasSubmitRequest(**data)


def test_kpacket_dimension_and_weight_guards():
    assert validate_weight("14", "rl", 2500)
    assert validate_shipping_dimensions("14", "rl", "US", 50, 40, 20)
    assert validate_shipping_dimensions("14", "rl", "US", 30, 25, 20) is None
    assert validate_shipping_dimensions("31", "em", "US", 160, 40, 40)
    assert validate_shipping_dimensions("32", "em", "JP", 280, 40, 40)


def test_invoice_semicolon_and_english_name():
    packed = serialize_invoice_items(
        [{"name_en": "Shoes", "quantity": 1, "unit_price_usd": 40, "hs_code": "6403", "origin_country": "KR"}],
        800,
    )
    assert packed["contents"] == "Shoes"
    assert packed["number"] == "1"
    assert packed["weight"] == "800"
    assert packed["EM_gubun"] == "Merchandise"
    try:
        validate_apply_input(
            {
                "shipping_method": "EMS",
                "countrycd": "JP",
                "receivename": "user@example.com",
                "receiveaddr3": "1-2-3 Street",
                "receiveaddr1": "Tokyo",
                "totweight": 500,
                "boxlength": 20,
                "boxwidth": 20,
                "boxheight": 10,
                "items": packed["items"],
            }
        )
        raise AssertionError("email recipient should fail")
    except ValueError as exc:
        assert "영문" in str(exc) or "이메일" in str(exc)


def test_build_ems_params_skips_empty_and_keeps_order():
    plain = build_ems_params(
        {
            "custno": "0005085217",
            "premiumcd": "31",
            "em_ee": "em",
            "countrycd": "JP",
            "totweight": 500,
            "snd_message": "",
            "boyn": "N",
        }
    )
    assert "custno=0005085217" in plain
    assert "premiumcd=31" in plain
    assert "snd_message" not in plain
    assert plain.index("custno") < plain.index("premiumcd")


def test_preview_does_not_write(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    body = preview_overseas(_req(), token)
    assert body["preview"]["recipient_name"] == "Hong Gildong"
    assert body["preview"]["is_test"] is True
    assert body["preview"]["expected_fee"] is not None
    assert list_overseas(token)["items"] == []


def test_create_requires_confirm_then_saves_mock(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    try:
        create_overseas(_req(), token)
        raise AssertionError("confirm required")
    except HTTPException as exc:
        assert exc.status_code == 400

    created = create_overseas(_req(confirm=True), token)
    assert created["success"] is True
    assert created["is_test"] is True
    assert created["tracking_no"].startswith("EG")
    items = list_overseas(token)["items"]
    assert len(items) == 1
    assert items[0]["status"] == "requested"
    assert items[0]["countrycd"] == "JP"
    assert items[0]["items"][0]["name_en"] == "Clothing"

    again = create_overseas(_req(confirm=True), token)
    assert again.get("duplicate_guard") is True
    assert len(list_overseas(token)["items"]) == 1

    canceled = cancel_overseas(items[0]["id"], token, confirm=True)
    assert canceled["success"] is True
    assert list_overseas(token)["items"][0]["status"] == "canceled"


def test_kpacket_reject_overweight_on_preview(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    try:
        preview_overseas(_req(shipping_method="KPACKET", totweight=2500), token)
        raise AssertionError("overweight should fail")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "중량" in str(exc.detail)
