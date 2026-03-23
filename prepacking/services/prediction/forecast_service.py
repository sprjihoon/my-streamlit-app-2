"""
forecast_service — 다중 시그널 앙상블 예측
──────────────────────────────────────────
시그널 1: 최근 7일 일평균 (가장 최근 트렌드)
시그널 2: 최근 14일 일평균
시그널 3: 최근 30일 일평균
시그널 4: 같은 요일 최근 8주 가중평균
시그널 5: ML(GradientBoosting) 예측

가중 앙상블로 최종 예측. 데이터가 많을수록 ML 비중 증가.
"""
from __future__ import annotations

import datetime as dt
import logging
import math

from prepacking.services.analysis import repeat_combination_service, repeat_sku_service, weekday_pattern_service
from prepacking.services.prediction import confidence_service
from prepacking.services.prediction import ml_forecast_service

logger = logging.getLogger(__name__)


def _ensemble_predict(
    daily: dict[str, int],
    target_date: str,
    frequency: int,
    weeks_back: int = 8,
) -> dict:
    """다중 시그널 앙상블 예측."""
    td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()

    avg_7 = _window_avg(daily, td, 7)
    avg_14 = _window_avg(daily, td, 14)
    avg_30 = _window_avg(daily, td, 30)

    same_wd = _same_weekday_weighted(daily, td, weeks_back)

    active_7 = _active_days(daily, td, 7)
    active_30 = _active_days(daily, td, 30)

    signals: list[tuple[float, float]] = []

    if active_7 >= 1:
        signals.append((avg_7, 3.0))
    if active_30 >= 2:
        signals.append((avg_14, 2.0))
    if active_30 >= 3:
        signals.append((avg_30, 1.5))
    if same_wd > 0:
        signals.append((same_wd, 2.5))

    ml_result = ml_forecast_service.predict_ml(daily, target_date, frequency)
    ml_qty = ml_result.get("predicted_qty", 0)
    ml_type = ml_result.get("model_type", "statistical")
    ml_accuracy = ml_result.get("train_accuracy", 0.0)
    ml_samples = ml_result.get("train_samples", 0)
    confidence_boost = ml_result.get("confidence_boost", 0.0)

    if ml_type == "ml" and ml_qty > 0:
        ml_weight = 2.0 + min(2.0, ml_accuracy * 3.0)
        signals.append((float(ml_qty), ml_weight))

    if not signals:
        total_qty = sum(daily.values())
        total_days = len([v for v in daily.values() if v > 0])
        if total_days > 0:
            fallback = total_qty / total_days
            return {
                "predicted_qty": max(1, int(round(fallback))),
                "stat_qty": max(1, int(round(fallback))),
                "ml_qty": ml_qty,
                "ml_model_type": ml_type,
                "ml_accuracy": ml_accuracy,
                "ml_samples": ml_samples,
                "confidence_boost": confidence_boost,
                "avg_7": avg_7, "avg_14": avg_14, "avg_30": avg_30,
                "avg_same_wd": same_wd,
            }
        return {
            "predicted_qty": 0, "stat_qty": 0, "ml_qty": 0,
            "ml_model_type": "none", "ml_accuracy": 0, "ml_samples": 0,
            "confidence_boost": 0, "avg_7": 0, "avg_14": 0, "avg_30": 0,
            "avg_same_wd": 0,
        }

    total_w = sum(w for _, w in signals)
    ensemble = sum(v * w for v, w in signals) / total_w
    stat_qty = max(0, int(round(ensemble)))

    return {
        "predicted_qty": stat_qty,
        "stat_qty": stat_qty,
        "ml_qty": ml_qty,
        "ml_model_type": ml_type,
        "ml_accuracy": ml_accuracy,
        "ml_samples": ml_samples,
        "confidence_boost": confidence_boost,
        "avg_7": avg_7, "avg_14": avg_14, "avg_30": avg_30,
        "avg_same_wd": same_wd,
    }


