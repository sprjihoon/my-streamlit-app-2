# -*- coding: utf-8 -*-
"""
backend/app/api/settings.py - 회사 설정 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from logic.db import get_connection

router = APIRouter(prefix="/settings", tags=["settings"])


class CompanySettings(BaseModel):
    """회사 설정 스키마"""
    company_name: str = "회사명"
    business_number: str = "000-00-00000"
    address: str = "주소를 입력하세요"
    business_type: str = "서비스"
    business_item: str = "물류대행"
    bank_name: str = "은행명"
    account_holder: str = "예금주"
    account_number: str = "계좌번호"
    representative: str = "대표자명"


class CompanySettingsResponse(CompanySettings):
    """회사 설정 응답"""
    updated_at: Optional[str] = None


def _ensure_settings_table():
    """설정 테이블 및 기본값 보장"""
    with get_connection() as con:
        # 테이블 존재 여부 확인
        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_settings'"
        ).fetchone()
        
        if not table_exists:
            con.execute("""
                CREATE TABLE company_settings(
                    id              INTEGER PRIMARY KEY CHECK (id = 1),
                    company_name    TEXT DEFAULT '회사명',
                    business_number TEXT DEFAULT '000-00-00000',
                    address         TEXT DEFAULT '주소를 입력하세요',
                    business_type   TEXT DEFAULT '서비스',
                    business_item   TEXT DEFAULT '물류대행',
                    bank_name       TEXT DEFAULT '은행명',
                    account_holder  TEXT DEFAULT '예금주',
                    account_number  TEXT DEFAULT '계좌번호',
                    representative  TEXT DEFAULT '대표자명',
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.commit()
        
        # 기본 레코드 삽입 (없으면)
        row = con.execute("SELECT 1 FROM company_settings WHERE id = 1").fetchone()
        if not row:
            con.execute("""
                INSERT INTO company_settings (id, company_name, business_number, address, 
                    business_type, business_item, bank_name, account_holder, account_number, representative)
                VALUES (1, '틸리언', '766-55-00323', '대구시 동구 첨단로8길 8 씨제이빌딩302호',
                    '서비스', '포장 및 충전업', '카카오뱅크', '장지훈', '3333-02-9946468', '장지훈')
            """)
            con.commit()


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings():
    """회사 설정 조회"""
    _ensure_settings_table()
    
    with get_connection() as con:
        row = con.execute("""
            SELECT company_name, business_number, address, business_type, business_item,
                   bank_name, account_holder, account_number, representative, updated_at
            FROM company_settings WHERE id = 1
        """).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Settings not found")
        
        return CompanySettingsResponse(
            company_name=row[0] or "",
            business_number=row[1] or "",
            address=row[2] or "",
            business_type=row[3] or "",
            business_item=row[4] or "",
            bank_name=row[5] or "",
            account_holder=row[6] or "",
            account_number=row[7] or "",
            representative=row[8] or "",
            updated_at=str(row[9]) if row[9] else None,
        )


@router.put("/company", response_model=CompanySettingsResponse)
async def update_company_settings(settings: CompanySettings):
    """회사 설정 업데이트 (관리자 전용)"""
    _ensure_settings_table()
    
    with get_connection() as con:
        con.execute("""
            UPDATE company_settings SET
                company_name = ?,
                business_number = ?,
                address = ?,
                business_type = ?,
                business_item = ?,
                bank_name = ?,
                account_holder = ?,
                account_number = ?,
                representative = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (
            settings.company_name,
            settings.business_number,
            settings.address,
            settings.business_type,
            settings.business_item,
            settings.bank_name,
            settings.account_holder,
            settings.account_number,
            settings.representative,
        ))
        con.commit()
    
    return await get_company_settings()

