"""해외배송 접수 화면과 같은 순서의 전체 접수 테스트."""

from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.ems.google_address import (
    google_maps_api_key,
    parse_place_result,
    supports_address_validation,
    validate_address_with_google,
)
from backend.app.services.ems.item_categories import suggest_item_categories


def _seed_user(db_path, token="tok-intake"):
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


def _payload(**overrides):
    data = {
        "shipping_method": "EMS",
        "countrycd": "JP",
        "sender_name": "스프링풀필먼트",
        "receivename": "Taro Yamada",
        "receivetelno": "+819088800111",
        "receivemail": "taro@example.com",
        "receivezipcode": "150-0001",
        "receiveaddr1": "Tokyo",
        "receiveaddr2": "Shibuya",
        "receiveaddr3": "Jingumae-1",
        "totweight": 500,
        "boxlength": 30,
        "boxwidth": 25,
        "boxheight": 15,
        "items": [
            {
                "name_en": "Clothing - Top",
                "quantity": 2,
                "unit_price_usd": 25,
                "hs_code": "610910",
                "origin_country": "KR",
            }
        ],
        "notes": "intake-flow",
        "confirm": False,
        "test_mode": True,
        "save_address": False,
        "save_address_label": "",
        "save_address_default": False,
    }
    data.update(overrides)
    return data


