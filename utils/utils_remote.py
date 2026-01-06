import pandas as pd
import logging
from typing import List, Dict
from logic.db import get_connection

logger = logging.getLogger(__name__)

def add_remote_area_fee(vendor: str, d_from: str, d_to: str, items: List[Dict] = None) -> dict:
    """
    공급처 + 날짜 기준으로 kpost_in에서 '도서행' == 'y'인 건수 계산,
    단가(out_extra) 적용 → '도서산간' 항목 인보이스에 추가
    
    Args:
        vendor: 공급처명
        d_from: 시작일 (YYYY-MM-DD)
        d_to: 종료일 (YYYY-MM-DD)
        items: 인보이스 항목 리스트 (선택사항, 제공되면 직접 추가)
    
    Returns:
        dict: 항목 딕셔너리 또는 None
    """
    try:
        with get_connection() as con:
            # 필수 테이블 존재 확인
            tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            
            if "kpost_in" not in tables:
                logger.warning(f"'{vendor}' kpost_in 테이블이 없어 도서산간 계산을 건너뜁니다.")
                return None
            
            # ① 공급처 + 별칭 목록
            name_list = [vendor]
            if "aliases" in tables:
                try:
                    alias_df = pd.read_sql(
                        "SELECT alias FROM aliases WHERE vendor = ? AND file_type IN ('kpost_in', 'all')",
                        con, params=(vendor,)
                    )
                    name_list.extend(alias_df["alias"].astype(str).str.strip().tolist())
                except Exception:
                    pass  # 별칭 조회 실패해도 계속 진행

            # ② kpost_in 필터 + 도서행 여부 확인
            try:
                placeholders = ",".join("?" * len(name_list))
                df = pd.read_sql(
                    f"""
                    SELECT 도서행 FROM kpost_in
                    WHERE TRIM(발송인명) IN ({placeholders})
                      AND DATE(접수일자) BETWEEN DATE(?) AND DATE(?)
                    """, con, params=(*name_list, d_from, d_to)
                )
            except Exception as e:
                logger.warning(f"'{vendor}' kpost_in 조회 실패: {str(e)[:100]}")
                return None

        if df.empty or "도서행" not in df.columns:
            logger.warning(f"'{vendor}' 도서산간 데이터 없음 or '도서행' 칼럼 없음")
            return None

        # 도서행 컬럼 정규화: 문자열로 변환 후 소문자 변환 및 공백 제거
        df["도서행"] = df["도서행"].astype(str).str.lower().str.strip()
        # 'y', 'yes', '예', '1', 'true' 등 도서행으로 간주되는 값들 모두 매칭
        # 빈 문자열, 'n', 'no', '0', 'false', 'nan' 등은 제외
        qty = df[
            df["도서행"].isin(["y", "yes", "예", "1", "true"]) & 
            ~df["도서행"].isin(["", "n", "no", "아니오", "0", "false", "nan", "none"])
        ].shape[0]

        logger.info(f"{vendor} 도서산간 적용 수량: {qty}")

        if qty == 0:
            return None

        try:
            with get_connection() as con:
                row = con.execute("SELECT 단가 FROM out_extra WHERE 항목 = '도서산간'").fetchone()
                unit = int(float(row[0])) if row else None
        except Exception as e:
            logger.error(f"도서산간 단가 조회 실패: {e}")
            unit = None

        if not unit:
            logger.error("out_extra 테이블에서 '도서산간' 단가를 찾을 수 없습니다.")
            return None

        # ③ 인보이스 항목 생성
        item = {
            "항목": "도서산간",
            "수량": qty,
            "단가": unit,
            "금액": qty * unit
        }
        
        # items가 제공되면 직접 추가
        if items is not None:
            items.append(item)
        
        return item
        
    except Exception as e:
        logger.warning(f"{vendor} 도서산간 계산 중 오류: {str(e)[:100]}")
        return None