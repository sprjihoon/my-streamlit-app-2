from __future__ import annotations

import sqlite3

from prepacking.common.enums import LocationAction, PackStatus
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.location.location_history_service import record_history
from prepacking.services.stock.prepack_stock_service import get_stock_by_id


def unwrap_stock(
    stock_id: int,
    unwrap_qty: int,
    reason: str = "",
    return_to_stock: bool = False,
    return_location: str = "",
    unwrap_by: str = "",
) -> dict:
    ensure_pp_tables()
    if unwrap_qty <= 0:
        return {}
    s = get_stock_by_id(stock_id)
    if not s:
        return {}
    curq = int(s.get("current_qty") or 0)
    avail = int(s.get("available_qty") or 0)
    take = min(unwrap_qty, avail, curq)
    if take <= 0:
        return {}
    new_cur = curq - take
    new_avail = max(0, avail - take)
    if new_cur <= 0:
        new_status = PackStatus.UNWRAPPED.value
    else:
        new_status = PackStatus.WAITING_UNWRAP.value
    loc = s.get("location_code") or ""
    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_unwrap_history (
                prepack_stock_id, supplier_name, target_type, target_code, target_name,
                unwrap_qty, unwrap_reason, return_to_stock_yn, return_location,
                unwrap_by, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (
                stock_id,
                s.get("supplier_name") or "",
                s.get("target_type") or "",
                s.get("target_code") or "",
                s.get("target_name") or "",
                take,
                reason,
                1 if return_to_stock else 0,
                return_location,
                unwrap_by,
            ),
        )
        con.execute(
            """
            UPDATE pp_stock
            SET current_qty = ?, available_qty = ?, pack_status = ?
            WHERE prepack_stock_id = ?
            """,
            (new_cur, new_avail, new_status, stock_id),
        )
        con.commit()
        cur = con.execute("SELECT last_insert_rowid()")
        unwrap_id = int(cur.fetchone()[0])
    record_history(
        stock_id,
        LocationAction.UNWRAP.value,
        loc,
        return_location or loc,
        take,
        action_by=unwrap_by,
        reason=reason,
    )
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_unwrap_history WHERE unwrap_id = ?",
            (unwrap_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def get_unwrap_history(supplier_name: str | None = None, limit: int = 100) -> list[dict]:
    ensure_pp_tables()
    sql = "SELECT * FROM pp_unwrap_history WHERE 1=1"
    params: list = []
    if supplier_name:
        sql += " AND supplier_name = ?"
        params.append(supplier_name)
    sql += " ORDER BY unwrap_at DESC LIMIT ?"
    params.append(limit)
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
