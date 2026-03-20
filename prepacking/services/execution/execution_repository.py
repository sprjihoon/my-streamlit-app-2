from __future__ import annotations

import sqlite3

from prepacking.database import ensure_pp_tables, get_pp_connection


def insert_execution(data: dict) -> int:
    ensure_pp_tables()
    cols = [
        "recommendation_id",
        "supplier_name",
        "target_type",
        "target_code",
        "target_name",
        "executed_qty",
        "executed_pack_unit",
        "executed_by",
        "execution_status",
        "memo",
    ]
    row = {k: data.get(k) for k in cols}
    placeholders = ", ".join("?" * len(cols))
    names = ", ".join(cols)
    with get_pp_connection() as con:
        con.execute(
            f"INSERT INTO pp_executions ({names}) VALUES ({placeholders})",
            tuple(row[c] for c in cols),
        )
        con.commit()
        cur = con.execute("SELECT last_insert_rowid()")
        return int(cur.fetchone()[0])


def get_executions_filtered(
    supplier_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    ensure_pp_tables()
    sql = "SELECT * FROM pp_executions WHERE 1=1"
    params: list = []
    if supplier_name:
        sql += " AND supplier_name = ?"
        params.append(supplier_name)
    if date_from:
        sql += " AND date(executed_at) >= date(?)"
        params.append(date_from)
    if date_to:
        sql += " AND date(executed_at) <= date(?)"
        params.append(date_to)
    sql += " ORDER BY executed_at DESC"
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def get_execution_by_id(execution_id: int) -> dict | None:
    ensure_pp_tables()
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_executions WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
