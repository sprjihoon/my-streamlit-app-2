"""해외배송 주문 엑셀을 접수 1건으로 바꾸는 테스트."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.ems.order_excel import (
    englishize_uploaded_addresses,
    order_excel_template_bytes,
    parse_order_workbook,
)

SAMPLE = Path(r"c:\Users\one\Downloads\NAVER WORKS\해외배송 예시.xls")

HEADERS = [
    "관리번호",
    "합포번호",
    "주문번호",
    "실제 상품명",
    "판매개수",
    "구매자결제금액",
    "배송지우편번호",
    "배송지주소",
    "수령자",
    "수령자전화",
    "수령자전화2",
    "메모",
    "중량",
    "원산지",
]


def _html_table(rows: list[list[str]]) -> bytes:
    def cell(value: str) -> str:
        return f"<td>{value}</td>"

    body = ["<tr>" + "".join(cell(name) for name in HEADERS) + "</tr>"]
    for row in rows:
        padded = row + [""] * (len(HEADERS) - len(row))
        body.append("<tr>" + "".join(cell(value) for value in padded) + "</tr>")
    html = (
        "<meta http-equiv='Content-Type' content='text/html; charset=utf-8'>"
        "<html xmlns:x=\"urn:schemas-microsoft-com:office:excel\">"
        "<body><table border=1>"
        + "".join(body)
        + "</table></body></html>"
    )
    return html.encode("utf-8")


def _malaysia_row(name: str, origin: str, weight: str) -> list[str]:
    return [
        "854743",
        "854743",
        "20260911801",
        name,
        "1",
        "0",
        "",
        "8, Jalan Ekoperniagaan 1/5, Taman Ekoperniagaan, 81100 Johor Bahru, Johor, Malaysia",
        "Xie Yu Zheng (Thoroughfare Group Sdn Bhd)",
        "+601154062583",
        "+601154062583",
        "말레이시아 샘플",
        weight,
        origin,
    ]


def test_html_xls_fills_one_shipment_and_leaves_gaps():
    raw = _html_table([
        _malaysia_row("PDRN 틴티드 립 앰플 새틴", "충청남도 천안시", "0.02"),
        _malaysia_row("PDRN 틴티드 립 앰플 자나", "국내", "1"),
        _malaysia_row("CCF 로즈 밀크 에센스 프렙", "", "0"),
    ])
    groups = parse_order_workbook(raw, filename="해외배송 예시.xls")
    assert len(groups) == 1
    group = groups[0]
    assert group["bundle_no"] == "854743"
    assert group["receivename"] == "Xie Yu Zheng (Thoroughfare Group Sdn Bhd)"
    assert group["receivetelno"] == "+601154062583"
    assert group["receivemail"] == ""
    assert group["countrycd"] == "MY"
    assert group["receivezipcode"] == "81100"
    assert group["receiveaddr1"] == "Johor"
    assert group["receiveaddr2"] == "Johor Bahru"
    assert group["receiveaddr3"] == "8, Jalan Ekoperniagaan 1/5, Taman Ekoperniagaan"
    assert group["notes"] == "말레이시아 샘플"
    assert group["totweight"] == 0
    assert group["boxlength"] == 0
    assert [item["product_name"] for item in group["items"]] == [
        "PDRN 틴티드 립 앰플 새틴",
        "PDRN 틴티드 립 앰플 자나",
        "CCF 로즈 밀크 에센스 프렙",
    ]
    assert all(item["name_en"] == "" for item in group["items"])
    assert group["items"][0]["quantity"] == 1
    assert group["items"][0]["unit_price_usd"] == 0
    assert group["items"][0]["hs_code"] == ""
    assert group["items"][0]["origin_country"] == "KR"
    assert group["items"][1]["origin_country"] == "KR"
    assert group["items"][2]["origin_country"] == ""
    missing = set(group["missing"])
    assert "이메일" in missing
    assert "총중량(g)" in missing
    assert "가로(cm)" in missing
    assert "단가 USD" in missing
    assert "HS 품목" in missing
    assert "HS코드" in missing
    assert "원산지" in missing
    assert "국가" not in missing
    assert "우편번호" not in missing


def test_management_number_stays_separate_from_bundle():
    same = _malaysia_row("Lip Tint", "국내", "0")
    same[0] = "M-1"
    same[1] = "100001"
    other_item = _malaysia_row("Lip Gloss", "국내", "0")
    other_item[0] = "M-2"
    other_item[1] = "100001"
    solo_a = _malaysia_row("Serum", "국내", "0")
    solo_a[0] = "M-9"
    solo_a[1] = ""
    solo_b = list(solo_a)
    solo_b[0] = "M-8"
    solo_b[3] = "Toner"
    raw = _html_table([same, other_item, solo_a, solo_b])
    groups = parse_order_workbook(raw, filename="orders.xls")
    assert [group["bundle_no"] for group in groups] == ["100001", "", ""]
    assert groups[0]["management_no"] == "M-1, M-2"
    assert [item["product_name"] for item in groups[0]["items"]] == ["Lip Tint", "Lip Gloss"]
    assert {groups[1]["management_no"], groups[2]["management_no"]} == {"M-9", "M-8"}
    assert all(len(group["items"]) == 1 for group in groups[1:])


def test_two_bundle_numbers_stay_two_shipments():
    second = _malaysia_row("Lip Tint", "KR", "0")
    second[0] = "900001"
    second[1] = "900001"
    second[7] = "1-2-3 Dogenzaka, Shibuya-ku, Tokyo, Japan"
    second[8] = "Taro Yamada"
    second[9] = "+819012345678"
    second[11] = ""
    raw = _html_table([
        _malaysia_row("PDRN 틴티드 립 앰플 새틴", "국내", "0"),
        second,
    ])
    groups = parse_order_workbook(raw, filename="orders.xls")
    assert [group["bundle_no"] for group in groups] == ["854743", "900001"]
    assert groups[1]["countrycd"] == "JP"
    assert groups[1]["receivename"] == "Taro Yamada"
    assert groups[1]["receivezipcode"] == ""
    assert "우편번호" in groups[1]["missing"]


def test_xlsx_upload_endpoint(isolated_runtime):
    import openpyxl

    token = _seed(isolated_runtime["db"])
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    sheet.append(_malaysia_row("Lip Ampoule", "국내", "0"))
    buffer = BytesIO()
    book.save(buffer)
    client = TestClient(app, raise_server_exceptions=False)
    denied = client.post(
        "/overseas-shipping/import-excel",
        files={"file": ("order.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert denied.status_code in {401, 422}
    response = client.post(
        "/overseas-shipping/import-excel",
        params={"token": token},
        files={"file": ("order.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    groups = response.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["countrycd"] == "MY"
    assert groups[0]["items"][0]["product_name"] == "Lip Ampoule"
    assert groups[0]["items"][0]["name_en"] == ""
    assert groups[0]["items"][0]["unit_price_usd"] == 0


def test_excel_template_downloads_and_parses_two_shipments(isolated_runtime):
    raw = order_excel_template_bytes()
    groups = parse_order_workbook(raw, filename="overseas-order-template.xlsx")
    assert [group["bundle_no"] for group in groups] == ["100001", "100002"]
    assert groups[0]["management_no"] == "M-100001"
    assert groups[1]["management_no"] == "M-100002"
    assert [item["product_name"] for item in groups[0]["items"]] == ["립틴트", "립글로스"]
    assert groups[0]["countrycd"] == "JP"
    assert groups[1]["countrycd"] == "MY"
    token = _seed(isolated_runtime["db"])
    client = TestClient(app, raise_server_exceptions=False)
    denied = client.get("/overseas-shipping/import-excel/template")
    assert denied.status_code in {401, 422}
    response = client.get("/overseas-shipping/import-excel/template", params={"token": token})
    assert response.status_code == 200, response.text
    assert "spreadsheetml" in response.headers["content-type"]
    assert response.content[:2] == b"PK"
    downloaded = parse_order_workbook(response.content, filename="overseas-order-template.xlsx")
    assert len(downloaded) == 2


def _japanese_row() -> list[str]:
    row = _malaysia_row("Lip Tint", "국내", "0")
    row[6] = ""
    row[7] = "東京都渋谷区渋谷1-1-1, 日本"
    row[8] = "ヤマダタロウ"
    row[9] = "+819012345678"
    row[11] = ""
    return row


def test_japanese_upload_prefers_google_verified_english_address(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.ems.google_address.google_maps_api_key",
        lambda *_args, **_kwargs: "test-key",
    )

    def fake_validate(api_key, addr, timeout=8):
        assert api_key == "test-key"
        assert addr["countryCode"] == "JP"
        assert "渋谷" in addr["addr3"]
        return {
            "ok": True,
            "suggested": {
                "suggestedAddr1": "Tokyo",
                "suggestedAddr2": "Shibuya",
                "suggestedAddr3": "1-1-1 Shibuya",
                "suggestedZip": "150-0001",
            },
        }

    monkeypatch.setattr(
        "backend.app.services.ems.google_address.validate_address_with_google",
        fake_validate,
    )
    groups = englishize_uploaded_addresses(parse_order_workbook(_html_table([_japanese_row()]), filename="jp.xls"))
    group = groups[0]
    assert group["countrycd"] == "JP"
    assert group["address_english"] == "google"
    assert group["receiveaddr1"] == "Tokyo"
    assert group["receiveaddr2"] == "Shibuya"
    assert group["receiveaddr3"] == "1-1-1 Shibuya"
    assert group["receivezipcode"] == "150-0001"
    assert group["receivename"] == "ヤマダタロウ"
    assert "우편번호" not in group["missing"]


def test_japanese_upload_romanizes_when_google_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.ems.google_address.google_maps_api_key",
        lambda *_args, **_kwargs: "",
    )
    groups = englishize_uploaded_addresses(parse_order_workbook(_html_table([_japanese_row()]), filename="jp.xls"))
    group = groups[0]
    assert group["countrycd"] == "JP"
    assert group["address_english"] == "romanized"
    assert "渋" not in group["receiveaddr3"]
    assert "1-1-1" in group["receiveaddr3"]
    assert group["receivename"] == "ヤマダタロウ"


def test_english_upload_keeps_the_parsed_address(monkeypatch):
    def fail_validate(*_args, **_kwargs):
        raise AssertionError("영문 주소는 구글 검증을 호출하지 않는다")

    monkeypatch.setattr(
        "backend.app.services.ems.google_address.validate_address_with_google",
        fail_validate,
    )
    groups = englishize_uploaded_addresses(parse_order_workbook(
        _html_table([_malaysia_row("Lip Tint", "국내", "0")]),
        filename="my.xls",
    ))
    assert groups[0]["address_english"] == ""
    assert groups[0]["receiveaddr1"] == "Johor"
    assert groups[0]["countrycd"] == "MY"


def test_china_upload_uses_map_english_address(monkeypatch):
    def fake_review(**_kwargs):
        return {
            "suggested_addr1": "Beijing",
            "suggested_addr2": "Chaoyang",
            "suggested_addr3": "1 Jianguo Road",
            "zipcode": "100020",
        }

    monkeypatch.setattr(
        "backend.app.services.ems.china_address.review_china_address",
        fake_review,
    )
    row = _malaysia_row("Lip Tint", "국내", "0")
    row[6] = "100020"
    row[7] = "建国路1号, 朝阳区, 北京市, 中国"
    row[9] = "+8613800138000"
    groups = englishize_uploaded_addresses(parse_order_workbook(_html_table([row]), filename="cn.xls"))
    group = groups[0]
    assert group["countrycd"] == "CN"
    assert group["address_english"] == "google"
    assert group["receiveaddr1"] == "Beijing"
    assert group["receiveaddr2"] == "Chaoyang"
    assert group["receiveaddr3"] == "1 Jianguo Road"
    assert group["receivezipcode"] == "100020"


def test_sample_workbook_is_one_shipment():
    if not SAMPLE.exists():
        return
    groups = parse_order_workbook(SAMPLE.read_bytes(), filename=SAMPLE.name)
    assert len(groups) == 1
    group = groups[0]
    assert group["bundle_no"] == "854743"
    assert group["countrycd"] == "MY"
    assert group["receivezipcode"] == "81100"
    assert group["receiveaddr1"] == "Johor"
    assert group["receiveaddr2"] == "Johor Bahru"
    assert len(group["items"]) == 21
    assert group["items"][0]["product_name"] == "PDRN 틴티드 립 앰플 새틴"
    assert all(item["name_en"] == "" for item in group["items"])
    assert all(item["quantity"] == 1 for item in group["items"])
    assert all(item["unit_price_usd"] == 0 for item in group["items"])
    assert all(not item["hs_code"] for item in group["items"])
    assert group["totweight"] == 0


def _seed(db_path, token="tok-excel"):
    import sqlite3

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
