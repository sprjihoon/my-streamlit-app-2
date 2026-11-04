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
    }
    base.update(overrides)
    return base


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
            _row(관리번호="900001", 주문번호="900001", 등록일=None, 상품명="날짜없음"),
        ]),
        "return_info",
        "return_info.xlsx",
    )
    assert ok, message

    again, again_message = ingest(
        _xlsx([
            _row(상태="입고대기", 반품메모="같은 건"),
            _row(관리번호="900002", 주문번호="900002", 상품명="새상품", 반품메모="추가"),
        ]),
        "return_info",
        "return_info_next.xlsx",
    )
    assert again, again_message

    missing, missing_message = ingest(
        _xlsx([{"상품명": "등록일없음", "관리번호": "1"}]),
        "return_info",
        "bad.xlsx",
    )
    assert missing is False
    assert "등록일" in missing_message

    with get_connection() as con:
        rows = con.execute(
            "SELECT 관리번호, 상품명, 상태, substr(등록일, 1, 10) FROM return_info ORDER BY id"
        ).fetchall()
        work_rows = con.execute("SELECT 업체명, 출처 FROM work_log").fetchall()

    assert rows == [
        ("897278", "샘플상품", "입고완료", "2026-11-03"),
        ("900002", "새상품", "입고완료", "2026-11-03"),
    ]
    assert work_rows == [("기존업체", "bot")]
    assert TABLE_DATE_COL["return_info"] == "등록일"
    assert DATE_COL["return_info"] == "등록일"
    assert UNIQUE_KEY["return_info"] == ["관리번호", "상품명", "옵션"]
    assert UNIQUE_KEY["work_log"] == ["no", "날짜", "업체명"]
    assert "return_info" in ALLOWED_UPLOAD_TABLES


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
