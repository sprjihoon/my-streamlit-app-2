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
        # WAL 모드: 동시 읽기 성능 향상 & 안정성
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA busy_timeout=5000;")
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

    /* 회사 설정 테이블 */
    CREATE TABLE IF NOT EXISTS company_settings(
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        company_name    TEXT DEFAULT '회사명',
        business_number TEXT DEFAULT '000-00-00000',
        address         TEXT DEFAULT '주소를 입력하세요',
        business_type   TEXT DEFAULT '서비스',
        business_item   TEXT DEFAULT '물류대행',
        bank_name       TEXT DEFAULT '은행명',
        account_holder  TEXT DEFAULT '예금주',
        account_number  TEXT DEFAULT '계좌번호',
        representative  TEXT DEFAULT '대표자명',
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS shipping_stats(
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        택배요금   INTEGER
    );

    /* 보관료 단가표 */
    CREATE TABLE IF NOT EXISTS storage_rates(
        rate_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name   TEXT UNIQUE NOT NULL,
        unit_price  INTEGER NOT NULL,
        unit        TEXT DEFAULT '월',
        description TEXT DEFAULT '',
        is_active   INTEGER DEFAULT 1
    );

    /* 거래처별 보관료 사용 내역 */
    CREATE TABLE IF NOT EXISTS vendor_storage(
        storage_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id   TEXT NOT NULL,
        rate_id     INTEGER,
        item_name   TEXT NOT NULL,
        qty         INTEGER DEFAULT 1,
        unit_price  INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        period      TEXT,
        remark      TEXT DEFAULT '',
        is_active   INTEGER DEFAULT 1,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (rate_id) REFERENCES storage_rates(rate_id)
    );

    /* 거래처별 추가 청구 비용 (보관비 등) */
    CREATE TABLE IF NOT EXISTS vendor_charges(
        charge_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id   TEXT NOT NULL,
        item_name   TEXT NOT NULL,
        qty         INTEGER DEFAULT 1,
        unit_price  INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        remark      TEXT DEFAULT '',
        charge_type TEXT DEFAULT '보관비',
        is_active   INTEGER DEFAULT 1,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
)

# 레거시 DB 컬럼 보강 맵
# 업로드 가능한 테이블들의 기본 스켈레톤 생성
CRITICAL_COLS = {
    # shipping_stats: 배송통계
    "shipping_stats": [
        ("배송일", "TEXT"), 
        ("공급처", "TEXT"), 
        ("택배요금", "INTEGER"),
        ("송장번호", "TEXT"),  # 중복 제거용
    ],
    # outbound_slip: 출고전표
    "outbound_slip": [("수량", "INTEGER")],
    # kpost_ret: 우체국 반품
    "kpost_ret": [
        ("수취인명", "TEXT"),
        ("배달일자", "TEXT"),
        ("우편물부피", "INTEGER"),
        ("등기번호", "TEXT"),
        ("수량", "INTEGER"),
    ],
    # 업로드 테이블 스켈레톤 (컬럼은 업로드 시 자동 추가됨)
    "inbound_slip": [
        ("상품코드", "TEXT"), 
        ("작업일", "TEXT"), 
        ("수량", "INTEGER"), 
        ("공급처", "TEXT")
    ],
    "kpost_in": [
        ("발송인명", "TEXT"), 
        ("접수일자", "TEXT"), 
        ("우편물부피", "INTEGER"),
        ("등기번호", "TEXT"),
        ("도서행", "TEXT"),  # 도서산간 여부
    ],
    "work_log": [
        ("날짜", "TEXT"), 
        ("업체명", "TEXT"), 
        ("분류", "TEXT"), 
        ("단가", "INTEGER"), 
        ("수량", "INTEGER"), 
        ("합계", "INTEGER"), 
        ("비고1", "TEXT")
    ],
}


# ─────────────────────────────────────
# 4. 테이블 & 컬럼 보강
# ─────────────────────────────────────
def _create_skeleton(con: sqlite3.Connection, tbl: str, col_defs: list[tuple[str, str]]):
    cols_sql = ", ".join(f"[{c}] {t}" for c, t in col_defs)
    con.execute(f"CREATE TABLE IF NOT EXISTS {tbl}(id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql});")


def ensure_tables() -> None:
    """필수 테이블 생성 + 레거시 컬럼 누락 보강.
    
    ⚠️ 중요: 이 함수는 기존 데이터를 절대 삭제하지 않습니다.
    - CREATE TABLE IF NOT EXISTS만 사용 (데이터 보존)
    - ALTER TABLE ADD COLUMN만 사용 (데이터 보존)
    - DROP TABLE, DELETE, TRUNCATE 절대 사용 안 함
    """
    with get_connection() as con:
        # DDL_SQL 실행 (CREATE TABLE IF NOT EXISTS만 사용 - 데이터 보존)
        # 이 스크립트는 테이블이 없을 때만 생성하며, 기존 데이터는 절대 삭제하지 않습니다.
        con.executescript(DDL_SQL)

        # shipping_zone 테이블 스키마 보강 (요금제, 구간, 요금 컬럼 추가)
        shipping_zone_cols = [c[1] for c in con.execute("PRAGMA table_info(shipping_zone);")]
        shipping_zone_required_cols = [
            ("요금제", "TEXT"),
            ("구간", "TEXT"),
            ("len_min_cm", "INTEGER"),
            ("len_max_cm", "INTEGER"),
            ("요금", "INTEGER")
        ]
        for col, coltype in shipping_zone_required_cols:
            if col not in shipping_zone_cols:
                try:
                    con.execute(f"ALTER TABLE shipping_zone ADD COLUMN [{col}] {coltype};")
                except sqlite3.OperationalError:
                    pass  # 이미 존재하거나 다른 오류 (무시)
        
        # invoice_items 테이블 스키마 보강 (remark 컬럼 추가)
        invoice_items_cols = [c[1] for c in con.execute("PRAGMA table_info(invoice_items);")]
        if "remark" not in invoice_items_cols:
            try:
                con.execute("ALTER TABLE invoice_items ADD COLUMN remark TEXT DEFAULT '';")
            except sqlite3.OperationalError:
                pass  # 이미 존재하거나 다른 오류 (무시)

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
        
        con.commit()


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

