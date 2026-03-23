"""
ml_forecast_service — 호환성 래퍼
─────────────────────────────────
기존 코드에서 ml_forecast_service를 import하는 곳이 있을 수 있으므로
빈 래퍼를 유지. 실제 로직은 pipeline.predictor로 이동.
"""
from __future__ import annotations


def train_and_predict(
    supplier_name: str,
    target_date: str,
    sku_daily_map: dict,
) -> dict[str, int]:
    return {}


def get_model_info(supplier_name: str, target_date: str) -> dict:
    return {"trained": False, "train_samples": 0, "train_accuracy": 0}
