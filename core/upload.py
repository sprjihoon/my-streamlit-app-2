"""
new_cal/core/upload.py
────────────────────────────────────────────────────────────
Excel(xlsx) 업로드 → 지정 테이블 적재 + uploads 메타 기록
  • 파일은 “타임스탬프_UUID.xlsx” 로 저장 (Windows 경로 안전)
  • uploads: filename · orig_name · table · date_min/max · file_hash · ts
  • file_hash UNIQUE → 동일 파일 두 번 못 올림
  • 테이블별 UNIQUE_KEY 로 행-중복 제거
  • 시간 포함 테이블(shipping_stats·inbound_slip) → 날짜 전용 컬럼 추가
"""

from __future__ import annotations
import hashlib, shutil, datetime as dt, uuid, sqlite3
from pathlib import Path
from typing import Literal
import pandas as pd
from .db import get_conn

# 저장 폴더 ────────────────────────────────────────────────
UPLOAD_DIR = Path("new_cal/data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 날짜 컬럼 정의 ──────────────────────────────────────────
TableName = Literal[
    "inbound_slip", "shipping_stats",
    "kpost_in", "kpost_ret", "work_log",
]
DATE_COL = {
    "inbound_slip":   "작업일",
    "shipping_stats": "배송일",
    "kpost_in":       "접수일자",
    "kpost_ret":      "배달일자",
    "work_log":       "날짜",
}
TIME_TABLES = {"shipping_stats", "inbound_slip"}

UNIQUE_KEY: dict[str, list[str] | None] = {
    "shipping_stats": None,
    "inbound_slip":   None,
    "work_log":       None,
    "kpost_in":       None,
    "kpost_ret":      None,
}

# ───────────── 헬퍼 ──────────────────────────────────────
def _md5(file) -> str:
    pos = file.tell(); file.seek(0)
    h = hashlib.md5()
    for chunk in iter(lambda: file.read(1 << 20), b""): h.update(chunk)
    file.seek(pos); return h.hexdigest()

def _save_file_to_disk(file):
    fname = f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex}.xlsx"
    path  = UPLOAD_DIR / fname
    with open(path, "wb") as out:
        shutil.copyfileobj(file, out)
    return path, fname

# ───────────── 인제스트 ─────────────────────────────────
def ingest(file, table: TableName) -> None:
    file_hash = _md5(file); file.seek(0)          # rewind!

    # 1) uploads 테이블 + 필드 보장
    with get_conn() as con:
        con.execute("""
          CREATE TABLE IF NOT EXISTS uploads (
            filename    TEXT,
            orig_name   TEXT,
            table_name  TEXT,
            date_min    TEXT,
            date_max    TEXT,
            file_hash   TEXT UNIQUE,
            uploaded_at TEXT
          )
        """)
        for col in ("orig_name", "file_hash"):
            try: con.execute(f"ALTER TABLE uploads ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError: pass
        con.commit()

    # 2) 파일-중복 차단
    with get_conn() as con:
        if con.execute("SELECT 1 FROM uploads WHERE file_hash=? LIMIT 1",
                       (file_hash,)).fetchone():
            raise ValueError("⚠️ 이미 동일한 파일을 업로드했습니다.")

    # 3) 저장 + DataFrame ------------------------------------------------
    from utils.clean import TRACK_COLS, normalize_tracking  # local import to avoid cycle

    path, fname = _save_file_to_disk(file)

    read_kwargs = {}
    if table == "kpost_in":
        # 1️⃣ 지정 컬럼 str dtype 강제
        read_kwargs["dtype"] = {col: "string" for col in TRACK_COLS}

    df = pd.read_excel(path, **read_kwargs)

    # 2️⃣ 송장번호 정규화
    if table == "kpost_in":
        for col in TRACK_COLS:
            if col in df.columns:
                df[col] = normalize_tracking(df[col])

    # 4) 시간 포함 열 → 날짜 전용
    if table in TIME_TABLES:
        col = DATE_COL[table]
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df[f"{col}_날짜"] = df[col].dt.date

    # 5) 행-중복 제거 ────────────────────────────────────
    key_cols = UNIQUE_KEY.get(table)
    if key_cols:
        try:
            # 테이블이 이미 있으면 기존 키 목록을 읽어 온다
            with get_conn() as con:
                existed = pd.read_sql(
                    f"SELECT {','.join(key_cols)} FROM {table}", con
                )
        except sqlite3.OperationalError:
            # 테이블이 아직 없으면 중복 비교 대상이 없음
            existed = pd.DataFrame(columns=key_cols)

        # existed 와 합쳐서 중복 행 제거
        df = (
            df.merge(existed, on=key_cols, how="left", indicator=True)
              .query("_merge == 'left_only'")
              .drop(columns="_merge")
        )


    # 6) 날짜 범위
    series = (pd.to_datetime(df[f"{DATE_COL[table]}_날짜"], errors="coerce")
              if table in TIME_TABLES else
              pd.to_datetime(df[DATE_COL.get(table, "")], errors="coerce")).dropna()
    d_min = series.min().date().isoformat() if not series.empty else ""
    d_max = series.max().date().isoformat() if not series.empty else ""

    # 7) DB 적재 + 메타 INSERT
    with get_conn() as con:
        df.to_sql(table, con, if_exists="append", index=False)
        con.execute("""
          INSERT INTO uploads
            (filename, orig_name, table_name,
             date_min, date_max, file_hash, uploaded_at)
          VALUES (?,?,?,?,?,?,datetime('now'))
        """, (fname, file.name, table, d_min, d_max, file_hash))
        con.commit()

# ───────────── 이력 조회 ────────────────────────────────
def list_uploads() -> pd.DataFrame:
    must_cols = ["orig_name","table_name","date_min","date_max",
                 "file_hash","uploaded_at"]
    with get_conn() as con:
        con.execute("CREATE TABLE IF NOT EXISTS uploads (filename TEXT)")
        for c in must_cols:
            try: con.execute(f"ALTER TABLE uploads ADD COLUMN {c} TEXT")
            except sqlite3.OperationalError: pass
        return pd.read_sql("""
          SELECT rowid AS id,
                 filename,
                 COALESCE(orig_name,'') AS 원본명,
                 table_name,
                 date_min  AS 시작일,
                 date_max  AS 종료일,
                 uploaded_at AS 업로드시각
          FROM uploads
          ORDER BY uploaded_at DESC
        """, con)