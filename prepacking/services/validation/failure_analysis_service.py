from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter

from prepacking.common.date_helper import now_kst
from prepacking.common.enums import ValidationResult
from prepacking.database import ensure_pp_tables, get_pp_connection


def analyze_failures(supplier_name: str, days: int = 30) -> dict:
    ensure_pp_tables()
    start = (now_kst().date() - dt.timedelta(days=max(1, days))).strftime("%Y-%m-%d")
    sql = """
        SELECT validation_result, failure_reason, target_name, target_code, predicted_qty, actual_qty
        FROM pp_validations
        WHERE date(validated_at) >= date(?)
          AND supplier_name = ?
          AND validation_result != ?
    """
    params = (start, supplier_name, ValidationResult.MATCHED.value)
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    total = len(rows)
    reasons = Counter()
    for r in rows:
        key = (r.get("failure_reason") or "").strip() or (r.get("validation_result") or "unknown")
        reasons[key] += 1
    sku_scores: dict[str, float] = {}
    for r in rows:
        label = (r.get("target_code") or "").strip() or (r.get("target_name") or "").strip() or "unknown"
        err = abs(int(r.get("predicted_qty") or 0) - int(r.get("actual_qty") or 0))
        sku_scores[label] = sku_scores.get(label, 0.0) + float(err)
    top_failed = sorted(sku_scores.keys(), key=lambda k: sku_scores[k], reverse=True)[:15]
    top_failed_skus = [{"sku_or_name": k, "error_weight": sku_scores[k]} for k in top_failed]
    suggestions: list[str] = []
    if reasons.get("over_predict", 0) > reasons.get("under_predict", 0):
        suggestions.append("Reduce safety stock or lower confidence-driven boosts for this supplier.")
    if reasons.get("under_predict", 0) > reasons.get("over_predict", 0):
        suggestions.append("Increase baseline forecasts or widen combination coverage for volatile SKUs.")
    if reasons.get("missed_demand", 0) > 0:
        suggestions.append("Review zero-prediction cases: add new SKUs or relax exclusion rules.")
    if total == 0:
        suggestions.append("No failed validations in range; widen the window or run validate_predictions first.")
    return {
        "total_failures": total,
        "by_reason": dict(reasons),
        "top_failed_skus": top_failed_skus,
        "improvement_suggestions": suggestions,
    }
