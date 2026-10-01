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
    clear_nation_cache,
    create_overseas,
    delete_saved_overseas_address,
    delete_saved_overseas_hs,
    delete_saved_overseas_sender,
    delete_overseas,
    list_overseas,
    get_overseas,
    list_saved_overseas_addresses,
    list_saved_overseas_hs,
    list_saved_overseas_senders,
    overseas_item_categories,
    overseas_label,
    overseas_meta,
    overseas_nations,
    overseas_quote,
    preview_overseas,
    save_overseas_address,
    save_overseas_hs,
    save_overseas_sender,
    update_saved_overseas_address,
    update_saved_overseas_hs,
    update_saved_overseas_sender,
)
from backend.app.services.ems.client import approval_no_for, mock_apply_ems
from backend.app.services.epost.seed128 import seed128_encrypt
from backend.app.services.ems.dimension_limits import validate_shipping_dimensions, validate_weight
from backend.app.services.ems.fields import (
    apply_sender_override,
    build_apply_params,
    build_ems_params,
    resolve_sender,
    epost_sender_name,
    hs_code_for_epost,
    to_euc_kr_text,
    sender_mobile_parts,
    format_recipient_tel,
    split_recipient_tel,
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
    assert packed["items"][0]["product_name"] == ""
    assert packed["number"] == "1"
    assert packed["weight"] == "800"
    assert packed["EM_gubun"] == "Merchandise"
    docs = serialize_invoice_items(
        [{"name_en": "Documents", "quantity": 1, "unit_price_usd": 1, "hs_code": "", "origin_country": "KR"}],
        400,
        contents_type="document",
    )
    assert docs["EM_gubun"] == "Document"
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


def test_latin_accents_fold_into_euc_kr_before_encrypt():
    plain = build_ems_params(
        {
            "receivename": "Jürgen Müller",
            "receiveaddr3": "Düsseldorf Straße 12",
            "contents": "Printed Documents",
        }
    )
    assert "Juergen Mueller" in plain
    assert "Duesseldorf Strasse 12" in plain
    assert "ü" not in plain
    assert "ß" not in plain
    plain.encode("euc-kr")
    seed128_encrypt(plain, "testkey123456789", encoding="euc-kr")
    assert to_euc_kr_text("홍길동") == "홍길동"
    try:
        build_ems_params({"receivename": "Hong 😀"})
        raise AssertionError("emoji should fail")
    except ValueError as exc:
        assert "넣을 수 없는 문자" in str(exc)


def test_preview_warns_and_corrects_before_epost(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    body = preview_overseas(
        _req(
            receivename="Jürgen Müller",
            receiveaddr1="Nordrhein-Westfalen",
            receiveaddr2="Düsseldorf",
            receiveaddr3="Königsallee 1",
            notes="Bitte übergabe",
            items=[{
                "product_name": "Lippenstift",
                "name_en": "Lip crème",
                "quantity": 1,
                "unit_price_usd": 12,
                "hs_code": "330410",
                "origin_country": "KR",
            }],
        ),
        token,
    )
    preview = body["preview"]
    assert preview["recipient_name"] == "Juergen Mueller"
    assert "Duesseldorf" in preview["recipient_addr"]
    assert "Koenigsallee" in preview["recipient_addr"]
    labels = {row["label"]: row for row in preview["text_corrections"]}
    assert labels["수취인"]["after"] == "Juergen Mueller"
    assert labels["시/군"]["before"] == "Düsseldorf"
    assert labels["1행 품목"]["after"] == "Lip creme"
    assert "메모" in labels
    try:
        preview_overseas(_req(receivename="Hong 😀"), token)
        raise AssertionError("emoji should be rejected before apply")
    except HTTPException as exc:
        assert exc.status_code == 400
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        assert "넣을 수 없는 문자" in str(detail.get("message") or detail)
        fields = {row["field"]: row for row in detail.get("field_errors") or []}
        assert "😀" in fields["receivename"]["chars"]


def test_preview_romanizes_cjk_and_keeps_hangul(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    body = preview_overseas(
        _req(
            receivename="홍길동",
            receiveaddr1="東京都",
            receiveaddr2="渋谷区",
            receiveaddr3="渋谷 1-1-1",
            notes="กรุงเทพ",
            items=[{
                "product_name": "北京市",
                "name_en": "Clothing",
                "quantity": 1,
                "unit_price_usd": 12,
                "hs_code": "610910",
                "origin_country": "KR",
            }],
        ),
        token,
    )
    preview = body["preview"]
    assert preview["recipient_name"] == "홍길동"
    assert "SeGuQu" in preview["recipient_addr"]
    assert "DongJingDou" in preview["recipient_addr"]
    labels = {row["label"]: row for row in preview["text_corrections"]}
    assert labels["시/군"]["after"] == "SeGuQu"
    assert labels["주/도"]["after"] == "DongJingDou"
    assert labels["메모"]["after"] == "krungethph"
    assert labels["1행 제품명"]["after"] == "BeiJingShi"
    assert "수취인" not in labels


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
    assert items[0]["ddp_krw"] == 0
    assert items[0]["spent_total"] == int(float(items[0]["ems_fee"] or 0))
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
    assert snapshot["sender"] == "Spring Fulfillment"
    assert snapshot["sendermobile1"] == "82"
    assert snapshot["sendermobile2"] == "10"


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
    ems = overseas_nations(token, premiumcd="31")
    kpacket = overseas_nations(token, premiumcd="14")
    assert ems["fallback"] is True
    assert kpacket["fallback"] is True
    ems_codes = {n["nationcd"] for n in ems["items"]}
    kpacket_codes = {n["nationcd"] for n in kpacket["items"]}
    assert "JP" in kpacket_codes
    assert "NG" in ems_codes
    assert "NG" not in kpacket_codes
    assert len(kpacket["items"]) < len(ems["items"])
    assert kpacket_codes.issubset(ems_codes)


def test_nations_and_quote_use_epost_when_credentials(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    clear_nation_cache()

    def fake_nations(premiumcd: str):
        if premiumcd == "14":
            return [
                {"nationcd": "JP", "nationnm": "일본", "nationfn": "JAPAN", "premiumcd": "14"},
                {"nationcd": "TW", "nationnm": "대만", "nationfn": "TAIWAN", "premiumcd": "14"},
            ]
        return [
            {"nationcd": "JP", "nationnm": "일본", "nationfn": "JAPAN", "premiumcd": premiumcd},
            {"nationcd": "TW", "nationnm": "대만", "nationfn": "TAIWAN", "premiumcd": premiumcd},
            {"nationcd": "NG", "nationnm": "나이지리아", "nationfn": "NIGERIA", "premiumcd": premiumcd},
        ]

    monkeypatch.setattr("backend.app.api.overseas_shipping.has_ems_credentials", lambda: True)
    monkeypatch.setattr("backend.app.api.overseas_shipping.get_available_nations", fake_nations)
    monkeypatch.setattr(
        "backend.app.api.overseas_shipping.get_shipping_quote",
        lambda *args, **kwargs: {"totalFee": 36500},
    )

    kpacket = overseas_nations(token, premiumcd="14")
    assert kpacket["fallback"] is False
    assert kpacket["source"] == "epost"
    assert [n["nationcd"] for n in kpacket["items"]] == ["JP", "TW"]
    ems = overseas_nations(token, premiumcd="31")
    assert any(n["nationcd"] == "NG" for n in ems["items"])

    quoted = overseas_quote(
        token,
        shipping_method="EMS",
        countrycd="JP",
        totweight=500,
        boxlength=30,
        boxwidth=25,
        boxheight=15,
    )
    assert quoted["ok"] is True
    assert quoted["live"] is True
    assert quoted["totalFee"] == 36500
    assert quoted["source"] == "epost"
    clear_nation_cache()


def test_chargeable_weight_is_the_heavier_of_volume_and_actual():
    from backend.app.services.ems.dimension_limits import chargeable_weight_g, volumetric_weight_g

    assert volumetric_weight_g("31", 30, 25, 15) == 1875
    assert volumetric_weight_g("32", 30, 25, 15) == 2250
    assert volumetric_weight_g("14", 30, 25, 15) is None
    chargeable, volume = chargeable_weight_g("31", "em", 500, 30, 25, 15)
    assert volume == 1875
    assert chargeable == 1875
    heavier_actual, _volume = chargeable_weight_g("31", "em", 3000, 30, 25, 15)
    assert heavier_actual == 3000

    validated = validate_apply_input(_req(totweight=500, boxlength=30, boxwidth=25, boxheight=15).model_dump())
    assert validated["totweight"] == 500
    assert validated["volume_weight"] == 1875
    assert validated["chargeable_weight"] == 1875
    params = build_apply_params(validated, order_no="TIL-1", custno="1", apprno="1")
    assert params["totweight"] == 1875
    assert params["weight"] == "1875"

    kpacket = validate_apply_input(
        _req(shipping_method="KPACKET", totweight=500, boxlength=20, boxwidth=15, boxheight=10).model_dump()
    )
    assert kpacket["volume_weight"] is None
    assert kpacket["chargeable_weight"] == 500

    quoted = None
    try:
        validate_apply_input(_req(totweight=500, boxlength=100, boxwidth=50, boxheight=40).model_dump())
        raise AssertionError("over volume should fail")
    except ValueError as exc:
        assert "부피중량 초과" in str(exc)
    assert quoted is None


def test_quote_mock_without_ems_keys(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    quoted = overseas_quote(token, shipping_method="KPACKET", countrycd="JP", totweight=500)
    assert quoted["ok"] is True
    assert quoted["live"] is False
    assert quoted["totalFee"] and quoted["totalFee"] > 0
    assert quoted["shipping_method_name"] == "K-Packet"
    assert quoted["duty"]["dutyPrepaid"] is False
    assert quoted["contents_label"] == "화물"
    assert quoted["parcel"]["totalFee"] == quoted["totalFee"]
    assert quoted["document"] is None


def test_document_and_parcel_quotes_and_apply(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    parcel = overseas_quote(token, shipping_method="EMS", countrycd="JP", totweight=400, contents_type="parcel")
    document = overseas_quote(token, shipping_method="EMS", countrycd="JP", totweight=400, contents_type="document")
    assert parcel["ok"] is True and document["ok"] is True
    assert parcel["contents_label"] == "화물"
    assert document["contents_label"] == "서류"
    assert parcel["parcel"]["totalFee"] != document["document"]["totalFee"]
    assert document["totalFee"] == document["document"]["totalFee"]
    assert document["totweight"] == 500

    try:
        overseas_quote(token, shipping_method="KPACKET", countrycd="JP", totweight=400, contents_type="document")
        raise AssertionError("kpacket document should fail")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "서류" in str(exc.detail)

    validated = validate_apply_input(_req(contents_type="document", totweight=400).model_dump())
    assert validated["contents_type"] == "document"
    assert validated["method"]["em_ee"] == "ee"
    assert validated["totweight"] == 500
    assert validated["boxlength"] == 0
    assert validated["invoice"]["EM_gubun"] == "Document"
    doc_plain = build_ems_params(
        build_apply_params(validated, order_no="TIL-DOC", custno="1", apprno="1")
    )
    assert "boxlength" not in doc_plain
    assert "boxwidth" not in doc_plain
    assert "boxheight" not in doc_plain
    assert "hs_code=4901999000" in doc_plain
    assert hs_code_for_epost("490199") == "4901999000"
    assert hs_code_for_epost("4901999000") == "4901999000"
    assert hs_code_for_epost("610910", document=True) == "4901999000"
    assert hs_code_for_epost("711719") == "7117199000"
    assert hs_code_for_epost("7117199000") == "7117199000"

    created = create_overseas(_req(confirm=True, contents_type="document", totweight=400, receivetelno="+819011122233"), token)
    assert created["success"] is True
    row = list_overseas(token)["items"][0]
    assert row["contents_type"] == "document"
    assert row["contents_label"] == "서류"
    assert row["totweight"] == 500
    label = overseas_label(created["id"], token)["label"]
    assert label["contents_gubun"] == "Document"
    assert label["contents_label"] == "서류"


def test_us_ddp_quote_and_infront_formula(isolated_runtime):
    from backend.app.services.ems.duty_deposit import calculate_duty_deposit, requires_us_ems_premium

    assert requires_us_ems_premium("US", 801) is True
    assert requires_us_ems_premium("US", 800) is False
    postal = calculate_duty_deposit(
        country_code="US",
        customs_value_usd=150,
        shipping_method="EMS",
        usd_krw=1400,
    )
    assert postal["dutyPrepaid"] is True
    assert postal["ddpPath"] == "postal"
    assert postal["depositKrw"] == 46_000
    assert postal["bufferKrw"] == 4_154
    subtotal = postal["breakdown"]["dutyUsd"] + postal["breakdown"]["serviceFeeUsd"]
    assert abs(postal["breakdown"]["bufferUsd"] - subtotal * 0.1) < 1e-9
    small = calculate_duty_deposit(
        country_code="US",
        customs_value_usd=1,
        shipping_method="EMS",
        usd_krw=1400,
    )
    assert small["depositKrw"] == 2_000
    over = calculate_duty_deposit(
        country_code="US",
        customs_value_usd=850,
        shipping_method="EMS",
        usd_krw=1400,
    )
    assert over["eligible"] is False
    assert "EMS 프리미엄" in (over["ineligibleReason"] or "")
    premium = calculate_duty_deposit(
        country_code="US",
        customs_value_usd=850,
        shipping_method="EMS_PREMIUM",
        usd_krw=1400,
    )
    assert premium["ddpPath"] == "premium"
    assert premium["depositKrw"] == 309_000
    premium_sub = premium["breakdown"]["dutyUsd"] + premium["breakdown"]["serviceFeeUsd"]
    assert abs(premium["breakdown"]["bufferUsd"] - premium_sub * 0.1) < 1e-9
    gb = calculate_duty_deposit(country_code="GB", customs_value_usd=100, usd_krw=1400)
    assert gb["dutyPrepaid"] is True
    assert gb["depositKrw"] == 32_000
    assert gb["bufferKrw"] == 2_856
    assert abs(gb["breakdown"]["bufferUsd"] - gb["breakdown"]["serviceFeeUsd"] * 0.1) < 1e-9

    token = _seed_user(isolated_runtime["db"])
    quoted = overseas_quote(
        token,
        shipping_method="EMS",
        countrycd="US",
        totweight=500,
        boxlength=20,
        boxwidth=20,
        boxheight=10,
        customs_value_usd=150,
    )
    assert quoted["ok"] is True
    assert quoted["duty"]["ddpPath"] == "postal"
    assert quoted["payableTotal"] == quoted["totalFee"] + quoted["duty"]["depositKrw"]


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


def test_saved_recipient_list_has_picker_autofill_fields(isolated_runtime):
    """수취인 모달이 고른 주소의 이름·전화·국가·주소를 접수 입력에 넣을 수 있어야 한다."""
    token = _seed_user(isolated_runtime["db"])
    save_overseas_address(_addr(), token)
    item = list_saved_overseas_addresses(token)["items"][0]
    for key in (
        "id",
        "label",
        "recipient_name",
        "recipient_phone",
        "recipient_email",
        "countrycd",
        "zipcode",
        "addr1",
        "addr2",
        "addr3",
        "is_default",
    ):
        assert key in item
    assert item["recipient_name"] == "Taro Yamada"
    assert item["countrycd"] == "JP"
    assert item["addr1"] == "Osaka"
    assert item["addr2"] == "Namba"
    assert item["addr3"] == "1-2-3 Namba Street"
    assert item["zipcode"] == "150-0001"


def test_list_row_can_reprint_label_after_create(isolated_runtime):
    """접수목록의 출력서류 버튼이 쓰는 라벨 API는 같은 건을 다시 내려준다."""
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(_req(confirm=True, receivetelno="+819099900077"), token)
    row = list_overseas(token)["items"][0]
    assert row["id"] == created["id"]
    first = overseas_label(row["id"], token)["label"]
    again = overseas_label(row["id"], token)["label"]
    assert first["regino"] == again["regino"] == created["tracking_no"]
    assert first["recipient"]["name"] == row["recipient_name"]
    html = overseas_label(row["id"], token, format="html")
    text = html.body.decode("utf-8")
    assert created["tracking_no"] in text
    assert "인쇄" in text
    cancel_overseas(row["id"], token, confirm=True)
    reprinted = overseas_label(row["id"], token)["label"]
    assert reprinted["status"] == "canceled"
    assert reprinted["regino"] == created["tracking_no"]


def test_ui_wires_recipient_picker_and_reprint_button():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    intake = (root / "frontend/src/app/overseas-shipping/page.tsx").read_text(encoding="utf-8")
    listing = (root / "frontend/src/app/overseas-shipping-list/page.tsx").read_text(encoding="utf-8")
    modal = (root / "frontend/src/components/OverseasRecipientPickerModal.tsx").read_text(encoding="utf-8")
    assert "OverseasRecipientPickerModal" in intake
    assert "applySaved(item)" in intake
    assert "setRecipientPickerOpen(true)" in intake
    assert 'href={`/overseas-print/${it.id}`}' in listing
    assert "출력서류" in listing
    assert "onSelect(a)" in modal
    assert "recipient_name" in modal


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
    assert label["sender"]["name"] == "Spring Fulfillment"
    assert label["recipient"]["name"] == "Hong Gildong"
    assert label["items"][0]["hs_code"] == "610910"
    assert label["customs_value_usd"] == 50.0
    assert "custno" not in label
    assert "apprno" not in json.dumps(label)
    assert "quickchart.io/barcode" in label["barcode_url"]

    html = overseas_label(created["id"], token, format="html")
    assert isinstance(html, HTMLResponse)
    text = html.body.decode("utf-8")
    assert "CN23" in text
    assert "1. CUSTOMS DECLARATION" in text
    assert "2. CUSTOMS DECLARATION" in text
    assert "6109109000" in text
    assert created["tracking_no"] in text
    assert "Clothing" in text

    pdf = overseas_label(created["id"], token, format="pdf")
    assert pdf.media_type == "application/pdf"
    import fitz

    form = fitz.open(stream=pdf.body, filetype="pdf")
    assert form.page_count == 3
    printed = "".join(page.get_text() for page in form)
    assert created["tracking_no"] in printed
    assert "Hong Gildong" in printed
    assert "6109109000" in printed
    assert "CN23" in printed
    assert "KOREA POST" in printed
    assert "Marie Renneberg" not in printed
    assert "EG053055332KR" not in printed
    assert "Stainless Steel Jewelry" not in printed

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


def test_label_pdf_lands_on_epost_answer_sheet():
    import fitz

    from backend.app.services.ems.form_pdf import render_label_pdf

    pdf = render_label_pdf(
        {
            "regino": "EG053055332KR",
            "posted_year": "2026",
            "posted_month": "10",
            "posted_day": "01",
            "posted_hour": "16",
            "posted_min": "11",
            "post_office_code": "70020",
            "post_office": "DONGDAEGU",
            "ems_fee": 37500,
            "totweight": 384,
            "volume_weight": 384,
            "boxlength": 18,
            "boxwidth": 16,
            "boxheight": 8,
            "contents_type": "parcel",
            "sender": {
                "name": "reindeer",
                "tel": "82-70-4191-8446",
                "address": "Daegu, Dong- gu, 1 Dongchon- ro 2F Parcel Room",
                "zip": "41142",
            },
            "recipient": {
                "name": "Marie Renneberg",
                "phone": "417-8480-9074",
                "addr3": "Kurvenstrasse 1 Zuerich Zurich",
                "zip": "8006",
                "country": "CH",
                "country_name": "Switzerland",
                "email": "mchrrenneberg1@aol.com",
            },
            "items": [{
                "name_en": "Stainless Steel Jewelry",
                "quantity": 1,
                "unit_price_usd": 20,
                "print_hs": "7117900000",
                "net_weight_g": "384",
                "origin_country": "KR",
            }],
        }
    )
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    found = {}
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                found.setdefault(span["text"].strip(), span["origin"])
    expected = {
        "EG053055332KR": (123.72, 82.08),
        "Marie Renneberg": (350.88, 170.28),
        "7117900000": (284.28, 351.24),
        "DONGDAEGU": (491.76, 398.88),
        "8006": (382.56, 303.84),
        "SWITZERLAND": (459.18, 302.76),
    }
    for text, origin in expected.items():
        assert text in found
        assert abs(found[text][0] - origin[0]) < 1.0
        assert abs(found[text][1] - origin[1]) < 1.0
    assert "KOREA POST" in page.get_text()
    assert "CN23" in page.get_text()


def _pdf_spans(pdf: bytes):
    import fitz

    doc = fitz.open(stream=pdf, filetype="pdf")
    found = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    found.append((span["text"], span["origin"], page.number))
    return doc, found


def _assert_span(found, text, origin, page=0):
    hits = [item for item in found if item[2] == page and item[0] == text]
    assert hits, text
    assert any(
        abs(hit[1][0] - origin[0]) < 1.0 and abs(hit[1][1] - origin[1]) < 1.0
        for hit in hits
    ), (text, [(hit[0], hit[1]) for hit in hits[:6]])


def test_premium_pdf_lands_on_epost_answer_sheet():
    from backend.app.services.ems.form_pdf import render_label_pdf

    pdf = render_label_pdf(
        {
            "shipping_method": "EMS_PREMIUM",
            "regino": "UP901002522KR",
            "posted_year": "2026",
            "posted_month": "10",
            "posted_day": "01",
            "posted_hour": "22",
            "posted_min": "34",
            "post_office_code": "70020",
            "post_office": "DONGDAEGU",
            "ems_fee": 109400,
            "totweight": 2000,
            "boxlength": 40,
            "boxwidth": 30,
            "boxheight": 20,
            "contents_type": "parcel",
            "sender": {
                "name": "Tillion",
                "tel": "+821027239490",
                "address": "1 Dongchon-ro 2F Parcel Room, Dong-gu, Daegu",
                "zip": "41142",
            },
            "recipient": {
                "name": "Alex Morgan",
                "phone": "+442087594321",
                "addr1": "England",
                "addr2": "Harmondsworth",
                "addr3": "Heathrow Airport, Colnbrook By-Pass",
                "zip": "UB7 0HJ",
                "country": "GB",
                "country_name": "United Kingdom",
                "email": "alex.morgan@example.com",
            },
            "items": [{
                "name_en": "Clothing",
                "quantity": 1,
                "unit_price_usd": 20,
                "print_hs": "6109109000",
                "net_weight_g": "2000",
                "origin_country": "KR",
            }],
        }
    )
    doc, found = _pdf_spans(pdf)
    assert doc.page_count == 2
    text = "".join(page.get_text() for page in doc)
    assert "CN23" in text
    assert "www.empspremium.co.kr" in text
    _assert_span(found, "UP901002522KR", (124.08, 82.08))
    _assert_span(found, "Alex Morgan", (350.88, 170.28))
    _assert_span(found, "6109109000", (284.28, 351.24))
    _assert_span(found, "DONGDAEGU", (491.76, 393.72))
    _assert_span(found, "UB7 0HJ", (373.56, 303.84))
    _assert_span(found, " UNITED KINGDOM", (459.18, 302.76))
    _assert_span(found, "4800 g", (420.36, 320.76))
    _assert_span(found, "4000 g", (420.36, 337.80))
    _assert_span(found, " 020- 8759- 4321", (343.27, 149.88))
    _assert_span(found, "40 * 30 * 20", (500.16, 340.08))
    assert "Marie Renneberg" not in text
    assert "EG053055332KR" not in text

    other = render_label_pdf(
        {
            "shipping_method": "EMS_PREMIUM",
            "regino": "UP000000001KR",
            "totweight": 500,
            "boxlength": 10,
            "boxwidth": 10,
            "boxheight": 10,
            "post_office": "SEOUL",
            "ems_fee": 1000,
            "sender": {"name": "Spring", "tel": "+821012341234", "address": "Seoul", "zip": "04524"},
            "recipient": {
                "name": "Jane Doe",
                "phone": "+442071112233",
                "addr3": "1 Main",
                "zip": "SW1A 1AA",
                "country": "GB",
                "country_name": "United Kingdom",
            },
            "items": [{
                "name_en": "Shoes",
                "quantity": 1,
                "unit_price_usd": 10,
                "print_hs": "6403990000",
                "net_weight_g": "500",
                "origin_country": "KR",
            }],
        }
    )
    other_text = "".join(page.get_text() for page in _pdf_spans(other)[0])
    assert "Alex Morgan" not in other_text
    assert "UP901002522KR" not in other_text
    assert "Jane Doe" in other_text


def test_kpacket_pdf_lands_on_epost_answer_sheet():
    import fitz

    from backend.app.services.ems.form_pdf import render_label_pdf

    pdf = render_label_pdf(
        {
            "shipping_method": "KPACKET",
            "order_no": "TIL-1790861691310",
            "regino": "LI086651482KR",
            "posted_year": "2026",
            "posted_month": "10",
            "posted_day": "01",
            "ems_fee": 44790,
            "totweight": 2000,
            "boxlength": 20,
            "boxwidth": 20,
            "boxheight": 20,
            "sender": {
                "name": "Tillion",
                "tel": "+821027239490",
                "address": "1 Dongchon-ro 2F Parcel Room, Dong-gu, Daegu",
                "zip": "41142",
            },
            "recipient": {
                "name": "Alex Morgan",
                "phone": "+442087594321",
                "addr1": "England",
                "addr2": "Harmondsworth",
                "addr3": "Heathrow Airport, Colnbrook By-Pass",
                "zip": "UB7 0HJ",
                "country": "GB",
                "country_name": "United Kingdom",
            },
            "items": [{
                "name_en": "Clothing",
                "quantity": 1,
                "unit_price_usd": 20,
                "print_hs": "6109109000",
                "net_weight_g": "2000",
                "origin_country": "KR",
            }],
        }
    )
    doc, found = _pdf_spans(pdf)
    assert doc.page_count == 1
    text = doc[0].get_text()
    assert "CN 22" in text
    assert "K- PACKET" in text
    assert "동대구" in text
    _assert_span(found, "LI086651482KR", (158.28, 182.40))
    _assert_span(found, "Alex Morgan", (69.60, 289.32))
    _assert_span(found, "Clothing", (316.20, 208.56))
    _assert_span(found, "6109109000", (464.04, 207.60))
    _assert_span(found, "UNITED KINGDOM", (74.64, 335.64))
    _assert_span(found, "volume 1333g", (176.76, 370.92))
    _assert_span(found, "2026.10.01.actual", (127.44, 357.12))
    _assert_span(found, "Tel: 82- 10- 2723- 9490", (105.60, 202.08))
    _assert_span(found, "Tel: 020- 8759- 4321", (97.20, 273.48))
    _assert_span(found, "ZIP: UB7 0HJ", (210.96, 273.48))
    _assert_span(found, "2000g", (212.52, 357.12))
    _assert_span(found, "44790", (247.08, 357.12))
    _assert_span(found, "GB", (287.28, 370.92))
    _assert_span(found, "20 * 20 * 20", (100.92, 374.28))
    _assert_span(found, "Heathrow Airport, Colnbrook By-Pass Harmondsworth", (69.60, 303.24))
    assert "원" in text
    # POST Exprès 로고 안쪽을 표 가로선이 가로지르지 않는다.
    shield = doc[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(80, 135.6, 120, 137.2), alpha=False)
    dark = sum(
        1
        for i in range(0, len(shield.samples), 3)
        if shield.samples[i] < 60 and shield.samples[i + 1] < 60 and shield.samples[i + 2] < 60
    )
    assert dark == 0
    letter = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(100, 137.8, 102, 138.3), alpha=False)
    assert min(letter.samples[:3]) > 240
    # 트랙킹 바코드 막대가 답안지처럼 좌우로 칸을 채운다.
    band = doc[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(100, 156, 275, 166), alpha=False)
    dark_x = [
        x
        for y in range(band.height)
        for x in range(band.width)
        if band.samples[(y * band.width + x) * 3] < 80
    ]
    assert dark_x
    left = 100 + min(dark_x) / 4
    right = 100 + max(dark_x) / 4
    assert left < 114 and right > 258, (left, right)

    other = render_label_pdf(
        {
            "shipping_method": "KPACKET",
            "order_no": "TIL-1",
            "regino": "LK000000001KR",
            "posted_year": "2026",
            "posted_month": "10",
            "posted_day": "02",
            "ems_fee": 1000,
            "totweight": 500,
            "boxlength": 10,
            "boxwidth": 10,
            "boxheight": 10,
            "sender": {"name": "Spring", "tel": "+821012341234", "address": "Seoul", "zip": "04524"},
            "recipient": {
                "name": "Jane Doe",
                "phone": "+442071112233",
                "addr1": "London",
                "addr3": "1 Main",
                "zip": "SW1A 1AA",
                "country": "GB",
                "country_name": "United Kingdom",
            },
            "items": [{
                "name_en": "Shoes",
                "quantity": 1,
                "unit_price_usd": 10,
                "print_hs": "6403990000",
                "net_weight_g": "500",
                "origin_country": "KR",
            }],
        }
    )
    other_text = _pdf_spans(other)[0][0].get_text()
    assert "Alex Morgan" not in other_text
    assert "LI086651482KR" not in other_text
    assert "Jane Doe" in other_text
    assert "CN 22" in other_text


def _thin_rule_runs(page, clip):
    """6배 확대에서 표 선 한 줄의 픽셀 두께. 겹친 두 줄이면 더 두껍다."""
    import fitz

    pix = page.get_pixmap(matrix=fitz.Matrix(6, 6), clip=fitz.Rect(*clip), alpha=False)
    x = pix.width // 2
    runs = []
    run = 0
    for y in range(pix.height):
        index = (y * pix.width + x) * pix.n
        if pix.samples[index] < 90:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    return [value for value in runs if value >= 2]


def test_each_shipping_method_prints_its_own_form():
    import fitz

    from backend.app.services.ems.form_pdf import render_label_pdf

    base = {
        "order_no": "TIL-1",
        "regino": "TEST000000KR",
        "post_office": "SEOUL",
        "ems_fee": 1000,
        "totweight": 500,
        "boxlength": 10,
        "boxwidth": 10,
        "boxheight": 10,
        "posted_year": "2026",
        "posted_month": "10",
        "posted_day": "01",
        "sender": {"name": "Spring", "tel": "+821012341234", "address": "Seoul", "zip": "04524"},
        "recipient": {
            "name": "Jane Doe",
            "phone": "+819012341234",
            "addr3": "1 Main",
            "zip": "100-0001",
            "country": "JP",
            "country_name": "Japan",
        },
        "items": [{
            "name_en": "Shoes",
            "quantity": 1,
            "unit_price_usd": 10,
            "print_hs": "6403990000",
            "net_weight_g": "500",
            "origin_country": "KR",
        }],
    }
    expected = {
        "EMS": {"pages": 3, "has": ("CN23", "KOREA POST"), "lacks": ("www.empspremium.co.kr", "K- PACKET", "CN 22")},
        "EMS_PREMIUM": {"pages": 2, "has": ("CN23", "www.empspremium.co.kr"), "lacks": ("K- PACKET", "CN 22")},
        "KPACKET": {"pages": 1, "has": ("CN 22", "K- PACKET"), "lacks": ("CN23", "www.empspremium.co.kr")},
    }
    for method, check in expected.items():
        pdf = render_label_pdf({**base, "shipping_method": method})
        doc = fitz.open(stream=pdf, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        assert doc.page_count == check["pages"], method
        for marker in check["has"]:
            assert marker in text, (method, marker)
        for marker in check["lacks"]:
            assert marker not in text, (method, marker)
        runs = _thin_rule_runs(doc[0], (80, 136, 200, 142))
        assert runs, method
        assert max(runs) <= 6, (method, runs)
        if method == "KPACKET":
            logo = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(100, 130, 100.5, 130.5), alpha=False)
            red, green, blue = logo.samples[:3]
            assert red > 180 and green < 80, (red, green, blue)


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


def test_sender_mobile_and_contract_approval_numbers(monkeypatch):
    parts = sender_mobile_parts({"tel1": "82", "tel2": "10", "tel3": "2723", "tel4": "9490"})
    assert parts == {
        "sendermobile1": "82",
        "sendermobile2": "10",
        "sendermobile3": "2723",
        "sendermobile4": "9490",
    }
    plain = build_ems_params(parts)
    assert "sendermobile1=82" in plain
    assert "sendermobile=010" not in plain
    assert epost_sender_name("틸리언") == "Tillion"
    assert epost_sender_name("Tillion") == "Tillion"
    recipient = split_recipient_tel("+442087594321", "GB")
    assert recipient["receivetelno1"] == "44"
    assert recipient["receivetelno2"] == "2087"
    assert format_recipient_tel("+442087594321", "GB") == "020-8759-4321"
    assert format_recipient_tel("+819012345678", "JP") == "090-1234-5678"
    assert "+" not in format_recipient_tel("+442087594321", "GB")
    monkeypatch.setenv("EMS_APPROVAL_NO", "70020C0247")
    monkeypatch.setenv("EMS_KPACKET_APPROVAL_NO", "70020J0048")
    assert approval_no_for("31") == "70020C0247"
    assert approval_no_for("32") == "70020C0247"
    assert approval_no_for("14") == "70020J0048"


def test_shipment_detail_keeps_product_name_apart_from_hs_item(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(
        _req(
            confirm=True,
            test_mode=True,
            items=[{
                "product_name": "PDRN 틴티드 립 앰플 새틴",
                "name_en": "Lip cosmetics",
                "quantity": 3,
                "unit_price_usd": 12,
                "hs_code": "330410",
                "origin_country": "KR",
            }],
        ),
        token,
    )
    detail = get_overseas(created["id"], token)
    assert detail["items"][0]["product_name"] == "PDRN 틴티드 립 앰플 새틴"
    assert detail["items"][0]["name_en"] == "Lip cosmetics"
    assert detail["items"][0]["quantity"] == 3
    assert detail["recipient_name"] == "Hong Gildong"
    assert detail["sender_name"]
    params = json.loads(
        sqlite3.connect(isolated_runtime["db"]).execute(
            "SELECT apply_snapshot FROM overseas_shipping_requests WHERE id=?",
            (created["id"],),
        ).fetchone()[0]
    )
    assert params["contents"] == "Lip cosmetics"
    assert "PDRN" not in params["contents"]


def test_list_shows_ddp_and_only_admin_can_delete(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(
        _req(
            confirm=True,
            countrycd="GB",
            receivename="Alex Morgan",
            receivetelno="+442087594321",
            receivezipcode="UB7 0HJ",
            receiveaddr1="England",
            receiveaddr2="West Drayton",
            receiveaddr3="1 Test Road",
        ),
        token,
    )
    row = list_overseas(token)["items"][0]
    assert row["ddp_krw"] > 0
    assert row["spent_total"] == int(float(row["ems_fee"])) + row["ddp_krw"]
    detail = get_overseas(created["id"], token)
    assert detail["ddp_krw"] == row["ddp_krw"]
    assert detail["spent_total"] == row["spent_total"]
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("UPDATE overseas_shipping_requests SET ddp_krw=NULL WHERE id=?", (created["id"],))
        con.commit()
    recomputed = list_overseas(token)["items"][0]
    assert recomputed["ddp_krw"] == row["ddp_krw"]
    assert recomputed["spent_total"] == row["spent_total"]
    try:
        delete_overseas(created["id"], token)
        raise AssertionError("staff cannot delete")
    except HTTPException as exc:
        assert exc.status_code == 403
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("UPDATE users SET is_admin=1 WHERE user_id=1")
        con.commit()
    deleted = delete_overseas(created["id"], token)
    assert deleted["success"] is True
    assert list_overseas(token)["items"] == []
    try:
        get_overseas(created["id"], token)
        raise AssertionError("deleted shipment stays gone")
    except HTTPException as exc:
        assert exc.status_code == 404
