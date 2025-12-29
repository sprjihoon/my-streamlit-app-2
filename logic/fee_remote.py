"""
logic/fee_remote.py - 도서산간 요금 계산
───────────────────────────────────────────
공급처 + 날짜 기준으로 kpost_in에서 '도서행' == 'y'인 건수 계산,
단가(out_extra) 적용.

Streamlit 의존성 제거 - 순수 Python 함수.
"""
import sqlite3
from typing import List, Dict, Tuple, Optional

import pandas as pd

from .db import get_connection


def add_remote_area_fee(
    vendor: str,
    d_from: str,
    d_to: str,
    items: List[Dict],
    db_path: str = "billing.db"
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    공급처 + 날짜 기준으로 kpost_in에서 '도서행' == 'y'인 건수 계산,
    단가(out_extra) 적용 → '도서산간' 항목 인보이스에 추가.
    
    Args:
        vendor: 공급처명
        d_from: 시작일 (YYYY-MM-DD)
        d_to: 종료일 (YYYY-MM-DD)
        items: 인보이스 항목 리스트 (in-place 수정)
        db_path: 데이터베이스 경로
    
    Returns:
        (성공 여부, 오류 메시지, 정보 메시지)
    """
    try:
        with get_connection() as con:
            # 필수 테이블 존재 확인
            tables = [
                row[0] for row in
                con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ]

            if "kpost_in" not in tables:
                return True, None, f"📭 '{vendor}' kpost_in 테이블이 없어 도서산간 계산을 건너뜁니다."

            # ① 공급처 + 별칭 목록
            name_list = [vendor]
            if "aliases" in tables:
                try:
                    alias_df = pd.read_sql(
                        "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'kpost_in'",
                        con, params=(vendor,)
                    )
                    name_list.extend(alias_df["alias"].astype(str).str.strip().tolist())
                except Exception:
                    pass

            # ② kpost_in 필터 + 도서행 여부 확인
            try:
                df = pd.read_sql(
                    f"""
                    SELECT 도서행 FROM kpost_in
                    WHERE TRIM(발송인명) IN ({','.join('?' * len(name_list))})
                      AND 접수일자 BETWEEN ? AND ?
                    """, con, params=(*name_list, d_from, d_to)
                )
            except Exception as e:
                return True, None, f"📭 '{vendor}' kpost_in 조회 실패: {str(e)[:100]}"

        if df.empty or "도서행" not in df.columns:
            return True, None, f"📭 '{vendor}' 도서산간 데이터 없음 or '도서행' 칼럼 없음"

        df["도서행"] = df["도서행"].astype(str).str.lower().str.strip()
        qty = df[df["도서행"] == "y"].shape[0]

        info_msg = f"✅ {vendor} 도서산간 적용 수량: {qty}"

        if qty == 0:
            return True, None, info_msg

        try:
            with sqlite3.connect(db_path) as con:
                row = con.execute(
                    "SELECT 단가 FROM out_extra WHERE 항목 = '도서산간'"
                ).fetchone()
                unit = int(row[0]) if row else None
        except Exception:
            unit = None

        if not unit:
            return False, "❗ out_extra 테이블에서 '도서산간' 단가를 찾을 수 없습니다.", None

        items.append({
            "항목": "도서산간",
            "수량": qty,
            "단가": unit,
            "금액": qty * unit
        })

        return True, None, info_msg

    except Exception as e:
        return False, f"⚠️ {vendor} 도서산간 계산 중 오류: {str(e)[:100]}", None


def calculate_remote_area_fee(
    vendor: str,
    d_from: str,
    d_to: str,
    db_path: str = "billing.db"
) -> Dict:
    """
    도서산간 요금만 계산하여 반환.
    
    Args:
        vendor: 공급처명
        d_from: 시작일 (YYYY-MM-DD)
        d_to: 종료일 (YYYY-MM-DD)
        db_path: 데이터베이스 경로
    
    Returns:
        {"항목": str, "수량": int, "단가": int, "금액": int} 또는 빈 딕셔너리
    """
    try:
        with get_connection() as con:
            tables = [
                row[0] for row in
                con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ]

            if "kpost_in" not in tables:
                return {}

            name_list = [vendor]
            if "aliases" in tables:
                try:
                    alias_df = pd.read_sql(
                        "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'kpost_in'",
                        con, params=(vendor,)
                    )
                    name_list.extend(alias_df["alias"].astype(str).str.strip().tolist())
                except Exception:
                    pass

            try:
                df = pd.read_sql(
                    f"""
                    SELECT 도서행 FROM kpost_in
                    WHERE TRIM(발송인명) IN ({','.join('?' * len(name_list))})
                      AND 접수일자 BETWEEN ? AND ?
                    """, con, params=(*name_list, d_from, d_to)
                )
            except Exception:
                return {}

        if df.empty or "도서행" not in df.columns:
            return {}

        df["도서행"] = df["도서행"].astype(str).str.lower().str.strip()
        qty = df[df["도서행"] == "y"].shape[0]

        if qty == 0:
            return {}

        try:
            with sqlite3.connect(db_path) as con:
                row = con.execute(
                    "SELECT 단가 FROM out_extra WHERE 항목 = '도서산간'"
                ).fetchone()
                unit = int(row[0]) if row else 0
        except Exception:
            unit = 0

        if not unit:
            return {}

        return {
            "항목": "도서산간",
            "수량": qty,
            "단가": unit,
            "금액": qty * unit
        }

    except Exception:
        return {}

