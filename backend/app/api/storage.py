# -*- coding: utf-8 -*-
"""
backend/app/api/storage.py - 보관료 관리 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from logic.db import get_connection

router = APIRouter(prefix="/storage", tags=["storage"])


# ========== 보관료 단가표 스키마 ==========
class StorageRate(BaseModel):
    rate_id: Optional[int] = None
    item_name: str = Field(..., description="품목명 (PLT, 단프라 등)")
    unit_price: int = Field(..., description="단가")
    unit: str = Field(default="월", description="단위")
    description: str = Field(default="", description="설명")
    is_active: bool = Field(default=True)


class StorageRateListResponse(BaseModel):
    success: bool = True
    rates: List[StorageRate]


# ========== 거래처별 보관료 스키마 ==========
class VendorStorage(BaseModel):
    storage_id: Optional[int] = None
    vendor_id: str = Field(..., description="거래처 ID")
    rate_id: Optional[int] = None
    item_name: str = Field(..., description="품목명")
    qty: int = Field(default=1, description="수량")
    unit_price: int = Field(..., description="단가")
    amount: int = Field(..., description="금액")
    period: Optional[str] = Field(default="", description="적용 기간 (예: 2024-11)")
    remark: str = Field(default="", description="비고")
    is_active: bool = Field(default=True)


class VendorStorageListResponse(BaseModel):
    success: bool = True
    storages: List[VendorStorage]
    total: int


# ========== 테이블 초기화 ==========
def _ensure_tables():
    """테이블 및 초기 데이터 보장"""
    with get_connection() as con:
        # 보관료 단가표
        con.execute("""
            CREATE TABLE IF NOT EXISTS storage_rates(
                rate_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name   TEXT UNIQUE NOT NULL,
                unit_price  INTEGER NOT NULL,
                unit        TEXT DEFAULT '월',
                description TEXT DEFAULT '',
                is_active   INTEGER DEFAULT 1
            )
        """)
        
        # 거래처별 보관료
        con.execute("""
            CREATE TABLE IF NOT EXISTS vendor_storage(
                storage_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id   TEXT NOT NULL,
                rate_id     INTEGER,
                item_name   TEXT NOT NULL,
                qty         INTEGER DEFAULT 1,
                unit_price  INTEGER NOT NULL,
                amount      INTEGER NOT NULL,
                period      TEXT,
                remark      TEXT DEFAULT '',
                is_active   INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 초기 데이터 삽입 (없으면)
        existing = con.execute("SELECT COUNT(*) FROM storage_rates").fetchone()[0]
        if existing == 0:
            initial_rates = [
                ("PLT", 30000, "월", "파렛트"),
                ("단프라", 4000, "월", "단프라 박스"),
                ("중량랙", 60000, "월", "중량랙"),
                ("중량랙셀", 12000, "월", "중량랙 셀"),
                ("행거", 60000, "월", "행거"),
            ]
            con.executemany(
                "INSERT INTO storage_rates (item_name, unit_price, unit, description) VALUES (?, ?, ?, ?)",
                initial_rates
            )
        con.commit()


# ========== 보관료 단가표 API ==========
@router.get("/rates", response_model=StorageRateListResponse)
async def list_storage_rates():
    """보관료 단가표 조회"""
    _ensure_tables()
    
    with get_connection() as con:
        rows = con.execute(
            "SELECT rate_id, item_name, unit_price, unit, description, is_active FROM storage_rates ORDER BY rate_id"
        ).fetchall()
        
        rates = [
            StorageRate(
                rate_id=r[0],
                item_name=r[1],
                unit_price=r[2],
                unit=r[3] or "월",
                description=r[4] or "",
                is_active=bool(r[5])
            )
            for r in rows
        ]
        
        return StorageRateListResponse(success=True, rates=rates)


@router.post("/rates", response_model=StorageRate)
async def create_storage_rate(rate: StorageRate):
    """새 보관료 단가 추가"""
    _ensure_tables()
    
    with get_connection() as con:
        try:
            cur = con.execute(
                "INSERT INTO storage_rates (item_name, unit_price, unit, description, is_active) VALUES (?, ?, ?, ?, ?)",
                (rate.item_name, rate.unit_price, rate.unit, rate.description, 1 if rate.is_active else 0)
            )
            con.commit()
            rate.rate_id = cur.lastrowid
            return rate
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"이미 존재하는 품목명입니다: {str(e)}")


@router.put("/rates/{rate_id}", response_model=StorageRate)
async def update_storage_rate(rate_id: int, rate: StorageRate):
    """보관료 단가 수정"""
    _ensure_tables()
    
    with get_connection() as con:
        con.execute(
            """UPDATE storage_rates SET 
                item_name = ?, unit_price = ?, unit = ?, description = ?, is_active = ?
            WHERE rate_id = ?""",
            (rate.item_name, rate.unit_price, rate.unit, rate.description, 1 if rate.is_active else 0, rate_id)
        )
        con.commit()
        rate.rate_id = rate_id
        return rate


