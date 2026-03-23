"""
forecast_service — 통계 + ML 앙상블 예측
────────────────────────────────────────
핵심 변경: 출하 확률(shipping probability)을 반영하여
실제 출하가 없을 가능성이 높은 SKU는 예측 0으로 처리.

1단계: 출하 확률 계산 (같은 요일 기준)
2단계: 확률이 임계값 이상일 때만 수량 예측
3단계: ML 모델과 앙상블
"""
from __future__ import annotations

import datetime as dt
import logging
import statistics as _stats

from prepacking.common.utils import normalize_sku_name
from prepacking.services.analysis import repeat_combination_service, repeat_sku_service, weekday_pattern_service
from prepacking.services.prediction import confidence_service
from prepacking.services.prediction import ml_forecast_service

logger = logging.getLogger(__name__)

SHIP_PROB_THRESHOLD = 0.15


def _active_avg(daily: dict[str, int], td: dt.date, days: int) -> tuple[float, int]:
    """최근 N일 중 출하일만의 평균과 출하일수를 반환."""
    vals = []
    for i in range(1, days + 1):
        d = td - dt.timedelta(days=i)
        v = daily.get(d.isoformat(), 0)
        if v > 0:
            vals.append(float(v))
    avg = sum(vals) / len(vals) if vals else 0.0
    return avg, len(vals)


def _same_weekday_stats(daily: dict[str, int], td: dt.date, weeks: int) -> tuple[float, float, int]:
    """같은 요일 최근 N주의 (출하일 평균, 출하 확률, 총 주수)."""
    total_weeks = 0
    ship_weeks = 0
    ship_vals = []
    for w in range(1, weeks + 1):
        past_d = td - dt.timedelta(weeks=w)
        v = daily.get(past_d.isoformat(), 0)
        total_weeks += 1
        if v > 0:
            ship_weeks += 1
            ship_vals.append(float(v))
    avg = sum(ship_vals) / len(ship_vals) if ship_vals else 0.0
    prob = ship_weeks / total_weeks if total_weeks > 0 else 0.0
    return avg, prob, total_weeks


def _overall_ship_probability(daily: dict[str, int], td: dt.date, days: int) -> float:
    """최근 N일 중 출하일 비율."""
    total = 0
    active = 0
    for i in range(1, days + 1):
        d = td - dt.timedelta(days=i)
        ds = d.isoformat()
        if ds in daily:
            total += 1
            if daily[ds] > 0:
                active += 1
        else:
            total += 1
    return active / total if total > 0 else 0.0


