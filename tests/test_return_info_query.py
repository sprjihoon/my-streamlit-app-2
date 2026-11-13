"""반품정보 조회는 원본 헤더로 거르고 페이지 단위로 돌려준다."""
from __future__ import annotations

import io
import sqlite3
from datetime import datetime
from urllib.parse import unquote
from zoneinfo import ZoneInfo

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
        "주문번호", "수령자", "상품명", "바코드", "옵션", "수량", "불량", "CS이력", "반품메모",
        "수정사항메모", "공급처", "입력구분",
    ]
    assert all(row["입력구분"] is None for row in body["rows"])
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
    assert headers[-1] == "입력구분"
    assert "반품메모" in headers
    assert sheet.max_row == 3

    with get_connection() as con:
        kept = con.execute("SELECT 업체명, 출처 FROM work_log").fetchone()
    assert kept == ("기존업체", "bot")


def test_return_info_hides_midnight_time_on_date_columns(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    ensure_tables()
    with get_connection() as con:
        con.execute(
            """INSERT INTO return_info
               (상태, 등록일, 입고일, 발주일, 관리번호, 상품명)
               VALUES (?,?,?,?,?,?)""",
            (
                "입고완료",
                "2026-11-13 00:00:00",
                "2026-11-13 00:00:00.000000",
                "2026-11-12 09:30:00",
                "M1",
                "셔츠",
            ),
        )
        con.commit()
    client = TestClient(app, raise_server_exceptions=False)
    listed = client.get("/return-info", params={"token": "admin-tok", "관리번호": "M1"})
    assert listed.status_code == 200
    row = listed.json()["rows"][0]
    assert row["등록일"] == "2026-11-13"
    assert row["입고일"] == "2026-11-13"
    assert row["발주일"] == "2026-11-12 09:30:00"

    exported = client.get("/return-info/export", params={"token": "admin-tok", "관리번호": "M1"})
    sheet = load_workbook(io.BytesIO(exported.content)).active
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    values = [cell.value for cell in next(sheet.iter_rows(min_row=2, max_row=2))]
    assert values[headers.index("등록일")] == "2026-11-13"


def test_return_info_report_uses_filtered_rows(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    with get_connection() as con:
        con.execute("UPDATE return_info SET 공급처=? WHERE 관리번호=?", ("헤이즐", "111"))
        con.execute("UPDATE return_info SET 공급처=? WHERE 관리번호=?", ("헤이즐샵", "333"))
        con.commit()
    client = TestClient(app, raise_server_exceptions=False)

    report = client.get("/return-info/report", params={"token": "admin-tok", "반품메모": "입고", "공급처": "헤이즐"})
    assert report.status_code == 200
    sheet = load_workbook(io.BytesIO(report.content)).active
    assert sheet["A1"].value == "반품 보고서"
    assert "A1:D1" in {str(item) for item in sheet.merged_cells.ranges}
    assert sheet["A1"].font.size == 22
    assert sheet["A2"].value is None
    assert sheet["A3"].value == "공급처"
    assert sheet["B3"].value == "헤이즐샵, 헤이즐"
    assert sheet["A4"].value == "작성일"
    assert sheet["B4"].value
    assert sheet["A5"].value == "등록자"
    assert sheet["B5"].value == "관리자"
    headers = [cell.value for cell in sheet[7]]
    assert headers == [
        "번호", "등록일", "등록자", "관리번호", "주문번호", "판매처", "수령자",
        "상품명", "옵션", "바코드", "수량", "불량", "CS이력", "반품메모", "수정사항메모",
    ]
    assert "상태" not in headers
    numbers = [sheet.cell(row, 1).value for row in range(8, sheet.max_row + 1)]
    managed = [sheet.cell(row, 4).value for row in range(8, sheet.max_row + 1)]
    assert numbers == [1, 2]
    assert managed == ["333", "111"]
    today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    disposition = unquote(report.headers["content-disposition"])
    assert f"헤이즐샵_헤이즐_{today}.xlsx" in disposition


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

    both = client.get("/return-info", params=[("판매처", "가을"), ("판매처", "봄날")])
    assert both.status_code == 200
    assert {row["관리번호"] for row in both.json()["rows"]} == {"222", "444"}

    ignored = client.get("/return-info", params={"CS이력": "없는문구"})
    assert ignored.status_code == 200
    assert ignored.json()["total"] == 4


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


def _manual_payload(**overrides):
    payload = {
        "상태": "입고대기",
        "등록일": "2026-11-05",
        "등록자": "",
        "입고일": "",
        "관리번호": "M-77",
        "발주일": "2026-11-04",
        "판매처": "봄날",
        "주문번호": "ORD-1",
        "수령자": "길동",
        "상품명": " 셔츠 ",
        "바코드": "8801",
        "옵션": "검정",
        "수량": 2,
        "불량": "정상",
        "CS이력": "전화 상담",
        "반품메모": "수동 입력",
        "공급처": "헤이즐",
    }
    payload.update(overrides)
    return payload


def test_return_info_manual_create_keeps_work_log(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    client = TestClient(app, raise_server_exceptions=False)

    denied = client.post("/return-info", json=_manual_payload())
    assert denied.status_code == 401
    assert denied.json()["detail"] == "로그인이 필요합니다."

    missing_date = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json=_manual_payload(등록일=""),
    )
    assert missing_date.status_code == 400
    assert missing_date.json()["detail"] == "등록일을 입력해 주세요."

    date_only = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json={"등록일": "2026-11-05", "등록자": "직원"},
    )
    assert date_only.status_code == 400
    assert date_only.json()["detail"] == "등록일 외에 내용을 하나 이상 입력해 주세요."

    bad_date = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json=_manual_payload(입고일="2026/11/06"),
    )
    assert bad_date.status_code == 400

    bad_qty = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json=_manual_payload(수량="1.5"),
    )
    assert bad_qty.status_code == 400
    assert bad_qty.json()["detail"] == "수량은 0 이상의 정수로 입력해 주세요."

    unknown = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json=_manual_payload(id=1),
    )
    assert unknown.status_code == 400
    assert unknown.json()["detail"] == "허용되지 않은 항목이 있습니다."

    created = client.post("/return-info", params={"token": "staff-tok"}, json=_manual_payload())
    assert created.status_code == 200
    body = created.json()
    assert body["id"]
    assert body["row"]["등록자"] == "직원"
    assert body["row"]["상품명"] == "셔츠"
    assert body["row"]["수량"] == 2
    assert body["row"]["입력구분"] == "수동 입력"
    assert body["row"]["수정사항메모"] is None

    noted = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json=_manual_payload(관리번호="M-79", 수정사항메모="입고 확인"),
    )
    assert noted.status_code == 200
    assert noted.json()["row"]["수정사항메모"] == "입고 확인"
    noted_row = client.get("/return-info", params={"token": "staff-tok", "관리번호": "M-79"})
    assert noted_row.status_code == 200
    assert noted_row.json()["rows"][0]["수정사항메모"] == "입고 확인"

    listed = client.get("/return-info", params={"token": "staff-tok", "관리번호": "M-77"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["rows"][0]["판매처"] == "봄날"
    assert listed.json()["rows"][0]["입력구분"] == "수동 입력"
    uploaded = client.get("/return-info", params={"관리번호": "111"})
    assert uploaded.json()["rows"][0]["입력구분"] is None

    duplicate = client.post("/return-info", params={"token": "staff-tok"}, json=_manual_payload(등록자="직원"))
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "같은 내용의 반품정보가 이미 있습니다."

    with get_connection() as con:
        con.execute(
            """INSERT INTO return_info
               (상태, 등록일, 등록자, 입고일, 관리번호, 발주일, 판매처, 주문번호, 수령자, 상품명, 바코드, 옵션, 수량, 불량, CS이력, 반품메모, 공급처)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "입고대기", "2026-11-06 09:00:00", "직원", None, "M-88", "2026-11-04",
                "봄날", "ORD-2", "길동", "바지", None, "검정", None, None, None, None, None,
            ),
        )
        con.commit()
    same_day = client.post(
        "/return-info",
        params={"token": "staff-tok"},
        json=_manual_payload(
            등록일="2026-11-06",
            관리번호="M-88",
            주문번호="ORD-2",
            상품명="바지",
            입고일="",
            바코드="",
            수량=None,
            불량="",
            CS이력="",
            반품메모="",
            공급처="",
        ),
    )
    assert same_day.status_code == 409

    with get_connection() as con:
        kept = con.execute("SELECT 업체명, 출처 FROM work_log").fetchone()
        saved = con.execute(
            "SELECT COUNT(*) FROM return_info WHERE 관리번호='M-77'"
        ).fetchone()[0]
        dated = con.execute(
            "SELECT COUNT(*) FROM return_info WHERE 관리번호='M-88'"
        ).fetchone()[0]
        uploads = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='uploads'"
        ).fetchone()
        upload_count = (
            con.execute("SELECT COUNT(*) FROM uploads").fetchone()[0] if uploads else 0
        )
    assert kept == ("기존업체", "bot")
    assert saved == 1
    assert dated == 1
    assert upload_count == 0


def test_return_info_defect_update_keeps_other_columns(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    client = TestClient(app, raise_server_exceptions=False)

    listed = client.get("/return-info", params={"token": "staff-tok"})
    assert listed.status_code == 200
    rows = {row["관리번호"]: row for row in listed.json()["rows"]}
    first = rows["111"]["id"]
    second = rows["222"]["id"]
    third = rows["333"]["id"]

    denied = client.post("/return-info/defect", json={"ids": [first], "불량": "불량"})
    assert denied.status_code == 401

    rejected = client.post(
        "/return-info/defect",
        params={"token": "staff-tok"},
        json={"ids": [first], "불량": "보류"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "불량은 정상 또는 불량만 선택할 수 있습니다."

    extra = client.post(
        "/return-info/defect",
        params={"token": "staff-tok"},
        json={"ids": [first], "불량": "불량", "상태": "완료"},
    )
    assert extra.status_code == 400
    assert extra.json()["detail"] == "불량과 수정사항메모만 변경할 수 있습니다."

    missing = client.post(
        "/return-info/defect",
        params={"token": "staff-tok"},
        json={"ids": [first, 999999], "불량": "불량", "수정사항메모": "없어야 함"},
    )
    assert missing.status_code == 404
    with get_connection() as con:
        untouched = con.execute(
            "SELECT 불량, 수정사항메모 FROM return_info WHERE id=?",
            (first,),
        ).fetchone()
    assert untouched == ("정상", None)

    updated = client.post(
        "/return-info/defect",
        params={"token": "staff-tok"},
        json={"ids": [first, second], "불량": "정상", "수정사항메모": "재검수"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"updated": 2, "불량": "정상", "수정사항메모": "재검수"}

    kept = client.post(
        "/return-info/defect",
        params={"token": "admin-tok"},
        json={"ids": [first], "불량": "불량"},
    )
    assert kept.status_code == 200
    assert "수정사항메모" not in kept.json()

    with get_connection() as con:
        changed = con.execute(
            "SELECT 관리번호, 불량, 수정사항메모, 상품명, 반품메모, 입력구분 FROM return_info WHERE id=?",
            (first,),
        ).fetchone()
        paired = con.execute(
            "SELECT 불량, 수정사항메모, 상품명 FROM return_info WHERE id=?",
            (second,),
        ).fetchone()
        skipped = con.execute(
            "SELECT 불량, 수정사항메모 FROM return_info WHERE id=?",
            (third,),
        ).fetchone()
        work = con.execute("SELECT 업체명, 출처 FROM work_log").fetchone()
    assert changed == ("111", "불량", "재검수", "셔츠", "아무개 입고", None)
    assert paired == ("정상", "재검수", "바지")
    assert skipped == ("정상", None)
    assert work == ("기존업체", "bot")

    exported = client.get("/return-info/export", params={"token": "staff-tok", "관리번호": "111"})
    assert exported.status_code == 200
    sheet = load_workbook(io.BytesIO(exported.content)).active
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    memo_col = headers.index("수정사항메모") + 1
    defect_col = headers.index("불량") + 1
    assert headers[headers.index("반품메모") + 1] == "수정사항메모"
    assert sheet.cell(2, defect_col).value == "불량"
    assert sheet.cell(2, memo_col).value == "재검수"

    report = client.get("/return-info/report", params={"token": "staff-tok", "관리번호": "111"})
    assert report.status_code == 200
    report_sheet = load_workbook(io.BytesIO(report.content)).active
    report_headers = [cell.value for cell in report_sheet[7]]
    assert report_headers[-1] == "수정사항메모"
    assert report_sheet.cell(8, len(report_headers)).value == "재검수"
    assert report_sheet.cell(8, report_headers.index("불량") + 1).value == "불량"


def test_return_info_edit_delete_and_restore_keep_work_log(isolated_runtime):
    _seed_users(isolated_runtime["db"])
    _insert_rows()
    client = TestClient(app, raise_server_exceptions=False)

    listed = client.get("/return-info", params={"token": "staff-tok"})
    rows = {row["관리번호"]: row for row in listed.json()["rows"]}
    target = rows["111"]["id"]
    other = rows["222"]["id"]

    guest = client.patch(f"/return-info/{target}", json={"상품명": "다른셔츠"})
    assert guest.status_code == 401

    unknown = client.patch(
        f"/return-info/{target}",
        params={"token": "staff-tok"},
        json={"비밀": "값"},
    )
    assert unknown.status_code == 400
    assert unknown.json()["detail"] == "허용되지 않은 항목이 있습니다."

    same = client.patch(
        f"/return-info/{target}",
        params={"token": "staff-tok"},
        json={"상품명": "셔츠"},
    )
    assert same.status_code == 200
    assert same.json()["changed"] is False

    edited = client.patch(
        f"/return-info/{target}",
        params={"token": "staff-tok"},
        json={"상품명": "다른셔츠", "수정사항메모": "색상 확인"},
    )
    assert edited.status_code == 200
    assert edited.json()["changed"] is True
    assert edited.json()["row"]["상품명"] == "다른셔츠"
    assert edited.json()["row"]["반품메모"] == "아무개 입고"

    removed = client.delete(f"/return-info/{target}", params={"token": "admin-tok"})
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True

    hidden = client.get("/return-info", params={"token": "staff-tok", "관리번호": "111"})
    assert hidden.json()["total"] == 0
    still = client.get("/return-info", params={"관리번호": "222"})
    assert still.json()["total"] == 1

    denied_log = client.get("/return-info/logs")
    assert denied_log.status_code == 401
    logs = client.get("/return-info/logs", params={"token": "staff-tok", "actor": "관리자"})
    assert logs.status_code == 200
    body = logs.json()
    assert body["summary"]["delete"] == 1
    assert body["rows"][0]["actor_name"] == "관리자"
    assert body["rows"][0]["action"] == "delete"
    assert body["rows"][0]["can_restore"] is True
    assert "111" in body["rows"][0]["summary"]
    delete_log_id = body["rows"][0]["id"]

    staff_edit = client.get("/return-info/logs", params={"token": "staff-tok", "action": "update", "actor": "직원"})
    assert staff_edit.json()["total"] == 1
    changes = {item["field"]: item for item in staff_edit.json()["rows"][0]["changes"]}
    assert changes["상품명"]["before"] == "셔츠"
    assert changes["상품명"]["after"] == "다른셔츠"
    assert changes["수정사항메모"]["after"] == "색상 확인"

    brought = client.post(f"/return-info/logs/{delete_log_id}/restore", params={"token": "staff-tok"})
    assert brought.status_code == 200
    again = client.post(f"/return-info/logs/{delete_log_id}/restore", params={"token": "staff-tok"})
    assert again.status_code == 409

    restored = client.get("/return-info", params={"token": "staff-tok", "관리번호": "111"})
    assert restored.json()["total"] == 1
    assert restored.json()["rows"][0]["상품명"] == "다른셔츠"
    assert restored.json()["rows"][0]["수정사항메모"] == "색상 확인"
    assert restored.json()["rows"][0]["id"] != other

    with get_connection() as con:
        work = con.execute("SELECT 업체명, 출처 FROM work_log").fetchone()
        live = con.execute(
            "SELECT COUNT(*) FROM return_info WHERE 관리번호='111' AND (deleted_at IS NULL OR TRIM(deleted_at)='')"
        ).fetchone()[0]
    assert work == ("기존업체", "bot")
    assert live == 1
