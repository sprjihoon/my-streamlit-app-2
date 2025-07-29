from __future__ import annotations
import sqlite3, textwrap, datetime as dt, pathlib, contextlib
import pandas as pd
import os
import sqlite3
import streamlit as st
import pandas as pd
from contextlib import contextmanager
import libsql_client
import textwrap
from datetime import date
import datetime as dt

"""
common.py – 전역 유틸 / DB 연결 / 스키마 보강
───────────────────────────────────────────────
* billing.db 자동 생성, 모든 필수 테이블·컬럼 보장
* ensure_column()  ·  ensure_tables()  ·  now_str() 등 제공
"""

# ── NEW: Timestamp → YYYY-MM-DD 문자열 자동 변환 ──
sqlite3.register_adapter(
    pd.Timestamp,
    lambda ts: ts.strftime("%Y-%m-%d")        # 필요하면 %Y-%m-%d %H:%M:%S
)


# ─────────────────────────────────────
# 0. 전역 상수
# ─────────────────────────────────────
DB_PATH  = pathlib.Path("billing.db")
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# ─────────────────────────────────────
# 1. DB 연결 (Turso 클라우드 DB)
# ─────────────────────────────────────

@contextmanager
def get_connection():
    """
    Streamlit Secrets에 저장된 정보를 사용하여 Turso DB에 연결합니다.
    Secrets가 없으면 로컬 'billing.db'에 fallback합니다.
    """
    db_url = st.secrets.get("TURSO_DB_URL")
    db_token = st.secrets.get("TURSO_DB_AUTH_TOKEN")

    if db_url and db_token:
        # Turso 클라우드 DB 연결
        try:
            with libsql_client.create_client(url=db_url, auth_token=db_token) as client:
                yield client
        except Exception as e:
            st.error(f"🚨 Turso DB 연결 실패: {e}")
            raise
    else:
        # 로컬 DB 파일로 fallback (개발/테스트용)
        try:
            con = sqlite3.connect("billing_local.db")
            yield con
        finally:
            if 'con' in locals() and con:
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
    "outbound_slip" : [("수량", "INTEGER")],
    "kpost_ret"     : [("수량", "INTEGER")],
}

# ─────────────────────────────────────
# 4. 테이블 & 컬럼 보강
# ─────────────────────────────────────

def _create_skeleton(con: sqlite3.Connection, tbl: str, col_defs: list[tuple[str,str]]):
    cols_sql = ", ".join(f"[{c}] {t}" for c, t in col_defs)
    con.execute(f"CREATE TABLE IF NOT EXISTS {tbl}(id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql});")


def ensure_tables() -> None:
    """필수 테이블 생성 + 레거시 컬럼 누락 보강.
    * 테이블이 없으면 _create_skeleton 으로 먼저 만들고 컬럼 루프는 건너뜀
    * 테이블이 이미 있으면 필요한 컬럼만 ALTER TABLE ADD COLUMN
    """
    with get_connection() as con:
        con.executescript(DDL_SQL)

        for tbl, col_defs in CRITICAL_COLS.items():
            tbl_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone() is not None

            if not tbl_exists:
                # 새 테이블 스켈레톤 생성 → 기본 컬럼은 이미 포함되므로 보강 필요 없음
                _create_skeleton(con, tbl, col_defs)
                continue  # ALTER 단계 건너뜀

            # 테이블이 있으면 누락 컬럼 보강
            existing_cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
            for col, coltype in col_defs:
                if col not in existing_cols:
                    con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {coltype};")

# 모듈 import 시 자동 실행
ensure_tables()

# ─────────────────────────────────────
# 5. 날짜/시간 유틸
# ─────────────────────────────────────

def now_str(fmt: str = DATE_FMT) -> str:
    return dt.datetime.now().strftime(fmt)

# ─────────────────────────────────────
# 6. 배송비 계산 예시
# ─────────────────────────────────────

def get_shipping_fee(size_grp: str, rate_type: str = "std") -> int:
    with contextlib.closing(get_connection()) as con:
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
    (업로드·매핑 페이지에서 호출)
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
