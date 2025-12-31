"""매핑 데이터 백업 스크립트"""
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
from logic.db import get_connection, DB_PATH

def backup_mapping_data():
    """vendors와 aliases 테이블을 백업"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    with get_connection() as con:
        # vendors 백업
        vendors_df = pd.read_sql("SELECT * FROM vendors", con)
        if not vendors_df.empty:
            vendors_backup_file = backup_dir / f"vendors_backup_{timestamp}.csv"
            vendors_df.to_csv(vendors_backup_file, index=False, encoding='utf-8-sig')
            print(f"✅ vendors 백업 완료: {vendors_backup_file} ({len(vendors_df)}개)")
        
        # aliases 백업
        aliases_df = pd.read_sql("SELECT * FROM aliases", con)
        if not aliases_df.empty:
            aliases_backup_file = backup_dir / f"aliases_backup_{timestamp}.csv"
            aliases_df.to_csv(aliases_backup_file, index=False, encoding='utf-8-sig')
            print(f"✅ aliases 백업 완료: {aliases_backup_file} ({len(aliases_df)}개)")
        
        # DB 내부 백업 테이블도 생성
        con.execute("DROP TABLE IF EXISTS vendors_backup")
        con.execute("DROP TABLE IF EXISTS aliases_backup")
        
        if not vendors_df.empty:
            vendors_df.to_sql('vendors_backup', con, if_exists='replace', index=False)
            print("✅ vendors_backup 테이블 생성 완료")
        
        if not aliases_df.empty:
            aliases_df.to_sql('aliases_backup', con, if_exists='replace', index=False)
            print("✅ aliases_backup 테이블 생성 완료")
        
        con.commit()
        print("\n백업 완료!")

if __name__ == "__main__":
    backup_mapping_data()