@router.delete("/rates/{rate_id}")
async def delete_storage_rate(rate_id: int):
    """보관료 단가 삭제"""
    _ensure_tables()
    
    with get_connection() as con:
        con.execute("DELETE FROM storage_rates WHERE rate_id = ?", (rate_id,))
        con.commit()
    
    return {"success": True}


# ========== 거래처별 보관료 API ==========
@router.get("/vendor", response_model=VendorStorageListResponse)
async def list_vendor_storage(vendor_id: Optional[str] = None, period: Optional[str] = None, active_only: bool = True):
    """거래처별 보관료 목록 조회"""
    _ensure_tables()
    
    with get_connection() as con:
        query = "SELECT storage_id, vendor_id, rate_id, item_name, qty, unit_price, amount, period, remark, is_active FROM vendor_storage WHERE 1=1"
        params = []
        
        if vendor_id:
            query += " AND vendor_id = ?"
            params.append(vendor_id)
        
        if period:
            query += " AND period = ?"
            params.append(period)
        
        if active_only:
            query += " AND is_active = 1"
        
        query += " ORDER BY vendor_id, item_name"
        
        rows = con.execute(query, params).fetchall()
        
        storages = [
            VendorStorage(
                storage_id=r[0],
                vendor_id=r[1],
                rate_id=r[2],
                item_name=r[3],
                qty=r[4],
                unit_price=r[5],
                amount=r[6],
                period=r[7] or "",
                remark=r[8] or "",
                is_active=bool(r[9])
            )
            for r in rows
        ]
        
        return VendorStorageListResponse(success=True, storages=storages, total=len(storages))


@router.get("/vendor/{storage_id}", response_model=VendorStorage)
async def get_vendor_storage(storage_id: int):
    """특정 보관료 내역 조회"""
    _ensure_tables()
    
    with get_connection() as con:
        row = con.execute(
            "SELECT storage_id, vendor_id, rate_id, item_name, qty, unit_price, amount, period, remark, is_active FROM vendor_storage WHERE storage_id = ?",
            (storage_id,)
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        
        return VendorStorage(
            storage_id=row[0],
            vendor_id=row[1],
            rate_id=row[2],
            item_name=row[3],
            qty=row[4],
            unit_price=row[5],
            amount=row[6],
            period=row[7] or "",
            remark=row[8] or "",
            is_active=bool(row[9])
        )


@router.post("/vendor", response_model=VendorStorage)
async def create_vendor_storage(storage: VendorStorage):
    """거래처 보관료 내역 추가"""
    _ensure_tables()
    
    with get_connection() as con:
        cur = con.execute(
            """INSERT INTO vendor_storage 
                (vendor_id, rate_id, item_name, qty, unit_price, amount, period, remark, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                storage.vendor_id,
                storage.rate_id,
                storage.item_name,
                storage.qty,
                storage.unit_price,
                storage.amount,
                storage.period,
                storage.remark,
                1 if storage.is_active else 0
            )
        )
        con.commit()
        storage.storage_id = cur.lastrowid
        return storage


@router.put("/vendor/{storage_id}", response_model=VendorStorage)
async def update_vendor_storage(storage_id: int, storage: VendorStorage):
    """거래처 보관료 내역 수정"""
    _ensure_tables()
    
    with get_connection() as con:
        con.execute(
            """UPDATE vendor_storage SET
                vendor_id = ?, rate_id = ?, item_name = ?, qty = ?, unit_price = ?, 
                amount = ?, period = ?, remark = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE storage_id = ?""",
            (
                storage.vendor_id,
                storage.rate_id,
                storage.item_name,
                storage.qty,
                storage.unit_price,
                storage.amount,
                storage.period,
                storage.remark,
                1 if storage.is_active else 0,
                storage_id
            )
        )
        con.commit()
        storage.storage_id = storage_id
        return storage


@router.delete("/vendor/{storage_id}")
async def delete_vendor_storage(storage_id: int):
    """거래처 보관료 내역 삭제"""
    _ensure_tables()
    
    with get_connection() as con:
        con.execute("DELETE FROM vendor_storage WHERE storage_id = ?", (storage_id,))
        con.commit()
    
    return {"success": True}


@router.get("/vendor/by-vendor/{vendor_id}", response_model=VendorStorageListResponse)
async def get_storage_by_vendor(vendor_id: str, period: Optional[str] = None):
    """특정 거래처의 보관료 목록"""
    return await list_vendor_storage(vendor_id=vendor_id, period=period)

