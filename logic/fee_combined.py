"""
logic/fee_combined.py - 합포장 요금 계산
───────────────────────────────────────────
배송통계 df_ship의 내품수량 기준으로,
합포장 (2개 초과분) 수량을 계산하고 인보이스 항목 추가.

Streamlit 의존성 제거 - 순수 Python 함수.
"""
import sqlite3
from typing import List, Dict, Optional, Tuple

import pandas as pd


def add_combined_pack_fee(
    df_ship: pd.DataFrame,
    items: List[Dict],
    db_path: str = "billing.db"
) -> Tuple[bool, Optional[str]]:
    """
    배송통계 df_ship의 내품수량 기준으로,
    합포장 (2개 초과분) 수량을 계산하고, out_extra 테이블의 단가로 인보이스 항목 추가.
    
    Args:
        df_ship: 배송통계 DataFrame
        items: 인보이스 항목 리스트 (in-place 수정됨)
        db_path: 데이터베이스 경로
    
    Returns:
        (성공 여부, 오류 메시지 또는 None)
    """
    if "내품수량" not in df_ship.columns:
        return False, "❗ '내품수량' 칼럼이 배송통계에 없습니다."

    # ① 초과 합포장 수량 계산
    df_ship = df_ship.copy()
    df_ship["내품수량"] = pd.to_numeric(df_ship["내품수량"], errors="coerce").fillna(0)
    df_ship["초과수량"] = df_ship["내품수량"] - 2
    df_ship["초과수량"] = df_ship["초과수량"].apply(lambda x: x if x > 0 else 0)
    total_qty = int(df_ship["초과수량"].sum())

    if total_qty == 0:
        return True, None

    # ② 단가 가져오기 (out_extra 테이블)
    try:
        with sqlite3.connect(db_path) as con:
            row = con.execute(
                "SELECT 단가 FROM out_extra WHERE 항목 = '합포장'"
            ).fetchone()
        unit = int(row[0]) if row else None
    except Exception:
        unit = None

    if not unit:
        return False, "❗ out_extra 테이블에서 '합포장' 단가를 찾을 수 없습니다."

    # ③ 인보이스 항목 추가
    items.append({
        "항목": "합포장 (2개 초과/개)",
        "수량": total_qty,
        "단가": unit,
        "금액": total_qty * unit
    })
    
    return True, None


def calculate_combined_pack_fee(
    df_ship: pd.DataFrame,
    db_path: str = "billing.db"
) -> Dict:
    """
    합포장 요금만 계산하여 반환.
    
    Args:
        df_ship: 배송통계 DataFrame
        db_path: 데이터베이스 경로
    
    Returns:
        {"항목": str, "수량": int, "단가": int, "금액": int} 또는 빈 딕셔너리
    """
    if "내품수량" not in df_ship.columns:
        return {}

    df_ship = df_ship.copy()
    df_ship["내품수량"] = pd.to_numeric(df_ship["내품수량"], errors="coerce").fillna(0)
    df_ship["초과수량"] = df_ship["내품수량"] - 2
    df_ship["초과수량"] = df_ship["초과수량"].apply(lambda x: x if x > 0 else 0)
    total_qty = int(df_ship["초과수량"].sum())

    if total_qty == 0:
        return {}

    try:
        with sqlite3.connect(db_path) as con:
            row = con.execute(
                "SELECT 단가 FROM out_extra WHERE 항목 = '합포장'"
            ).fetchone()
        unit = int(row[0]) if row else 0
    except Exception:
        unit = 0

    if not unit:
        return {}

    return {
        "항목": "합포장 (2개 초과/개)",
        "수량": total_qty,
        "단가": unit,
        "금액": total_qty * unit
    }

