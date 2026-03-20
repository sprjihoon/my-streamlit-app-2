from __future__ import annotations

import datetime as dt

from prepacking.common.date_helper import today_kst
from prepacking.database import get_pp_connection


def _start_date(days: int) -> str:
    d = today_kst() - dt.timedelta(days=max(0, int(days)))
    return d.strftime("%Y-%m-%d")


def get_overview_report(supplier_name: str = None, days: int = 30) -> dict:
    start = _start_date(days)
    sup = (supplier_name or "").strip() or None
    with get_pp_connection() as con:
        if sup:
            total_recommendations = con.execute(
                """
                SELECT COUNT(*) FROM pp_recommendations
                WHERE recommendation_date >= ? AND supplier_name = ?
                """,
                (start, sup),
            ).fetchone()[0]
            approved_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_recommendations
                WHERE recommendation_date >= ? AND supplier_name = ? AND status = 'approved'
                """,
                (start, sup),
            ).fetchone()[0]
            rejected_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_recommendations
                WHERE recommendation_date >= ? AND supplier_name = ? AND status = 'rejected'
                """,
                (start, sup),
            ).fetchone()[0]
            executed_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_executions
                WHERE date(executed_at) >= date(?) AND supplier_name = ?
                """,
                (start, sup),
            ).fetchone()[0]
            row_prod = con.execute(
                """
                SELECT COALESCE(SUM(executed_qty), 0) FROM pp_executions
                WHERE date(executed_at) >= date(?) AND supplier_name = ?
                """,
                (start, sup),
            ).fetchone()
            total_produced_qty = int(row_prod[0] or 0)
            row_used = con.execute(
                """
                SELECT COALESCE(SUM(used_qty), 0) FROM pp_validations
                WHERE date(validated_at) >= date(?) AND supplier_name = ?
                """,
                (start, sup),
            ).fetchone()
            total_used_qty = int(row_used[0] or 0)
            row_conf = con.execute(
                """
                SELECT AVG(confidence_score) FROM pp_recommendations
                WHERE recommendation_date >= ? AND supplier_name = ?
                """,
                (start, sup),
            ).fetchone()
            active_stock_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_stock
                WHERE COALESCE(current_qty, 0) > 0 AND supplier_name = ?
                """,
                (sup,),
            ).fetchone()[0]
        else:
            total_recommendations = con.execute(
                """
                SELECT COUNT(*) FROM pp_recommendations
                WHERE recommendation_date >= ?
                """,
                (start,),
            ).fetchone()[0]
            approved_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_recommendations
                WHERE recommendation_date >= ? AND status = 'approved'
                """,
                (start,),
            ).fetchone()[0]
            rejected_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_recommendations
                WHERE recommendation_date >= ? AND status = 'rejected'
                """,
                (start,),
            ).fetchone()[0]
            executed_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_executions
                WHERE date(executed_at) >= date(?)
                """,
                (start,),
            ).fetchone()[0]
            row_prod = con.execute(
                """
                SELECT COALESCE(SUM(executed_qty), 0) FROM pp_executions
                WHERE date(executed_at) >= date(?)
                """,
                (start,),
            ).fetchone()
            total_produced_qty = int(row_prod[0] or 0)
            row_used = con.execute(
                """
                SELECT COALESCE(SUM(used_qty), 0) FROM pp_validations
                WHERE date(validated_at) >= date(?)
                """,
                (start,),
            ).fetchone()
            total_used_qty = int(row_used[0] or 0)
            row_conf = con.execute(
                """
                SELECT AVG(confidence_score) FROM pp_recommendations
                WHERE recommendation_date >= ?
                """,
                (start,),
            ).fetchone()
            active_stock_count = con.execute(
                """
                SELECT COUNT(*) FROM pp_stock
                WHERE COALESCE(current_qty, 0) > 0
                """
            ).fetchone()[0]
    avg_confidence = float(row_conf[0] or 0) if row_conf and row_conf[0] is not None else 0.0
    utilization_rate = (
        float(total_used_qty) / float(total_produced_qty) if total_produced_qty > 0 else 0.0
    )
    return {
        "total_recommendations": int(total_recommendations or 0),
        "approved_count": int(approved_count or 0),
        "rejected_count": int(rejected_count or 0),
        "executed_count": int(executed_count or 0),
        "total_produced_qty": total_produced_qty,
        "total_used_qty": total_used_qty,
        "utilization_rate": utilization_rate,
        "active_stock_count": int(active_stock_count or 0),
        "avg_confidence": avg_confidence,
    }