def _window_avg(daily: dict[str, int], td: dt.date, days: int) -> float:
    total = 0
    for i in range(1, days + 1):
        d = td - dt.timedelta(days=i)
        total += daily.get(d.isoformat(), 0)
    return total / days


def _active_days(daily: dict[str, int], td: dt.date, days: int) -> int:
    count = 0
    for i in range(1, days + 1):
        d = td - dt.timedelta(days=i)
        if daily.get(d.isoformat(), 0) > 0:
            count += 1
    return count


def _same_weekday_weighted(daily: dict[str, int], td: dt.date, weeks: int) -> float:
    vals = []
    for w in range(1, weeks + 1):
        past_d = td - dt.timedelta(weeks=w)
        vals.append(float(daily.get(past_d.isoformat(), 0)))
    nonzero = [v for v in vals if v > 0]
    if not nonzero:
        return 0.0
    n = len(vals)
    weights = [float(i + 1) for i in range(n)]
    num = sum(w * v for w, v in zip(weights, vals))
    den = sum(weights)
    return num / den if den else 0.0


def _variability_coefficient(daily: dict[str, int], td: dt.date, days: int = 30) -> float:
    import statistics
    vals = []
    for i in range(1, days + 1):
        d = td - dt.timedelta(days=i)
        vals.append(float(daily.get(d.isoformat(), 0)))
    if len(vals) < 2:
        return 0.0
    m = statistics.mean(vals)
    if m <= 1e-9:
        return min(1.0, statistics.pstdev(vals))
    return min(1.0, statistics.pstdev(vals) / m)


MAX_GPT_ITEMS = 10


def predict_for_date(
    supplier_name: str,
    target_date: str,
    weeks_back: int = 8,
    use_gpt: bool = False,
) -> list[dict]:
    if weeks_back < 1:
        weeks_back = 1
    lookback_days = max(weeks_back * 7 + 45, 120)
    wb = weekday_pattern_service.weekday_basis_for(target_date)

    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        td = dt.date.today()

    skus = repeat_sku_service.load_repeat_sku_daily_totals(
        supplier_name, target_date, lookback_days
    )
    combos = repeat_combination_service.load_repeat_combo_daily_totals(
        supplier_name, target_date, lookback_days
    )
    out: list[dict] = []

    all_rows = []
    for row in skus:
        all_rows.append(("single_sku", row))
    for row in combos:
        all_rows.append(("combination", row))

    for target_type, row in all_rows:
        daily = {k: int(v) for k, v in row["daily"].items()}

        result = _ensemble_predict(daily, target_date, row["frequency"], weeks_back)

        var = _variability_coefficient(daily, td, 30)
        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        base_conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )
        final_conf = min(1.0, base_conf + result.get("confidence_boost", 0.0))

        ml_type = result.get("ml_model_type", "statistical")
        model_label = "ml" if ml_type == "ml" else "ensemble"

        entry = {
            "target_type": target_type,
            "target_name": row.get("target_name", ""),
            "target_code": row.get("target_code", row.get("combination_key", "")),
            "sku_code": row.get("sku_code", ""),
            "barcode": row.get("barcode", ""),
            "option_name": row.get("option_name", ""),
            "combination_key": row.get("combination_key", ""),
            "items": row.get("items", []),
            "predicted_qty": result["predicted_qty"],
            "stat_qty": result["stat_qty"],
            "ml_qty": result.get("ml_qty", 0),
            "ml_model_type": ml_type,
            "ml_accuracy": round(result.get("ml_accuracy", 0), 3),
            "ml_samples": result.get("ml_samples", 0),
            "confidence_score": round(final_conf, 3),
            "recent_7d_avg": round(result.get("avg_7", 0), 1),
            "recent_30d_avg": round(result.get("avg_30", 0), 1),
            "recent_same_weekday_avg": round(result.get("avg_same_wd", 0), 1),
            "weekday_basis": wb,
            "frequency": row["frequency"],
            "model_used": model_label,
            "gpt_reason": "",
            "gpt_confidence": "",
        }

        out.append(entry)

    return out
