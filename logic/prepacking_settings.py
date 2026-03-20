"""
logic/prepacking_settings.py - 설정 & 공급처 & 로케이션
─────────────────────────────────────────────────────
프리패킹 설정 CRUD, 공급처 목록, 로케이션 자동완성.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .db import get_connection, now_str

_DEFAULTS = {"min_predicted_qty": 1, "min_frequency": 1, "min_sku_count": 2, "retention_days": 2}


def get_settings(vendor: str = "_default") -> Dict[str, Any]:
    with get_connection() as con:
        row = con.execute(
            "SELECT min_predicted_qty, min_frequency, min_sku_count, retention_days "
            "FROM prepacking_settings WHERE vendor = ?", (vendor,),
        ).fetchone()
        if not row and vendor != "_default":
            row = con.execute(
                "SELECT min_predicted_qty, min_frequency, min_sku_count, retention_days "
                "FROM prepacking_settings WHERE vendor = '_default'",
            ).fetchone()
    if row:
        return {"min_predicted_qty": row[0], "min_frequency": row[1], "min_sku_count": row[2], "retention_days": row[3]}
    return dict(_DEFAULTS)


def save_settings(vendor: str, settings: Dict[str, Any]) -> None:
    with get_connection() as con:
        con.execute(
            """INSERT INTO prepacking_settings (vendor, min_predicted_qty, min_frequency, min_sku_count, retention_days, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(vendor) DO UPDATE SET
                 min_predicted_qty=excluded.min_predicted_qty,
                 min_frequency=excluded.min_frequency,
                 min_sku_count=excluded.min_sku_count,
                 retention_days=excluded.retention_days,
                 updated_at=excluded.updated_at""",
            (
                vendor,
                settings.get("min_predicted_qty", 3),
                settings.get("min_frequency", 5),
                settings.get("min_sku_count", 2),
                settings.get("retention_days", 2),
                now_str(),
            ),
        )
        con.commit()


def get_all_settings() -> List[Dict[str, Any]]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT vendor, min_predicted_qty, min_frequency, min_sku_count, retention_days "
            "FROM prepacking_settings ORDER BY vendor"
        ).fetchall()
    return [
        {"vendor": r[0], "min_predicted_qty": r[1], "min_frequency": r[2], "min_sku_count": r[3], "retention_days": r[4]}
        for r in rows
    ]


def suggest_locations(vendor: str, prefix: str = "", limit: int = 10) -> List[str]:
    with get_connection() as con:
        if prefix:
            rows = con.execute(
                "SELECT DISTINCT location FROM prepacking_productions "
                "WHERE vendor=? AND location LIKE ? AND location != '' ORDER BY updated_at DESC LIMIT ?",
                (vendor, f"{prefix}%", limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT DISTINCT location FROM prepacking_productions "
                "WHERE vendor=? AND location != '' ORDER BY updated_at DESC LIMIT ?",
                (vendor, limit),
            ).fetchall()
    return [r[0] for r in rows]


def get_vendors_with_data() -> List[str]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT DISTINCT 공급처 FROM shipping_stats WHERE 공급처 IS NOT NULL AND 공급처 != '' ORDER BY 공급처"
        ).fetchall()
    return [r[0] for r in rows]
