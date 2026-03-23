from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from prepacking.models.schemas import PPValidationRequest
from prepacking.services.prediction.backtest_service import run_backtest
from prepacking.services.validation.accuracy_service import get_accuracy_summary
from prepacking.services.validation.failure_analysis_service import analyze_failures
from prepacking.services.validation.validation_service import get_validation_results, validate_predictions

router = APIRouter(prefix="/pp/validation", tags=["prepacking-validation"])
logger = logging.getLogger(__name__)


@router.post("/run")
def post_run_validation(body: PPValidationRequest) -> list[dict]:
    return validate_predictions(body.supplier_name, body.target_date)


@router.get("/results")
def validation_results(
    supplier_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    return get_validation_results(
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/accuracy")
def validation_accuracy(supplier_name: str | None = None, days: int = 30) -> dict:
    return get_accuracy_summary(supplier_name or "", days=days)


@router.get("/failures")
def validation_failures(supplier_name: str, days: int = 30) -> dict:
    if not (supplier_name or "").strip():
        raise HTTPException(status_code=400, detail="supplier_name_required")
    return analyze_failures(supplier_name, days=days)


@router.post("/backtest")
def post_backtest(body: PPValidationRequest) -> dict:
    """과거 특정일에 대해 예측을 실행하고 실제 출하 데이터와 비교."""
    if not (body.supplier_name or "").strip():
        raise HTTPException(status_code=400, detail="supplier_name_required")
    if not (body.target_date or "").strip():
        raise HTTPException(status_code=400, detail="target_date_required")
    try:
        result = run_backtest(body.supplier_name, body.target_date)
    except Exception as exc:
        logger.exception("backtest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if "error" in result:
        raise HTTPException(status_code=400, detail=result.get("message", result["error"]))
    return result
