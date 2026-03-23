"""
predictor — SeasonalNaive 기반 예측기
──────────────────────────────────────
핵심: 7일 전 같은 요일 값을 그대로 예측.
7일 전에 출하 0이면 → 0, 20이면 → 20.

이것이 가장 정확한 baseline이며, ML이 이를 이기기 전까지는
이 방식을 사용한다.

보조 로직:
- 7일 전 데이터가 없으면 14일 전, 21일 전 순서로 폴백
- 최근 4주 같은 요일 중앙값으로 이상치 보정
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

    # 전체 공급처 수준 트렌드 스케일링 계산
    trend_scale = _compute_supplier_trend_scale(sku_series_map, td_ts)

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

        predicted_qty, ship_prob, method_detail = _seasonal_naive_predict(
            series, td_ts
        )

        # 트렌드 스케일링 적용 (0이 아닌 예측에만)
        if predicted_qty > 0 and trend_scale != 1.0:
            predicted_qty = max(1, int(round(predicted_qty * trend_scale)))
            method_detail += f",scale={trend_scale:.2f}"

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


def _compute_supplier_trend_scale(
    sku_series_map: dict[str, pd.Series],
    td: pd.Timestamp,
) -> float:
    """
    전체 공급처 수준의 트렌드 스케일링 팩터 계산.

    직전 7일 총합 vs 그 전 7일 총합 비율로 증가/감소 추세를 반영.
    급격한 변동 방지를 위해 0.6~1.5 범위로 제한.
    """
    if not sku_series_map:
        return 1.0

    cutoff = td - pd.Timedelta(days=1)
    recent_start = cutoff - pd.Timedelta(days=6)
    prev_start = recent_start - pd.Timedelta(days=7)
    prev_end = recent_start - pd.Timedelta(days=1)

    recent_total = 0.0
    prev_total = 0.0

    for series in sku_series_map.values():
        recent_window = series[(series.index >= recent_start) & (series.index <= cutoff)]
        prev_window = series[(series.index >= prev_start) & (series.index <= prev_end)]
        recent_total += recent_window.sum()
        prev_total += prev_window.sum()

    if prev_total < 10:
        return 1.0

    raw_scale = recent_total / prev_total
    return max(0.6, min(1.5, raw_scale))


def _daily_to_filled_series(
    daily: dict, td_ts: pd.Timestamp, lookback_days: int
) -> pd.Series | None:
    """daily dict를 연속 날짜 시계열로 변환. 0인 날도 포함."""
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


def _seasonal_naive_predict(
    series: pd.Series,
    td: pd.Timestamp,
) -> tuple[int, float, str]:
    """
    SeasonalNaive 예측 — 같은 요일 최근 4주 중앙값 기반.

    중앙값을 사용하면:
    - 이상치에 강건 (한 주만 비정상적으로 높아도 영향 적음)
    - 0이 많으면 자연스럽게 0으로 수렴
    - 변동성이 큰 SKU에서도 안정적

    출하 확률이 25% 미만이면 0으로 예측.
    """
    cutoff = td - pd.Timedelta(days=1)
    past = series[series.index <= cutoff]

    if past.empty:
        return 0, 0.0, "no_data"

    # 같은 요일 최근 6주 데이터 수집 (0 포함)
    wd_vals: list[float] = []
    for w in range(1, 7):
        d = td - pd.Timedelta(weeks=w)
        if d in past.index:
            wd_vals.append(float(past[d]))
        elif d >= past.index.min():
            wd_vals.append(0.0)

    if not wd_vals:
        return 0, 0.0, "no_weekday_data"

    # 출하 확률
    ship_count = len([v for v in wd_vals if v > 0])
    ship_prob = ship_count / len(wd_vals)

    # 출하 확률이 매우 낮으면 0 (1/6 미만 = 16.7%)
    if ship_prob < 0.16:
        return 0, ship_prob, f"low_prob({ship_prob:.0%})"

    # 활성값만 추출
    active_vals = [v for v in wd_vals if v > 0]

    # 중앙값 (0 포함) — 과다예측 방지의 핵심
    median_all = float(np.median(wd_vals))
    # 활성값 중앙값 — 과소예측 방지
    median_active = float(np.median(active_vals)) if active_vals else 0.0

    # 최근 1주 값
    d_7 = td - pd.Timedelta(weeks=1)
    val_7 = float(past[d_7]) if d_7 in past.index else 0.0

    # 예측 로직: 출하 확률에 따라 다른 전략
    if ship_prob >= 0.5:
        # 자주 출하되는 SKU: 활성값 중앙값 기반 (과소예측 방지)
        if val_7 > 0:
            blended = val_7 * 0.4 + median_active * 0.6
        else:
            blended = median_active * ship_prob
        predicted = max(0, int(round(blended)))
        method = f"freq(7d={val_7:.0f},medA={median_active:.0f},p={ship_prob:.0%})"
    else:
        # 가끔 출하되는 SKU: 전체 중앙값 기반 (과다예측 방지)
        if median_all > 0:
            predicted = max(0, int(round(median_all)))
            method = f"rare_med({median_all:.0f},p={ship_prob:.0%})"
        elif val_7 > 0:
            predicted = max(0, int(round(val_7 * ship_prob)))
            method = f"rare_7d({val_7:.0f}*{ship_prob:.0%})"
        else:
            predicted = 0
            method = "rare_zero"

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
