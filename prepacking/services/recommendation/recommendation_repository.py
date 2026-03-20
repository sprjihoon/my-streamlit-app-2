from __future__ import annotations

from prepacking.database import ensure_pp_tables, get_pp_connection


def _fetchone_dict(cur) -> dict | None:
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _fetchall_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def insert_recommendation(data: dict) -> int:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            INSERT INTO pp_recommendations (
                recommendation_date, target_date, supplier_name, target_type,
                target_code, target_name, option_name, combination_key,
                predicted_qty, recommended_pack_unit, confidence_score, risk_score,
                recommendation_reason, weekday_basis, recent_7d_avg, recent_30d_avg,
                recent_same_weekday_avg, source_upload_id, status
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                data.get("recommendation_date"),
                data.get("target_date"),
                data.get("supplier_name"),
                data.get("target_type"),
                data.get("target_code", ""),
                data.get("target_name"),
                data.get("option_name", ""),
                data.get("combination_key", ""),
                int(data.get("predicted_qty", 0)),
                int(data.get("recommended_pack_unit", 1)),
                float(data.get("confidence_score", 0.0)),
                float(data.get("risk_score", 0.0)),
                data.get("recommendation_reason", ""),
                data.get("weekday_basis"),
                float(data.get("recent_7d_avg", 0.0)),
                float(data.get("recent_30d_avg", 0.0)),
                float(data.get("recent_same_weekday_avg", 0.0)),
                data.get("source_upload_id"),
                data.get("status", "recommended"),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def update_recommendation_status(recommendation_id: int, status: str) -> bool:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            UPDATE pp_recommendations
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE recommendation_id = ?
            """,
            (status, int(recommendation_id)),
        )
        con.commit()
        return cur.rowcount > 0


def get_recommendations_by_date(supplier_name: str, target_date: str) -> list[dict]:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT * FROM pp_recommendations
            WHERE supplier_name = ? AND target_date = ?
            ORDER BY recommendation_id DESC
            """,
            (supplier_name, target_date),
        )
        return _fetchall_dicts(cur)


def get_recommendation_by_id(recommendation_id: int) -> dict | None:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            "SELECT * FROM pp_recommendations WHERE recommendation_id = ?",
            (int(recommendation_id),),
        )
        return _fetchone_dict(cur)
