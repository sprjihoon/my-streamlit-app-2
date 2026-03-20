from __future__ import annotations

from prepacking.database import ensure_pp_tables, get_pp_connection


def _fetchall_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def insert_approval(data: dict) -> int:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            INSERT INTO pp_approvals (
                recommendation_id, action_type, original_qty, adjusted_qty,
                action_reason, approved_by, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(data["recommendation_id"]),
                data.get("action_type"),
                int(data.get("original_qty", 0)),
                int(data.get("adjusted_qty", 0)),
                data.get("action_reason", ""),
                data.get("approved_by", ""),
                data.get("memo", ""),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def get_approvals_by_recommendation(recommendation_id: int) -> list[dict]:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT * FROM pp_approvals
            WHERE recommendation_id = ?
            ORDER BY approval_id ASC
            """,
            (int(recommendation_id),),
        )
        return _fetchall_dicts(cur)
