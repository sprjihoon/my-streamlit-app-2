"""
forecast_service — 경량 통계 예측
─────────────────────────────────
핵심: "출하가 있는 날의 평균 수량"을 예측값으로 사용.
작업지시서 목적 = 출하 발생 시 몇 개 준비할지 → 확률 곱하지 않음.

시그널 (출하일만의 평균):
  1. 최근 14일 출하일 평균 (가중치 4) — 최근 트렌드
  2. 최근 30일 출하일 평균 (가중치 2) — 중기 트렌드
  3. 같은 요일 최근 8주 출하일 평균 (가중치 3) — 요일 패턴
"""
from __future__ import annotations

import datetime as dt
import logging
import statistics as _stats

from prepacking.services.analysis import repeat_combination_service, repeat_sku_service, weekday_pattern_service
from prepacking.services.prediction import confidence_service

logger = logging.getLogger(__name__)


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


def _same_weekday_avg(daily: dict[str, int], td: dt.date, weeks: int) -> float:
    """같은 요일 최근 N주 중 출하가 있던 날만의 평균 수량."""
    nonzero = []
    for w in range(1, weeks + 1):
        past_d = td - dt.timedelta(weeks=w)
        v = daily.get(past_d.isoformat(), 0)
        if v > 0:
            nonzero.append(float(v))
    return sum(nonzero) / len(nonzero) if nonzero else 0.0


def _predict_qty(daily: dict[str, int], td: dt.date, weeks_back: int = 8) -> dict:
    avg_14, active_14 = _active_avg(daily, td, 14)
    avg_30, active_30 = _active_avg(daily, td, 30)
    wd_avg = _same_weekday_avg(daily, td, weeks_back)

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
            predicted_qty = max(1, int(round(total_qty / active_total)))
        else:
            predicted_qty = 0
        return {"predicted_qty": predicted_qty,
                "avg_14": avg_14, "avg_30": avg_30, "avg_same_wd": wd_avg}

    total_w = sum(w for _, w in signals)
    predicted = sum(v * w for v, w in signals) / total_w
    predicted_qty = max(0, int(round(predicted)))

    return {
        "predicted_qty": predicted_qty,
        "avg_14": avg_14,
        "avg_30": avg_30,
        "avg_same_wd": wd_avg,
    }


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

        result = _predict_qty(daily, td, weeks_back)

        data_days = weekday_pattern_service.distinct_active_days(
            daily, target_date, lookback_days
        )
        var = _variability_coeff(daily, td, 30)
        base_conf = confidence_service.calculate_confidence(
            row["frequency"], var, data_days
        )

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
            "stat_qty": result["predicted_qty"],
            "ml_qty": 0,
            "ml_model_type": "statistical",
            "ml_accuracy": 0,
            "ml_samples": 0,
            "confidence_score": round(base_conf, 3),
            "recent_7d_avg": round(result.get("avg_14", 0), 1),
            "recent_30d_avg": round(result.get("avg_30", 0), 1),
            "recent_same_weekday_avg": round(result.get("avg_same_wd", 0), 1),
            "weekday_basis": wb,
            "frequency": row["frequency"],
            "model_used": "statistical",
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
