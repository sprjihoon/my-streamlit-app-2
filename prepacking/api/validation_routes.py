from __future__ import annotations

from fastapi import APIRouter, HTTPException

from prepacking.models.schemas import PPValidationRequest
from prepacking.services.validation.accuracy_service import get_accuracy_summary
from prepacking.services.validation.failure_analysis_service import analyze_failures
from prepacking.services.validation.validation_service import get_validation_results, validate_predictions

router = APIRouter(prefix="/pp/validation", tags=["prepacking-validation"])


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
