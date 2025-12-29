"""
backend/app/api/vendors.py - 거래처/매핑 관련 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd

from logic.db import get_connection

router = APIRouter(prefix="/vendors", tags=["vendors"])

# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class VendorCreate(BaseModel):
    vendor: str  # PK
    name: str
    rate_type: str = "A"
    sku_group: str = "≤100"
    active: str = "YES"
    barcode_f: str = "NO"
    custbox_f: str = "NO"
    void_f: str = "NO"
    pp_bag_f: str = "NO"
    mailer_f: str = "NO"
    video_out_f: str = "NO"
    video_ret_f: str = "NO"
    # 별칭 매핑
    alias_inbound_slip: List[str] = []
    alias_shipping_stats: List[str] = []
    alias_kpost_in: List[str] = []
    alias_kpost_ret: List[str] = []
    alias_work_log: List[str] = []


class VendorResponse(BaseModel):
    vendor: str
    name: Optional[str] = None
    rate_type: Optional[str] = None
    sku_group: Optional[str] = None
    active: Optional[str] = "YES"
    barcode_f: Optional[str] = "NO"
    custbox_f: Optional[str] = "NO"
    void_f: Optional[str] = "NO"
    pp_bag_f: Optional[str] = "NO"
    mailer_f: Optional[str] = "NO"
    video_out_f: Optional[str] = "NO"
    video_ret_f: Optional[str] = "NO"


class AliasInfo(BaseModel):
    alias: str
    file_type: str
    vendor: Optional[str] = None


class UnmatchedAliasResponse(BaseModel):
    file_type: str
    aliases: List[str]
    count: int


# ─────────────────────────────────────
# 테이블 보장
# ─────────────────────────────────────
FLAG_COLS = ["barcode_f", "custbox_f", "void_f", "pp_bag_f", "mailer_f", "video_out_f", "video_ret_f"]

def ensure_tables():
    """vendors, aliases 테이블 생성 및 컬럼 보장"""
    with get_connection() as con:
        # vendors 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS vendors(
                vendor     TEXT PRIMARY KEY,
                name       TEXT,
                rate_type  TEXT,
                sku_group  TEXT,
                active     TEXT DEFAULT 'YES'
            )""")
        
        # 컬럼 보강
        cols = [c[1] for c in con.execute("PRAGMA table_info(vendors);")]
        for col in ["name", "rate_type", "sku_group", "active"] + FLAG_COLS:
            if col not in cols:
                con.execute(f"ALTER TABLE vendors ADD COLUMN {col} TEXT;")
        
        # aliases 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS aliases(
                alias     TEXT,
                vendor    TEXT,
                file_type TEXT,
                PRIMARY KEY(alias, file_type)
            )""")
        con.commit()


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.get("", response_model=List[VendorResponse])
@router.get("/", response_model=List[VendorResponse])
async def list_vendors(active_only: bool = False):
    """전체 거래처 목록 조회"""
    ensure_tables()
    with get_connection() as con:
        query = "SELECT * FROM vendors"
        if active_only:
            query += " WHERE active = 'YES'"
        query += " ORDER BY vendor"
        df = pd.read_sql(query, con)
    
    return df.to_dict(orient="records")


@router.get("/{vendor_id}", response_model=Dict[str, Any])
async def get_vendor(vendor_id: str):
    """특정 거래처 상세 조회 (별칭 포함)"""
    ensure_tables()
    with get_connection() as con:
        vendor_row = con.execute(
            "SELECT * FROM vendors WHERE vendor = ?", (vendor_id,)
        ).fetchone()
        
        if not vendor_row:
            raise HTTPException(status_code=404, detail="Vendor not found")
        
        # 컬럼명 가져오기
        cols = [c[1] for c in con.execute("PRAGMA table_info(vendors);")]
        vendor_dict = dict(zip(cols, vendor_row))
        
        # 별칭 조회
        aliases_df = pd.read_sql(
            "SELECT alias, file_type FROM aliases WHERE vendor = ?",
            con, params=[vendor_id]
        )
        
        alias_map = {
            "alias_inbound_slip": [],
            "alias_shipping_stats": [],
            "alias_kpost_in": [],
            "alias_kpost_ret": [],
            "alias_work_log": []
        }
        
        for _, row in aliases_df.iterrows():
            key = f"alias_{row['file_type']}"
            if key in alias_map:
                alias_map[key].append(row['alias'])
        
        vendor_dict.update(alias_map)
    
    return vendor_dict


@router.post("", response_model=Dict[str, str])
@router.post("/", response_model=Dict[str, str])
async def create_or_update_vendor(data: VendorCreate):
    """거래처 생성 또는 업데이트"""
    ensure_tables()
    
    if not data.vendor.strip():
        raise HTTPException(status_code=400, detail="vendor(PK) is required")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    
    try:
        with get_connection() as con:
            # 존재 여부 확인
            existing = con.execute(
                "SELECT 1 FROM vendors WHERE vendor = ?", (data.vendor,)
            ).fetchone()
            
            if existing:
                # 업데이트
                con.execute("""
                    UPDATE vendors SET 
                        name=?, rate_type=?, sku_group=?, active=?,
                        barcode_f=?, custbox_f=?, void_f=?, pp_bag_f=?, mailer_f=?,
                        video_out_f=?, video_ret_f=?
                    WHERE vendor=?
                """, (
                    data.name.strip(), data.rate_type, data.sku_group, data.active,
                    data.barcode_f, data.custbox_f, data.void_f, data.pp_bag_f, data.mailer_f,
                    data.video_out_f, data.video_ret_f, data.vendor
                ))
                action = "updated"
            else:
                # 신규 삽입
                con.execute("""
                    INSERT INTO vendors(
                        vendor, name, rate_type, sku_group, active,
                        barcode_f, custbox_f, void_f, pp_bag_f, mailer_f,
                        video_out_f, video_ret_f
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    data.vendor, data.name.strip(), data.rate_type, data.sku_group, data.active,
                    data.barcode_f, data.custbox_f, data.void_f, data.pp_bag_f, data.mailer_f,
                    data.video_out_f, data.video_ret_f
                ))
                action = "created"
            
            # 별칭 저장
            con.execute("DELETE FROM aliases WHERE vendor = ?", (data.vendor,))
            
            def insert_aliases(file_type: str, aliases: List[str]):
                for alias in aliases:
                    if alias.strip():
                        con.execute(
                            "INSERT OR REPLACE INTO aliases VALUES (?, ?, ?)",
                            (alias.strip(), data.vendor, file_type)
                        )
            
            insert_aliases("inbound_slip", data.alias_inbound_slip)
            insert_aliases("shipping_stats", data.alias_shipping_stats)
            insert_aliases("kpost_in", data.alias_kpost_in)
            insert_aliases("kpost_ret", data.alias_kpost_ret)
            insert_aliases("work_log", data.alias_work_log)
            
            con.commit()
        
        return {"status": "success", "action": action, "vendor": data.vendor}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: str):
    """거래처 삭제"""
    ensure_tables()
    try:
        with get_connection() as con:
            con.execute("DELETE FROM vendors WHERE vendor = ?", (vendor_id,))
            con.execute("DELETE FROM aliases WHERE vendor = ?", (vendor_id,))
            con.commit()
        return {"status": "success", "deleted": vendor_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aliases/unmatched", response_model=List[UnmatchedAliasResponse])
async def get_unmatched_aliases():
    """미매칭 별칭 목록 조회"""
    ensure_tables()
    
    SRC_TABLES = [
        ("inbound_slip", "공급처", "inbound_slip"),
        ("shipping_stats", "공급처", "shipping_stats"),
        ("kpost_in", "발송인명", "kpost_in"),
        ("kpost_ret", "수취인명", "kpost_ret"),
        ("work_log", "업체명", "work_log"),
    ]
    
    result = []
    
    with get_connection() as con:
        for tbl, col, ft in SRC_TABLES:
            # 테이블 존재 확인
            table_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone()
            
            if not table_exists:
                continue
            
            # 컬럼 존재 확인
            cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
            if col not in cols:
                continue
            
            try:
                # 전체 alias
                all_aliases = pd.read_sql(
                    f"SELECT DISTINCT [{col}] as alias FROM {tbl} WHERE [{col}] IS NOT NULL AND TRIM([{col}]) != ''",
                    con
                )
                
                # 매핑된 alias
                mapped = pd.read_sql(
                    "SELECT DISTINCT alias FROM aliases WHERE file_type = ?",
                    con, params=[ft]
                )
                
                # 미매칭 찾기
                if not all_aliases.empty:
                    unmatched = all_aliases[~all_aliases['alias'].isin(mapped['alias'])]
                    if not unmatched.empty:
                        result.append({
                            "file_type": ft,
                            "aliases": unmatched['alias'].tolist(),
                            "count": len(unmatched)
                        })
            except Exception:
                continue
    
    return result


@router.get("/aliases/available/{file_type}", response_model=List[str])
async def get_available_aliases(file_type: str, exclude_vendor: Optional[str] = None):
    """특정 파일 타입에서 사용 가능한 별칭 목록"""
    ensure_tables()
    
    SRC_TABLES = {
        "inbound_slip": ("inbound_slip", "공급처"),
        "shipping_stats": ("shipping_stats", "공급처"),
        "kpost_in": ("kpost_in", "발송인명"),
        "kpost_ret": ("kpost_ret", "수취인명"),
        "work_log": ("work_log", "업체명"),
    }
    
    if file_type not in SRC_TABLES:
        return []
    
    tbl, col = SRC_TABLES[file_type]
    
    with get_connection() as con:
        # 테이블 존재 확인
        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
        ).fetchone()
        
        if not table_exists:
            return []
        
        # 컬럼 존재 확인
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
        if col not in cols:
            return []
        
        try:
            # 원본 테이블에서 모든 고유 값
            all_aliases = pd.read_sql(
                f"SELECT DISTINCT [{col}] as alias FROM {tbl} WHERE [{col}] IS NOT NULL AND TRIM([{col}]) != ''",
                con
            )
            
            # 이미 매핑된 별칭 (특정 vendor 제외 가능)
            if exclude_vendor:
                mapped = pd.read_sql(
                    "SELECT DISTINCT alias FROM aliases WHERE file_type = ? AND vendor != ?",
                    con, params=[file_type, exclude_vendor]
                )
            else:
                mapped = pd.read_sql(
                    "SELECT DISTINCT alias FROM aliases WHERE file_type = ?",
                    con, params=[file_type]
                )
            
            # 사용 가능한 별칭 (매핑되지 않은 것)
            if not all_aliases.empty:
                available = all_aliases[~all_aliases['alias'].isin(mapped['alias'])]
                return sorted(available['alias'].tolist())
            
        except Exception:
            pass
    
    return []

