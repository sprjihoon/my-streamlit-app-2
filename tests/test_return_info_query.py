"""반품정보 조회는 원본 헤더로 거르고 페이지 단위로 돌려준다."""
from __future__ import annotations

import io
import sqlite3

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app.main import app
from logic.db import ensure_tables, get_connection


def _seed_users(db_path):
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
            "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?,?,?,?)",
            ("admin-return", "x", "관리자", 1),
        )
        admin_id = con.execute("SELECT user_id FROM users WHERE username='admin-return'").fetchone()[0]
        con.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?,?,?,?)",
            ("staff-return", "x", "직원", 0),
        )
        staff_id = con.execute("SELECT user_id FROM users WHERE username='staff-return'").fetchone()[0]
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", ("admin-tok", admin_id))
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", ("staff-tok", staff_id))
        con.commit()


def _insert_rows():
    ensure_tables()
    rows = [
        ("입고완료", "2026-11-03", "staff", "2026-11-04", "111", "2026-11-01", "봄", "A1", "길동", "셔츠", "검정", 1, "정상", "이력1", "아무개 입고"),
        ("입고대기", "2026-11-05", "other", "2026-11-06", "222", "2026-11-02", "가을", "A2", "영희", "바지", "흰", 2, "불량", "이력2", "아무개 불량"),
        ("입고완료", "2026-11-03", "staff", None, "333", "2026-11-01", "봄", "A3", "길동", "모자", None, 1, "정상", "이력3", "아무개 입고"),
    ]
    with get_connection() as con:
        con.executemany(
            """INSERT INTO return_info
               (상태, 등록일, 등록자, 입고일, 관리번호, 발주일, 판매처, 주문번호, 수령자, 상품명, 옵션, 수량, 불량, CS이력, 반품메모)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        con.execute(
            "INSERT INTO work_log (날짜, 업체명, 분류, 출처) VALUES (?, ?, ?, ?)",
            ("2026-11-01", "기존업체", "입고", "bot"),
        )
        con.commit()


def test_return_info_filters_pages_and_export(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    client = TestClient(app, raise_server_exceptions=False)

    staff = client.get("/return-info", params={"token": "staff-tok", "반품메모": "입고"})
    assert staff.status_code == 200
    assert staff.json()["total"] == 2

    memo = client.get("/return-info", params={"반품메모": "입고", "page_size": 50})
    assert memo.status_code == 200
    body = memo.json()
    assert body["columns"] == [
        "상태", "등록일", "등록자", "입고일", "관리번호", "발주일", "판매처",
        "주문번호", "수령자", "상품명", "바코드", "옵션", "수량", "불량", "CS이력", "반품메모", "공급처",
    ]
    assert body["total"] == 2
    assert {row["관리번호"] for row in body["rows"]} == {"111", "333"}

    page = client.get(
        "/return-info",
        params={"token": "admin-tok", "반품메모": "입고", "page": 2, "page_size": 1},
    )
    assert page.status_code == 200
    paged = page.json()
    assert paged["total"] == 2
    assert paged["page"] == 2
    assert len(paged["rows"]) == 1
    assert paged["rows"][0]["관리번호"] == "111"

    dated = client.get(
        "/return-info",
        params={"token": "admin-tok", "등록일_from": "2026-11-05", "등록일_to": "2026-11-05"},
    )
    assert dated.status_code == 200
    assert [row["관리번호"] for row in dated.json()["rows"]] == ["222"]

    exported = client.get("/return-info/export", params={"token": "admin-tok", "반품메모": "입고"})
    assert exported.status_code == 200
    sheet = load_workbook(io.BytesIO(exported.content)).active
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    assert headers[:4] == ["상태", "등록일", "등록자", "입고일"]
    assert "반품메모" in headers
    assert sheet.max_row == 3

    with get_connection() as con:
        kept = con.execute("SELECT 업체명, 출처 FROM work_log").fetchone()
    assert kept == ("기존업체", "bot")


def test_return_info_choice_values_match_uploaded_text(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    client = TestClient(app, raise_server_exceptions=False)

    options = client.get("/return-info/options")
    assert options.status_code == 200
    body = options.json()
    assert set(body["판매처"]) == {"봄", "가을"}
    assert set(body["상품명"]) == {"셔츠", "바지", "모자"}

    with get_connection() as con:
        con.execute(
            """INSERT INTO return_info
               (상태, 등록일, 등록자, 입고일, 관리번호, 발주일, 판매처, 주문번호, 수령자, 상품명, 옵션, 수량, 불량, CS이력, 반품메모)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("입고완료", "2026-11-04", "staff", None, "444", "2026-11-01", "봄날", "A4", "길동", "셔츠", None, 1, "정상", "", "메모"),
        )
        con.commit()

    broad = client.get("/return-info", params={"판매처": "봄"})
    assert broad.status_code == 200
    assert {row["관리번호"] for row in broad.json()["rows"]} == {"111", "333", "444"}

    narrow = client.get("/return-info", params={"판매처": "봄날"})
    assert narrow.status_code == 200
    assert [row["관리번호"] for row in narrow.json()["rows"]] == ["444"]

    with get_connection() as con:
        con.execute("UPDATE return_info SET 공급처=? WHERE 관리번호=?", ("헤이즐", "111"))
        con.execute("UPDATE return_info SET 공급처=? WHERE 관리번호=?", ("헤이즐샵", "222"))
        con.commit()

    suppliers = client.get("/return-info/options")
    assert set(suppliers.json()["공급처"]) == {"헤이즐", "헤이즐샵"}
    supplier_rows = client.get("/return-info", params={"공급처": "헤이즐"})
    assert {row["관리번호"] for row in supplier_rows.json()["rows"]} == {"111", "222"}
    one_supplier = client.get("/return-info", params={"공급처": "헤이즐샵"})
    assert [row["관리번호"] for row in one_supplier.json()["rows"]] == ["222"]


