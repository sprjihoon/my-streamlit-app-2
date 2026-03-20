from __future__ import annotations

import datetime as dt
import sqlite3

from prepacking.common.enums import ValidationResult
from prepacking.common.date_helper import now_kst
from prepacking.database import ensure_pp_tables, get_pp_connection


def calculate_accuracy(predicted: int, actual: int) -> dict:
    over_predict_qty = max(predicted - actual, 0)
    under_predict_qty = max(actual - predicted, 0)
    denom = max(abs(predicted), abs(actual), 1)
    accuracy_rate = max(0.0, 1.0 - abs(predicted - actual) / denom)
    if predicted == 0 and actual > 0:
        vr = ValidationResult.MISSED.value
    elif predicted == actual:
        vr = ValidationResult.MATCHED.value
    elif predicted > actual:
        vr = ValidationResult.OVER.value
    else:
        vr = ValidationResult.UNDER.value
    return {
        "accuracy_rate": accuracy_rate,
        "over_predict_qty": over_predict_qty,
        "under_predict_qty": under_predict_qty,
        "validation_result": vr,
    }


def get_accuracy_summary(supplier_name: str, days: int = 30) -> dict:
    ensure_pp_tables()
    start = (now_kst().date() - dt.timedelta(days=max(1, days))).strftime("%Y-%m-%d")
    sql = """
        SELECT accuracy_rate, validation_result, predicted_qty, actual_qty
        FROM pp_validations
        WHERE date(validated_at) >= date(?)
    """
    params: list = [start]
    if supplier_name:
        sql += " AND supplier_name = ?"
        params.append(supplier_name)
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    n = len(rows)
    if n == 0:
        return {
            "avg_accuracy": 0.0,
            "avg_mape": 0.0,
            "total_validated": 0,
            "matched_count": 0,
            "over_count": 0,
            "under_count": 0,
            "missed_count": 0,
        }
    accs = [float(r.get("accuracy_rate") or 0) for r in rows]
    mape_terms: list[float] = []
    for r in rows:
        p = int(r.get("predicted_qty") or 0)
        a = int(r.get("actual_qty") or 0)
        base = max(abs(a), 1)
        mape_terms.append(abs(p - a) / base)
    matched = sum(1 for r in rows if r.get("validation_result") == ValidationResult.MATCHED.value)
    over_c = sum(1 for r in rows if r.get("validation_result") == ValidationResult.OVER.value)
    under_c = sum(1 for r in rows if r.get("validation_result") == ValidationResult.UNDER.value)
    missed_c = sum(1 for r in rows if r.get("validation_result") == ValidationResult.MISSED.value)
    return {
        "avg_accuracy": sum(accs) / n,
        "avg_mape": sum(mape_terms) / len(mape_terms),
        "total_validated": n,
        "matched_count": matched,
        "over_count": over_c,
        "under_count": under_c,
        "missed_count": missed_c,
    }
