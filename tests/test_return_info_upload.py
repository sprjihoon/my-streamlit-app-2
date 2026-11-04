"""반품정보 업로드는 새 테이블에만 적재하고 작업일지 규칙을 바꾸지 않는다."""
from __future__ import annotations

import io

import pandas as pd

from backend.app.api.upload import ALLOWED_UPLOAD_TABLES, TABLE_DATE_COL
from logic.db import ensure_tables, get_connection
from logic.upload import DATE_COL, UNIQUE_KEY, ingest


def test_return_info_ingest_keeps_work_log_rules(isolated_runtime, monkeypatch):
    monkeypatch.setattr("logic.upload.UPLOAD_DIR", isolated_runtime["uploads"])
    ensure_tables()

    with get_connection() as con:
        con.execute(
            "INSERT INTO work_log (날짜, 업체명, 분류, 출처) VALUES (?, ?, ?, ?)",
            ("2026-11-01", "기존업체", "입고", "bot"),
        )
        con.commit()

    buf = io.BytesIO()
    pd.DataFrame(
        {"반품번호": ["R-1", "R-2"], "업체명": ["봄", "가을"]}
    ).to_excel(buf, index=False)
    buf.seek(0)
    buf.name = "returns.xlsx"

    ok, message = ingest(buf, "return_info", "returns.xlsx")
    assert ok, message

    with get_connection() as con:
        rows = con.execute(
            "SELECT 반품번호, 업체명 FROM return_info ORDER BY id"
        ).fetchall()
        work_rows = con.execute(
            "SELECT 업체명, 출처 FROM work_log"
        ).fetchall()
        uploads = con.execute(
            "SELECT table_name FROM uploads WHERE table_name = 'return_info'"
        ).fetchall()

    assert rows == [("R-1", "봄"), ("R-2", "가을")]
    assert work_rows == [("기존업체", "bot")]
    assert uploads == [("return_info",)]
    assert "return_info" in ALLOWED_UPLOAD_TABLES
    assert "return_info" not in TABLE_DATE_COL
    assert "return_info" not in DATE_COL
    assert UNIQUE_KEY["work_log"] == ["no", "날짜", "업체명"]
    assert DATE_COL["work_log"] == "날짜"
