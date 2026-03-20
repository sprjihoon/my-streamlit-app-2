from __future__ import annotations

import sqlite3

from prepacking.database import ensure_pp_tables, get_pp_connection


def insert_location(data: dict) -> bool:
    ensure_pp_tables()
    cols = [
        "location_code",
        "location_name",
        "location_zone",
        "location_type",
        "max_capacity",
        "current_capacity",
        "is_active",
        "note",
    ]
    row = {c: data.get(c) for c in cols}
    placeholders = ", ".join("?" * len(cols))
    names = ", ".join(cols)
    try:
        with get_pp_connection() as con:
            con.execute(
                f"INSERT INTO pp_locations ({names}) VALUES ({placeholders})",
                tuple(row[c] for c in cols),
            )
            con.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_all_locations(
    zone: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    ensure_pp_tables()
    sql = "SELECT * FROM pp_locations WHERE 1=1"
    params: list = []
    if zone:
        sql += " AND location_zone = ?"
        params.append(zone)
    if active_only:
        sql += " AND is_active = 1"
    sql += " ORDER BY location_zone, location_code"
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def update_capacity(location_code: str, delta: int) -> bool:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            UPDATE pp_locations
            SET current_capacity = MAX(0, current_capacity + ?)
            WHERE location_code = ?
            """,
            (delta, location_code),
        )
        con.commit()
        return cur.rowcount > 0


def get_location(location_code: str) -> dict | None:
    ensure_pp_tables()
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_locations WHERE location_code = ?",
            (location_code,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
