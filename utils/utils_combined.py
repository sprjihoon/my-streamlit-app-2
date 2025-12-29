import sqlite3
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def add_combined_pack_fee(df_ship: pd.DataFrame) -> dict:
    """
    배송통계 df_ship의 내품수량 기준으로,
    합포장 (2개 초과분) 수량을 계산하고, out_extra 테이블의 단가로 인보이스 항목 추가.
    """
    if "내품수량" not in df_ship.columns:
        logger.warning("'내품수량' 칼럼이 배송통계에 없습니다.")
        return None

    # ① 초과 합포장 수량 계산
    df_ship["내품수량"] = pd.to_numeric(df_ship["내품수량"], errors="coerce").fillna(0)
    df_ship["초과수량"] = df_ship["내품수량"] - 2
    df_ship["초과수량"] = df_ship["초과수량"].apply(lambda x: x if x > 0 else 0)
    total_qty = int(df_ship["초과수량"].sum())

    if total_qty == 0:
        return None

    # ② 단가 가져오기 (out_extra 테이블)
    try:
        with sqlite3.connect("billing.db") as con:
            row = con.execute("SELECT 단가 FROM out_extra WHERE 항목 = '합포장'").fetchone()
        unit = int(row[0]) if row else None
    except Exception:
        unit = None

    if not unit:
        logger.error("out_extra 테이블에서 '합포장' 단가를 찾을 수 없습니다.")
        return None

    # ③ 인보이스 항목 반환
    return {
        "항목": "합포장 (2개 초과/개)",
        "수량": total_qty,
        "단가": unit,
        "금액": total_qty * unit
    }