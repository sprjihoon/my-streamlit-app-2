"""
predictor — Baseline-first 예측기
──────────────────────────────────
원칙: ML은 walk-forward validation에서 baseline을 이긴 후에만 사용.
현재 ML이 baseline을 이기지 못하므로 SeasonalNaive 기반 예측 사용.

핵심 수정: series에 출하 0인 날이 없으므로,
같은 요일이 데이터 범위 내에 있으면 0으로 간주.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def predict_for_date(
    supplier_name: str,
    target_date: str,
    weeks_back: int = 8,
    use_gpt: bool = False,
) -> list[dict]:
    from prepacking.common.utils import normalize_sku_name
    from prepacking.services.analysis import repeat_sku_service, repeat_combination_service
    from prepacking.services.analysis import weekday_pattern_service
    from prepacking.services.prediction import confidence_service

    try:
        td = dt.datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        td = dt.date.today()

    td_ts = pd.Timestamp(td)
    lookback_days = max(weeks_back * 7 + 45, 120)
    wb = weekday_pattern_service.weekday_basis_for(target_date)

    skus = repeat_sku_service.load_repeat_sku_daily_totals(
        supplier_name, target_date, lookback_days
    )
    combos = repeat_combination_service.load_repeat_combo_daily_totals(
        supplier_name, target_date, lookback_days
    )

    all_rows: list[tuple[str, dict]] = []
    sku_series_map: dict[str, pd.Series] = {}

    for row in skus:
        all_rows.append(("single_sku", row))
        pn = normalize_sku_name(row.get("target_code", ""))
        on = normalize_sku_name(row.get("option_name", ""))
        key = f"{pn}||{on}"
        daily = row.get("daily", {})
        s = _daily_to_filled_series(daily, td_ts, lookback_days)
        if s is not None:
            sku_series_map[key] = s

    for row in combos:
        all_rows.append(("combination", row))
        ckey = row.get("combination_key", "")
        daily = row.get("daily", {})
        s = _daily_to_filled_series(daily, td_ts, lookback_days)
        if s is not None:
            sku_series_map[f"combo||{ckey}"] = s

    out: list[dict] = []

    for target_type, row in all_rows:
        if target_type == "combination":
            ckey = row.get("combination_key", "")
            series_key = f"combo||{ckey}"
        else:
            pn = normalize_sku_name(row.get("target_code", ""))
            on = normalize_sku_name(row.get("option_name", ""))
            series_key = f"{pn}||{on}"

        series = sku_series_map.get(series_key)
        if series is None or series.empty:
            continue

        predicted_qty, ship_prob, method_detail = _smart_baseline_predict(
            series, td_ts, weeks_back
        )

        daily_dict = {k: int(v) for k, v in row.get("daily", {}).items()}
        data_days = weekday_pattern_service.distinct_active_days(
            daily_dict, target_date, lookback_days
        )
        var = _variability_coeff(series, td_ts)
        base_conf = confidence_service.calculate_confidence(
            row.get("frequency", 0), var, data_days
        )

        cutoff = td_ts - pd.Timedelta(days=1)
        past = series[series.index <= cutoff]
        avg_14 = float(past.tail(14).mean()) if len(past) >= 1 else 0.0
        avg_30 = float(past.tail(30).mean()) if len(past) >= 1 else 0.0

        wd_vals = []
        for w in range(1, weeks_back + 1):
            d = td_ts - pd.Timedelta(weeks=w)
            if d in series.index:
                wd_vals.append(float(series[d]))
            else:
                wd_vals.append(0.0)
        wd_active = [v for v in wd_vals if v > 0]
        wd_avg = np.mean(wd_active) if wd_active else 0.0

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
            "stat_qty": predicted_qty,
            "ml_qty": 0,
            "ml_model_type": "statistical",
            "ml_accuracy": 0,
            "ml_samples": 0,
            "confidence_score": round(base_conf, 3),
            "recent_7d_avg": round(avg_14, 1),
            "recent_30d_avg": round(avg_30, 1),
            "recent_same_weekday_avg": round(wd_avg, 1),
            "weekday_basis": wb,
            "frequency": row.get("frequency", 0),
            "model_used": "statistical",
            "ship_probability": round(ship_prob, 3),
            "gpt_reason": method_detail,
            "gpt_confidence": "",
        }
        out.append(entry)

    return out


def _daily_to_filled_series(
    daily: dict, td_ts: pd.Timestamp, lookback_days: int
) -> pd.Series | None:
    """
    daily dict를 연속 날짜 시계열로 변환.
    출하가 없는 날도 0으로 채움 — 출하 확률 계산에 필수.
    """
    if not daily:
        return None

    raw = {pd.Timestamp(k): int(v) for k, v in daily.items()}
    if not raw:
        return None

    start = td_ts - pd.Timedelta(days=lookback_days)
    end = td_ts - pd.Timedelta(days=1)
    date_range = pd.date_range(start, end, freq="D")

    filled = pd.Series(0.0, index=date_range)
    for d, v in raw.items():
        if d in filled.index:
            filled[d] = float(v)

    return filled


def _smart_baseline_predict(
    series: pd.Series,
    td: pd.Timestamp,
    weeks_back: int = 8,
) -> tuple[int, float, str]:
    """
    스마트 baseline 예측.
    series는 연속 날짜 (0 포함)이므로 출하 확률이 정확하게 계산됨.
    """
    cutoff = td - pd.Timedelta(days=1)
    past = series[series.index <= cutoff]

    if past.empty:
        return 0, 0.0, "no_data"

    # === 같은 요일 데이터 수집 (0 포함) ===
    wd_data: list[tuple[int, float]] = []
    for w in range(1, weeks_back + 1):
        d = td - pd.Timedelta(weeks=w)
        if d in past.index:
            wd_data.append((w, float(past[d])))
        elif d >= past.index.min():
            wd_data.append((w, 0.0))

    if not wd_data:
        return 0, 0.0, "no_weekday_data"

    # === 출하 확률 (0 포함이므로 정확) ===
    total_weeks = len(wd_data)
    ship_weeks = len([d for d in wd_data if d[1] > 0])
    ship_prob = ship_weeks / total_weeks

    if ship_prob == 0:
        return 0, 0.0, "zero_ship_prob"

    # === 가중 평균 (출하가 있는 주만, 최근에 높은 가중치) ===
    active_data = [(w, q) for w, q in wd_data if q > 0]
    if not active_data:
        return 0, 0.0, "no_active_weekday"

    weights = []
    qtys = []
    for weeks_ago, qty in active_data:
        weight = 1.0 / weeks_ago
        weights.append(weight)
        qtys.append(qty)

    weighted_avg = float(np.average(qtys, weights=weights))

    # === 트렌드 반영 ===
    recent_2w = [q for w, q in active_data if w <= 2]
    older_2w = [q for w, q in active_data if w > 2]

    trend_factor = 1.0
    if recent_2w and older_2w:
        recent_mean = np.mean(recent_2w)
        older_mean = np.mean(older_2w)
        if older_mean > 0:
            raw_trend = recent_mean / older_mean
            trend_factor = max(0.5, min(1.5, raw_trend))

    adjusted_qty = weighted_avg * trend_factor

    # === 출하 확률 적용 ===
    if ship_prob >= 0.5:
        final_qty = adjusted_qty
    elif ship_prob >= 0.25:
        final_qty = adjusted_qty * ship_prob * 2
    else:
        final_qty = adjusted_qty * ship_prob

    predicted = max(0, int(round(final_qty)))

    method = f"wd_weighted(prob={ship_prob:.0%},trend={trend_factor:.2f},wAvg={weighted_avg:.1f})"
    return predicted, ship_prob, method


def _variability_coeff(series: pd.Series, td: pd.Timestamp, days: int = 30) -> float:
    cutoff = td - pd.Timedelta(days=1)
    start = cutoff - pd.Timedelta(days=days - 1)
    w = series[(series.index >= start) & (series.index <= cutoff)]
    active = w[w > 0]
    if len(active) < 2:
        return 0.0
    m = float(active.mean())
    if m <= 1e-9:
        return 1.0
    return min(1.0, float(active.std() / m))
