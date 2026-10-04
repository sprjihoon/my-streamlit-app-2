"""Shared auth, table setup, and pickup row mapping."""
from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from backend.app.services.epost.fields import treat_status_label
from logic.db import get_connection

KST = ZoneInfo("Asia/Seoul")


def ensure_pickup_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS kpost_pickup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor TEXT NOT NULL DEFAULT 'infront',
                order_no TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT NOT NULL,
                zipcode TEXT NOT NULL,
                addr1 TEXT NOT NULL,
                addr2 TEXT NOT NULL,
                pickup_date TEXT NOT NULL,
                goods_name TEXT,
                box_size TEXT,
                box_quantity INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                tracking_no TEXT,
                req_no TEXT,
                res_no TEXT,
                res_date TEXT,
                price TEXT,
                post_office TEXT,
                treat_status TEXT,
                treat_status_name TEXT,
                status TEXT NOT NULL DEFAULT 'requested',
                is_test INTEGER NOT NULL DEFAULT 0,
                insert_snapshot TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                canceled_at TEXT,
                canceled_by TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_kpost_pickup_created ON kpost_pickup_requests(created_at DESC)"
        )
        
        # Migration: Add box_quantity column if it doesn't exist
        try:
            con.execute("SELECT box_quantity FROM kpost_pickup_requests LIMIT 1")
        except Exception:
            con.execute("ALTER TABLE kpost_pickup_requests ADD COLUMN box_quantity INTEGER NOT NULL DEFAULT 1")

        # Migration: 숫자코드 treat_status → Korean text (1회성, 이미 변환된 행은 영향 없음)
        from backend.app.services.epost.fields import TREAT_STATUS_LABELS
        for code, label in TREAT_STATUS_LABELS.items():
            con.execute(
                "UPDATE kpost_pickup_requests SET treat_status=?, treat_status_name=? "
                "WHERE treat_status=?",
                (label, label, code),
            )
        
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT NOT NULL,
                zipcode TEXT NOT NULL,
                addr1 TEXT NOT NULL,
                addr2 TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, label)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_saved_recipients_user ON saved_recipients(user_id, created_at DESC)"
        )
        con.commit()


def _get_user(token: str) -> dict[str, Any]:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        row = con.execute(
            """
            SELECT u.user_id, u.nickname, u.department, u.is_admin
            FROM sessions s JOIN users u USING(user_id)
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return {
        "user_id": row[0],
        "nickname": row[1] or "",
        "department": row[2] or "",
        "is_admin": bool(row[3]),
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    keys = [
        "id",
        "vendor",
        "order_no",
        "recipient_name",
        "recipient_phone",
        "zipcode",
        "addr1",
        "addr2",
        "pickup_date",
        "goods_name",
        "box_size",
        "box_quantity",
        "notes",
        "tracking_no",
        "req_no",
        "res_no",
        "res_date",
        "price",
        "post_office",
        "treat_status",
        "treat_status_name",
        "status",
        "is_test",
        "created_by",
        "created_at",
        "canceled_at",
        "canceled_by",
    ]
    data = dict(zip(keys, row))
    data["is_test"] = bool(data["is_test"])
    if data.get("status") == "canceled":
        data["treat_status_name"] = "취소"
    else:
        data["treat_status_name"] = treat_status_label(
            data.get("treat_status"), data.get("treat_status_name")
        )
    return data
