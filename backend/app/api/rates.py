"""
backend/app/api/rates.py - 요금표 관리 API
기존 Streamlit 앱의 테이블 스키마를 그대로 사용합니다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import pandas as pd

from logic.db import get_connection

router = APIRouter(prefix="/rates", tags=["rates"])

# ─────────────────────────────────────
# Pydantic Models (기존 DB 스키마와 일치)
# ─────────────────────────────────────

class OutBasicRate(BaseModel):
    sku_group: str = Field(alias="SKU 구간")
    unit_price: int = Field(alias="기본단가")
    
    class Config:
        populate_by_name = True


class OutExtraRate(BaseModel):
    item: str = Field(alias="항목")
    unit_price: int = Field(alias="단가")
    
    class Config:
        populate_by_name = True


class ShippingZoneRate(BaseModel):
    rate_type: str = Field(alias="요금제")
    zone: str = Field(alias="구간")
    len_min_cm: int
    len_max_cm: int
    price: int = Field(alias="요금")
    
    class Config:
        populate_by_name = True


class MaterialRate(BaseModel):
    item: str = Field(alias="항목")
    unit_price: int = Field(alias="단가")
    size_code: Optional[str] = None
    
    class Config:
        populate_by_name = True


TABLES_INFO = {
    "out_basic": "출고비 (SKU 구간)",
    "out_extra": "추가 작업 단가",
    "shipping_zone": "배송 요금 구간",
    "material_rates": "부자재 요금표",
}


# ─────────────────────────────────────
# 테이블 보장 (기존 스키마 유지)
# ─────────────────────────────────────
def ensure_rate_tables():
    """요금 테이블 존재 확인 (기존 테이블이 있으면 그대로 사용)"""
    with get_connection() as con:
        # out_basic - 기존 스키마: [SKU 구간], [출고비]
        con.execute("""
            CREATE TABLE IF NOT EXISTS out_basic(
                [SKU 구간] TEXT PRIMARY KEY,
                [출고비] INTEGER
            )""")
        
        # out_extra - 기존 스키마: [항목], [단가]
        con.execute("""
            CREATE TABLE IF NOT EXISTS out_extra(
                [항목] TEXT PRIMARY KEY,
                [단가] INTEGER
            )""")
        
        # shipping_zone - 기존 스키마: [요금제], [구간], len_min_cm, len_max_cm, [요금]
        con.execute("""
            CREATE TABLE IF NOT EXISTS shipping_zone(
                [요금제] TEXT,
                [구간] TEXT,
                len_min_cm INTEGER,
                len_max_cm INTEGER,
                [요금] INTEGER,
                PRIMARY KEY([요금제], [구간])
            )""")
        
        # material_rates - 기존 스키마: [항목], [단가], size_code
        con.execute("""
            CREATE TABLE IF NOT EXISTS material_rates(
                [항목] TEXT PRIMARY KEY,
                [단가] INTEGER,
                size_code TEXT
            )""")
        
        con.commit()


# ─────────────────────────────────────
# API Endpoints (기존 DB 스키마 사용)
# ─────────────────────────────────────

@router.get("/tables")
async def list_rate_tables():
    """사용 가능한 요금 테이블 목록"""
    return TABLES_INFO


@router.get("/out_basic")
async def get_out_basic():
    """출고비 요금표 조회"""
    ensure_rate_tables()
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM out_basic", con)
    # 프론트엔드용 일관된 필드명으로 변환
    # 실제 DB 컬럼: SKU 구간, 출고비
    result = []
    for _, row in df.iterrows():
        result.append({
            "sku_group": str(row.get("SKU 구간", "")),
            "단가": int(row.get("출고비", 0)) if row.get("출고비") else 0
        })
    return result


@router.post("/out_basic")
async def update_out_basic(rates: List[Dict[str, Any]]):
    """출고비 요금표 전체 업데이트"""
    ensure_rate_tables()
    try:
        with get_connection() as con:
            con.execute("DELETE FROM out_basic")
            for rate in rates:
                sku_group = rate.get("sku_group", rate.get("SKU 구간", ""))
                unit_price = rate.get("단가", rate.get("출고비", 0))
                con.execute(
                    "INSERT INTO out_basic ([SKU 구간], [출고비]) VALUES (?, ?)",
                    (sku_group, int(unit_price))
                )
            con.commit()
        return {"status": "success", "count": len(rates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/out_extra")
async def get_out_extra():
    """추가 작업 단가 조회"""
    ensure_rate_tables()
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM out_extra", con)
    result = []
    for _, row in df.iterrows():
        result.append({
            "항목": row.get("항목", ""),
            "단가": int(row.get("단가", 0))
        })
    return result


@router.post("/out_extra")
async def update_out_extra(rates: List[Dict[str, Any]]):
    """추가 작업 단가 전체 업데이트"""
    ensure_rate_tables()
    try:
        with get_connection() as con:
            con.execute("DELETE FROM out_extra")
            for rate in rates:
                con.execute(
                    "INSERT INTO out_extra ([항목], [단가]) VALUES (?, ?)",
                    (rate.get("항목", ""), int(rate.get("단가", 0)))
                )
            con.commit()
        return {"status": "success", "count": len(rates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shipping_zone")
async def get_shipping_zone(rate_type: Optional[str] = None):
    """배송 요금 구간 조회"""
    ensure_rate_tables()
    with get_connection() as con:
        if rate_type:
            df = pd.read_sql(
                "SELECT * FROM shipping_zone WHERE [요금제] = ? ORDER BY len_min_cm",
                con, params=[rate_type]
            )
        else:
            df = pd.read_sql("SELECT * FROM shipping_zone ORDER BY [요금제], len_min_cm", con)
    result = []
    for _, row in df.iterrows():
        result.append({
            "요금제": row.get("요금제", ""),
            "구간": row.get("구간", ""),
            "len_min_cm": int(row.get("len_min_cm", 0)),
            "len_max_cm": int(row.get("len_max_cm", 0)),
            "요금": int(row.get("요금", 0))
        })
    return result


@router.post("/shipping_zone")
async def update_shipping_zone(rates: List[Dict[str, Any]], rate_type: Optional[str] = None):
    """배송 요금 구간 업데이트 (특정 요금제만 또는 전체)"""
    ensure_rate_tables()
    try:
        with get_connection() as con:
            if rate_type:
                con.execute("DELETE FROM shipping_zone WHERE [요금제] = ?", (rate_type,))
            else:
                con.execute("DELETE FROM shipping_zone")
            
            for rate in rates:
                con.execute(
                    "INSERT INTO shipping_zone ([요금제], [구간], len_min_cm, len_max_cm, [요금]) VALUES (?, ?, ?, ?, ?)",
                    (
                        rate.get("요금제", ""),
                        rate.get("구간", ""),
                        int(rate.get("len_min_cm", 0)),
                        int(rate.get("len_max_cm", 0)),
                        int(rate.get("요금", 0))
                    )
                )
            con.commit()
        return {"status": "success", "count": len(rates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/material_rates")
async def get_material_rates():
    """부자재 요금표 조회"""
    ensure_rate_tables()
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM material_rates", con)
    result = []
    for _, row in df.iterrows():
        result.append({
            "항목": row.get("항목", ""),
            "단가": int(row.get("단가", 0)),
            "size_code": row.get("size_code", "")
        })
    return result


@router.post("/material_rates")
async def update_material_rates(rates: List[Dict[str, Any]]):
    """부자재 요금표 전체 업데이트"""
    ensure_rate_tables()
    try:
        with get_connection() as con:
            con.execute("DELETE FROM material_rates")
            for rate in rates:
                con.execute(
                    "INSERT INTO material_rates ([항목], [단가], size_code) VALUES (?, ?, ?)",
                    (
                        rate.get("항목", ""),
                        int(rate.get("단가", 0)),
                        rate.get("size_code", "")
                    )
                )
            con.commit()
        return {"status": "success", "count": len(rates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{table_name}")
async def get_rate_table(table_name: str):
    """범용 요금 테이블 조회"""
    if table_name not in TABLES_INFO:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    
    ensure_rate_tables()
    with get_connection() as con:
        df = pd.read_sql(f"SELECT * FROM {table_name}", con)
    return {
        "table": table_name,
        "description": TABLES_INFO[table_name],
        "data": df.to_dict(orient="records")
    }

