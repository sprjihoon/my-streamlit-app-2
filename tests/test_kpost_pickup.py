from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from backend.app.api.kpost_pickup import (
    PickupSubmitRequest,
    cancel_pickup,
    create_pickup,
    list_pickups,
    preview_pickup,
)
from backend.app.services.epost.fields import (
    build_return_pickup_params,
    normalize_pickup_addr2,
    normalize_ret_visit_ymd,
    require_phone,
    split_pickup_address,
)
from backend.app.services.epost.seed128 import SS1, seed128_encrypt


def _seed_user(db_path, token="tok-pickup"):
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


def _req(**overrides) -> PickupSubmitRequest:
    data = {
        "recipient_name": "홍길동",
        "recipient_phone": "010-1234-5678",
        "zipcode": "06236",
        "addr1": "서울특별시 강남구 테헤란로 123",
        "addr2": "201호",
        "pickup_date": "2026-09-10",
        "goods_name": "의류",
        "box_size": "DEFAULT",
        "box_quantity": 1,
        "notes": "문앞",
        "confirm": False,
        "test_mode": True,
    }
    data.update(overrides)
    return PickupSubmitRequest(**data)


def test_seed128_matches_infront_reference():
    assert SS1[109] == 0x04040400
    assert (
        seed128_encrypt("custNo=0005085217&apprNo=7002080922&recNm=테스트", "testkey123456789")
        == "bc9b2a92bbaf266cda7e0a6c7e0f357d1635e1d35b725cc903f814452592c5ac6a8f447d5bec0fc22db4e2f221cd50111291f1c2ec9260b3418eec181d0cf3cb"
    )


def test_field_guards():
    assert normalize_pickup_addr2("3층") == "제3층"
    addr1, addr2 = split_pickup_address("서울특별시 강남구 테헤란로 123", "201호")
    assert addr1.startswith("서울")
    assert addr2 == "201호"
    assert require_phone("010-1234-5678", "수거 연락처") == "01012345678"
    try:
        require_phone("12", "수거 연락처")
        raise AssertionError("short phone should fail")
    except ValueError:
        pass
    try:
        normalize_ret_visit_ymd("2026-09-12")
        raise AssertionError("saturday should fail")
    except ValueError as exc:
        assert "토·일" in str(exc)


def test_build_return_pickup_params_ord_center_rec_customer():
    params = build_return_pickup_params(
        {
            "cust_no": "TEST",
            "appr_no": "0000000000",
            "order_no": "SPB123",
            "center": {
                "ord_nm": "인프론트",
                "zip": "41142",
                "addr1": "대구광역시 동구 동촌로 1",
                "addr2": "동대구우체국 2층 소포실",
                "phone": "01027239490",
            },
            "pickup": {
                "name": "홍길동",
                "zip": "06236",
                "addr1": "서울특별시 강남구 테헤란로 123",
                "addr2": "201호",
                "phone": "01012345678",
            },
            "goods_nm": "의류",
            "weight": 2,
            "volume": 60,
            "qty": 3,
            "ret_visit_ymd": "2026-09-10",
            "test_yn": "Y",
        }
    )
    assert params["reqType"] == "2"
    assert params["payType"] == "2"
    assert params["officeSer"] == "260940699"
    assert params["ordZip"] == "41142"
    assert params["recZip"] == "06236"
    assert params["recAddr2"] == "201호"
    assert params["qty"] == 3
    assert "recMob" not in params
    assert params["ordMob"] == "01027239490"


def test_office_ser_uses_spring_fulfillment_code(monkeypatch):
    from backend.app.services.epost.fields import resolve_office_ser

    assert resolve_office_ser({}) == "260940699"
    monkeypatch.setenv("EPOST_OFFICE_SER", "260940699")
    assert resolve_office_ser() == "260940699"


def test_preview_does_not_write(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    body = preview_pickup(_req(), token)
    assert body["preview"]["recipient_name"] == "홍길동"
    assert body["preview"]["is_test"] is True
    assert list_pickups(token)["items"] == []


def test_create_requires_confirm_then_saves_mock(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    try:
        create_pickup(_req(), token)
        raise AssertionError("confirm required")
    except HTTPException as exc:
        assert exc.status_code == 400

    created = create_pickup(_req(confirm=True), token)
    assert created["success"] is True
    assert created["is_test"] is True
    assert created["tracking_no"].startswith("7")
    items = list_pickups(token)["items"]
    assert len(items) == 1
    assert items[0]["status"] == "requested"

    again = create_pickup(_req(confirm=True), token)
    assert again.get("duplicate_guard") is True
    assert len(list_pickups(token)["items"]) == 1

    canceled = cancel_pickup(items[0]["id"], token, confirm=True)
    assert canceled["success"] is True
    assert list_pickups(token)["items"][0]["status"] == "canceled"


def test_missing_detail_rejected_when_live_like_validation(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    monkeypatch.setenv("EPOST_API_KEY", "x")
    monkeypatch.setenv("EPOST_SECURITY_KEY", "y")
    monkeypatch.setenv("EPOST_CUSTOMER_ID", "1")
    monkeypatch.setenv("EPOST_APPROVAL_NO", "2")
    monkeypatch.setenv("INFRONT_CENTER_PHONE", "01027239490")
    try:
        preview_pickup(_req(addr2="", test_mode=False), token)
        raise AssertionError("empty addr2 should fail")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "상세주소" in str(exc.detail)
