import sqlite3
import pandas as pd
import logging
from logic.db import get_connection

logger = logging.getLogger(__name__)

def add_remote_area_fee(vendor: str, d_from: str, d_to: str) -> dict:
    """
    공급처 + 날짜 기준으로 kpost_in에서 '도서행' == 'y'인 건수 계산,
    단가(out_extra) 적용 → '도서산간' 항목 인보이스에 추가
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
                        "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'kpost_in'",
                        con, params=(vendor,)
                    )
                    name_list.extend(alias_df["alias"].astype(str).str.strip().tolist())
                except Exception:
                    pass  # 별칭 조회 실패해도 계속 진행

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
                logger.warning(f"'{vendor}' kpost_in 조회 실패: {str(e)[:100]}")
                return None

        if df.empty or "도서행" not in df.columns:
            logger.warning(f"'{vendor}' 도서산간 데이터 없음 or '도서행' 칼럼 없음")
            return None

        # 2025-07-28: 일부 파일은 도서행 표기가 누락되어 전체 건수를 사용
        df["도서행"] = df["도서행"].astype(str).str.lower().str.strip()
        qty = df[df["도서행"] == "y"].shape[0]

        logger.info(f"{vendor} 도서산간 적용 수량: {qty}")

        if qty == 0:
            return None

        try:
            with sqlite3.connect("billing.db") as con:
                row = con.execute("SELECT 단가 FROM out_extra WHERE 항목 = '도서산간'").fetchone()
                unit = int(row[0]) if row else None
        except Exception:
            unit = None

        if not unit:
            logger.error("out_extra 테이블에서 '도서산간' 단가를 찾을 수 없습니다.")
            return None

        return {
            "항목": "도서산간",
            "수량": qty,
            "단가": unit,
            "금액": qty * unit
        }
        
    except Exception as e:
        logger.warning(f"{vendor} 도서산간 계산 중 오류: {str(e)[:100]}")
        return None