# -*- coding: utf-8 -*-
"""
backend/app/api/vendor_charges.py - 거래처별 추가 청구 비용 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from logic.db import get_connection

router = APIRouter(prefix="/vendor-charges", tags=["vendor-charges"])


class VendorCharge(BaseModel):
    """거래처별 청구 비용 항목"""
    charge_id: Optional[int] = None
    vendor_id: str = Field(..., description="거래처 ID 또는 이름")
    item_name: str = Field(..., description="품명")
    qty: int = Field(default=1, description="수량")
    unit_price: int = Field(..., description="단가")
    amount: int = Field(..., description="금액")
    remark: str = Field(default="", description="비고")
    charge_type: str = Field(default="보관비", description="비용 유형 (보관비, 기타 등)")
    is_active: bool = Field(default=True, description="활성 상태")


class VendorChargeResponse(VendorCharge):
    """응답용 스키마"""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VendorChargeListResponse(BaseModel):
    """목록 응답"""
    success: bool = True
    charges: List[VendorChargeResponse]
    total: int


def _ensure_table():
    """테이블 존재 보장"""
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS vendor_charges(
                charge_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id   TEXT NOT NULL,
                item_name   TEXT NOT NULL,
                qty         INTEGER DEFAULT 1,
                unit_price  INTEGER NOT NULL,
                amount      INTEGER NOT NULL,
                remark      TEXT DEFAULT '',
                charge_type TEXT DEFAULT '보관비',
                is_active   INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()


@router.get("", response_model=VendorChargeListResponse)
@router.get("/", response_model=VendorChargeListResponse)
async def list_vendor_charges(vendor_id: Optional[str] = None, active_only: bool = True):
    """거래처별 청구 비용 목록 조회"""
    _ensure_table()
    
    with get_connection() as con:
        query = "SELECT * FROM vendor_charges WHERE 1=1"
        params = []
        
        if vendor_id:
            query += " AND vendor_id = ?"
            params.append(vendor_id)
        
        if active_only:
            query += " AND is_active = 1"
        
        query += " ORDER BY vendor_id, item_name"
        
        rows = con.execute(query, params).fetchall()
        columns = [desc[0] for desc in con.execute(query, params).description] if rows else []
        
        charges = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            charges.append(VendorChargeResponse(
                charge_id=row_dict.get("charge_id"),
                vendor_id=row_dict.get("vendor_id", ""),
                item_name=row_dict.get("item_name", ""),
                qty=row_dict.get("qty", 1),
                unit_price=row_dict.get("unit_price", 0),
                amount=row_dict.get("amount", 0),
                remark=row_dict.get("remark", ""),
                charge_type=row_dict.get("charge_type", "보관비"),
                is_active=bool(row_dict.get("is_active", 1)),
                created_at=str(row_dict.get("created_at", "")) if row_dict.get("created_at") else None,
                updated_at=str(row_dict.get("updated_at", "")) if row_dict.get("updated_at") else None,
            ))
        
        return VendorChargeListResponse(
            success=True,
            charges=charges,
            total=len(charges)
        )


@router.get("/{charge_id}", response_model=VendorChargeResponse)
async def get_vendor_charge(charge_id: int):
    """특정 청구 비용 조회"""
    _ensure_table()
    
    with get_connection() as con:
        row = con.execute(
            "SELECT * FROM vendor_charges WHERE charge_id = ?",
            (charge_id,)
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Charge not found")
        
        columns = [desc[0] for desc in con.execute("SELECT * FROM vendor_charges LIMIT 1").description]
        row_dict = dict(zip(columns, row))
        
        return VendorChargeResponse(
            charge_id=row_dict.get("charge_id"),
            vendor_id=row_dict.get("vendor_id", ""),
            item_name=row_dict.get("item_name", ""),
            qty=row_dict.get("qty", 1),
            unit_price=row_dict.get("unit_price", 0),
            amount=row_dict.get("amount", 0),
            remark=row_dict.get("remark", ""),
            charge_type=row_dict.get("charge_type", "보관비"),
            is_active=bool(row_dict.get("is_active", 1)),
            created_at=str(row_dict.get("created_at", "")) if row_dict.get("created_at") else None,
            updated_at=str(row_dict.get("updated_at", "")) if row_dict.get("updated_at") else None,
        )


@router.post("", response_model=VendorChargeResponse)
@router.post("/", response_model=VendorChargeResponse)
async def create_vendor_charge(charge: VendorCharge):
    """새 청구 비용 추가"""
    _ensure_table()
    
    with get_connection() as con:
        cur = con.execute(
            """
            INSERT INTO vendor_charges 
                (vendor_id, item_name, qty, unit_price, amount, remark, charge_type, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                charge.vendor_id,
                charge.item_name,
                charge.qty,
                charge.unit_price,
                charge.amount,
                charge.remark,
                charge.charge_type,
                1 if charge.is_active else 0,
            )
        )
        con.commit()
        charge_id = cur.lastrowid
    
    return await get_vendor_charge(charge_id)


@router.put("/{charge_id}", response_model=VendorChargeResponse)
async def update_vendor_charge(charge_id: int, charge: VendorCharge):
    """청구 비용 수정"""
    _ensure_table()
    
    with get_connection() as con:
        # 존재 확인
        existing = con.execute(
            "SELECT 1 FROM vendor_charges WHERE charge_id = ?",
            (charge_id,)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Charge not found")
        
        con.execute(
            """
            UPDATE vendor_charges SET
                vendor_id = ?,
                item_name = ?,
                qty = ?,
                unit_price = ?,
                amount = ?,
                remark = ?,
                charge_type = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE charge_id = ?
            """,
            (
                charge.vendor_id,
                charge.item_name,
                charge.qty,
                charge.unit_price,
                charge.amount,
                charge.remark,
                charge.charge_type,
                1 if charge.is_active else 0,
                charge_id,
            )
        )
        con.commit()
    
    return await get_vendor_charge(charge_id)


@router.delete("/{charge_id}")
async def delete_vendor_charge(charge_id: int):
    """청구 비용 삭제"""
    _ensure_table()
    
    with get_connection() as con:
        existing = con.execute(
            "SELECT 1 FROM vendor_charges WHERE charge_id = ?",
            (charge_id,)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Charge not found")
        
        con.execute("DELETE FROM vendor_charges WHERE charge_id = ?", (charge_id,))
        con.commit()
    
    return {"success": True, "message": "Deleted successfully"}


@router.get("/by-vendor/{vendor_id}", response_model=VendorChargeListResponse)
async def get_charges_by_vendor(vendor_id: str, active_only: bool = True):
    """특정 거래처의 청구 비용 목록"""
    return await list_vendor_charges(vendor_id=vendor_id, active_only=active_only)

