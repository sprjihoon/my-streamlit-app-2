from __future__ import annotations

import sqlite3

from prepacking.common.enums import ValidationResult
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.validation.accuracy_service import calculate_accuracy


def _actual_shipped_qty(con: sqlite3.Connection, supplier_name: str, target_date: str, rec: dict) -> int:
    tc = (rec.get("target_code") or "").strip()
    ck = (rec.get("combination_key") or "").strip()
    tn = (rec.get("target_name") or "").strip()
    op = (rec.get("option_name") or "").strip()
    parts: list[str] = []
    params: list = [target_date, supplier_name]
    if tc:
        parts.append("sku_code = ?")
        params.append(tc)
    if ck:
        parts.append("combo_no = ?")
        params.append(ck)
    parts.append(
        "(product_name = ? AND (ifnull(option_name,'') = ? OR (? = '' AND ifnull(option_name,'') = '')))"
    )
    params.extend([tn, op, op])
    if not parts:
        return 0
    sql = f"""
        SELECT COALESCE(SUM(qty), 0) AS q FROM pp_shipping_stats
        WHERE shipping_date = ? AND supplier_name = ?
          AND ({' OR '.join(parts)})
    """
    cur = con.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] if row else 0)


def _scalar_int(con: sqlite3.Connection, sql: str, params: tuple) -> int:
    cur = con.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] if row and row[0] is not None else 0)


def validate_predictions(supplier_name: str, target_date: str) -> list[dict]:
    ensure_pp_tables()
    out: list[dict] = []
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            """
            SELECT * FROM pp_recommendations
            WHERE supplier_name = ? AND target_date = ?
            ORDER BY recommendation_id
            """,
            (supplier_name, target_date),
        )
        recs = [dict(r) for r in cur.fetchall()]
        for rec in recs:
            rid = int(rec.get("recommendation_id") or 0)
            predicted = int(rec.get("predicted_qty") or 0)
            actual = _actual_shipped_qty(con, supplier_name, target_date, rec)
            executed = _scalar_int(
                con,
                "SELECT COALESCE(SUM(executed_qty), 0) FROM pp_executions WHERE recommendation_id = ?",
                (rid,),
            )
            used = _scalar_int(
                con,
                """
                SELECT COALESCE(SUM(qty), 0) FROM pp_location_history
                WHERE related_recommendation_id = ? AND lower(action_type) = 'use'
                """,
                (rid,),
            )
            unwrap_q = _scalar_int(
                con,
                """
                SELECT COALESCE(SUM(u.unwrap_qty), 0)
                FROM pp_unwrap_history u
                JOIN pp_stock s ON s.prepack_stock_id = u.prepack_stock_id
                JOIN pp_executions e ON e.execution_id = s.source_execution_id
                WHERE e.recommendation_id = ?
                """,
                (rid,),
            )
            calc = calculate_accuracy(predicted, actual)
            unused = max(executed - used, 0)
            usage_rate = used / max(executed, 1) if executed else 0.0
            unwrap_rate = unwrap_q / max(executed, 1) if executed else 0.0
            fr = ""
            vr = calc["validation_result"]
            if vr == ValidationResult.OVER.value:
                fr = "over_predict"
            elif vr == ValidationResult.UNDER.value:
                fr = "under_predict"
            elif vr == ValidationResult.MISSED.value:
                fr = "missed_demand"
            elif vr == ValidationResult.MATCHED.value:
                fr = ""
            con.execute(
                """
                INSERT INTO pp_validations (
                    recommendation_id, supplier_name, target_type, target_code, target_name,
                    target_date, predicted_qty, actual_qty, executed_qty, used_qty, unused_qty,
                    unwrap_qty, over_predict_qty, under_predict_qty, accuracy_rate, usage_rate,
                    unwrap_rate, validation_result, failure_reason, validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    rid,
                    supplier_name,
                    rec.get("target_type") or "",
                    rec.get("target_code") or "",
                    rec.get("target_name") or "",
                    target_date,
                    predicted,
                    actual,
                    executed,
                    used,
                    unused,
                    unwrap_q,
                    calc["over_predict_qty"],
                    calc["under_predict_qty"],
                    calc["accuracy_rate"],
                    usage_rate,
                    unwrap_rate,
                    vr,
                    fr,
                ),
            )
            con.commit()
            vid = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
            cur2 = con.execute("SELECT * FROM pp_validations WHERE validation_id = ?", (vid,))
            row = cur2.fetchone()
            if row:
                out.append(dict(row))
    return out


def get_validation_results(
    supplier_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    ensure_pp_tables()
    sql = "SELECT * FROM pp_validations WHERE 1=1"
    params: list = []
    if supplier_name:
        sql += " AND supplier_name = ?"
        params.append(supplier_name)
    if date_from:
        sql += " AND date(validated_at) >= date(?)"
        params.append(date_from)
    if date_to:
        sql += " AND date(validated_at) <= date(?)"
        params.append(date_to)
    sql += " ORDER BY validated_at DESC"
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
