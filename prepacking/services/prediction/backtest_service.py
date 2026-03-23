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

        if actual_qty > 0 and abs(best_qty - actual_qty) <= max(1, int(actual_qty * 0.2)):
            result_type = "matched"
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
    ml_count = sum(1 for p in predictions if p.get("model_type") in ("ml", "ensemble"))
    stat_count = sum(1 for p in predictions if p.get("model_type") == "statistical")

    total_predicted = sum(p["predicted_qty"] for p in predictions)
    total_actual = sum(p["actual_qty"] for p in predictions) + sum(m["actual_qty"] for m in missed_items)

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
            "total_error": int(sum(p["error_abs"] for p in predictions) + sum(m["error_abs"] for m in missed_items)),
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
