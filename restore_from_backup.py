"""
백업 데이터베이스에서 복구 스크립트
"""
import sqlite3
import pandas as pd
from pathlib import Path
from logic.db import get_connection, DB_PATH

def restore_from_backup(backup_db_path: str):
    """백업 DB에서 요금표 데이터 복구"""
    backup_path = Path(backup_db_path)
    
    if not backup_path.exists():
        print(f"[ERROR] 백업 파일을 찾을 수 없습니다: {backup_path}")
        return False
    
    print(f"백업 파일에서 복구 시작: {backup_path}")
    
    # 백업 DB 연결
    backup_con = sqlite3.connect(backup_path)
    
    # 현재 DB 연결
    with get_connection() as current_con:
        tables_to_restore = ['shipping_zone', 'out_basic', 'out_extra', 'material_rates']
        
        for table in tables_to_restore:
            try:
                # 백업에서 데이터 읽기
                df = pd.read_sql(f"SELECT * FROM {table}", backup_con)
                
                if df.empty:
                    print(f"[SKIP] {table}: 백업에 데이터 없음")
                    continue
                
                print(f"\n[{table}] 복구 중... ({len(df)}건)")
                
                # 현재 테이블에 데이터가 있으면 확인
                try:
                    current_count = current_con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if current_count > 0:
                        response = input(f"  현재 {table}에 {current_count}건이 있습니다. 덮어쓰시겠습니까? (y/n): ")
                        if response.lower() != 'y':
                            print(f"  [SKIP] {table} 복구 건너뜀")
                            continue
                        # 기존 데이터 삭제
                        current_con.execute(f"DELETE FROM {table}")
                except:
                    pass  # 테이블이 없으면 계속 진행
                
                # 데이터 복구
                df.to_sql(table, current_con, if_exists='append', index=False)
                current_con.commit()
                
                print(f"  [OK] {table} 복구 완료: {len(df)}건")
                
            except Exception as e:
                print(f"  [ERROR] {table} 복구 실패: {e}")
        
        backup_con.close()
        print("\n복구 완료!")
        return True

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("사용법: python restore_from_backup.py <백업DB경로>")
        print("\n사용 가능한 백업 파일:")
        print("  - data/billing.db")
        print("  - new_cal/data/billing.db")
        sys.exit(1)
    
    backup_path = sys.argv[1]
    restore_from_backup(backup_path)

