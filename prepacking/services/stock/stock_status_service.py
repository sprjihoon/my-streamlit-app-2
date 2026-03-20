from __future__ import annotations

import datetime as dt
import sqlite3

from prepacking.common.date_helper import now_kst
from prepacking.common.enums import PackStatus
from prepacking.database import ensure_pp_tables, get_pp_connection


def get_stock_summary(supplier_name: str | None = None) -> dict:
    ensure_pp_tables()
    base = "SELECT pack_status, location_code, current_qty, available_qty FROM pp_stock WHERE 1=1"
    params: list = []
    if supplier_name:
        base += " AND supplier_name = ?"
        params.append(supplier_name)
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(base, params).fetchall()]
    total_packed = sum(int(r.get("current_qty") or 0) for r in rows)
    total_available = sum(int(r.get("available_qty") or 0) for r in rows)
    by_status: dict[str, int] = {}
    by_location: dict[str, int] = {}
    for r in rows:
        st = r.get("pack_status") or ""
        by_status[st] = by_status.get(st, 0) + 1
        loc = r.get("location_code") or ""
        by_location[loc] = by_location.get(loc, 0) + 1
    return {
        "total_packed": total_packed,
        "total_available": total_available,
        "by_status": by_status,
        "by_location": by_location,
    }


def get_expiring_stock(days_ahead: int = 2) -> list[dict]:
    ensure_pp_tables()
    end = (now_kst().date() + dt.timedelta(days=max(0, days_ahead))).strftime("%Y-%m-%d")
    today = now_kst().date().strftime("%Y-%m-%d")
    skip = (PackStatus.FULLY_USED.value, PackStatus.DISPOSED.value)
    sql = f"""
        SELECT * FROM pp_stock
        WHERE expiry_at IS NOT NULL AND expiry_at != ''
          AND date(expiry_at) <= date(?)
          AND date(expiry_at) >= date(?)
          AND pack_status NOT IN ({",".join("?" * len(skip))})
        ORDER BY expiry_at ASC
    """
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, (end, today, *skip))
        return [dict(r) for r in cur.fetchall()]
