from __future__ import annotations

import sqlite3

from prepacking.database import ensure_pp_tables, get_pp_connection


def record_history(
    stock_id: int,
    action_type: str,
    from_loc: str,
    to_loc: str,
    qty: int,
    action_by: str = "",
    reason: str = "",
    recommendation_id: int | None = None,
    execution_id: int | None = None,
) -> int:
    ensure_pp_tables()
    meta: dict = {}
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT target_type, target_code, target_name FROM pp_stock WHERE prepack_stock_id = ?",
            (stock_id,),
        )
        s = cur.fetchone()
        if s:
            meta = dict(s)
    tgt_type = meta.get("target_type") or ""
    tgt_code = meta.get("target_code") or ""
    tgt_name = meta.get("target_name") or ""
    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_location_history (
                prepack_stock_id, target_type, target_code, target_name,
                action_type, from_location, to_location, qty,
                related_recommendation_id, related_execution_id,
                action_reason, action_by, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stock_id,
                tgt_type,
                tgt_code,
                tgt_name,
                action_type,
                from_loc,
                to_loc,
                qty,
                recommendation_id,
                execution_id,
                reason,
                action_by,
                "",
            ),
        )
        con.commit()
        cur = con.execute("SELECT last_insert_rowid()")
        return int(cur.fetchone()[0])


def get_history(
    stock_id: int | None = None,
    location_code: str | None = None,
    limit: int = 100,
) -> list[dict]:
    ensure_pp_tables()
    sql = "SELECT * FROM pp_location_history WHERE 1=1"
    params: list = []
    if stock_id is not None:
        sql += " AND prepack_stock_id = ?"
        params.append(stock_id)
    if location_code:
        sql += " AND (from_location = ? OR to_location = ?)"
        params.extend([location_code, location_code])
    sql += " ORDER BY action_at DESC LIMIT ?"
    params.append(limit)
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
