"""
logic/upload.py - 파일 업로드 로직
────────────────────────────────────────────────────────────
Excel(xlsx) 업로드 → 지정 테이블 적재 + uploads 메타 기록
  • 파일은 "타임스탬프_UUID.xlsx" 로 저장 (Windows 경로 안전)
  • uploads: filename · orig_name · table · date_min/max · file_hash · ts
  • file_hash UNIQUE → 동일 파일 두 번 못 올림
  • 테이블별 UNIQUE_KEY 로 행-중복 제거
  • 시간 포함 테이블(shipping_stats·inbound_slip) → 날짜 전용 컬럼 추가

순수 Python 함수 (FastAPI 백엔드에서 사용).
"""

from __future__ import annotations

import hashlib
import shutil
import datetime as dt
import uuid
import sqlite3
import os
from pathlib import Path
from typing import Literal, BinaryIO, Tuple

import pandas as pd
import re

from .db import get_connection, ensure_column


# ───────────── 한국어 날짜 파싱 ─────────────────────────────────
def _parse_korean_date(date_str: str, default_year: int = None) -> pd.Timestamp:
    """
    한국어 날짜 형식을 파싱합니다.
    지원 형식:
      - "1월 2일", "1월2일"
      - "2025년 1월 2일", "2025년1월2일"
      - "25년 1월 2일"
    """
    if pd.isna(date_str):
        return pd.NaT
    
    date_str = str(date_str).strip()
    if not date_str:
        return pd.NaT
    
    # 기본 연도 설정
    if default_year is None:
        default_year = dt.datetime.now().year
    
    # 패턴 1: "2025년 1월 2일" 또는 "25년 1월 2일"
    match = re.match(r'(\d{2,4})년\s*(\d{1,2})월\s*(\d{1,2})일?', date_str)
    if match:
        year = int(match.group(1))
        if year < 100:  # 2자리 연도
            year = 2000 + year
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return pd.Timestamp(year=year, month=month, day=day)
        except:
            return pd.NaT
    
    # 패턴 2: "1월 2일" 또는 "1월2일"
    match = re.match(r'(\d{1,2})월\s*(\d{1,2})일?', date_str)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        try:
            return pd.Timestamp(year=default_year, month=month, day=day)
        except:
            return pd.NaT
    
    return pd.NaT


def _parse_date_column(series: pd.Series, default_year: int = None) -> pd.Series:
    """
    날짜 컬럼을 파싱합니다. 표준 형식 우선, 실패시 한국어 형식 시도.
    """
    # 먼저 표준 datetime 파싱 시도
    result = pd.to_datetime(series, errors='coerce')
    
    # NaT인 값들에 대해 한국어 날짜 파싱 시도
    nat_mask = result.isna() & series.notna()
    if nat_mask.any():
        korean_parsed = series[nat_mask].apply(
            lambda x: _parse_korean_date(x, default_year)
        )
        result.loc[nat_mask] = korean_parsed
    
    return result
from .clean import TRACK_COLS, normalize_tracking


