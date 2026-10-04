"""Vendor, rate, storage, and vendor-charge lookups."""
from typing import Any, Dict

from logic.db import get_connection

from .common import _clamp_limit, _clamp_offset, _fetch_allowed

_RATE_TABLE_COLS = {
    "out_basic": ["SKU 구간", "출고비"],
    "out_extra": ["항목", "단가"],
    "shipping_zone": ["요금제", "구간", "len_min_cm", "len_max_cm", "요금"],
    "material_rates": ["항목", "단가", "size_code"],
}
_RATE_TABLE_ORDER = {
    "out_basic": "SKU 구간",
    "out_extra": "항목",
    "shipping_zone": "요금제",
    "material_rates": "항목",
}

def _lookup_vendors(args: Dict, user_id: str, user_name: str) -> Dict:
    q = (args.get("query") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    where = "vendor IS NOT NULL"
    params: tuple = ()
    if q:
        where += " AND (vendor LIKE ? OR IFNULL(name, '') LIKE ?)"
        params = (f"%{q}%", f"%{q}%")
    with get_connection() as con:
        vendors = _fetch_allowed(
            con, "vendors", ["vendor", "name"],
            where=where, params=params, order_by="vendor",
            limit=limit, offset=offset,
        )
        alias_where = "alias IS NOT NULL AND vendor IS NOT NULL"
        alias_params: tuple = ()
        if q:
            alias_where += " AND (alias LIKE ? OR vendor LIKE ?)"
            alias_params = (f"%{q}%", f"%{q}%")
        aliases = _fetch_allowed(
            con, "aliases", ["alias", "vendor"],
            where=alias_where, params=alias_params, order_by="alias",
            limit=limit, offset=offset,
        )
    return {
        "success": True,
        "vendors": [r.get("vendor") for r in vendors["rows"] if r.get("vendor")],
        "aliases": aliases["rows"],
        "truncated": vendors["truncated"] or aliases["truncated"],
        "limit": limit,
        "offset": offset,
    }

def _lookup_rate_tables(args: Dict, user_id: str, user_name: str) -> Dict:
    table = (args.get("table") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    if table == "all" or not table:
        return {
            "success": False,
            "error": "테이블을 하나만 지정하세요: out_basic, out_extra, shipping_zone, material_rates",
            "allowed_tables": list(_RATE_TABLE_COLS.keys()),
        }
    if table not in _RATE_TABLE_COLS:
        return {"success": False, "error": "허용되지 않은 요금 테이블입니다.", "allowed_tables": list(_RATE_TABLE_COLS)}
    with get_connection() as con:
        fetched = _fetch_allowed(
            con, table, _RATE_TABLE_COLS[table],
            order_by=_RATE_TABLE_ORDER[table],
            limit=limit, offset=offset,
        )
    return {
        "success": True,
        "table": table,
        "rows": fetched["rows"],
        "truncated": fetched["truncated"],
        "limit": limit,
        "offset": offset,
    }

def _lookup_storage(args: Dict, user_id: str, user_name: str) -> Dict:
    vendor = (args.get("vendor") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    result: Dict[str, Any] = {"success": True, "storage_rates": [], "vendor_storage": []}
    with get_connection() as con:
        rates = _fetch_allowed(
            con, "storage_rates",
            ["item_name", "unit_price", "unit", "description", "is_active"],
            order_by="item_name", limit=limit, offset=offset,
        )
        result["storage_rates"] = rates["rows"]
        vs_where = "1=1"
        vs_params: tuple = ()
        if vendor:
            vs_where = "vendor_id LIKE ? OR item_name LIKE ?"
            vs_params = (f"%{vendor}%", f"%{vendor}%")
        storage = _fetch_allowed(
            con, "vendor_storage",
            ["vendor_id", "item_name", "qty", "unit_price", "amount", "period", "remark", "is_active"],
            where=vs_where, params=vs_params, order_by="vendor_id",
            limit=limit, offset=offset,
        )
        result["vendor_storage"] = storage["rows"]
        result["truncated"] = rates["truncated"] or storage["truncated"]
        result["limit"] = limit
        result["offset"] = offset
    return result

def _lookup_vendor_charges_tool(args: Dict, user_id: str, user_name: str) -> Dict:
    vendor = (args.get("vendor") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    where = "1=1"
    params: tuple = ()
    if vendor:
        where = "vendor_id LIKE ? OR item_name LIKE ?"
        params = (f"%{vendor}%", f"%{vendor}%")
    with get_connection() as con:
        fetched = _fetch_allowed(
            con, "vendor_charges",
            ["vendor_id", "item_name", "qty", "unit_price", "amount", "remark", "charge_type", "is_active"],
            where=where, params=params, order_by="vendor_id",
            limit=limit, offset=offset,
        )
    if fetched.get("missing"):
        return {"success": True, "charges": [], "message": "추가 청구 테이블이 없습니다."}
    return {
        "success": True,
        "charges": fetched["rows"],
        "truncated": fetched["truncated"],
        "limit": limit,
        "offset": offset,
    }
