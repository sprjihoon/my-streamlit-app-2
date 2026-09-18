from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from backend.app.api.overseas_shipping import (
    OverseasSubmitRequest,
    SavedOverseasAddressRequest,
    SavedOverseasHsRequest,
    SavedOverseasSenderRequest,
    cancel_overseas,
    create_overseas,
    delete_saved_overseas_address,
    delete_saved_overseas_hs,
    delete_saved_overseas_sender,
    list_overseas,
    list_saved_overseas_addresses,
    list_saved_overseas_hs,
    list_saved_overseas_senders,
    overseas_item_categories,
    overseas_label,
    overseas_meta,
    overseas_nations,
    preview_overseas,
    save_overseas_address,
    save_overseas_hs,
    save_overseas_sender,
    update_saved_overseas_address,
    update_saved_overseas_hs,
    update_saved_overseas_sender,
)
from backend.app.services.ems.client import mock_apply_ems
from backend.app.services.ems.dimension_limits import validate_shipping_dimensions, validate_weight
from backend.app.services.ems.fields import (
    apply_sender_override,
    build_ems_params,
    resolve_sender,
    serialize_invoice_items,
    validate_apply_input,
)
from backend.app.services.ems.item_categories import suggest_item_categories


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
        "sender_name": "",
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


def test_snapshot_excludes_contract_secrets(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(_req(confirm=True, receivetelno="+819099900001"), token)
    with sqlite3.connect(isolated_runtime["db"]) as con:
        row = con.execute(
            "SELECT apply_snapshot FROM overseas_shipping_requests WHERE id=?",
            (created["id"],),
        ).fetchone()
    snapshot = json.loads(row[0])
    assert "custno" not in snapshot
    assert "apprno" not in snapshot
    assert snapshot["premiumcd"] == "31"
    assert snapshot["sender"] == "스프링풀필먼트"


def test_cancel_requires_confirm(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(_req(confirm=True, receivetelno="+819099900002"), token)
    try:
        cancel_overseas(created["id"], token, confirm=False)
        raise AssertionError("cancel confirm required")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_meta_and_nations_fallback_without_ems_keys(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    meta = overseas_meta(token)
    assert meta["live_ready"] is False
    assert meta["sender"]["name"] == "스프링풀필먼트"
    nations = overseas_nations(token, premiumcd="14")
    assert nations["fallback"] is True
    assert any(n["nationcd"] == "JP" for n in nations["items"])


def test_mock_apply_prefixes():
    assert mock_apply_ems("31", "em", "JP")["regino"].startswith("EG")
    assert mock_apply_ems("32", "em", "US")["regino"].startswith("FX")
    assert mock_apply_ems("14", "rl", "TW")["regino"].startswith("LK")


def test_sender_name_override_and_default():
    defaulted = validate_apply_input(_req().model_dump())
    assert defaulted["sender"]["name"] == "스프링풀필먼트"
    overridden = validate_apply_input(_req(sender_name="Spring Shop JP").model_dump())
    assert overridden["sender"]["name"] == "Spring Shop JP"
    try:
        apply_sender_override(resolve_sender(), "bad@email.com")
        raise AssertionError("email sender should fail")
    except ValueError as exc:
        assert "이메일" in str(exc)


def test_preview_and_create_use_custom_sender(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    preview = preview_overseas(_req(sender_name="Custom Sender"), token)
    assert preview["preview"]["sender_name"] == "Custom Sender"
    created = create_overseas(_req(confirm=True, sender_name="Custom Sender", receivetelno="+819099900010"), token)
    assert created["preview"]["sender_name"] == "Custom Sender"
    assert list_overseas(token)["items"][0]["sender_name"] == "Custom Sender"


def _addr(**overrides) -> SavedOverseasAddressRequest:
    data = {
        "label": "오사카창고",
        "recipient_name": "Taro Yamada",
        "recipient_phone": "+819011112222",
        "recipient_email": "taro@example.com",
        "countrycd": "JP",
        "zipcode": "150-0001",
        "addr1": "Osaka",
        "addr2": "Namba",
        "addr3": "1-2-3 Namba Street",
        "is_default": True,
    }
    data.update(overrides)
    return SavedOverseasAddressRequest(**data)


def test_saved_overseas_address_crud_and_isolation(isolated_runtime):
    token_a = _seed_user(isolated_runtime["db"], token="tok-a")
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin, department) VALUES (?,?,?,?,?)",
            ("other", "x", "다른담당", 0, "물류팀"),
        )
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, 2)", ("tok-b",))
        con.commit()

    saved = save_overseas_address(_addr(), token_a)
    assert saved["success"] is True
    assert saved["is_default"] is True
    assert list_saved_overseas_addresses(token_a)["items"][0]["label"] == "오사카창고"

    try:
        save_overseas_address(_addr(), token_a)
        raise AssertionError("duplicate alias should fail")
    except HTTPException as exc:
        assert exc.status_code == 400

    updated = update_saved_overseas_address(saved["id"], _addr(label="도쿄창고", is_default=False), token_a)
    assert updated["label"] == "도쿄창고"
    assert list_saved_overseas_addresses("tok-b")["items"] == []

    other = save_overseas_address(_addr(label="B창고"), "tok-b")
    try:
        delete_saved_overseas_address(other["id"], token_a)
        raise AssertionError("other user delete should fail")
    except HTTPException as exc:
        assert exc.status_code == 403

    deleted = delete_saved_overseas_address(saved["id"], token_a)
    assert deleted["success"] is True
    assert list_saved_overseas_addresses(token_a)["items"] == []


def test_create_can_save_address_book(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(
        _req(
            confirm=True,
            receivetelno="+819099900020",
            save_address=True,
            save_address_label="접수저장",
            save_address_default=True,
        ),
        token,
    )
    assert created["success"] is True
    items = list_saved_overseas_addresses(token)["items"]
    assert len(items) == 1
    assert items[0]["label"] == "접수저장"
    assert items[0]["is_default"] is True


def test_item_category_hs_completion(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    meta = overseas_meta(token)
    assert any(c["hs_code"] == "610910" for c in meta["item_categories"])
    hits = overseas_item_categories(token, q="610910")
    assert hits["items"][0]["hs_code"] == "610910"
    assert hits["items"][0]["name_en"]
    laptop = suggest_item_categories("laptop")
    assert any("Laptop" in c["name_en"] for c in laptop)
    shirts = overseas_item_categories(token, q="T-shirts")
    assert any(item["hs_code"].startswith("6109") for item in shirts["items"])
    notebooks = overseas_item_categories(token, q="847130")
    assert any(item["hs_code"] == "847130" for item in notebooks["items"])


def test_overseas_http_api(isolated_runtime):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    token = _seed_user(isolated_runtime["db"])
    client = TestClient(app, raise_server_exceptions=False)
    meta = client.get("/overseas-shipping/meta", params={"token": token})
    assert meta.status_code == 200
    assert meta.json()["sender"]["name"] == "스프링풀필먼트"
    cats = client.get("/overseas-shipping/item-categories", params={"token": token, "q": "의류"})
    assert cats.status_code == 200
    assert any(item["hs_code"] == "610910" for item in cats.json()["items"])
    preview = client.post(
        "/overseas-shipping/preview",
        params={"token": token},
        json=_req(sender_name="API Sender").model_dump(),
    )
    assert preview.status_code == 200
    assert preview.json()["preview"]["sender_name"] == "API Sender"
    saved = client.post(
        "/overseas-shipping/saved-addresses",
        params={"token": token},
        json=_addr(label="API주소").model_dump(),
    )
    assert saved.status_code == 200
    listed = client.get("/overseas-shipping/saved-addresses", params={"token": token})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["label"] == "API주소"


def test_saved_sender_and_hs_reuse(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    sender = save_overseas_sender(
        SavedOverseasSenderRequest(
            label="본사",
            name="스프링풀필먼트 본사",
            phone="+821012345678",
            zipcode="13494",
            addr1="Gyeonggi-do",
            addr2="Seongnam",
            addr3="Bundang 1",
            is_default=True,
        ),
        token,
    )
    assert sender["success"] is True
    assert list_saved_overseas_senders(token)["items"][0]["label"] == "본사"
    updated = update_saved_overseas_sender(
        sender["id"],
        SavedOverseasSenderRequest(
            label="본사",
            name="스프링풀필먼트",
            phone="+821012345678",
            zipcode="13494",
            addr1="Gyeonggi-do",
            addr2="Seongnam",
            addr3="Bundang 1-2",
            is_default=True,
        ),
        token,
    )
    assert updated["label"] == "본사"

    hs = save_overseas_hs(
        SavedOverseasHsRequest(
            label="커스텀의류",
            name_ko="커스텀의류",
            name_en="Custom Apparel",
            hs_code="610990",
            origin_country="KR",
        ),
        token,
    )
    assert hs["hs_code"] == "610990"
    hits = overseas_item_categories(token, q="610990")
    assert hits["items"][0]["hs_code"] == "610990"
    assert hits["items"][0]["saved"] is True
    meta = overseas_meta(token)
    assert any(row["hs_code"] == "610990" for row in meta["saved_hs"])

    created = create_overseas(
        _req(
            confirm=True,
            receivetelno="+819099900030",
            sender_name="스프링풀필먼트",
            sender_zipcode="13494",
            sender_addr1="Gyeonggi-do",
            sender_addr3="Bundang 1-2",
            save_sender=True,
            save_sender_label="접수발송인",
            items=[{
                "name_en": "Custom Apparel",
                "quantity": 1,
                "unit_price_usd": 20,
                "hs_code": "610990",
                "origin_country": "KR",
            }],
        ),
        token,
    )
    assert created["success"] is True
    listed_hs = list_saved_overseas_hs(token)["items"]
    assert any(row["hs_code"] == "610990" and row["name_en"] == "Custom Apparel" for row in listed_hs)

    update_saved_overseas_hs(
        hs["id"],
        SavedOverseasHsRequest(
            label="커스텀의류",
            name_ko="커스텀의류",
            name_en="Custom Apparel",
            hs_code="610991",
            origin_country="KR",
        ),
        token,
    )
    assert list_saved_overseas_hs(token, q="610991")["items"][0]["hs_code"] == "610991"
    assert delete_saved_overseas_hs(hs["id"], token)["success"] is True
    assert delete_saved_overseas_sender(sender["id"], token)["success"] is True


def test_label_from_saved_shipment_not_epost_pdf(isolated_runtime):
    from fastapi.responses import HTMLResponse

    from backend.app.services.ems.label import build_shipment_label

    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(_req(confirm=True, receivetelno="+819099900088"), token)
    body = overseas_label(created["id"], token)
    label = body["label"]
    assert label["source"] == "internal"
    assert label["regino"] == created["tracking_no"]
    assert label["sender"]["name"] == "스프링풀필먼트"
    assert label["recipient"]["name"] == "Hong Gildong"
    assert label["items"][0]["hs_code"] == "610910"
    assert label["customs_value_usd"] == 50.0
    assert "custno" not in label
    assert "apprno" not in json.dumps(label)
    assert "quickchart.io/barcode" in label["barcode_url"]

    html = overseas_label(created["id"], token, format="html")
    assert isinstance(html, HTMLResponse)
    text = html.body.decode("utf-8")
    assert "Customs Declaration (CN22)" in text
    assert created["tracking_no"] in text
    assert "Clothing" in text

    built = build_shipment_label(
        {
            "id": 1,
            "order_no": "TIL-1",
            "shipping_method": "KPACKET",
            "countrycd": "TW",
            "sender_name": "Spring",
            "recipient_name": "Chen",
            "recipient_addr3": "1 Main St",
            "tracking_no": "LK123456789KR",
            "is_test": False,
            "items": [{"name_en": "Shoes", "quantity": 1, "unit_price_usd": 12, "hs_code": "6403"}],
        }
    )
    assert built["service_label"] == "K-PACKET"
    assert built["ems_applied"] is True

    try:
        overseas_label(created["id"], "bad-token")
        raise AssertionError("label requires login")
    except HTTPException as exc:
        assert exc.status_code == 401

    try:
        overseas_label(9_999_999, token)
        raise AssertionError("missing shipment should 404")
    except HTTPException as exc:
        assert exc.status_code == 404


def test_label_html_escapes_and_prints_canceled(isolated_runtime):
    from fastapi.responses import HTMLResponse

    from backend.app.services.ems.label import build_shipment_label, render_label_html

    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(
        _req(
            confirm=True,
            receivetelno="+819099900099",
            receivename="Hong<script>",
            items=[
                {
                    "name_en": 'Shirt "A"',
                    "quantity": 1,
                    "unit_price_usd": 10,
                    "hs_code": "610910",
                    "origin_country": "KR",
                }
            ],
        ),
        token,
    )
    html = overseas_label(created["id"], token, format="html")
    assert isinstance(html, HTMLResponse)
    text = html.body.decode("utf-8")
    assert "<script>" not in text
    assert "Hong&lt;script&gt;" in text
    assert "Shirt &quot;A&quot;" in text
    assert html.media_type.startswith("text/html")

    cancel_overseas(created["id"], token, confirm=True)
    canceled_html = overseas_label(created["id"], token, format="html")
    assert "취소된 접수" in canceled_html.body.decode("utf-8")

    escaped = render_label_html(
        build_shipment_label(
            {
                "order_no": "TIL-XSS",
                "shipping_method": "EMS",
                "countrycd": "JP",
                "recipient_name": "<b>x</b>",
                "recipient_addr3": "<img>",
                "tracking_no": "EG000000001KR",
                "items": [{"name_en": "<svg>", "quantity": 1, "unit_price_usd": 1}],
            }
        )
    )
    assert "<svg>" not in escaped
    assert "&lt;svg&gt;" in escaped
    assert "&lt;b&gt;x&lt;/b&gt;" in escaped
