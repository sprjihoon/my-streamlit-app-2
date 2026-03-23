"""
forecast_service — AI 하이브리드 예측 파이프라인
───────────────────────────────────────────────
1단계: ML(GradientBoosting) 예측
2단계: GPT 보정 (ML 결과 + 통계 데이터를 GPT에게 전달하여 최종 수량 결정)
3단계: 폴백 — ML/GPT 모두 실패 시 기존 가중이동평균
"""
from __future__ import annotations

import logging
import statistics

import numpy as np

from prepacking.services.analysis import repeat_combination_service, repeat_sku_service, weekday_pattern_service
from prepacking.services.prediction import confidence_service
from prepacking.services.prediction import ml_forecast_service
from prepacking.services.prediction import gpt_adjust_service

logger = logging.getLogger(__name__)

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


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


def _same_weekday_values(daily: dict[str, int], target_date: str, weeks: int = 12) -> list[float]:
    """같은 요일 과거 N주 출하량 리스트."""
    import datetime as dt
    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return []
    vals = []
    for w in range(1, weeks + 1):
        past_d = td - dt.timedelta(weeks=w)
        vals.append(float(daily.get(past_d.isoformat(), 0)))
    return vals


def _compute_trend(daily: dict[str, int], target_date: str, days: int = 14) -> float:
    """최근 N일 추세 기울기."""
    import datetime as dt
    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return 0.0
    vals = []
    for i in range(days, 0, -1):
        d = td - dt.timedelta(days=i)
        vals.append(float(daily.get(d.isoformat(), 0)))
    if len(vals) < 3:
        return 0.0
    x = np.arange(len(vals), dtype=float)
    y = np.array(vals, dtype=float)
    if np.std(x) == 0:
        return 0.0
    return float(np.polyfit(x, y, 1)[0])


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
    out: list[dict] = []

    all_rows = []
    for row in skus:
        all_rows.append(("single_sku", row))
    for row in combos:
        all_rows.append(("combination", row))

    gpt_batch: list[dict] = []

    for target_type, row in all_rows:
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
        ml_accuracy = ml_result.get("train_accuracy", 0.0)
        ml_samples = ml_result.get("train_samples", 0)
        confidence_boost = ml_result.get("confidence_boost", 0.0)

        same_wd_vals = _same_weekday_values(daily, target_date, 4)
        trend = _compute_trend(daily, target_date, 14)
        avg_7 = weekday_pattern_service.window_average_daily(daily, target_date, 7)
        avg_14 = weekday_pattern_service.window_average_daily(daily, target_date, 14) if hasattr(weekday_pattern_service, 'window_average_daily') else avg_7
        avg_30 = weekday_pattern_service.window_average_daily(daily, target_date, 30)
        avg_same_wd = weekday_pattern_service.recent_same_weekday_average(daily, target_date)

        best_qty = ml_qty if ml_type == "ml" else stat_qty
        final_conf = min(1.0, base_conf + confidence_boost)
        model_used = f"ml+gpt" if ml_type == "ml" else "stat+gpt"

        entry = {
            "target_type": target_type,
            "target_name": row.get("target_name", ""),
            "target_code": row.get("target_code", row.get("combination_key", "")),
            "sku_code": row.get("sku_code", ""),
            "barcode": row.get("barcode", ""),
            "option_name": row.get("option_name", ""),
            "combination_key": row.get("combination_key", ""),
            "items": row.get("items", []),
            "predicted_qty": best_qty,
            "stat_qty": stat_qty,
            "ml_qty": ml_qty,
            "ml_model_type": ml_type,
            "ml_accuracy": round(ml_accuracy, 3),
            "ml_samples": ml_samples,
            "confidence_score": round(final_conf, 3),
            "recent_7d_avg": round(avg_7, 1),
            "recent_30d_avg": round(avg_30, 1),
            "recent_same_weekday_avg": round(avg_same_wd, 1),
            "weekday_basis": wb,
            "frequency": row["frequency"],
            "model_used": model_used,
            "gpt_reason": "",
            "gpt_confidence": "",
        }

        gpt_batch.append({
            "entry": entry,
            "supplier_name": supplier_name,
            "target_date": target_date,
            "weekday_idx": wb,
            "avg_14d": round(avg_14, 1),
            "same_wd_vals": same_wd_vals,
            "cv": round(var, 3),
            "trend": round(trend, 3),
        })

    for item in gpt_batch:
        entry = item["entry"]
        best_qty = entry["predicted_qty"]

        if best_qty <= 0:
            entry["model_used"] = entry.get("ml_model_type", "statistical")
            out.append(entry)
            continue

        try:
            gpt_result = gpt_adjust_service.adjust_with_gpt(
                supplier_name=item["supplier_name"],
                target_name=entry["target_name"],
                target_type=entry["target_type"],
                target_date=item["target_date"],
                weekday_idx=item["weekday_idx"],
                ml_qty=entry["ml_qty"],
                ml_accuracy=entry["ml_accuracy"],
                ml_samples=entry.get("ml_samples", 0),
                stat_qty=entry["stat_qty"],
                avg_7d=entry["recent_7d_avg"],
                avg_14d=item["avg_14d"],
                avg_30d=entry["recent_30d_avg"],
                avg_same_wd=entry["recent_same_weekday_avg"],
                same_wd_history=item["same_wd_vals"],
                cv=item["cv"],
                trend=item["trend"],
                frequency=entry["frequency"],
            )

            if gpt_result.get("used_gpt"):
                entry["predicted_qty"] = gpt_result["adjusted_qty"]
                entry["gpt_reason"] = gpt_result.get("reason", "")
                entry["gpt_confidence"] = gpt_result.get("confidence", "")
                entry["model_used"] = f"{entry['ml_model_type']}+gpt"
                gpt_conf_map = {"high": 0.15, "medium": 0.05, "low": -0.05}
                gpt_boost = gpt_conf_map.get(gpt_result.get("confidence", ""), 0.0)
                entry["confidence_score"] = round(
                    min(1.0, max(0.0, entry["confidence_score"] + gpt_boost)), 3
                )
            else:
                entry["gpt_reason"] = gpt_result.get("reason", "")
                entry["model_used"] = entry.get("ml_model_type", "statistical")

        except Exception as exc:
            logger.warning("GPT adjust skipped for %s: %s", entry["target_name"], exc)
            entry["model_used"] = entry.get("ml_model_type", "statistical")

        out.append(entry)

    return out