def _stat_predict(daily: dict[str, int], td: dt.date, weeks_back: int = 8) -> tuple[int, float]:
    """
    경량 통계 예측 — 출하 확률을 반영.
    반환: (예측 수량, 출하 확률)
    """
    wd_avg, wd_prob, wd_weeks = _same_weekday_stats(daily, td, weeks_back)
    avg_14, active_14 = _active_avg(daily, td, 14)
    avg_30, active_30 = _active_avg(daily, td, 30)

    overall_prob = _overall_ship_probability(daily, td, 30)
    ship_prob = max(wd_prob, overall_prob * 0.5) if wd_weeks >= 2 else overall_prob

    if ship_prob < SHIP_PROB_THRESHOLD:
        return 0, ship_prob

    signals: list[tuple[float, float]] = []
    if active_14 >= 1:
        signals.append((avg_14, 4.0))
    if active_30 >= 2:
        signals.append((avg_30, 2.0))
    if wd_avg > 0:
        signals.append((wd_avg, 3.0))

    if not signals:
        total_qty = sum(daily.values())
        active_total = len([v for v in daily.values() if v > 0])
        if active_total > 0:
            raw = total_qty / active_total
            return max(1, int(round(raw * ship_prob))), ship_prob
        return 0, ship_prob

    total_w = sum(w for _, w in signals)
    raw_qty = sum(v * w for v, w in signals) / total_w

    adjusted = raw_qty * min(1.0, ship_prob * 2.0)
    return max(0, int(round(adjusted))), ship_prob


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

    all_rows: list[tuple[str, dict]] = []
    sku_daily_map: dict[str, dict[str, int]] = {}

    for row in skus:
        all_rows.append(("single_sku", row))
        pn = normalize_sku_name(row.get("target_code", ""))
        on = normalize_sku_name(row.get("option_name", ""))
        key = f"{pn}||{on}"
        sku_daily_map[key] = {k: int(v) for k, v in row["daily"].items()}

    for row in combos:
        all_rows.append(("combination", row))
        ckey = row.get("combination_key", "")
        sku_daily_map[f"combo||{ckey}"] = {k: int(v) for k, v in row["daily"].items()}

    ml_predictions: dict[str, int] = {}
    ml_info = {"trained": False, "train_samples": 0, "train_accuracy": 0}
    try:
        ml_predictions = ml_forecast_service.train_and_predict(
            supplier_name, target_date, sku_daily_map,
        )
        ml_info = ml_forecast_service.get_model_info(supplier_name, target_date)
    except Exception as exc:
        logger.warning("ML prediction failed for %s: %s", supplier_name, exc)

    ml_trained = ml_info.get("trained", False)
    ml_accuracy = ml_info.get("train_accuracy", 0)

    out: list[dict] = []

    for target_type, row in all_rows:
        daily = {k: int(v) for k, v in row["daily"].items()}

        stat_qty, ship_prob = _stat_predict(daily, td, weeks_back)

        if target_type == "combination":
            ckey = row.get("combination_key", "")
            ml_key = f"combo||{ckey}"
        else:
            pn = normalize_sku_name(row.get("target_code", ""))
            on = normalize_sku_name(row.get("option_name", ""))
            ml_key = f"{pn}||{on}"

        ml_qty = ml_predictions.get(ml_key, 0)

        if ml_trained and ml_qty > 0 and ml_accuracy >= 0.3:
            predicted_qty = ml_qty
            model_used = "ml"
        elif ml_trained and ml_qty > 0 and stat_qty > 0:
            predicted_qty = int(round(ml_qty * 0.6 + stat_qty * 0.4))
            model_used = "ensemble"
        else:
            predicted_qty = stat_qty
            model_used = "statistical"

        avg_14, _ = _active_avg(daily, td, 14)
        avg_30, _ = _active_avg(daily, td, 30)
        wd_avg, _, _ = _same_weekday_stats(daily, td, weeks_back)

        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        var = _variability_coeff(daily, td, 30)
        base_conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )
        if model_used == "ml":
            base_conf = min(1.0, base_conf + 0.1)

        entry = {
            "target_type": target_type,
            "target_name": row.get("target_name", ""),
            "target_code": row.get("target_code", row.get("combination_key", "")),
            "sku_code": row.get("sku_code", ""),
            "barcode": row.get("barcode", ""),
            "option_name": row.get("option_name", ""),
            "combination_key": row.get("combination_key", ""),
            "items": row.get("items", []),
            "predicted_qty": predicted_qty,
            "stat_qty": stat_qty,
            "ml_qty": ml_qty,
            "ml_model_type": model_used,
            "ml_accuracy": round(ml_accuracy, 3),
            "ml_samples": ml_info.get("train_samples", 0),
            "confidence_score": round(base_conf, 3),
            "recent_7d_avg": round(avg_14, 1),
            "recent_30d_avg": round(avg_30, 1),
            "recent_same_weekday_avg": round(wd_avg, 1),
            "weekday_basis": wb,
            "frequency": row["frequency"],
            "model_used": model_used,
            "ship_probability": round(ship_prob, 3),
            "gpt_reason": "",
            "gpt_confidence": "",
        }

        out.append(entry)

    return out


def _variability_coeff(daily: dict[str, int], td: dt.date, days: int = 30) -> float:
    vals = []
    for i in range(1, days + 1):
        d = td - dt.timedelta(days=i)
        v = daily.get(d.isoformat(), 0)
        if v > 0:
            vals.append(float(v))
    if len(vals) < 2:
        return 0.0
    m = _stats.mean(vals)
    if m <= 1e-9:
        return 1.0
    return min(1.0, _stats.pstdev(vals) / m)
