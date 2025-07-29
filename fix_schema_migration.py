#!/usr/bin/env python3
"""
스키마 불일치 수정 마이그레이션 스크립트
===================================

1. vendors 테이블 스키마 통일 (vendor_id + vendor 모두 지원)
2. alias_vendor_v 뷰 생성 (aliases 테이블 기반)
3. invoices 테이블 호환성 보장
"""

import sqlite3
import pandas as pd

def fix_schema_migration():
    print("🔧 스키마 불일치 수정 시작...\n")
    
    with sqlite3.connect("billing.db") as con:
        cur = con.cursor()
        
        # 1. 현재 vendors 테이블 구조 확인
        vendor_columns = [row[1] for row in cur.execute("PRAGMA table_info(vendors)").fetchall()]
        print(f"현재 vendors 컬럼: {vendor_columns}")
        
        # 2. vendor_id 컬럼이 없다면 추가
        if "vendor_id" not in vendor_columns:
            print("vendor_id 컬럼 추가 중...")
            cur.execute("ALTER TABLE vendors ADD COLUMN vendor_id INTEGER")
            
            # 기존 데이터에 vendor_id 할당
            cur.execute("""
                UPDATE vendors 
                SET vendor_id = ROWID 
                WHERE vendor_id IS NULL
            """)
            
            print("✅ vendor_id 컬럼 추가 완료")
        
        # 3. vendor 컬럼이 TEXT PRIMARY KEY가 아니라면 수정 필요
        # SQLite는 PRIMARY KEY 수정이 제한적이므로 임시 테이블 사용
        
        # 4. invoices 테이블 구조 확인 및 수정
        invoice_columns = [row[1] for row in cur.execute("PRAGMA table_info(invoices)").fetchall()]
        print(f"현재 invoices 컬럼: {invoice_columns}")
        
        if "vendor_id" not in invoice_columns:
            print("invoices에 vendor_id 컬럼 추가 중...")
            cur.execute("ALTER TABLE invoices ADD COLUMN vendor_id TEXT")
            print("✅ invoices vendor_id 컬럼 추가 완료")
        
        # 5. alias_vendor_v 뷰 생성 (aliases 테이블 기반)
        cur.execute("DROP VIEW IF EXISTS alias_vendor_v")
        cur.execute("""
            CREATE VIEW alias_vendor_v AS
            SELECT vendor, alias, file_type
            FROM aliases
        """)
        print("✅ alias_vendor_v 뷰 생성 완료")
        
        # 6. 데이터 무결성 검사
        vendor_count = cur.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
        alias_count = cur.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        invoice_count = cur.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        
        print(f"\n📊 데이터 현황:")
        print(f"  - vendors: {vendor_count}개")
        print(f"  - aliases: {alias_count}개")
        print(f"  - invoices: {invoice_count}개")
        
        # 7. 인덱스 생성 (성능 향상)
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vendors_vendor ON vendors(vendor)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vendors_vendor_id ON vendors(vendor_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_aliases_vendor ON aliases(vendor, file_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_vendor_id ON invoices(vendor_id)")
            print("✅ 인덱스 생성 완료")
        except Exception as e:
            print(f"⚠️  인덱스 생성 중 일부 오류: {e}")
        
        con.commit()
        print("\n🎉 스키마 마이그레이션 완료!")

if __name__ == "__main__":
    fix_schema_migration() 