from __future__ import annotations

import datetime as dt
import sqlite3

from prepacking.common.date_helper import now_kst
from prepacking.common.enums import PackStatus
from prepacking.database import ensure_pp_tables, get_pp_connection


def create_stock(
    supplier_name: str,
    target_type: str,
    target_name: str,
    combination_key: str,
    qty: int,
    location_code: str = "",
    execution_id: int | None = None,
    option_name: str = "",
    expiry_days: int = 7,
) -> int:
    ensure_pp_tables()
    exp = (now_kst().date() + dt.timedelta(days=max(0, expiry_days))).strftime("%Y-%m-%d")
    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_stock (
                supplier_name, target_type, target_code, target_name, option_name,
                combination_key, current_qty, reserved_qty, available_qty,
                pack_status, location_code, packed_at, expiry_at, last_moved_at,
                source_execution_id, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, CURRENT_TIMESTAMP, ?, NULL, ?, '')
            """,
            (
                supplier_name,
                target_type,
                combination_key or "",
                target_name,
                option_name,
                combination_key,
                qty,
                qty,
                PackStatus.PACKED.value,
                location_code,
                exp,
                execution_id,
            ),
        )
        con.commit()
        cur = con.execute("SELECT last_insert_rowid()")
        return int(cur.fetchone()[0])


def use_stock(stock_id: int, use_qty: int) -> dict:
    ensure_pp_tables()
    if use_qty <= 0:
        row = get_stock_by_id(stock_id)
        return row or {}
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_stock WHERE prepack_stock_id = ?",
            (stock_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        s = dict(row)
        avail = int(s.get("available_qty") or 0)
        curq = int(s.get("current_qty") or 0)
        orig_cur = curq
        take = min(use_qty, avail, curq)
        new_cur = curq - take
        new_avail = max(0, avail - take)
        if new_cur <= 0:
            status = PackStatus.FULLY_USED.value
        elif new_cur < orig_cur:
            status = PackStatus.PARTIALLY_USED.value
        else:
            status = s.get("pack_status") or PackStatus.PACKED.value
        con.execute(
            """
            UPDATE pp_stock
            SET current_qty = ?, available_qty = ?, pack_status = ?, memo = memo
            WHERE prepack_stock_id = ?
            """,
            (new_cur, new_avail, status, stock_id),
        )
        con.commit()
    return get_stock_by_id(stock_id) or {}


def get_active_stock(supplier_name: str | None = None) -> list[dict]:
    ensure_pp_tables()
    active = (
        PackStatus.PACKED.value,
        PackStatus.PARTIALLY_USED.value,
    )
    sql = f"""
        SELECT * FROM pp_stock
        WHERE pack_status IN ({",".join("?" * len(active))})
    """
    params: list = list(active)
    if supplier_name:
        sql += " AND supplier_name = ?"
        params.append(supplier_name)
    sql += " ORDER BY packed_at DESC"
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def get_stock_by_id(stock_id: int) -> dict | None:
    ensure_pp_tables()
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_stock WHERE prepack_stock_id = ?",
            (stock_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_stock_status(stock_id: int, new_status: str) -> bool:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            "UPDATE pp_stock SET pack_status = ? WHERE prepack_stock_id = ?",
            (new_status, stock_id),
        )
        con.commit()
        return cur.rowcount > 0