def test_staff_intake_flow_matches_overseas_shipping_page(isolated_runtime):
    token = _seed_user(isolated_runtime["db"])
    client = TestClient(app, raise_server_exceptions=False)

    denied = client.get("/overseas-shipping/meta")
    assert denied.status_code in {401, 422}

    bad = client.get("/overseas-shipping/meta", params={"token": "nope"})
    assert bad.status_code == 401

    # 1) 화면 진입: meta + 국가 + 주소록
    meta = client.get("/overseas-shipping/meta", params={"token": token})
    assert meta.status_code == 200
    body = meta.json()
    assert body["live_ready"] is False
    assert body["sender"]["name"] == "스프링풀필먼트"
    assert {m["code"] for m in body["methods"]} == {"EMS", "EMS_PREMIUM", "KPACKET"}
    assert any(c["hs_code"] == "610910" for c in body["item_categories"])

    nations = client.get("/overseas-shipping/nations", params={"token": token, "premiumcd": "31"})
    assert nations.status_code == 200
    assert any(n["nationcd"] == "JP" for n in nations.json()["items"])

    saved = client.get("/overseas-shipping/saved-addresses", params={"token": token})
    assert saved.status_code == 200
    assert saved.json()["items"] == []

    # 2) 배송방법 변경 시 국가 재조회 (화면 changeMethod)
    kpacket_nations = client.get("/overseas-shipping/nations", params={"token": token, "premiumcd": "14"})
    assert kpacket_nations.status_code == 200
    assert kpacket_nations.json()["fallback"] is True
    ems_codes = {n["nationcd"] for n in nations.json()["items"]}
    kpacket_codes = {n["nationcd"] for n in kpacket_nations.json()["items"]}
    assert len(kpacket_codes) < len(ems_codes)
    assert kpacket_codes.issubset(ems_codes)

    quote = client.get(
        "/overseas-shipping/quote",
        params={
            "token": token,
            "shipping_method": "EMS",
            "countrycd": "JP",
            "totweight": 500,
            "boxlength": 30,
            "boxwidth": 25,
            "boxheight": 15,
        },
    )
    assert quote.status_code == 200
    assert quote.json()["ok"] is True
    assert quote.json()["totalFee"] > 0

    # 3) HS코드 완성 (화면 품목 검색)
    hs = client.get("/overseas-shipping/item-categories", params={"token": token, "q": "610910"})
    assert hs.status_code == 200
    picked = hs.json()["items"][0]
    assert picked["hs_code"] == "610910"
    assert picked["name_en"]
    assert suggest_item_categories("의류")[0]["hs_code"]

    # 4) 구글 주소 자동완성 파싱 + Address Validation (화면 blur)
    parsed = parse_place_result(
        {
            "address_components": [
                {"long_name": "1", "short_name": "1", "types": ["street_number"]},
                {"long_name": "Jingumae", "short_name": "Jingumae", "types": ["sublocality_level_2"]},
                {"long_name": "Shibuya", "short_name": "Shibuya", "types": ["sublocality_level_1"]},
                {"long_name": "Tokyo", "short_name": "Tokyo", "types": ["administrative_area_level_1"]},
                {"long_name": "150-0001", "short_name": "150-0001", "types": ["postal_code"]},
            ]
        },
        "JP",
    )
    assert supports_address_validation("JP") is True
    gmaps_key = google_maps_api_key()
    assert gmaps_key, "Google Maps key required for intake address step"
    validated_addr = validate_address_with_google(
        gmaps_key,
        {
            "addr3": parsed["addr3"],
            "addr2": parsed["addr2"],
            "addr1": parsed["addr1"],
            "zip": parsed["zip"],
            "countryCode": "JP",
        },
    )
    assert validated_addr and validated_addr.get("ok") is True
    suggested = validated_addr["suggested"]
    addr3 = suggested["suggestedAddr3"] or parsed["addr3"]
    addr2 = suggested["suggestedAddr2"] or parsed["addr2"]
    addr1 = suggested["suggestedAddr1"] or parsed["addr1"]
    zipcode = suggested["suggestedZip"] or parsed["zip"]

    payload = _payload(
        sender_name="Spring Shop JP",
        receivename="Taro Yamada",
        receiveaddr1=addr1,
        receiveaddr2=addr2,
        receiveaddr3=addr3,
        receivezipcode=zipcode,
        items=[{
            "name_en": picked["name_en"],
            "quantity": 2,
            "unit_price_usd": 25,
            "hs_code": picked["hs_code"],
            "origin_country": "KR",
        }],
        save_address=True,
        save_address_label="시부야기본",
        save_address_default=True,
    )

    # 5) 미리보기: 확인 전 쓰기 금지
    preview = client.post("/overseas-shipping/preview", params={"token": token}, json=payload)
    assert preview.status_code == 200
    preview_body = preview.json()["preview"]
    assert preview_body["sender_name"] == "Spring Shop JP"
    assert preview_body["recipient_name"] == "Taro Yamada"
    assert preview_body["countrycd"] == "JP"
    assert preview_body["is_test"] is True
    listed_before = client.get("/overseas-shipping", params={"token": token})
    assert listed_before.status_code == 200
    assert listed_before.json()["items"] == []

    # 6) 확인 없이 접수는 거부
    no_confirm = client.post("/overseas-shipping", params={"token": token}, json=payload)
    assert no_confirm.status_code == 400

    # 7) 확인 후 테스트 접수
    created = client.post(
        "/overseas-shipping",
        params={"token": token},
        json={**payload, "confirm": True},
    )
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["success"] is True
    assert created_body["is_test"] is True
    assert created_body["tracking_no"].startswith("EG")
    assert created_body["preview"]["sender_name"] == "Spring Shop JP"

    listed = client.get("/overseas-shipping", params={"token": token})
    items = listed.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["status"] == "requested"
    assert row["sender_name"] == "Spring Shop JP"
    assert row["recipient_name"] == "Taro Yamada"
    assert row["items"][0]["hs_code"] == "610910"
    assert row["tracking_no"] == created_body["tracking_no"]

    with sqlite3.connect(isolated_runtime["db"]) as con:
        snap = json.loads(
            con.execute(
                "SELECT apply_snapshot FROM overseas_shipping_requests WHERE id=?",
                (row["id"],),
            ).fetchone()[0]
        )
    assert "custno" not in snap
    assert "apprno" not in snap
    assert snap["sender"] == "Spring Shop JP"

    label_json = client.get(f"/overseas-shipping/{row['id']}/label", params={"token": token})
    assert label_json.status_code == 200
    label = label_json.json()["label"]
    assert label["source"] == "internal"
    assert label["regino"] == created_body["tracking_no"]
    assert label["sender"]["name"] == "Spring Shop JP"
    assert "CN22" in client.get(
        f"/overseas-shipping/{row['id']}/label",
        params={"token": token, "format": "html"},
    ).text

    book = client.get("/overseas-shipping/saved-addresses", params={"token": token})
    assert book.json()["items"][0]["label"] == "시부야기본"
    assert book.json()["items"][0]["is_default"] is True

    saved_hs = client.get("/overseas-shipping/saved-hs", params={"token": token, "q": "610910"})
    assert saved_hs.status_code == 200
    assert any(row["hs_code"] == "610910" for row in saved_hs.json()["items"])
    reused = client.get("/overseas-shipping/item-categories", params={"token": token, "q": "610910"})
    assert reused.json()["items"][0]["hs_code"] == "610910"

    # 8) 같은 날 같은 수취인 중복 가드
    again = client.post(
        "/overseas-shipping",
        params={"token": token},
        json={**payload, "confirm": True},
    )
    assert again.status_code == 200
    assert again.json().get("duplicate_guard") is True
    assert len(client.get("/overseas-shipping", params={"token": token}).json()["items"]) == 1

    # 9) 목록 취소: 확인 전 거부, 확인 후 취소
    shipment_id = row["id"]
    cancel_denied = client.post(
        f"/overseas-shipping/{shipment_id}/cancel",
        params={"token": token, "confirm": False},
    )
    assert cancel_denied.status_code == 400
    canceled = client.post(
        f"/overseas-shipping/{shipment_id}/cancel",
        params={"token": token, "confirm": True},
    )
    assert canceled.status_code == 200
    assert client.get("/overseas-shipping", params={"token": token}).json()["items"][0]["status"] == "canceled"


def test_intake_flow_rejects_invalid_form_before_write(isolated_runtime):
    token = _seed_user(isolated_runtime["db"], token="tok-guard")
    client = TestClient(app, raise_server_exceptions=False)

    overweight = client.post(
        "/overseas-shipping/preview",
        params={"token": token},
        json=_payload(shipping_method="KPACKET", totweight=2500, receivetelno="+819088800222"),
    )
    assert overweight.status_code == 400
    assert "중량" in overweight.json()["detail"]

    missing_addr = client.post(
        "/overseas-shipping/preview",
        params={"token": token},
        json=_payload(receiveaddr3="", receivetelno="+819088800223"),
    )
    assert missing_addr.status_code == 400

    email_name = client.post(
        "/overseas-shipping/preview",
        params={"token": token},
        json=_payload(receivename="user@example.com", receivetelno="+819088800224"),
    )
    assert email_name.status_code == 400

    assert client.get("/overseas-shipping", params={"token": token}).json()["items"] == []
