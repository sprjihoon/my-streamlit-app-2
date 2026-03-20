from __future__ import annotations

import sqlite3

from prepacking.common.enums import LocationAction
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.location import location_repository
from prepacking.services.location.location_history_service import record_history


def create_location(
    location_code: str,
    location_name: str = "",
    zone: str = "",
    location_type: str = "shelf",
    max_capacity: int = 100,
) -> bool:
    data = {
        "location_code": location_code,
        "location_name": location_name,
        "location_zone": zone,
        "location_type": location_type,
        "max_capacity": max_capacity,
        "current_capacity": 0,
        "is_active": 1,
        "note": "",
    }
    return location_repository.insert_location(data)


def get_locations(zone: str | None = None, active_only: bool = True) -> list[dict]:
    return location_repository.get_all_locations(zone=zone, active_only=active_only)


def update_location_capacity(location_code: str, delta: int) -> bool:
    return location_repository.update_capacity(location_code, delta)


def move_stock(
    stock_id: int,
    from_location: str,
    to_location: str,
    qty: int,
    moved_by: str = "",
    reason: str = "",
) -> bool:
    ensure_pp_tables()
    if qty <= 0 or not to_location:
        return False
    loc_f = location_repository.get_location(from_location) if from_location else True
    loc_t = location_repository.get_location(to_location)
    if from_location and not loc_f:
        return False
    if not loc_t:
        return False
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT location_code, current_qty, available_qty FROM pp_stock WHERE prepack_stock_id = ?",
            (stock_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        s = dict(row)
        if from_location and (s.get("location_code") or "") != from_location:
            return False
        avail = int(s.get("available_qty") or 0)
        if qty > avail:
            return False
        con.execute(
            """
            UPDATE pp_stock
            SET location_code = ?, last_moved_at = CURRENT_TIMESTAMP
            WHERE prepack_stock_id = ?
            """,
            (to_location, stock_id),
        )
        con.commit()
    record_history(
        stock_id,
        LocationAction.MOVE.value,
        from_location,
        to_location,
        qty,
        action_by=moved_by,
        reason=reason,
    )
    if from_location:
        location_repository.update_capacity(from_location, -qty)
    location_repository.update_capacity(to_location, qty)
    return True
