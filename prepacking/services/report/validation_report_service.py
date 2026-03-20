from __future__ import annotations

import datetime as dt

from prepacking.common.date_helper import today_kst
from prepacking.database import get_pp_connection

_TOP_N = 10


def _start_date(days: int) -> str:
    d = today_kst() - dt.timedelta(days=max(0, int(days)))
    return d.strftime("%Y-%m-%d")


def get_validation_report(supplier_name: str = None, days: int = 30) -> dict:
    start = _start_date(days)
    sup = (supplier_name or "").strip() or None
    base_where = "date(validated_at) >= date(?)"
    params_base: list = [start]
    if sup:
        base_where += " AND supplier_name = ?"
        params_base.append(sup)
    with get_pp_connection() as con:
        total_validated = con.execute(
            f"SELECT COUNT(*) FROM pp_validations WHERE {base_where}",
            params_base,
        ).fetchone()[0]
        row_acc = con.execute(
            f"SELECT AVG(accuracy_rate) FROM pp_validations WHERE {base_where}",
            params_base,
        ).fetchone()
        avg_accuracy = float(row_acc[0] or 0) if row_acc and row_acc[0] is not None else 0.0
        row_mape = con.execute(
            f"""
            SELECT AVG(
                ABS(predicted_qty - actual_qty) * 1.0
                / CASE WHEN IFNULL(actual_qty, 0) < 1 THEN 1.0 ELSE actual_qty END
            )
            FROM pp_validations
            WHERE {base_where}
            """,
            params_base,
        ).fetchone()
        avg_mape = float(row_mape[0] or 0) if row_mape and row_mape[0] is not None else 0.0
        row_unwrap = con.execute(
            f"SELECT AVG(unwrap_rate) FROM pp_validations WHERE {base_where}",
            params_base,
        ).fetchone()
        unwrap_rate = float(row_unwrap[0] or 0) if row_unwrap and row_unwrap[0] is not None else 0.0
        cur = con.execute(
            f"""
            SELECT validation_result, COUNT(*) AS c
            FROM pp_validations
            WHERE {base_where}
            GROUP BY validation_result
            """,
            params_base,
        )
        by_result = {"matched": 0, "over": 0, "under": 0, "missed": 0}
        for r, c in cur.fetchall():
            key = (r or "").strip().lower()
            if key in by_result:
                by_result[key] = int(c or 0)
        sku_group = "supplier_name || '|' || COALESCE(target_code,'') || '|' || target_name"
        top_acc_sql = f"""
            SELECT {sku_group} AS sku_key,
                   AVG(accuracy_rate) AS acc,
                   COUNT(*) AS n
            FROM pp_validations
            WHERE {base_where}
            GROUP BY supplier_name, target_code, target_name
            HAVING COUNT(*) >= 1 AND AVG(accuracy_rate) IS NOT NULL
            ORDER BY acc DESC
            LIMIT ?
        """
        top_accurate_rows = con.execute(top_acc_sql, params_base + [_TOP_N]).fetchall()
        top_inacc_sql = f"""
            SELECT {sku_group} AS sku_key,
                   AVG(accuracy_rate) AS acc,
                   COUNT(*) AS n
            FROM pp_validations
            WHERE {base_where}
            GROUP BY supplier_name, target_code, target_name
            HAVING COUNT(*) >= 1 AND AVG(accuracy_rate) IS NOT NULL
            ORDER BY acc ASC
            LIMIT ?
        """
        top_inaccurate_rows = con.execute(top_inacc_sql, params_base + [_TOP_N]).fetchall()
        trend_rows = con.execute(
            f"""
            SELECT date(validated_at) AS d, AVG(accuracy_rate) AS accuracy
            FROM pp_validations
            WHERE {base_where}
            GROUP BY date(validated_at)
            ORDER BY d
            """,
            params_base,
        ).fetchall()
    top_accurate_skus = [
        {"sku_key": str(a[0]), "accuracy": float(a[1] or 0), "samples": int(a[2] or 0)}
        for a in top_accurate_rows
    ]
    top_inaccurate_skus = [
        {"sku_key": str(a[0]), "accuracy": float(a[1] or 0), "samples": int(a[2] or 0)}
        for a in top_inaccurate_rows
    ]
    daily_accuracy_trend = [
        {"date": str(t[0]), "accuracy": float(t[1] or 0) if t[1] is not None else 0.0}
        for t in trend_rows
    ]
    return {
        "total_validated": int(total_validated or 0),
        "avg_accuracy": avg_accuracy,
        "avg_mape": avg_mape,
        "by_result": by_result,
        "unwrap_rate": unwrap_rate,
        "top_accurate_skus": top_accurate_skus,
        "top_inaccurate_skus": top_inaccurate_skus,
        "daily_accuracy_trend": daily_accuracy_trend,
    }
