"""
backtest_service — 예측 정확도 백테스트
──────────────────────────────────────
과거 특정일을 대상으로 예측을 실행하고,
해당일의 실제 출하 데이터와 비교하여 정확도를 산출한다.
GPT 호출은 비용이 발생하므로 백테스트에서는 ML+통계만 사용한다.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict

from prepacking.database import get_pp_connection
from prepacking.services.analysis import (
    repeat_combination_service,
    repeat_sku_service,
    weekday_pattern_service,
)
from prepacking.services.prediction import confidence_service, ml_forecast_service

logger = logging.getLogger(__name__)


def _safe_str(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("none", "nan", "null") else s


def _load_actual_shipments(supplier_name: str, target_date: str) -> dict[str, int]:
    """
    특정일의 실제 출하 데이터를 DB에서 조회.
    key = "상품명||옵션명" (단일 SKU) 또는 combo_key, value = 총 수량
    """
    with get_pp_connection() as con:
        rows = con.execute(
            """
            SELECT product_name, option_name, sku_code, combo_no, qty, inner_qty
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date = ?
            """,
            (supplier_name.strip(), target_date),
        ).fetchall()

    sku_totals: dict[str, int] = defaultdict(int)
    combo_groups: dict[str, set] = defaultdict(set)
    combo_qtys: dict[str, int] = defaultdict(int)

    for row in rows:
        pn = _safe_str(row[0])
        on = _safe_str(row[1])
        sku = _safe_str(row[2])
        combo = _safe_str(row[3])
        qty = int(row[4] or 1)
        inner_qty = int(row[5] or 1)

        key = f"{pn}||{on}"
        sku_totals[key] += qty

        if combo:
            combo_groups[combo].add(key)
            combo_qtys[combo] += qty

    return sku_totals


def _weighted_moving_average(values: list[float]) -> float:
    if not values:
        return 0.0
    n = len(values)
    weights = [float(i + 1) for i in range(n)]
    num = sum(w * v for w, v in zip(weights, values))
    den = sum(weights)
    return num / den if den else 0.0


def _variability_coefficient(values: list[float]) -> float:
    import statistics as st
    if len(values) < 2:
        return 0.0
    m = st.mean(values)
    if m <= 1e-9:
        return min(1.0, st.pstdev(values) if len(values) > 1 else 0.0)
    return min(1.0, st.pstdev(values) / m)


def run_backtest(
    supplier_name: str,
    target_date: str,
    weeks_back: int = 8,
) -> dict:
    """
    과거 특정일에 대해 예측을 실행하고 실제 데이터와 비교.
    GPT는 호출하지 않고 ML+통계만 사용 (비용 절감).
    """
    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return {"error": "invalid_date", "target_date": target_date}

    if td >= dt.date.today():
        return {"error": "future_date", "message": "백테스트는 과거 날짜만 가능합니다."}

    actual = _load_actual_shipments(supplier_name, target_date)
    if not actual:
        return {
            "error": "no_actual_data",
            "message": f"{target_date}에 {supplier_name}의 출하 데이터가 없습니다.",
            "target_date": target_date,
        }

    lookback_days = max(weeks_back * 7 + 45, 120)
    wb = weekday_pattern_service.weekday_basis_for(target_date)

    skus = repeat_sku_service.load_repeat_sku_daily_totals(
        supplier_name, target_date, lookback_days
    )
    combos = repeat_combination_service.load_repeat_combo_daily_totals(
        supplier_name, target_date, lookback_days
    )

    predictions: list[dict] = []

    for row in skus:
        daily = {k: int(v) for k, v in row["daily"].items()}
        stat_weeks = weekday_pattern_service.bucket_weekly_totals(
            daily, target_date, weeks_back
        )
        stat_pred = _weighted_moving_average(stat_weeks)
        stat_qty = max(0, int(round(stat_pred)))

        var = _variability_coefficient(stat_weeks)
        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        base_conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )

        ml_result = ml_forecast_service.predict_ml(
            daily, target_date, row["frequency"],
        )
        ml_qty = ml_result.get("predicted_qty", 0)
        ml_type = ml_result.get("model_type", "statistical")
        confidence_boost = ml_result.get("confidence_boost", 0.0)

        best_qty = ml_qty if ml_type == "ml" else stat_qty
        final_conf = min(1.0, base_conf + confidence_boost)

        target_name = row.get("target_name", "")
        option_name = row.get("option_name", "")
        actual_key = f"{target_name}||{option_name}"
        actual_qty = actual.pop(actual_key, 0)

        error_abs = abs(best_qty - actual_qty)
        error_pct = (error_abs / actual_qty * 100) if actual_qty > 0 else (100.0 if best_qty > 0 else 0.0)

        if best_qty == actual_qty:
            result_type = "matched"
        elif best_qty > actual_qty:
            result_type = "over"
        else:
            result_type = "under"

        predictions.append({
            "target_type": "single_sku",
            "target_name": target_name,
            "option_name": option_name,
            "sku_code": row.get("sku_code", ""),
            "barcode": row.get("barcode", ""),
            "predicted_qty": best_qty,
            "stat_qty": stat_qty,
            "ml_qty": ml_qty,
            "model_type": ml_type,
            "actual_qty": actual_qty,
            "error_abs": error_abs,
            "error_pct": round(error_pct, 1),
            "result_type": result_type,
            "confidence_score": round(final_conf, 3),
            "frequency": row["frequency"],
        })

    for row in combos:
        daily = {k: int(v) for k, v in row["daily"].items()}
        stat_weeks = weekday_pattern_service.bucket_weekly_totals(
            daily, target_date, weeks_back
        )
        stat_pred = _weighted_moving_average(stat_weeks)
        stat_qty = max(0, int(round(stat_pred)))

        var = _variability_coefficient(stat_weeks)
        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        base_conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )

        ml_result = ml_forecast_service.predict_ml(
            daily, target_date, row["frequency"],
        )
        ml_qty = ml_result.get("predicted_qty", 0)
        ml_type = ml_result.get("model_type", "statistical")
        confidence_boost = ml_result.get("confidence_boost", 0.0)

        best_qty = ml_qty if ml_type == "ml" else stat_qty
        final_conf = min(1.0, base_conf + confidence_boost)

        target_name = row.get("target_name", "")
        actual_qty = 0
        combo_items = row.get("items", [])
        for ci in combo_items:
            ci_key = f"{ci.get('product_name', '')}||{ci.get('option_name', '')}"
            actual_qty += actual.pop(ci_key, 0)

        error_abs = abs(best_qty - actual_qty)
        error_pct = (error_abs / actual_qty * 100) if actual_qty > 0 else (100.0 if best_qty > 0 else 0.0)

        if best_qty == actual_qty:
            result_type = "matched"
        elif best_qty > actual_qty:
            result_type = "over"
        else:
            result_type = "under"

        predictions.append({
            "target_type": "combination",
            "target_name": target_name,
            "option_name": "",
            "sku_code": "",
            "barcode": "",
            "items": combo_items,
            "predicted_qty": best_qty,
            "stat_qty": stat_qty,
            "ml_qty": ml_qty,
            "model_type": ml_type,
            "actual_qty": actual_qty,
            "error_abs": error_abs,
            "error_pct": round(error_pct, 1),
            "result_type": result_type,
            "confidence_score": round(final_conf, 3),
            "frequency": row["frequency"],
        })

    missed_items: list[dict] = []
    for key, qty in actual.items():
        if qty <= 0:
            continue
        parts = key.split("||", 1)
        missed_items.append({
            "target_type": "missed",
            "target_name": parts[0] if parts else key,
            "option_name": parts[1] if len(parts) > 1 else "",
            "predicted_qty": 0,
            "actual_qty": qty,
            "error_abs": qty,
            "error_pct": 100.0,
            "result_type": "missed",
        })

    total_predicted = sum(p["predicted_qty"] for p in predictions)
    total_actual = sum(p["actual_qty"] for p in predictions) + sum(m["actual_qty"] for m in missed_items)
    total_error = sum(p["error_abs"] for p in predictions) + sum(m["error_abs"] for m in missed_items)

    items_with_actual = [p for p in predictions if p["actual_qty"] > 0]
    if items_with_actual:
        mape_values = [p["error_pct"] for p in items_with_actual]
        avg_mape = sum(mape_values) / len(mape_values)
        accuracy = max(0.0, 100.0 - avg_mape)
    else:
        avg_mape = 0.0
        accuracy = 0.0

    matched = sum(1 for p in predictions if p["result_type"] == "matched")
    over = sum(1 for p in predictions if p["result_type"] == "over")
    under = sum(1 for p in predictions if p["result_type"] == "under")

    ml_count = sum(1 for p in predictions if p.get("model_type") == "ml")
    stat_count = len(predictions) - ml_count

    predictions.sort(key=lambda x: (-x["error_abs"], -x["actual_qty"]))

    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]

    return {
        "target_date": target_date,
        "weekday_name": weekday_kr[td.weekday()],
        "supplier_name": supplier_name,
        "summary": {
            "accuracy": round(accuracy, 1),
            "avg_mape": round(avg_mape, 1),
            "total_predicted": total_predicted,
            "total_actual": total_actual,
            "total_error": total_error,
            "item_count": len(predictions),
            "matched": matched,
            "over": over,
            "under": under,
            "missed": len(missed_items),
            "ml_count": ml_count,
            "stat_count": stat_count,
        },
        "items": predictions,
        "missed_items": missed_items,
    }
