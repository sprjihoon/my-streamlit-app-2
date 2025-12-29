"""
logic/db.py - DB 연결 헬퍼
───────────────────────────────────
Streamlit 의존성 제거된 순수 Python 버전.
billing.db 자동 생성, 모든 필수 테이블·컬럼 보장.
"""
from __future__ import annotations

import sqlite3
import textwrap
import datetime as dt
import pathlib
import os
from contextlib import contextmanager

import pandas as pd

# ── Timestamp → YYYY-MM-DD 문자열 자동 변환 ──
sqlite3.register_adapter(
    pd.Timestamp,
    lambda ts: ts.strftime("%Y-%m-%d")
)

# ─────────────────────────────────────
# 0. 전역 상수
# ─────────────────────────────────────
DB_PATH = pathlib.Path(os.getenv("BILLING_DB", "billing.db"))
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# ─────────────────────────────────────
# 1. DB 연결
# ─────────────────────────────────────
@contextmanager
def get_connection():
    """로컬 'billing.db' 파일에 직접 연결합니다."""
    con = None
    try:
        con = sqlite3.connect(DB_PATH)
        yield con
    finally:
        if con:
            con.close()


# ─────────────────────────────────────
# 2. 컬럼 보강 유틸
# ─────────────────────────────────────
def ensure_column(tbl: str, col: str, coltype: str = "TEXT") -> None:
    with get_connection() as con:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
        if col not in cols:
            con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {coltype};")


# ─────────────────────────────────────
# 3. DDL – 최종 테이블 구조
# ─────────────────────────────────────
DDL_SQL = textwrap.dedent(
    """
    /* 기본 테이블 */
    CREATE TABLE IF NOT EXISTS vendors(
        vendor_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor     TEXT UNIQUE,
        name       TEXT,
        rate_type  TEXT,
        sku_group  TEXT
    );

    CREATE TABLE IF NOT EXISTS invoices(
        invoice_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id    INTEGER,
        period_from  DATE,
        period_to    DATE,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_amount REAL,
        currency     TEXT DEFAULT 'KRW',
        status       TEXT DEFAULT 'draft',
        FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
    );

    CREATE TABLE IF NOT EXISTS invoice_items(
        item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        item_name  TEXT,
        qty        REAL,
        unit_price REAL,
        amount     REAL,
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS shipping_zone(
        zone_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        rate_type TEXT,
        size_grp  TEXT,
        fee_krw   INTEGER,
        UNIQUE(rate_type, size_grp)
    );

    CREATE TABLE IF NOT EXISTS shipping_stats(
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        택배요금   INTEGER
    );
    """
)

# 레거시 DB 컬럼 보강 맵
CRITICAL_COLS = {
    "shipping_stats": [("택배요금", "INTEGER")],
    "outbound_slip": [("수량", "INTEGER")],
    "kpost_ret": [("수량", "INTEGER")],
}


# ─────────────────────────────────────
# 4. 테이블 & 컬럼 보강
# ─────────────────────────────────────
def _create_skeleton(con: sqlite3.Connection, tbl: str, col_defs: list[tuple[str, str]]):
    cols_sql = ", ".join(f"[{c}] {t}" for c, t in col_defs)
    con.execute(f"CREATE TABLE IF NOT EXISTS {tbl}(id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql});")


def ensure_tables() -> None:
    """필수 테이블 생성 + 레거시 컬럼 누락 보강."""
    with get_connection() as con:
        con.executescript(DDL_SQL)

        for tbl, col_defs in CRITICAL_COLS.items():
            tbl_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone() is not None

            if not tbl_exists:
                _create_skeleton(con, tbl, col_defs)
                continue

            existing_cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
            for col, coltype in col_defs:
                if col not in existing_cols:
                    con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {coltype};")


# ─────────────────────────────────────
# 5. 날짜/시간 유틸
# ─────────────────────────────────────
def now_str(fmt: str = DATE_FMT) -> str:
    return dt.datetime.now().strftime(fmt)


# ─────────────────────────────────────
# 6. 배송비 계산 예시
# ─────────────────────────────────────
def get_shipping_fee(size_grp: str, rate_type: str = "std") -> int:
    with get_connection() as con:
        row = con.execute(
            "SELECT fee_krw FROM shipping_zone WHERE size_grp=? AND rate_type=? LIMIT 1",
            (size_grp, rate_type),
        ).fetchone()
    if row is None:
        raise ValueError(f"🚚 요금표에 '{rate_type}/{size_grp}' 구간이 없습니다.")
    return int(row[0])


# ─────────────────────────────────────
# 7. DataFrame 헬퍼
# ─────────────────────────────────────
def df_from_sql(sql: str, params: tuple | list | None = None) -> pd.DataFrame:
    with get_connection() as con:
        df = pd.read_sql(sql, con, params=params)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ─────────────────────────────────────
# 8. aliases ↔ vendor 캐시 재생성 함수
# ─────────────────────────────────────
def refresh_alias_vendor_cache() -> None:
    """
    aliases(alias, file_type, vendor) 로부터
    alias_vendor_cache 캐시 테이블을 새로 만든다.
    """
    with get_connection() as con:
        con.executescript(
            """
            DROP TABLE IF EXISTS alias_vendor_cache;
            CREATE TABLE alias_vendor_cache AS
            SELECT alias, file_type, vendor
              FROM aliases;
            """
        )

