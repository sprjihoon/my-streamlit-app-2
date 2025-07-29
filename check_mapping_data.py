import sqlite3
import pandas as pd

DB_PATH = "billing.db"

def check_data():
    """로컬 billing.db 파일의 vendors와 aliases 테이블 내용을 확인합니다."""
    print(f"🔍 '{DB_PATH}' 파일에서 업체 매핑 데이터를 확인합니다...")
    
    try:
        with sqlite3.connect(DB_PATH) as con:
            print("\n--- vendors 테이블 ---")
            vendors_df = pd.read_sql("SELECT * FROM vendors ORDER BY vendor LIMIT 10", con)
            if vendors_df.empty:
                print("❌ 비어있음")
            else:
                print(f"✅ {len(pd.read_sql('SELECT vendor FROM vendors', con))}개의 공급처 중 일부:")
                print(vendors_df.to_string())

            print("\n--- aliases 테이블 (kpost_in) ---")
            aliases_df = pd.read_sql("SELECT * FROM aliases WHERE file_type='kpost_in' ORDER BY vendor, alias LIMIT 10", con)
            if aliases_df.empty:
                print("❌ 비어있음")
            else:
                print(f"✅ {len(pd.read_sql('SELECT alias FROM aliases', con))}개의 별칭 중 일부:")
                print(aliases_df.to_string())
                
    except Exception as e:
        print(f"\n🚨 오류 발생: {e}")
        print(f"'{DB_PATH}' 파일이 존재하지 않거나 손상되었을 수 있습니다.")

if __name__ == "__main__":
    check_data() 