"""
기본 요금표 데이터 복구 스크립트
native_app의 DEFAULT_DATA를 사용하여 복구
"""
from logic.db import get_connection
import pandas as pd

DEFAULT_DATA = {
    "out_basic": pd.DataFrame({
        "SKU 구간": ["≤100", "≤300", "≤500", "≤1,000", "≤2,000", ">2,000"],
        "출고비": [900, 950, 1000, 1100, 1200, 1300],
    }),
    "out_extra": pd.DataFrame({
        "항목": ["입고검수", "바코드 부착", "합포장", "완충작업", "출고영상촬영", "반품영상촬영"],
        "단가": [100, 150, 100, 100, 200, 400],
    }),
    "shipping_zone": pd.DataFrame({
        "요금제": ["표준"] * 6 + ["A"] * 6,
        "구간": ["극소", "소", "중", "대", "특대", "특특대"] * 2,
        "len_min_cm": [0, 51, 71, 101, 121, 141] * 2,
        "len_max_cm": [50, 70, 100, 120, 140, 160] * 2,
        "요금": [2100, 2400, 2900, 3800, 7400, 10400, 1900, 2100, 2500, 3300, 7200, 10200],
    }),
    "material_rates": pd.DataFrame({
        "항목": ["택배 봉투 소형", "택배 봉투 대형", "박스 중형", "박스 대형"],
        "단가": [80, 120, 500, 800],
        "size_code": ["극소", "소", "중", "대"],
    }),
}

def restore_default_rates():
    """기본 요금표 데이터 복구"""
    print("="*60)
    print("기본 요금표 데이터 복구")
    print("="*60)
    
    with get_connection() as con:
        for table_name, df in DEFAULT_DATA.items():
            try:
                # 현재 데이터 확인
                current_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                
                if current_count > 0:
                    print(f"\n[{table_name}] 현재 {current_count}건의 데이터가 있습니다.")
                    print("기존 데이터를 유지하고 기본 데이터는 추가하지 않습니다.")
                    continue
                
                # 테이블이 없으면 생성
                if table_name == "shipping_zone":
                    con.execute("""
                        CREATE TABLE IF NOT EXISTS shipping_zone(
                            [요금제] TEXT,
                            [구간] TEXT,
                            len_min_cm INTEGER,
                            len_max_cm INTEGER,
                            [요금] INTEGER,
                            PRIMARY KEY([요금제], [구간])
                        )
                    """)
                elif table_name == "out_basic":
                    con.execute("""
                        CREATE TABLE IF NOT EXISTS out_basic(
                            [SKU 구간] TEXT PRIMARY KEY,
                            [출고비] INTEGER
                        )
                    """)
                elif table_name == "out_extra":
                    con.execute("""
                        CREATE TABLE IF NOT EXISTS out_extra(
                            [항목] TEXT PRIMARY KEY,
                            [단가] INTEGER
                        )
                    """)
                elif table_name == "material_rates":
                    con.execute("""
                        CREATE TABLE IF NOT EXISTS material_rates(
                            [항목] TEXT PRIMARY KEY,
                            [단가] INTEGER,
                            size_code TEXT
                        )
                    """)
                
                # 데이터 삽입
                df.to_sql(table_name, con, if_exists='append', index=False)
                con.commit()
                
                print(f"\n[OK] {table_name}: {len(df)}건 복구 완료")
                print(df)
                
            except Exception as e:
                print(f"\n[ERROR] {table_name} 복구 실패: {e}")
                import traceback
                traceback.print_exc()
    
    print("\n" + "="*60)
    print("복구 완료!")
    print("="*60)

if __name__ == "__main__":
    restore_default_rates()

