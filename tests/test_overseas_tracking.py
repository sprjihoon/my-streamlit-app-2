from __future__ import annotations

import sqlite3

from backend.app.api.overseas_shipping import (
    OverseasSubmitRequest,
    create_overseas,
    list_overseas,
    refresh_overseas_statuses,
)
from backend.app.services.ems.tracking import canonicalize_ems_status, parse_ems_trace_html


def _seed_user(db_path, token="tok-overseas-track"):
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
                "quantity": 1,
                "unit_price_usd": 20,
                "hs_code": "610910",
                "origin_country": "KR",
            }
        ],
        "notes": "",
        "confirm": True,
        "test_mode": True,
    }
    data.update(overrides)
    return OverseasSubmitRequest(**data)


def _live(db_path: str, shipment_id: int, **fields: str) -> None:
    sets = ", ".join(f"{key}=?" for key in fields)
    with sqlite3.connect(db_path) as con:
        con.execute(
            f"UPDATE overseas_shipping_requests SET is_test=0, {sets} WHERE id=?",
            (*fields.values(), shipment_id),
        )
        con.commit()


def test_parse_uses_latest_event_not_page_chrome():
    html = """
    <script>if( type == 1 ) { // 배달완료 }</script>
    <table>
      <tr><th>처리일시</th><th>처리현황</th><th>우체국</th><th>상세설명</th></tr>
      <tr><td>2026.01.12 16:41</td><td>&nbsp;접수</td><td>IN400099</td><td>접수</td></tr>
      <tr><td>2026.01.13 13:33</td><td>&nbsp;발송교환국에도착</td><td>INBOMA</td><td></td></tr>
      <tr><td>2026.01.21 10:14</td><td>&nbsp;배달완료</td><td>제주우편집중국</td><td>수령인</td></tr>
    </table>
    """
    parsed = parse_ems_trace_html(html)
    assert parsed["treatStusCd"] == "배달완료"
    assert parsed["treatStusNm"] == "배달완료"
    assert parsed["eventAt"] == "2026.01.21 10:14"
    assert parsed["office"] == "제주우편집중국"


def test_empty_trace_is_not_delivered():
    html = "<p>현재 고객님이 신청하신 접수번호에 대하여 배달정보를 찾지 못했습니다.</p>"
    assert parse_ems_trace_html(html) == {"noRecord": "1"}
    assert canonicalize_ems_status("발송준비") == "발송준비"
    assert canonicalize_ems_status("발송교환국에도착") == "운송중"
    assert canonicalize_ems_status("교환국 도착") == "운송중"
    assert canonicalize_ems_status("통관검사중") == "통관중"


def test_refresh_status_saves_latest_event_and_skips_terminal(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    moving = create_overseas(_req(receivename="Moving Kim"), token)
    done = create_overseas(_req(receivename="Done Lee", receivetelno="+819011122233"), token)
    test_row = create_overseas(_req(receivename="Test Park", receivetelno="+819044455566"), token)
    _live(isolated_runtime["db"], moving["id"], tracking_no="EG123456789KR", treat_status="접수")
    _live(
        isolated_runtime["db"],
        done["id"],
        tracking_no="EG987654321KR",
        treat_status="배달완료",
        treat_status_name="배달완료",
    )
    calls: list[str] = []

    def fake_track(regino: str):
        calls.append(regino)
        if regino == "EG123456789KR":
            return {
                "treatStusCd": "운송중",
                "treatStusNm": "교환국 도착",
                "eventAt": "2026.10.08 09:10",
                "office": "국제우편물류센터",
                "regiNo": regino,
            }
        return {"treatStusCd": "배달완료", "treatStusNm": "배달완료", "regiNo": regino}

    monkeypatch.setattr("backend.app.api.overseas_shipping.track_ems_regino", fake_track)
    result = refresh_overseas_statuses(token)
    assert calls == ["EG123456789KR"]
    assert result["checked"] == 1
    assert result["delivered"] == 0
    assert result["failed"] == 0
    items = {row["id"]: row for row in list_overseas(token)["items"]}
    assert items[moving["id"]]["treat_status"] == "운송중"
    assert items[moving["id"]]["treat_status_name"] == "교환국 도착"
    assert items[moving["id"]]["treat_event_at"] == "2026.10.08 09:10"
    assert items[moving["id"]]["treat_office"] == "국제우편물류센터"
    assert items[done["id"]]["treat_status"] == "배달완료"
    assert items[test_row["id"]]["is_test"] is True
    assert items[test_row["id"]]["treat_status"] in (None, "")


def test_refresh_counts_new_delivery_and_keeps_status_when_trace_empty(isolated_runtime, monkeypatch):
    token = _seed_user(isolated_runtime["db"])
    created = create_overseas(_req(), token)
    _live(isolated_runtime["db"], created["id"], tracking_no="LK123456789KR", treat_status="발송")

    monkeypatch.setattr(
        "backend.app.api.overseas_shipping.track_ems_regino",
        lambda regino: {"noRecord": "1", "regiNo": regino},
    )
    quiet = refresh_overseas_statuses(token)
    assert quiet["checked"] == 1
    assert quiet["delivered"] == 0
    assert list_overseas(token)["items"][0]["treat_status"] == "발송"

    monkeypatch.setattr(
        "backend.app.api.overseas_shipping.track_ems_regino",
        lambda regino: {
            "treatStusCd": "배달완료",
            "treatStusNm": "배달완료",
            "eventAt": "2026.10.08 18:00",
            "office": "TOKYO",
            "regiNo": regino,
        },
    )
    done = refresh_overseas_statuses(token)
    assert done["delivered"] == 1
    assert "배달완료 1건" in done["message"]
    item = list_overseas(token)["items"][0]
    assert item["treat_status"] == "배달완료"
    assert item["treat_office"] == "TOKYO"