def _normalize_worklog_date_col(series: pd.Series) -> pd.Series:
    """work_log 날짜를 YYYY-MM-DD 문자열로 정규화한다.
    
    '3월 4일', '2025년 3월 4일' 등 한국어 형식도 변환한다.
    이미 datetime이면 strftime으로 변환한다.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y-%m-%d")

    current_year = dt.datetime.now().year

    def _convert(val):
        if pd.isna(val) or val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        if re.match(r'^\d{4}-\d{2}-\d{2}', s):
            return s[:10]
        m = re.match(r'(\d{2,4})년\s*(\d{1,2})월\s*(\d{1,2})일?', s)
        if m:
            y = int(m.group(1))
            if y < 100:
                y = 2000 + y
            return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m = re.match(r'(\d{1,2})월\s*(\d{1,2})일?', s)
        if m:
            return f"{current_year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        try:
            ts = pd.to_datetime(s)
            return ts.strftime("%Y-%m-%d")
        except Exception:
            return val

    return series.apply(_convert)

# 저장 폴더 - 환경변수 우선, 없으면 절대경로 사용
def _get_upload_dir() -> Path:
    """업로드 디렉토리 경로 반환 (지연 초기화)"""
    env_dir = os.getenv("UPLOAD_DIR")
    if env_dir:
        return Path(env_dir)
    # Docker/Railway 환경 감지
    if os.path.exists("/app/data"):
        return Path("/app/data/uploads")
    return Path("data/uploads")

UPLOAD_DIR = _get_upload_dir()

# 주의: 디렉토리 생성은 런타임에 _save_file_to_disk()에서 수행

# 날짜 컬럼 정의
TableName = Literal[
    "inbound_slip", "shipping_stats",
    "kpost_in", "kpost_ret", "work_log",
]

DATE_COL = {
    "inbound_slip": "작업일",
    "shipping_stats": "배송일",
    "kpost_in": "접수일자",
    "kpost_ret": "배달일자",
    "work_log": "날짜",
}

TIME_TABLES = {"shipping_stats", "inbound_slip"}

UNIQUE_KEY: dict[str, list[str] | None] = {
    "shipping_stats": ["송장번호", "배송일"],
    "inbound_slip": ["상품코드", "작업일", "수량"],
    "work_log": ["날짜", "업체명", "분류", "수량", "단가"],  # 단가 추가!
    "kpost_in": ["등기번호"],
    "kpost_ret": ["등기번호", "배달일자"],
}


# ───────────── 헬퍼 ──────────────────────────────────────
def _md5(file: BinaryIO) -> str:
    """파일의 MD5 해시값 계산."""
    pos = file.tell()
    file.seek(0)
    h = hashlib.md5()
    for chunk in iter(lambda: file.read(1 << 20), b""):
        h.update(chunk)
    file.seek(pos)
    return h.hexdigest()


def _save_file_to_disk(file: BinaryIO, orig_name: str = "") -> Tuple[Path, str]:
    """파일을 디스크에 저장."""
    # 디렉토리가 없으면 생성 (런타임 보장)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    fname = f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex}.xlsx"
    path = UPLOAD_DIR / fname
    with open(path, "wb") as out:
        file.seek(0)
        shutil.copyfileobj(file, out)
    return path, fname


# ───────────── HTML/Excel 파일 읽기 ─────────────────────
def _read_excel_or_html(path: Path, **kwargs) -> pd.DataFrame:
    """
    Excel 파일 또는 HTML 형식의 XLS 파일을 읽습니다.
    
    일부 시스템에서는 .xls 확장자로 HTML 테이블을 내보내기 때문에
    파일 내용을 확인하여 적절한 방법으로 읽습니다.
    
    여러 시트가 있는 경우 데이터가 있는 첫 번째 시트를 자동으로 선택합니다.
    """
    # 파일 시작 부분을 읽어서 HTML인지 확인
    with open(path, 'rb') as f:
        header = f.read(1024).lower()
    
    # HTML 시그니처 확인
    is_html = (
        b'<html' in header or 
        b'<!doctype html' in header or
        b'<table' in header or
        b'<meta' in header or
        b'<?xml' in header  # XML 스프레드시트도 처리
    )
    
    if is_html:
        try:
            # HTML 테이블로 읽기 (header=0: 첫 번째 행을 헤더로 사용)
            tables = pd.read_html(path, header=0, **{k: v for k, v in kwargs.items() if k != 'dtype'})
            if tables:
                df = tables[0]  # 첫 번째 테이블 사용
                
                # 숫자 인덱스 컬럼인 경우 첫 번째 행을 헤더로 변환
                if all(isinstance(c, (int, float)) for c in df.columns):
                    df.columns = df.iloc[0].astype(str).str.strip()
                    df = df[1:].reset_index(drop=True)
                
                # dtype 적용 (문자열 타입 변환)
                if 'dtype' in kwargs:
                    for col, dtype in kwargs['dtype'].items():
                        if col in df.columns:
                            df[col] = df[col].astype(dtype)
                return df
            else:
                raise ValueError("HTML 파일에 테이블이 없습니다.")
        except Exception as e:
            # HTML 읽기 실패 시 Excel로 시도
            print(f"HTML 읽기 실패, Excel로 재시도: {e}")
            return _read_excel_with_best_sheet(path, **kwargs)
    else:
        # 일반 Excel 파일 - 여러 시트 중 데이터가 있는 시트 선택
        return _read_excel_with_best_sheet(path, **kwargs)


def _read_excel_with_best_sheet(path: Path, **kwargs) -> pd.DataFrame:
    """
    Excel 파일에서 데이터가 있는 최적의 시트를 자동으로 선택하여 읽습니다.
    
    여러 시트가 있는 경우:
    1. 각 시트를 확인하여 데이터가 있는 시트 목록 생성
    2. 가장 많은 행을 가진 시트 선택
    """
    try:
        xl = pd.ExcelFile(path)
        sheet_names = xl.sheet_names
        
        if len(sheet_names) == 1:
            # 시트가 하나면 그냥 읽기
            return pd.read_excel(path, **kwargs)
        
        # 여러 시트가 있는 경우, 데이터가 있는 시트 찾기
        best_sheet = None
        best_row_count = 0
        
        for sheet_name in sheet_names:
            try:
                # 빠른 확인을 위해 처음 몇 행만 읽기
                df_check = pd.read_excel(path, sheet_name=sheet_name, nrows=5)
                if len(df_check.columns) > 0 and len(df_check) > 0:
                    # 전체 행 수 확인
                    df_full = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
                    if len(df_full) > best_row_count:
                        best_row_count = len(df_full)
                        best_sheet = sheet_name
            except Exception:
                continue
        
        if best_sheet:
            return pd.read_excel(path, sheet_name=best_sheet, **kwargs)
        
        # 데이터가 있는 시트를 찾지 못한 경우 기본 시트 사용
        return pd.read_excel(path, **kwargs)
        
    except Exception:
        # ExcelFile 생성 실패 시 기본 방식으로 읽기
        return pd.read_excel(path, **kwargs)


# ───────────── 인제스트 ─────────────────────────────────
def ingest(
    file: BinaryIO,
    table: TableName,
    orig_name: str = ""
) -> Tuple[bool, str]:
    """
    Excel 파일을 DB에 적재.
    
    Args:
        file: 업로드된 파일 (바이너리 모드)
        table: 대상 테이블명
        orig_name: 원본 파일명
    
    Returns:
        (성공 여부, 메시지)
    """
    file_hash = _md5(file)
    file.seek(0)

    # 1) uploads 테이블 + 필드 보장
    with get_connection() as con:
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
            try:
                con.execute(f"ALTER TABLE uploads ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        con.commit()

    # 2) 파일-중복 차단
    with get_connection() as con:
        if con.execute(
            "SELECT 1 FROM uploads WHERE file_hash=? LIMIT 1",
            (file_hash,)
        ).fetchone():
            return False, "⚠️ 이미 동일한 파일을 업로드했습니다."

    # 3) 저장 + DataFrame
    path, fname = _save_file_to_disk(file, orig_name)

    # 송장/등기번호 컬럼을 문자열로 읽기 (모든 테이블 공통)
    read_kwargs = {"dtype": {col: "string" for col in TRACK_COLS}}

    # HTML 형식 XLS 파일 감지 및 처리
    try:
        df = _read_excel_or_html(path, **read_kwargs)
    except Exception as e:
        return False, f"⚠️ 파일 읽기 실패: {str(e)}"
    
    # 컬럼명 정리 (공백 제거, 줄바꿈 제거, 특수 공백 문자 제거)
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace(r'[\n\r\t\xa0]', '', regex=True)  # 줄바꿈, 탭, 비표준 공백 제거
        .str.replace(r'\s+', ' ', regex=True)  # 연속 공백을 단일 공백으로
        .str.strip()  # 다시 양쪽 공백 제거
    )

    # 송장번호 정규화 (해당 컬럼이 있는 모든 테이블에 적용)
    for col in TRACK_COLS:
        if col in df.columns:
            df[col] = normalize_tracking(df[col])

    # 4) 날짜 컬럼 파싱 (모든 테이블에 적용)
    date_col = DATE_COL.get(table)
    if date_col and date_col in df.columns:
        # 한국어 날짜 형식 지원 ("1월 2일", "2025년 1월 2일" 등)
        df[date_col] = _parse_date_column(df[date_col])
        
        # 시간 포함 테이블은 별도의 날짜 전용 컬럼 추가
        if table in TIME_TABLES:
            df[f"{date_col}_날짜"] = df[date_col].dt.date
    elif date_col:
        # 필수 날짜 컬럼이 없으면 에러
        # 디버깅: 컬럼명과 유사한 컬럼 찾기
        similar_cols = [c for c in df.columns if date_col.replace(' ', '') in c.replace(' ', '')]
        available_cols = ", ".join([f"'{c}'" for c in df.columns.tolist()[:15]])
        
        if similar_cols:
            return False, f"⚠️ 필수 컬럼 '{date_col}'이(가) 없습니다. 유사한 컬럼 발견: {similar_cols}. 파일의 컬럼: {available_cols}"
        return False, f"⚠️ 필수 컬럼 '{date_col}'이(가) 없습니다. 파일의 컬럼: {available_cols}"

    # 5) 행-중복 제거
    # work_log: pandas 비교 불안정 → 전체 삽입 후 SQL dedup 방식 사용 (8단계에서 처리)
    # 그 외 테이블: set 기반 pandas dedup
    key_cols = UNIQUE_KEY.get(table)
    date_col = DATE_COL.get(table)
    if key_cols and table != "work_log":
        try:
            with get_connection() as con:
                col_sql = ", ".join(f"[{c}]" for c in key_cols)
                existed = pd.read_sql(
                    f"SELECT {col_sql} FROM {table}", con
                )
        except sqlite3.OperationalError:
            existed = pd.DataFrame(columns=key_cols)

        def _to_key_str(row):
            parts = []
            for kc in key_cols:
                v = row.get(kc, "")
                if pd.isna(v) or v is None:
                    parts.append("__NA__")
                elif isinstance(v, float):
                    parts.append(str(int(v)) if v == int(v) else str(v))
                else:
                    s = str(v).strip()
                    if len(s) > 10 and s[4] == '-' and s[7] == '-':
                        s = s[:10]
                    parts.append(s)
            return "|".join(parts)

        df_for_key = df.copy()
        if date_col and date_col in df_for_key.columns:
            if pd.api.types.is_datetime64_any_dtype(df_for_key[date_col]):
                df_for_key[date_col] = df_for_key[date_col].dt.strftime('%Y-%m-%d')

        new_keys = df_for_key[key_cols].apply(_to_key_str, axis=1)

        if date_col and date_col in existed.columns:
            existed[date_col] = pd.to_datetime(
                existed[date_col], errors='coerce'
            ).dt.strftime('%Y-%m-%d').fillna('')
        existed_keys = set(existed[key_cols].apply(_to_key_str, axis=1))

        mask = ~new_keys.isin(existed_keys)
        df = df[mask].reset_index(drop=True)

        if date_col and date_col in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

    # 6-1) work_log: 출처='excel' 기본값 설정 + 날짜 YYYY-MM-DD 정규화 + 업체명 null 필터링
    if table == "work_log":
        if "출처" not in df.columns:
            df["출처"] = "excel"
        else:
            df["출처"] = df["출처"].fillna("excel")
        date_col_wl = DATE_COL.get(table, "")
        if date_col_wl and date_col_wl in df.columns:
            df[date_col_wl] = _normalize_worklog_date_col(df[date_col_wl])
        # 업체명 없는 행 제거 (인보이스 계산에 반영되지 않으므로)
        if "업체명" in df.columns:
            before = len(df)
            df = df[df["업체명"].notna() & (df["업체명"].astype(str).str.strip() != "")]
            df = df.reset_index(drop=True)
            removed = before - len(df)
            if removed > 0:
                print(f"[work_log] 업체명 없는 행 {removed}건 제외")

    # 6) 날짜 범위 (이미 파싱된 날짜 컬럼 사용)
    date_col_name = DATE_COL.get(table, "")
    if date_col_name and date_col_name in df.columns:
        series = pd.to_datetime(df[date_col_name], errors="coerce")
    else:
        series = pd.Series(dtype='datetime64[ns]')
    series = series.dropna()
    d_min = series.min().date().isoformat() if not series.empty else ""
    d_max = series.max().date().isoformat() if not series.empty else ""

    # 7) 테이블에 없는 컬럼 자동 추가
    with get_connection() as con:
        # 테이블이 없으면 생성 (ensure_tables가 이미 했지만 안전장치)
        existing_cols = []
        try:
            existing_cols = [c[1] for c in con.execute(f"PRAGMA table_info({table});")]
        except sqlite3.OperationalError:
            # 테이블이 없으면 빈 리스트로 시작
            existing_cols = []
        
        # DataFrame의 모든 컬럼 확인 및 추가
        for col in df.columns:
            # 컬럼명 그대로 사용 (공백, 특수문자 포함)
            if col not in existing_cols:
                # 숫자 컬럼인지 확인하여 적절한 타입 지정
                if df[col].dtype in ['int64', 'Int64']:
                    coltype = "INTEGER"
                elif df[col].dtype in ['float64', 'Float64']:
                    coltype = "REAL"
                else:
                    coltype = "TEXT"
                # 특수문자 포함 컬럼명을 대괄호로 감싸서 추가
                try:
                    con.execute(f'ALTER TABLE [{table}] ADD COLUMN [{col}] {coltype};')
                    existing_cols.append(col)  # 추가된 컬럼을 리스트에 추가
                except sqlite3.OperationalError as e:
                    # 이미 존재하는 컬럼이거나 다른 오류
                    err_msg = str(e).lower()
                    if "duplicate column" not in err_msg and "already exists" not in err_msg:
                        # 다른 오류는 재발생
                        raise
        con.commit()
    
    # 8) DB 적재 + 메타 INSERT
    with get_connection() as con:
        try:
            df.to_sql(table, con, if_exists="append", index=False)
        except (sqlite3.OperationalError, ValueError) as e:
            # 컬럼 누락 에러인 경우 다시 컬럼 추가 시도
            err_msg = str(e)
            if "no such column" in err_msg.lower() or "has no column" in err_msg.lower():
                # 누락된 컬럼 찾기
                missing_col = None
                for col in df.columns:
                    if col.lower() in err_msg.lower() or col in err_msg:
                        missing_col = col
                        break
                
                if missing_col:
                    # 컬럼 추가 재시도
                    if df[missing_col].dtype in ['int64', 'Int64']:
                        coltype = "INTEGER"
                    elif df[missing_col].dtype in ['float64', 'Float64']:
                        coltype = "REAL"
                    else:
                        coltype = "TEXT"
                    con.execute(f'ALTER TABLE [{table}] ADD COLUMN [{missing_col}] {coltype};')
                    con.commit()
                    # 다시 시도
                    df.to_sql(table, con, if_exists="append", index=False)
                else:
                    raise
            else:
                raise
        # work_log: INSERT 후 SQL로 중복 제거 (날짜+업체명+분류+수량+단가 기준)
        # bot 행은 절대 삭제하지 않고, excel 행 중 중복만 제거
        if table == "work_log":
            count_before_dedup = con.execute("SELECT COUNT(*) FROM work_log WHERE 출처='excel'").fetchone()[0]
            con.execute("""
                DELETE FROM work_log
                WHERE 출처 = 'excel'
                AND id NOT IN (
                    SELECT MIN(id) FROM work_log
                    GROUP BY [날짜], [업체명], [분류], [수량], [단가]
                )
            """)
            count_after_dedup = con.execute("SELECT COUNT(*) FROM work_log WHERE 출처='excel'").fetchone()[0]
            dedup_removed = count_before_dedup - count_after_dedup
            saved_count = len(df) - dedup_removed
            print(f"[work_log] 삽입 {len(df)}건, 중복제거 {dedup_removed}건, 최종저장 {saved_count}건")

        con.execute("""
          INSERT INTO uploads
            (filename, orig_name, table_name,
             date_min, date_max, file_hash, uploaded_at)
          VALUES (?,?,?,?,?,?,datetime('now'))
        """, (fname, orig_name or getattr(file, 'name', fname), table, d_min, d_max, file_hash))
        con.commit()

    if table == "work_log":
        return True, f"✅ {table} 테이블에 {saved_count}건 적재 완료 (중복 {dedup_removed}건 제거)"
    return True, f"✅ {table} 테이블에 {len(df)}건 적재 완료"


# ───────────── 이력 조회 ────────────────────────────────
def list_uploads() -> pd.DataFrame:
    """업로드 이력 조회."""
    must_cols = [
        "orig_name", "table_name", "date_min", "date_max",
        "file_hash", "uploaded_at"
    ]
    with get_connection() as con:
        con.execute("CREATE TABLE IF NOT EXISTS uploads (filename TEXT)")
        for c in must_cols:
            try:
                con.execute(f"ALTER TABLE uploads ADD COLUMN {c} TEXT")
            except sqlite3.OperationalError:
                pass
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


def delete_upload(upload_id: int) -> Tuple[bool, str]:
    """업로드 기록 삭제 (파일은 유지)."""
    with get_connection() as con:
        cur = con.execute(
            "DELETE FROM uploads WHERE rowid = ?",
            (upload_id,)
        )
        if cur.rowcount == 0:
            return False, "❌ 해당 업로드 기록을 찾을 수 없습니다."
        con.commit()
    return True, "✅ 업로드 기록이 삭제되었습니다."

