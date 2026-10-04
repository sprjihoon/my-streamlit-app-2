"""Shared repair-log constants, schema ensure, and text/barcode helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from backend.app.config import settings
from backend.app.services import repair_catalog
from logic.db import get_connection

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "repair"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

def ensure_repair_tables():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_barcode (
                바코드 TEXT PRIMARY KEY,
                업체명 TEXT NOT NULL,
                제품명 TEXT NOT NULL,
                옵션 TEXT,
                상품코드 TEXT,
                로케이션 TEXT,
                상품명 TEXT,
                출처 TEXT,
                저장시간 TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_work_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                날짜 TEXT,
                업체명 TEXT,
                제품명 TEXT,
                옵션 TEXT,
                바코드 TEXT,
                작업 TEXT,
                수량 INTEGER DEFAULT 1,
                비용 INTEGER DEFAULT 0,
                비고 TEXT,
                작성자 TEXT,
                저장시간 TIMESTAMP,
                출처 TEXT,
                barcode_image TEXT,
                before_image TEXT,
                after_image TEXT
            )
        """)
        existing_cols = [c[1] for c in con.execute("PRAGMA table_info(repair_work_log)")]
        for col, coltype in [
            ("불량명", "TEXT"),
            ("수정자", "TEXT"),
            ("수정시간", "TIMESTAMP"),
            ("extra_images", "TEXT"),
            ("inbound_item_id", "TEXT"),   # 입고 품목 연결 (additive)
            ("defect_case_id", "TEXT"),    # 입고 결함 케이스 (additive)
        ]:
            if col not in existing_cols:
                con.execute(f"ALTER TABLE repair_work_log ADD COLUMN [{col}] {coltype}")
        # repair_barcode 마이그레이션
        bc_cols = [c[1] for c in con.execute("PRAGMA table_info(repair_barcode)")]
        for _col in ("도매처", "도매처주소", "도매처연락처"):
            if _col not in bc_cols:
                con.execute(f"ALTER TABLE repair_barcode ADD COLUMN {_col} TEXT")
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_photo_inbox (
                user_id TEXT PRIMARY KEY,
                channel_id TEXT,
                channel_type TEXT,
                user_name TEXT,
                extra_rounds INTEGER DEFAULT 0,
                notified_n INTEGER DEFAULT 0,
                flush_after REAL,
                updated_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_photo_inbox_file (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                name TEXT,
                ext TEXT,
                created_at TEXT
            )
        """)
        con.commit()
    repair_catalog.ensure_catalog_tables()

def _clean(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    if s.lower() in ("", "nan", "none"):
        return None
    return s


def _clean_vendor(v) -> Optional[str]:
    """공급처 컬럼 값에서 '공급처 ' 접두어를 제거한다.
    예: '공급처 헤이즐샵1' → '헤이즐샵1'
    """
    s = _clean(v)
    if s and s.startswith("공급처 "):
        s = s[len("공급처 "):].strip() or None
    return s or None


def _strip_option(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return v.strip().strip("[]").strip()


def _lookup_barcode(con, barcode: str) -> Optional[dict]:
    if not barcode:
        return None
    code = barcode.strip()
    row = con.execute(
        """SELECT 바코드, 업체명, 제품명, 옵션, 상품코드, 로케이션, 상품명, 도매처
           FROM repair_barcode
           WHERE 바코드 = ? OR UPPER(TRIM(바코드)) = UPPER(?)""",
        (code, code),
    ).fetchone()
    if not row:
        return None
    return {
        "바코드": row[0],
        "업체명": row[1],
        "제품명": row[2],
        "옵션": row[3],
        "상품코드": row[4],
        "로케이션": row[5],
        "상품명": row[6],
        "도매처": row[7],
    }


def _resolve_vendor(con, vendor: str) -> str:
    """별칭이면 정식 업체명으로. 없으면 원문 유지."""
    if not vendor:
        return vendor
    raw = vendor.strip()
    row = con.execute(
        """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
           UNION
           SELECT vendor FROM aliases
           WHERE LOWER(alias) = LOWER(?) AND file_type IN ('work_log', 'all')""",
        (raw, raw),
    ).fetchone()
    if row:
        return row[0]
    # 자체제작_베으 → 베으 부분 일치 별칭
    suffix = raw.split("_")[-1] if "_" in raw else raw
    if suffix != raw:
        row = con.execute(
            """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
               UNION
               SELECT vendor FROM aliases
               WHERE LOWER(alias) = LOWER(?) AND file_type IN ('work_log', 'all')""",
            (suffix, suffix),
        ).fetchone()
        if row:
            return row[0]
    return raw
