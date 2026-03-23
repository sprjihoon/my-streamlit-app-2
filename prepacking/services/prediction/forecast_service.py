"""
forecast_service — 새 파이프라인 기반 예측 (v2)
──────────────────────────────────────────────
기존 인터페이스를 유지하면서 내부를 pipeline 모듈로 교체.
누수 방지, 시간순 검증, baseline 비교가 적용된 구조.
"""
from __future__ import annotations

from prepacking.services.prediction.pipeline.predictor import predict_for_date

__all__ = ["predict_for_date"]
