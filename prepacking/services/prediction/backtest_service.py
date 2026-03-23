"""
backtest_service — 예측 정확도 백테스트 (v2)
──────────────────────────────────────────
새 파이프라인 기반. MAE/RMSE/WAPE/sMAPE 메트릭 추가.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict

import numpy as np

from prepacking.common.utils import normalize_sku_name, safe_int, safe_str
from prepacking.database import get_pp_connection
from prepacking.services.prediction import forecast_service
from prepacking.services.prediction.pipeline.metrics import compute_all_metrics

logger = logging.getLogger(__name__)


def _run_post_calibration(supplier_name: str, target_date: str, actual_map: dict[str, int]) -> None:
    """백테스트 완료 후 캐시된 컨텍스트로 캘리브레이션 실행."""
    try:
        from prepacking.services.prediction.pipeline.predictor import _last_context
        from prepacking.services.prediction.pipeline.calibration import calibrate_from_backtest

        ctx = _last_context
        if not ctx or ctx.get("supplier_name") != supplier_name:
            return

        result = calibrate_from_backtest(
            supplier_name=supplier_name,
            target_date=target_date,
            sku_series_map=ctx["sku_series_map"],
            all_rows=ctx["all_rows"],
            actual_map=actual_map,
            td_ts=ctx["td_ts"],
        )
        if result:
            logger.info("Post-calibration for %s: acc=%.1f%%", supplier_name, result["accuracy"])
    except Exception as exc:
        logger.warning("Post-calibration failed for %s: %s", supplier_name, exc)


def _load_actual_shipments(supplier_name: str, target_date: str) -> dict[str, int]:
    with get_pp_connection() as con:
        rows = con.execute(
            """
            SELECT product_name, option_name, qty
            FROM pp_shipping_stats
            WHERE TRIM(supplier_name) = TRIM(?)
              AND shipping_date = ?
            """,
            (supplier_name.strip(), target_date),
        ).fetchall()

    sku_totals: dict[str, int] = defaultdict(int)
    for row in rows:
        pn = normalize_sku_name(row[0])
        on = normalize_sku_name(row[1])
        qty = max(1, safe_int(row[2], 1))
        key = f"{pn}||{on}"
        sku_totals[key] += qty

    return sku_totals


def run_backtest(
    supplier_name: str,
    target_date: str,
    weeks_back: int = 8,
) -> dict:
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

    predicted_items = forecast_service.predict_for_date(
        supplier_name, target_date, weeks_back, use_gpt=False,
    )

    predictions: list[dict] = []
    actual_remaining = dict(actual)

    for item in predicted_items:
        target_type = item.get("target_type", "single_sku")
        target_name = item.get("target_name", "")
        option_name = item.get("option_name", "")
        target_code = item.get("target_code", "")
        best_qty = item.get("predicted_qty", 0)

        actual_qty = 0
        if target_type == "combination":
            combo_items = item.get("items", [])
            for ci in combo_items:
                ci_pn = normalize_sku_name(ci.get("product_name", ""))
                ci_on = normalize_sku_name(ci.get("option_name", ""))
                ci_key = f"{ci_pn}||{ci_on}"
                actual_qty += actual_remaining.pop(ci_key, 0)
        else:
            pn_norm = normalize_sku_name(target_code) if target_code else normalize_sku_name(target_name)
            on_norm = normalize_sku_name(option_name)
            actual_key = f"{pn_norm}||{on_norm}"
            actual_qty = actual_remaining.pop(actual_key, 0)

        if best_qty == 0 and actual_qty == 0:
            continue

        error_abs = abs(best_qty - actual_qty)
        error_pct = (error_abs / actual_qty * 100) if actual_qty > 0 else (100.0 if best_qty > 0 else 0.0)

        # matched 기준: 소량은 ±2개, 대량은 ±30% 이내
        tolerance = max(2, int(actual_qty * 0.3)) if actual_qty > 0 else 1
        if actual_qty > 0 and abs(best_qty - actual_qty) <= tolerance:
            result_type = "matched"
        elif best_qty == 0 and actual_qty > 0:
            result_type = "under"
        elif best_qty > actual_qty:
            result_type = "over"
        else:
            result_type = "under"

        predictions.append({
            "target_type": target_type,
            "target_name": target_name,
            "option_name": option_name,
            "sku_code": item.get("sku_code", ""),
            "barcode": item.get("barcode", ""),
            "items": item.get("items", []),
            "predicted_qty": best_qty,
            "stat_qty": item.get("stat_qty", 0),
            "ml_qty": item.get("ml_qty", 0),
            "model_type": item.get("model_used", "statistical"),
            "actual_qty": actual_qty,
            "error_abs": error_abs,
            "error_pct": round(error_pct, 1),
            "result_type": result_type,
            "confidence_score": item.get("confidence_score", 0),
            "frequency": item.get("frequency", 0),
        })

    missed_items: list[dict] = []
    for key, qty in actual_remaining.items():
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

    # === 새 메트릭 계산 ===
    all_actual = []
    all_predicted = []
    for p in predictions:
        all_actual.append(p["actual_qty"])
        all_predicted.append(p["predicted_qty"])
    for m in missed_items:
        all_actual.append(m["actual_qty"])
        all_predicted.append(0)

    y_true = np.array(all_actual, dtype=float)
    y_pred = np.array(all_predicted, dtype=float)
    detailed_metrics = compute_all_metrics(y_true, y_pred) if len(y_true) > 0 else {}

    # ═══ 3단계 정확도 체계 ═══

    total_predicted = sum(p["predicted_qty"] for p in predictions)
    total_actual = sum(p["actual_qty"] for p in predictions) + sum(m["actual_qty"] for m in missed_items)
    total_abs_error = sum(p["error_abs"] for p in predictions) + sum(m["error_abs"] for m in missed_items)

    # 1) 총합 정확도 — 전체 물량 오차율
    if total_actual > 0:
        volume_error = abs(total_predicted - total_actual) / total_actual * 100
        acc_volume = max(0.0, 100.0 - volume_error)
    else:
        acc_volume = 0.0

    # 2) SKU 매칭률 — 개별 SKU를 얼마나 정확히 맞췄나
    matched = sum(1 for p in predictions if p["result_type"] == "matched")
    over = sum(1 for p in predictions if p["result_type"] == "over")
    under = sum(1 for p in predictions if p["result_type"] == "under")
    total_items = len(predictions) + len(missed_items)
    acc_sku_match = (matched / total_items * 100) if total_items > 0 else 0.0

    # 3) 수량 근접률 — 예측이 실제와 근접한 SKU 비율
    #    소량(≤5): ±3개 이내, 대량(>5): ±60% 이내
    qty_close_count = 0
    for p in predictions:
        aq = p["actual_qty"]
        pq = p["predicted_qty"]
        if aq == 0 and pq == 0:
            qty_close_count += 1
        elif aq > 0 and aq <= 5:
            if abs(pq - aq) <= 3:
                qty_close_count += 1
        elif aq > 5:
            ratio = pq / aq
            if 0.4 <= ratio <= 1.6:
                qty_close_count += 1
        elif aq == 0 and pq <= 2:
            qty_close_count += 1
    for m in missed_items:
        pass  # missed = 0 predicted, actual > 0 → not close
    items_with_data = len(predictions) + len(missed_items)
    acc_qty_close = (qty_close_count / max(items_with_data, 1)) * 100

    # WAPE (참고용)
    wape_pct = (total_abs_error / total_actual * 100) if total_actual > 0 else 0.0

    # 종합 정확도 = 총합 30% + SKU매칭 40% + 수량근접 30%
    accuracy = acc_volume * 0.3 + acc_sku_match * 0.4 + acc_qty_close * 0.3

    # 참고용 MAPE
    items_with_actual = [p for p in predictions if p["actual_qty"] > 0]
    avg_mape = 0.0
    if items_with_actual:
        mape_values = [min(p["error_pct"], 200.0) for p in items_with_actual]
        avg_mape = sum(mape_values) / len(mape_values)

    ml_count = sum(1 for p in predictions if p.get("model_type") not in ("statistical", None, ""))
    stat_count = sum(1 for p in predictions if p.get("model_type") in ("statistical", "stat_override", "stat_only"))

    predictions.sort(key=lambda x: (-x["error_abs"], -x["actual_qty"]))

    # 백테스트 완료 후 자동 캘리브레이션
    _run_post_calibration(supplier_name, target_date, actual)

    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]

    return {
        "target_date": target_date,
        "weekday_name": weekday_kr[td.weekday()],
        "supplier_name": supplier_name,
        "summary": {
            "accuracy": round(accuracy, 1),
            "acc_volume": round(acc_volume, 1),
            "acc_sku_match": round(acc_sku_match, 1),
            "acc_qty_close": round(acc_qty_close, 1),
            "wape_pct": round(wape_pct, 1),
            "avg_mape": round(avg_mape, 1),
            "total_predicted": total_predicted,
            "total_actual": total_actual,
            "total_error": int(total_abs_error),
            "item_count": len(predictions),
            "matched": matched,
            "over": over,
            "under": under,
            "missed": len(missed_items),
            "ml_count": ml_count,
            "stat_count": stat_count,
            **detailed_metrics,
        },
        "items": predictions,
        "missed_items": missed_items,
    }
