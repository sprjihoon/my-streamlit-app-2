from __future__ import annotations

import logging
import statistics

from prepacking.services.analysis import repeat_combination_service, repeat_sku_service, weekday_pattern_service
from prepacking.services.prediction import confidence_service

logger = logging.getLogger(__name__)


def _weighted_moving_average(values: list[float]) -> float:
    if not values:
        return 0.0
    n = len(values)
    weights = [float(i + 1) for i in range(n)]
    num = sum(w * v for w, v in zip(weights, values))
    den = sum(weights)
    return num / den if den else 0.0


def _variability_coefficient(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    if m <= 1e-9:
        spread = statistics.pstdev(values) if len(values) > 1 else 0.0
        return min(1.0, spread)
    return min(1.0, statistics.pstdev(values) / m)


def predict_for_date(
    supplier_name: str,
    target_date: str,
    weeks_back: int = 8,
) -> list[dict]:
    if weeks_back < 1:
        weeks_back = 1
    lookback_days = max(weeks_back * 7 + 45, 120)
    wb = weekday_pattern_service.weekday_basis_for(target_date)
    skus = repeat_sku_service.load_repeat_sku_daily_totals(
        supplier_name, target_date, lookback_days
    )
    combos = repeat_combination_service.load_repeat_combo_daily_totals(
        supplier_name, target_date, lookback_days
    )
    logger.warning(
        "predict_for_date: supplier=%s target=%s skus=%d combos=%d lookback=%d",
        supplier_name, target_date, len(skus), len(combos), lookback_days,
    )
    out: list[dict] = []
    for row in skus:
        daily = {k: int(v) for k, v in row["daily"].items()}
        weeks = weekday_pattern_service.bucket_weekly_totals(
            daily, target_date, weeks_back
        )
        pred = _weighted_moving_average(weeks)
        var = _variability_coefficient(weeks)
        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )
        out.append(
            {
                "target_type": "single_sku",
                "target_name": row["target_name"],
                "target_code": row["target_code"],
                "combination_key": "",
                "predicted_qty": int(round(max(0.0, pred))),
                "confidence_score": conf,
                "recent_7d_avg": weekday_pattern_service.window_average_daily(
                    daily, target_date, 7
                ),
                "recent_30d_avg": weekday_pattern_service.window_average_daily(
                    daily, target_date, 30
                ),
                "recent_same_weekday_avg": weekday_pattern_service.recent_same_weekday_average(
                    daily, target_date
                ),
                "weekday_basis": wb,
                "frequency": row["frequency"],
            }
        )
    for row in combos:
        daily = {k: int(v) for k, v in row["daily"].items()}
        weeks = weekday_pattern_service.bucket_weekly_totals(
            daily, target_date, weeks_back
        )
        pred = _weighted_moving_average(weeks)
        var = _variability_coefficient(weeks)
        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )
        out.append(
            {
                "target_type": "combination",
                "target_name": row["target_name"],
                "target_code": row["combination_key"],
                "combination_key": row["combination_key"],
                "predicted_qty": int(round(max(0.0, pred))),
                "confidence_score": conf,
                "recent_7d_avg": weekday_pattern_service.window_average_daily(
                    daily, target_date, 7
                ),
                "recent_30d_avg": weekday_pattern_service.window_average_daily(
                    daily, target_date, 30
                ),
                "recent_same_weekday_avg": weekday_pattern_service.recent_same_weekday_average(
                    daily, target_date
                ),
                "weekday_basis": wb,
                "frequency": row["frequency"],
            }
        )
    return out
