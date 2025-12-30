# -*- coding: utf-8 -*-
"""회사 설정 테이블 생성 및 초기값 설정"""
from logic.db import get_connection

def create_company_settings():
    with get_connection() as con:
        # 테이블 존재 확인
        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_settings'"
        ).fetchone()
        
        if not table_exists:
            print("company_settings 테이블 생성 중...")
            con.execute("""
                CREATE TABLE company_settings(
                    id              INTEGER PRIMARY KEY CHECK (id = 1),
                    company_name    TEXT DEFAULT '',
                    business_number TEXT DEFAULT '',
                    address         TEXT DEFAULT '',
                    business_type   TEXT DEFAULT '',
                    business_item   TEXT DEFAULT '',
                    bank_name       TEXT DEFAULT '',
                    account_holder  TEXT DEFAULT '',
                    account_number  TEXT DEFAULT '',
                    representative  TEXT DEFAULT '',
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.commit()
            print("테이블 생성 완료")
        else:
            print("company_settings 테이블 이미 존재")
        
        # 기본 레코드 존재 확인
        row = con.execute("SELECT 1 FROM company_settings WHERE id = 1").fetchone()
        if not row:
            print("기본 설정 레코드 삽입 중...")
            con.execute("""
                INSERT INTO company_settings (id, company_name, business_number, address, 
                    business_type, business_item, bank_name, account_holder, account_number, representative)
                VALUES (1, '틸리언', '766-55-00323', '대구시 동구 첨단로8길 8 씨제이빌딩302호',
                    '서비스', '포장 및 충전업', '카카오뱅크', '장지훈', '3333-02-9946468', '장지훈')
            """)
            con.commit()
            print("기본 설정 삽입 완료")
        else:
            print("기본 설정 레코드 이미 존재")
        
        # 현재 설정 출력
        row = con.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        print(f"현재 설정: {row}")

if __name__ == "__main__":
    create_company_settings()