def test_return_info_keyword_matches_attached_text(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    ensure_tables()
    notes = ["아무개반송", "아무개입고", "아무개1", "아무개 입고", "아마개", "홍길동"]
    with get_connection() as con:
        con.executemany(
            """INSERT INTO return_info
               (상태, 등록일, 등록자, 입고일, 관리번호, 발주일, 판매처, 주문번호, 수령자, 상품명, 옵션, 수량, 불량, CS이력, 반품메모)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("입고완료", "2026-11-03", "staff", None, str(index), "2026-11-01", "봄", str(index), "길동", "셔츠", None, 1, "정상", "", note)
                for index, note in enumerate(notes, start=1)
            ],
        )
        con.commit()
    client = TestClient(app, raise_server_exceptions=False)

    found = client.get("/return-info", params={"q": "아무개"})
    assert found.status_code == 200
    assert {row["반품메모"] for row in found.json()["rows"]} == {"아무개반송", "아무개입고", "아무개1", "아무개 입고"}


def test_return_info_keyword_searches_every_column(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    client = TestClient(app, raise_server_exceptions=False)

    product = client.get("/return-info", params={"q": "모자"})
    assert product.status_code == 200
    assert [row["관리번호"] for row in product.json()["rows"]] == ["333"]

    memo = client.get("/return-info", params={"q": "아무개", "상품명": "바지"})
    assert memo.status_code == 200
    assert [row["관리번호"] for row in memo.json()["rows"]] == ["222"]

    escaped = client.get("/return-info", params={"q": "%"})
    assert escaped.status_code == 200
    assert escaped.json()["total"] == 0

    too_long = client.get("/return-info", params={"q": "가" * 101})
    assert too_long.status_code == 400

    exported = client.get("/return-info/export", params={"q": "모자"})
    assert exported.status_code == 200
    sheet = load_workbook(io.BytesIO(exported.content)).active
    assert sheet.max_row == 2
    assert sheet["J2"].value == "모자"

    with get_connection() as con:
        kept = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
    assert kept == 1
