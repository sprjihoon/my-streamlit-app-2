import pandas as pd
import logging
from typing import List, Dict
from logic.db import get_connection

logger = logging.getLogger(__name__)

def add_combined_pack_fee(df_ship: pd.DataFrame, items: List[Dict] = None) -> dict:
    """
    배송통계 df_ship의 내품수량 기준으로,
    합포장 (2개 초과분) 수량을 계산하고, out_extra 테이블의 단가로 인보이스 항목 추가.
    
    Args:
        df_ship: 배송통계 DataFrame
        items: 인보이스 항목 리스트 (선택사항, 제공되면 직접 추가)
    
    Returns:
        dict: 항목 딕셔너리 또는 None
    """
    if "내품수량" not in df_ship.columns:
        logger.warning("'내품수량' 칼럼이 배송통계에 없습니다.")
        return None

    # ① 초과 합포장 수량 계산
    df_ship = df_ship.copy()
    df_ship["내품수량"] = pd.to_numeric(df_ship["내품수량"], errors="coerce").fillna(0)
    df_ship["초과수량"] = df_ship["내품수량"] - 2
    df_ship["초과수량"] = df_ship["초과수량"].apply(lambda x: x if x > 0 else 0)
    total_qty = int(df_ship["초과수량"].sum())

    if total_qty == 0:
        return None

    # ② 단가 가져오기 (out_extra 테이블)
    try:
        with get_connection() as con:
            row = con.execute("SELECT 단가 FROM out_extra WHERE 항목 = '합포장'").fetchone()
        unit = int(float(row[0])) if row else None
    except Exception as e:
        logger.error(f"합포장 단가 조회 실패: {e}")
        unit = None

    if not unit:
        logger.error("out_extra 테이블에서 '합포장' 단가를 찾을 수 없습니다.")
        return None

    # ③ 인보이스 항목 생성
    item = {
        "항목": "합포장 (2개 초과/개)",
        "수량": total_qty,
        "단가": unit,
        "금액": total_qty * unit
    }
    
    # items가 제공되면 직접 추가
    if items is not None:
        items.append(item)
    
    return item