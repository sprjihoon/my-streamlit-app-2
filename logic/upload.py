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
    "work_log": ["no", "날짜", "업체명"],  # no+날짜+업체명: no는 월마다·파일마다 리셋되므로 업체명 포함해야 유니크
    "kpost_in": ["등기번호"],
    "kpost_ret": ["등기번호", "배달일자"],
}

# 우체국 데이터 허용 컬럼 (화이트리스트)
# 계산에 필요한 컬럼만 DB에 저장 — 이름·주소·전화번호 등 개인정보는 자동 제외
KPOST_ALLOWED_COLS: dict[str, set[str]] = {
    "kpost_in": {
        "발송인명",    # 거래처 필터링 키 (업체명)
        "접수일자",    # 날짜 필터
        "우편물부피",  # 사이즈 구간 계산 (신버전, 숫자 cm)
        "부피",        # 사이즈 구간 계산 (구버전 호환, 숫자 cm)
        "규격",        # 사이즈 구간 계산 (텍스트 구간명: 극소/소/중/대/특대)
        "등기번호",    # 중복 제거 키
        "도서행",      # 도서산간 여부
    },
    "kpost_ret": {
        "수취인명",    # 거래처 필터링 키 (업체명)
        "배달일자",    # 날짜 필터
        "우편물부피",  # 사이즈 구간 계산
        "등기번호",    # 중복 제거 키
        "수량",        # 건수 집계
    },
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


def _count_meaningful_rows(df: pd.DataFrame) -> int:
    """'no', 'Unnamed' 컬럼을 제외한 실제 데이터 행 수 반환."""
    meaningful_cols = [
        c for c in df.columns
        if str(c).strip() != 'no' and not str(c).startswith('Unnamed')
    ]
    if not meaningful_cols:
        meaningful_cols = list(df.columns)
    return int(df[meaningful_cols].notna().any(axis=1).sum())


def _read_excel_with_best_sheet(path: Path, **kwargs) -> pd.DataFrame:
    """
    Excel 파일에서 실제 데이터가 가장 많은 시트를 선택하여 읽습니다.
    
    시트 선택 기준: 의미있는 컬럼(no·Unnamed 제외)의 non-null 행 수
    → 빈 템플릿 행(no열만 채워진)이 많은 시트가 잘못 선택되는 버그 방지
    """
    try:
        with pd.ExcelFile(path) as xl:
            sheet_names = xl.sheet_names

            if len(sheet_names) == 1:
                return pd.read_excel(xl, **kwargs)

            best_sheet = None
            best_row_count = 0

            for sheet_name in sheet_names:
                try:
                    df_check = pd.read_excel(xl, sheet_name=sheet_name, nrows=5)
                    if len(df_check.columns) > 0 and len(df_check) > 0:
                        df_full = pd.read_excel(xl, sheet_name=sheet_name, **kwargs)
                        # 의미있는 데이터 행수 기준으로 최적 시트 선택
                        meaningful_count = _count_meaningful_rows(df_full)
                        if meaningful_count > best_row_count:
                            best_row_count = meaningful_count
                            best_sheet = sheet_name
                except Exception:
                    continue

            if best_sheet:
                return pd.read_excel(xl, sheet_name=best_sheet, **kwargs)

            return pd.read_excel(xl, **kwargs)

    except Exception:
        return pd.read_excel(path, **kwargs)


def _patch_openpyxl_filters():
    """openpyxl CustomFilter.val 세터의 ValueError를 무시하도록 패치.
    
    일부 Excel 파일의 자동 필터 조건 값이
    'Value must be either numerical or a string containing a wildcard' 오류를
    발생시키는 버그(openpyxl filters.py)를 우회합니다.
    """
    try:
        from openpyxl.worksheet import filters as _filters
        if getattr(_filters, "_patched_safe", False):
            return

        # CustomFilter.__init__ 을 감싸서 val 설정 시 ValueError 무시
        _orig_cf_init = _filters.CustomFilter.__init__

        def _safe_cf_init(self, *args, **kwargs):
            try:
                _orig_cf_init(self, *args, **kwargs)
            except (ValueError, TypeError):
                # val 설정 실패 시 빈 문자열로 대체
                if not hasattr(self, "val"):
                    try:
                        object.__setattr__(self, "val", "")
                    except Exception:
                        pass

        _filters.CustomFilter.__init__ = _safe_cf_init

        # 혹시 from_tree 경로도 막기: Serialisable.from_tree 래핑
        from openpyxl.descriptors.serialisable import Serialisable
        _orig_from_tree = Serialisable.from_tree.__func__ if hasattr(Serialisable.from_tree, '__func__') else None
        if _orig_from_tree is None:
            _orig_from_tree = Serialisable.from_tree

        @classmethod  # type: ignore[misc]
        def _safe_from_tree(cls, el):
            try:
                return _orig_from_tree(cls, el)
            except (ValueError, TypeError):
                return cls.__new__(cls)

        # CustomFilter 에만 적용
        _filters.CustomFilter.from_tree = _safe_from_tree

        _filters._patched_safe = True
    except Exception:
        pass


def _read_excel_readonly_fallback(path: Path, **kwargs) -> pd.DataFrame:
    """openpyxl read_only 모드로 Excel 읽기.
    
    데이터 유효성 검사 규칙 파싱 오류를 우회하기 위해
    read_only=True로 열어 파싱 단계를 건너뜁니다.
    """
    import openpyxl
    dtype = kwargs.get("dtype", {})
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    dfs = []
    for ws in wb.worksheets:
        try:
            rows = list(ws.values)
        except Exception:
            continue
        if not rows:
            continue
        headers = [str(c) if c is not None else f"Unnamed:{i}" for i, c in enumerate(rows[0])]
        df_sheet = pd.DataFrame(rows[1:], columns=headers)
        for col, dt in dtype.items():
            if col in df_sheet.columns:
                try:
                    df_sheet[col] = df_sheet[col].astype(dt)
                except Exception:
                    pass
        if _count_meaningful_rows(df_sheet) > 0:
            dfs.append(df_sheet)
    wb.close()
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def _read_all_sheets_concat(path: Path, **kwargs) -> pd.DataFrame:
    """모든 시트를 읽어 하나의 DataFrame으로 합칩니다 (work_log 연간 파일용).
    
    합산 시트나 중복 시트가 포함된 경우를 대비해 concat 후
    no+날짜+업체명 기준으로 시트간 중복 행을 제거합니다.
    openpyxl 데이터 유효성 오류 발생 시 패치 후 재시도, 그래도 실패하면
    read_only 모드로 자동 재시도합니다.
    """
    def _do_concat(xl) -> pd.DataFrame:
        dfs = []
        for sheet_name in xl.sheet_names:
            try:

                df_sheet = pd.read_excel(xl, sheet_name=sheet_name, **kwargs)
                if _count_meaningful_rows(df_sheet) > 0:
                    dfs.append(df_sheet)
            except Exception:
                continue
        if dfs:
            df_concat = pd.concat(dfs, ignore_index=True)
            dedup_cols = [c for c in ["no", "날짜", "업체명"] if c in df_concat.columns]
            if len(dedup_cols) >= 2:
                before = len(df_concat)
                df_concat = df_concat.drop_duplicates(subset=dedup_cols, keep="first")
                removed = before - len(df_concat)
                if removed > 0:
                    print(f"[work_log] 시트간 중복 {removed}건 제거")
            return df_concat.reset_index(drop=True)
        return pd.read_excel(xl, **kwargs)

    try:
        with pd.ExcelFile(path) as xl:
            return _do_concat(xl)
    except (ValueError, TypeError):
        # openpyxl 데이터 유효성 규칙 파싱 오류 → 패치 후 재시도, 그래도 실패하면 read_only
        print("[work_log] openpyxl 데이터 유효성 오류 감지, 패치 후 재시도")
        _patch_openpyxl_filters()
        try:
            with pd.ExcelFile(path) as xl:
                return _do_concat(xl)
        except Exception:
            print("[work_log] 패치 후에도 실패, read_only 모드로 재시도")
            return _read_excel_readonly_fallback(path, **kwargs)
    except Exception:
        try:
            return _read_excel_readonly_fallback(path, **kwargs)
        except Exception:
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

    # 3) 임시 저장 → DataFrame 읽기 → 원본 파일 즉시 삭제
    path, fname = _save_file_to_disk(file, orig_name)

    # 송장/등기번호 컬럼을 문자열로 읽기 (모든 테이블 공통)
    read_kwargs = {"dtype": {col: "string" for col in TRACK_COLS}}

    # HTML 형식 XLS 파일 감지 및 처리
    # work_log: 연간 파일(월별 시트)이면 모든 시트를 합쳐서 읽기
    try:
        if table == "work_log":
            df = _read_all_sheets_concat(path, **read_kwargs)
        else:
            df = _read_excel_or_html(path, **read_kwargs)
    except Exception as e:
        # 마지막 수단: openpyxl 패치 후 read_only fallback 직접 시도
        if table == "work_log":
            try:
                _patch_openpyxl_filters()
                df = _read_excel_readonly_fallback(path, **read_kwargs)
            except Exception:
                return False, f"⚠️ 파일 읽기 실패: {str(e)}"
        else:
            return False, f"⚠️ 파일 읽기 실패: {str(e)}"
    finally:
        # 성공/실패 여부에 관계없이 원본 파일 즉시 삭제 (개인정보 보호)
        path.unlink(missing_ok=True)
    
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

    # 3-1) 개인정보 보호: kpost_in / kpost_ret 화이트리스트 필터링
    # 계산에 필요한 컬럼만 유지하고, 이름·주소·전화번호 등은 DB에 저장하지 않음
    if table in KPOST_ALLOWED_COLS:
        allowed = KPOST_ALLOWED_COLS[table]
        df = df[[c for c in df.columns if c in allowed]]

    # 4) 날짜 컬럼 파싱 (모든 테이블에 적용)
    date_col = DATE_COL.get(table)
    if date_col and date_col in df.columns:
        # 한국어 날짜 형식 지원 ("1월 2일", "2025년 1월 2일" 등)
        df[date_col] = _parse_date_column(df[date_col])

        # 날짜 없는 행 제거 (다른 시트의 메모·목록 행 등이 혼입되는 것 방지)
        before = len(df)
        df = df[df[date_col].notna()].reset_index(drop=True)
        removed = before - len(df)
        if removed > 0:
            print(f"[{table}] 날짜 없는 행 {removed}건 제외")

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

    # 5) 행-중복 제거 (set 기반 pandas dedup)
    # work_log: no+날짜 조합으로 중복 제거. no 컬럼이 없는 구형 파일은 건너뜀.
    key_cols = UNIQUE_KEY.get(table)
    date_col = DATE_COL.get(table)

    # work_log이고 no 컬럼이 없는 구형 파일 → dedup 불가, 건너뜀
    if table == "work_log" and "no" not in df.columns:
        key_cols = None

    if key_cols:
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
        con.execute("""
          INSERT INTO uploads
            (filename, orig_name, table_name,
             date_min, date_max, file_hash, uploaded_at)
          VALUES (?,?,?,?,?,?,datetime('now', '+9 hours'))
        """, (fname, orig_name or getattr(file, 'name', fname), table, d_min, d_max, file_hash))
        con.commit()

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

