#!/usr/bin/env python3
import sqlite3
import pandas as pd

def quick_schema_check():
    try:
        with sqlite3.connect("billing.db") as con:
            # 1. 모든 테이블 목록
            tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            print("📋 존재하는 테이블:", tables)
            
            # 2. 각 테이블 스키마 확인
            for table in ["invoices", "vendors", "aliases", "kpost_in", "shipping_zone"]:
                if table in tables:
                    schema = con.execute(f"PRAGMA table_info({table})").fetchall()
                    columns = [f"{row[1]}({row[2]})" for row in schema]
                    print(f"\n📊 {table}: {columns}")
                    
                    # 데이터 건수
                    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    print(f"   데이터: {count}건")
                else:
                    print(f"\n❌ {table}: 테이블 없음")
            
            # 3. invoices 테이블 샘플 데이터 (있다면)
            if "invoices" in tables:
                try:
                    sample = pd.read_sql("SELECT * FROM invoices LIMIT 3", con)
                    print(f"\n📄 invoices 샘플:")
                    print(sample.to_string())
                except Exception as e:
                    print(f"invoices 샘플 조회 실패: {e}")
                    
    except Exception as e:
        print(f"데이터베이스 연결 실패: {e}")

if __name__ == "__main__":
    quick_schema_check() 