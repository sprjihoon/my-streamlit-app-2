from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from backend.app.api.kpost_pickup import (
    PickupSubmitRequest,
    SavedRecipientRequest,
    cancel_pickup,
    create_pickup,
    delete_saved_recipient,
    list_pickups,
    list_saved_recipients,
    preview_pickup,
    refresh_pickup_statuses,
    save_recipient,
    update_saved_recipient,
)
from backend.app.services.epost.fields import (
    build_return_pickup_params,
    normalize_pickup_addr2,
    normalize_ret_visit_ymd,
    require_phone,
    resolve_infront_center,
    split_pickup_address,
    treat_status_from_tracking_text,
    treat_status_label,
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


def test_seed128_matches_rfc4269_and_infront_reference():
    from backend.app.services.epost.seed128 import _seed_encrypt, _seed_round_key

    assert SS1[109] == 0x04040400
    zero_ct = _seed_encrypt(bytes(range(16)), _seed_round_key(bytes(16))).hex()
    assert zero_ct == "5ebac6e0054e166819aff1cc6d346cdb"
    assert (
        seed128_encrypt("custNo=0005085217&apprNo=7002080922&recNm=테스트", "testkey123456789")
        == "bc9b2a92bbaf266cda7e0a6c7e0f357d1635e1d35b725cc903f814452592c5ac6a8f447d5bec0fc22db4e2f221cd50111291f1c2ec9260b3418eec181d0cf3cb"
    )


def test_treat_status_label_maps_picked_up_to_completed():
    assert treat_status_label("01") == "수거완료"
    assert treat_status_label("00") == "신청접수"
    assert treat_status_label("1", "집하완료") == "수거완료"
    assert treat_status_label("", "집하완료") == "수거완료"
    assert treat_status_from_tracking_text("집하완료 동대구우체국") == "01"
    assert treat_status_from_tracking_text("배달완료") == "03"


def test_resolve_center_ignores_legacy_infront_name():
    center = resolve_infront_center(
        {
            "INFRONT_CENTER_NAME": "인프론트",
            "INFRONT_CENTER_ORD_NM": "인프론트",
        }
    )
    assert center["display_name"] == "스프링풀필먼트"
    assert center["ord_nm"] == "스프링풀필먼트"


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
                "ord_nm": "스프링풀필먼트",
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
    assert params["ordCompNm"] == "스프링풀필먼트"
    assert params["ordZip"] == "41142"
    assert params["recZip"] == "06236"
    assert params["recAddr2"] == "201호"
    assert params["qty"] == 3
    assert "recMob" not in params
    assert params["ordMob"] == "01027239490"


def test_office_ser_uses_spring_fulfillment_code(monkeypatch):
    from backend.app.services.epost.fields import resolve_office_ser

    assert resolve_office_ser({}) == "260940699"
    monkeypatch.setenv("EPOST_OFFICE_SER", "260537802")
    assert resolve_office_ser() == "260940699"
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
    assert items[0]["tracking_no"] == created["tracking_no"]
    assert len(items[0]["tracking_no"]) >= 10

    again = create_pickup(_req(confirm=True), token)
    assert again.get("duplicate_guard") is True
    assert len(list_pickups(token)["items"]) == 1

    canceled = cancel_pickup(items[0]["id"], token, confirm=True)
    assert canceled["success"] is True
    assert list_pickups(token)["items"][0]["status"] == "canceled"
    assert list_pickups(token)["items"][0]["treat_status_name"] == "취소"


def test_refresh_status_marks_pickup_complete(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    created = create_pickup(_req(confirm=True), token)
    pickup_id = created["id"]
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "UPDATE kpost_pickup_requests SET is_test=0, treat_status='00', treat_status_name='신청접수' WHERE id=?",
            (pickup_id,),
        )
        con.commit()

    monkeypatch.setattr(
        "backend.app.api.kpost_pickup.get_res_info_with_dates",
        lambda order_no, req_ymds: {
            "treatStusCd": "01",
            "treatStusNm": "수거완료",
            "regiNo": "7111111111111",
        },
    )
    result = refresh_pickup_statuses(token)
    assert result["completed"] == 1
    item = list_pickups(token)["items"][0]
    assert item["treat_status_name"] == "수거완료"
    assert item["tracking_no"] == "7111111111111"


def test_refresh_status_uses_public_tracking_when_getresinfo_stays_requested(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    created = create_pickup(_req(confirm=True), token)
    pickup_id = created["id"]
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            """
            UPDATE kpost_pickup_requests
            SET is_test=0, treat_status='00', treat_status_name='신청접수', tracking_no='7222222222222'
            WHERE id=?
            """,
            (pickup_id,),
        )
        con.commit()

    monkeypatch.setattr(
        "backend.app.api.kpost_pickup.get_res_info_with_dates",
        lambda order_no, req_ymds: {"treatStusCd": "00", "treatStusNm": "신청접수", "regiNo": "7222222222222"},
    )
    monkeypatch.setattr(
        "backend.app.api.kpost_pickup.track_regi_no",
        lambda regi_no: {"treatStusCd": "01", "treatStusNm": "수거완료", "regiNo": regi_no},
    )
    result = refresh_pickup_statuses(token)
    assert result["completed"] == 1
    assert list_pickups(token)["items"][0]["treat_status_name"] == "수거완료"


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


def _saved_req(**overrides) -> SavedRecipientRequest:
    data = {
        "label": "본사",
        "recipient_name": "홍길동",
        "recipient_phone": "010-1234-5678",
        "zipcode": "06236",
        "addr1": "서울특별시 강남구 테헤란로 123",
        "addr2": "201호",
    }
    data.update(overrides)
    return SavedRecipientRequest(**data)


def test_saved_recipient_alias_crud_and_autofill_fields(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    saved = save_recipient(_saved_req(), token)
    assert saved["success"] is True
    assert saved["label"] == "본사"

    listed = list_saved_recipients(token)
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert item["recipient_name"] == "홍길동"
    assert item["recipient_phone"] == "01012345678"
    assert item["zipcode"] == "06236"
    assert item["addr1"].startswith("서울")
    assert item["addr2"] == "201호"

    try:
        save_recipient(_saved_req(), token)
        raise AssertionError("duplicate alias should fail")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "본사" in str(exc.detail)

    updated = update_saved_recipient(item["id"], _saved_req(label="경기창고"), token)
    assert updated["label"] == "경기창고"
    assert list_saved_recipients(token)["items"][0]["label"] == "경기창고"

    deleted = delete_saved_recipient(item["id"], token)
    assert deleted["success"] is True
    assert list_saved_recipients(token)["items"] == []


def test_saved_recipient_isolated_by_user(isolated_runtime):
    token_a = _seed_user(isolated_runtime["db"], token="tok-a")
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin, department) VALUES (?,?,?,?,?)",
            ("other", "x", "다른담당", 0, "물류팀"),
        )
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, 2)", ("tok-b",))
        con.commit()

    save_recipient(_saved_req(label="A창고"), token_a)
    assert list_saved_recipients("tok-b")["items"] == []
    other = save_recipient(_saved_req(label="B창고"), "tok-b")
    assert [row["label"] for row in list_saved_recipients(token_a)["items"]] == ["A창고"]

    try:
        update_saved_recipient(other["id"], _saved_req(label="침범"), token_a)
        raise AssertionError("other user update should fail")
    except HTTPException as exc:
        assert exc.status_code == 403

    try:
        delete_saved_recipient(other["id"], token_a)
        raise AssertionError("other user delete should fail")
    except HTTPException as exc:
        assert exc.status_code == 403
