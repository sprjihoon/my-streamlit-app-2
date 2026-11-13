"""반품정보 업로드는 재입고 대기 엑셀 양식만 받고 작업일지는 건드리지 않는다."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from backend.app.api.upload import ALLOWED_UPLOAD_TABLES, TABLE_DATE_COL
from logic.db import ensure_tables, get_connection
from logic.upload import DATE_COL, UNIQUE_KEY, ingest

SAMPLE_XLS = Path(r"C:\Users\one\Downloads\NAVER WORKS\restockin_wait_20261104_130251.xls")


def _xlsx(rows: list[dict]) -> io.BytesIO:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)
    buf.name = "return_info.xlsx"
    return buf


def _row(**overrides) -> dict:
    base = {
        "상태": "입고완료",
        "등록일": "2026-11-03",
        "등록자": "staff",
        "입고일": "2026-11-04",
        "관리번호": "897278",
        "발주일": "2026-11-03",
        "판매처": "샘플판매처",
        "주문번호": "897278",
        "수령자": "샘플",
        "상품명": "샘플상품",
        "옵션": None,
        "수량": 1,
        "불량": "정상",
        "CS이력": "이력",
        "반품메모": "메모",
        "바코드": "8801234567890",
    }
    base.update(overrides)
    return base


def test_staff_can_upload_return_info_but_cannot_delete(isolated_runtime, monkeypatch):
    import sqlite3

    from fastapi.testclient import TestClient

    from backend.app.main import app

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
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
            ("staff-upload", "x", "직원", 0),
        )
        staff_id = con.execute("SELECT user_id FROM users WHERE username='staff-upload'").fetchone()[0]
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", ("staff-up", staff_id))
        con.commit()

    monkeypatch.setattr(
        "backend.app.api.upload.ingest",
        lambda *_args, **_kwargs: (True, "반품정보 업로드 완료"),
    )
    client = TestClient(app, raise_server_exceptions=False)
    files = {
        "file": (
            "return.xlsx",
            b"not-a-real-workbook",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    staff = client.post("/upload", data={"table": "return_info", "token": "staff-up"}, files=files)
    assert staff.status_code == 200
    assert staff.json()["success"] is True

    other = client.post("/upload", data={"table": "work_log", "token": "staff-up"}, files=files)
    assert other.status_code == 403

    guest = client.post("/upload", data={"table": "return_info"}, files=files)
    assert guest.status_code == 401

    wiped = client.delete("/upload/table/return_info", params={"token": "staff-up"})
    assert wiped.status_code == 403
    period = client.delete(
        "/upload/table/return_info/period",
        params={"token": "staff-up", "date_from": "2026-11-01", "date_to": "2026-11-04"},
    )
    assert period.status_code == 403


def test_return_info_form_dedup_keeps_work_log(isolated_runtime, monkeypatch):
    monkeypatch.setattr("logic.upload.UPLOAD_DIR", isolated_runtime["uploads"])
    ensure_tables()

    with get_connection() as con:
        con.execute(
            "INSERT INTO work_log (날짜, 업체명, 분류, 출처) VALUES (?, ?, ?, ?)",
            ("2026-11-01", "기존업체", "입고", "bot"),
        )
        con.commit()

    ok, message = ingest(
        _xlsx([
            _row(),
            _row(),
            _row(관리번호="900001", 주문번호="900001", 등록일=None, 상품명="날짜없음"),
        ]),
        "return_info",
        "return_info.xlsx",
    )
    assert ok, message
    assert "중복 행 1건을 걸러냈습니다" in message

    again, again_message = ingest(
        _xlsx([
            _row(),
            _row(상태="입고대기", 반품메모="같은 건"),
            _row(관리번호="900002", 주문번호="900002", 상품명="새상품", 반품메모="추가"),
        ]),
        "return_info",
        "return_info_next.xlsx",
    )
    assert again, again_message
    assert "중복 행 1건을 걸러냈습니다" in again_message

    missing, missing_message = ingest(
        _xlsx([{"상품명": "등록일없음", "관리번호": "1"}]),
        "return_info",
        "bad.xlsx",
    )
    assert missing is False
    assert "등록일" in missing_message

    with get_connection() as con:
        rows = con.execute(
            "SELECT 관리번호, 상품명, 상태, substr(등록일, 1, 10), 바코드 FROM return_info ORDER BY id"
        ).fetchall()
        stored_dates = con.execute("SELECT 등록일, 입고일, 발주일 FROM return_info").fetchall()
        work_rows = con.execute("SELECT 업체명, 출처 FROM work_log").fetchall()

    assert rows == [
        ("897278", "샘플상품", "입고완료", "2026-11-03", "8801234567890"),
        ("897278", "샘플상품", "입고대기", "2026-11-03", "8801234567890"),
        ("900002", "새상품", "입고완료", "2026-11-03", "8801234567890"),
    ]
    assert stored_dates == [("2026-11-03", "2026-11-04", "2026-11-03")] * 3
    assert work_rows == [("기존업체", "bot")]
    assert TABLE_DATE_COL["return_info"] == "등록일"
    assert DATE_COL["return_info"] == "등록일"
    assert UNIQUE_KEY["return_info"] is None
    assert UNIQUE_KEY["work_log"] == ["no", "날짜", "업체명"]
    assert "return_info" in ALLOWED_UPLOAD_TABLES


def test_return_info_keeps_long_cs_history(isolated_runtime, monkeypatch):
    monkeypatch.setattr("logic.upload.UPLOAD_DIR", isolated_runtime["uploads"])
    ensure_tables()
    memo = "상담 " + ("상세내역 " * 800)
    ok, message = ingest(
        _xlsx([_row(관리번호="900010", 주문번호="900010", CS이력=memo)]),
        "return_info",
        "long_cs.xlsx",
    )
    assert ok, message
    assert "중복" not in message
    with get_connection() as con:
        stored = con.execute("SELECT CS이력 FROM return_info").fetchone()[0]
    assert stored == memo
    assert len(stored) > 4000


@pytest.mark.skipif(not SAMPLE_XLS.exists(), reason="로컬 양식 파일이 없습니다")
def test_real_restockin_wait_form(isolated_runtime, monkeypatch):
    monkeypatch.setattr("logic.upload.UPLOAD_DIR", isolated_runtime["uploads"])
    ensure_tables()
    ok, message = ingest(SAMPLE_XLS.open("rb"), "return_info", SAMPLE_XLS.name)
    assert ok, message
    with get_connection() as con:
        row = con.execute(
            """SELECT 상태, substr(등록일, 1, 10), 관리번호, 판매처, 상품명, 수량
               FROM return_info"""
        ).fetchone()
    assert row == ("입고완료", "2026-11-03", "897278", "틸리언 수기", "강제배송", 1)
