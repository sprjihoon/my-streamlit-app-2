"""
logic/fee_inbound.py - 입고검수 요금 계산
───────────────────────────────────────────
공급처 + 날짜 기준으로 inbound_slip에서 작업일자 필터,
수량 총합 × out_extra 테이블 '입고검수' 단가 계산.

Streamlit 의존성 제거 - 순수 Python 함수.
"""
import sqlite3
from typing import List, Dict, Tuple, Optional

import pandas as pd

from .db import get_connection


def add_inbound_inspection_fee(
    vendor: str,
    d_from: str,
    d_to: str,
    items: List[Dict],
    db_path: str = "billing.db"
) -> Tuple[bool, Optional[str]]:
    """
    공급처 + 날짜 기준으로 inbound_slip에서 작업일자 필터,
    수량 총합 × out_extra 테이블 '입고검수' 단가 → 인보이스 항목 추가.
    
    Args:
        vendor: 공급처명
        d_from: 시작일 (YYYY-MM-DD)
        d_to: 종료일 (YYYY-MM-DD)
        items: 인보이스 항목 리스트 (in-place 수정)
        db_path: 데이터베이스 경로
    
    Returns:
        (성공 여부, 오류 메시지 또는 None)
    """
    with get_connection() as con:
        # ① 공급처 별칭 가져오기
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'inbound_slip'",
            con, params=(vendor,)
        )
        name_list = [vendor] + alias_df["alias"].tolist()

        # ② 입고전표 로드 및 필터
        df = pd.read_sql(
            f"""
            SELECT 작업일, 수량, 공급처 FROM inbound_slip
            WHERE 공급처 IN ({','.join('?' * len(name_list))})
            """, con, params=name_list
        )

        if df.empty:
            return True, None

        # 날짜 필터
        df["작업일"] = pd.to_datetime(df["작업일"], errors="coerce").dt.date
        d_from_dt = pd.to_datetime(d_from).date()
        d_to_dt = pd.to_datetime(d_to).date()
        df = df[(df["작업일"] >= d_from_dt) & (df["작업일"] <= d_to_dt)]

        if df.empty or "수량" not in df.columns:
            return True, None

        # 수량을 숫자로 변환 (문자열 연결 방지)
        df["수량"] = pd.to_numeric(df["수량"], errors="coerce").fillna(0)
        total_qty = int(df["수량"].sum())

        # ③ 단가 가져오기 (out_extra 테이블)
        row = con.execute(
            "SELECT 단가 FROM out_extra WHERE 항목 = '입고검수'"
        ).fetchone()
        unit = int(row[0]) if row else None

    if not unit:
        return False, "❗ '입고검수' 단가를 out_extra 테이블에서 찾을 수 없습니다."

    if total_qty == 0:
        return True, None

    # ④ 인보이스 항목 추가
    items.append({
        "항목": "입고검수",
        "수량": total_qty,
        "단가": unit,
        "금액": total_qty * unit
    })
    
    return True, None


def calculate_inbound_inspection_fee(
    vendor: str,
    d_from: str,
    d_to: str,
    db_path: str = "billing.db"
) -> Dict:
    """
    입고검수 요금만 계산하여 반환.
    
    Args:
        vendor: 공급처명
        d_from: 시작일 (YYYY-MM-DD)
        d_to: 종료일 (YYYY-MM-DD)
        db_path: 데이터베이스 경로
    
    Returns:
        {"항목": str, "수량": int, "단가": int, "금액": int} 또는 빈 딕셔너리
    """
    with get_connection() as con:
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'inbound_slip'",
            con, params=(vendor,)
        )
        name_list = [vendor] + alias_df["alias"].tolist()

        df = pd.read_sql(
            f"""
            SELECT 작업일, 수량, 공급처 FROM inbound_slip
            WHERE 공급처 IN ({','.join('?' * len(name_list))})
            """, con, params=name_list
        )

        if df.empty:
            return {}

        df["작업일"] = pd.to_datetime(df["작업일"], errors="coerce").dt.date
        d_from_dt = pd.to_datetime(d_from).date()
        d_to_dt = pd.to_datetime(d_to).date()
        df = df[(df["작업일"] >= d_from_dt) & (df["작업일"] <= d_to_dt)]

        if df.empty or "수량" not in df.columns:
            return {}

        df["수량"] = pd.to_numeric(df["수량"], errors="coerce").fillna(0)
        total_qty = int(df["수량"].sum())

        if total_qty == 0:
            return {}

        row = con.execute(
            "SELECT 단가 FROM out_extra WHERE 항목 = '입고검수'"
        ).fetchone()
        unit = int(row[0]) if row else 0

    if not unit:
        return {}

    return {
        "항목": "입고검수",
        "수량": total_qty,
        "단가": unit,
        "금액": total_qty * unit
    }

