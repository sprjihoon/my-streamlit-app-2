from __future__ import annotations

import sqlite3

from prepacking.common.date_helper import now_str
from prepacking.common.enums import LocationAction
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.location.location_history_service import record_history


def restore_to_stock(
    unwrap_id: int,
    restore_location: str = "",
    restored_by: str = "",
) -> dict:
    ensure_pp_tables()
    marker = "[RESTORED]"
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_unwrap_history WHERE unwrap_id = ?",
            (unwrap_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "unwrap_not_found"}
        u = dict(row)
        memo = u.get("memo") or ""
        if marker in memo:
            return {"ok": False, "error": "already_restored", "unwrap_id": unwrap_id}
        stock_id = int(u.get("prepack_stock_id") or 0)
        suffix = f"{marker} {now_str()} by={restored_by}"
        con.execute(
            "UPDATE pp_unwrap_history SET memo = trim(COALESCE(memo,'') || ' ' || ?) WHERE unwrap_id = ?",
            (suffix, unwrap_id),
        )
        con.commit()
    if stock_id:
        record_history(
            stock_id,
            LocationAction.RETURN.value,
            u.get("return_location") or "",
            restore_location,
            int(u.get("unwrap_qty") or 0),
            action_by=restored_by,
            reason="restore_unwrap",
        )
    return {
        "ok": True,
        "unwrap_id": unwrap_id,
        "prepack_stock_id": stock_id,
        "restore_location": restore_location,
    }
