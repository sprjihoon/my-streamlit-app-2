# -*- coding: utf-8 -*-
"""
backend/app/api/settings.py - 회사 설정 및 부가 서비스 단가 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
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


# ============================================================
# 부가 서비스 단가 (out_extra) API
# ============================================================

class ExtraFeeItem(BaseModel):
    """부가 서비스 단가 항목"""
    항목: str
    단가: int


class ExtraFeeItemUpdate(BaseModel):
    """부가 서비스 단가 업데이트"""
    단가: int


def _ensure_out_extra_table():
    """out_extra 테이블 보장"""
    with get_connection() as con:
        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='out_extra'"
        ).fetchone()
        
        if not table_exists:
            con.execute("""
                CREATE TABLE out_extra(
                    항목 TEXT PRIMARY KEY,
                    단가 INTEGER DEFAULT 0
                )
            """)
            # 기본 항목 추가
            default_items = [
                ('입고검수', 100),
                ('바코드 부착', 150),
                ('합포장', 100),
                ('완충작업', 100),
                ('출고영상촬영', 200),
                ('반품영상촬영', 400),
                ('도서산간', 400),
            ]
            con.executemany("INSERT OR IGNORE INTO out_extra (항목, 단가) VALUES (?, ?)", default_items)
            con.commit()


@router.get("/extra-fees", response_model=List[ExtraFeeItem])
async def get_extra_fees():
    """부가 서비스 단가 목록 조회"""
    _ensure_out_extra_table()
    
    with get_connection() as con:
        rows = con.execute("SELECT 항목, 단가 FROM out_extra ORDER BY 항목").fetchall()
        return [ExtraFeeItem(항목=row[0], 단가=row[1] or 0) for row in rows]


@router.put("/extra-fees/{item_name}", response_model=ExtraFeeItem)
async def update_extra_fee(item_name: str, update: ExtraFeeItemUpdate):
    """부가 서비스 단가 업데이트 (관리자 전용)"""
    _ensure_out_extra_table()
    
    with get_connection() as con:
        # 존재 여부 확인
        row = con.execute("SELECT 1 FROM out_extra WHERE 항목 = ?", (item_name,)).fetchone()
        
        if not row:
            # 새 항목 추가
            con.execute("INSERT INTO out_extra (항목, 단가) VALUES (?, ?)", (item_name, update.단가))
        else:
            # 기존 항목 업데이트
            con.execute("UPDATE out_extra SET 단가 = ? WHERE 항목 = ?", (update.단가, item_name))
        
        con.commit()
        
        return ExtraFeeItem(항목=item_name, 단가=update.단가)


@router.post("/extra-fees", response_model=ExtraFeeItem)
async def create_extra_fee(item: ExtraFeeItem):
    """부가 서비스 단가 항목 추가 (관리자 전용)"""
    _ensure_out_extra_table()
    
    with get_connection() as con:
        # 중복 체크
        row = con.execute("SELECT 1 FROM out_extra WHERE 항목 = ?", (item.항목,)).fetchone()
        if row:
            raise HTTPException(status_code=400, detail=f"'{item.항목}' 항목이 이미 존재합니다.")
        
        con.execute("INSERT INTO out_extra (항목, 단가) VALUES (?, ?)", (item.항목, item.단가))
        con.commit()
        
        return item


@router.delete("/extra-fees/{item_name}")
async def delete_extra_fee(item_name: str):
    """부가 서비스 단가 항목 삭제 (관리자 전용)"""
    _ensure_out_extra_table()
    
    with get_connection() as con:
        con.execute("DELETE FROM out_extra WHERE 항목 = ?", (item_name,))
        con.commit()
        
        return {"message": f"'{item_name}' 항목이 삭제되었습니다."}

