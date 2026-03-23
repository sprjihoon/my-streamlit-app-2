from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from prepacking.models.schemas import PPValidationRequest
from prepacking.models.schemas import PPWalkForwardRequest
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


@router.post("/walk-forward")
def post_walk_forward(body: PPWalkForwardRequest) -> dict:
    """Walk-forward validation — 시간순 검증 + baseline 비교."""
    from prepacking.services.prediction.pipeline.data_loader import load_daily_series
    from prepacking.services.prediction.pipeline.validation import walk_forward_validate
    from prepacking.services.prediction.pipeline.models import create_best_model

    if not (body.supplier_name or "").strip():
        raise HTTPException(status_code=400, detail="supplier_name_required")

    try:
        daily_df = load_daily_series(body.supplier_name)
        if daily_df.empty:
            raise HTTPException(status_code=400, detail="no_data")

        result = walk_forward_validate(
            daily_df=daily_df,
            test_start=body.test_start,
            test_end=body.test_end,
            model_factory=lambda: create_best_model(),
            train_min_days=body.train_min_days,
            max_skus=body.max_skus,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("walk-forward validation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result


@router.post("/calibrate")
def post_calibrate(body: PPValidationRequest) -> dict:
    """업체별 예측 파라미터 자동 캘리브레이션."""
    from prepacking.services.prediction.pipeline.calibration import calibrate_supplier

    if not (body.supplier_name or "").strip():
        raise HTTPException(status_code=400, detail="supplier_name_required")

    try:
        result = calibrate_supplier(body.supplier_name)
    except Exception as exc:
        logger.exception("calibration failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/calibrate-all")
def post_calibrate_all() -> dict:
    """모든 업체의 예측 파라미터를 자동 캘리브레이션."""
    import numpy as np
    from prepacking.database import get_pp_connection
    from prepacking.services.prediction.pipeline.calibration import calibrate_supplier

    with get_pp_connection() as con:
        rows = con.execute(
            "SELECT DISTINCT supplier_name FROM pp_shipping_stats WHERE supplier_name IS NOT NULL"
        ).fetchall()

    suppliers = [r[0] for r in rows if r[0]]
    results = []

    for s in suppliers:
        try:
            r = calibrate_supplier(s)
            results.append(r)
        except Exception as exc:
            logger.warning("calibration failed for %s: %s", s, exc)
            results.append({"supplier_name": s, "error": str(exc)})

    successes = [r for r in results if "error" not in r]
    avg_acc = (
        float(np.mean([r["best_params"]["avg_accuracy"] for r in successes]))
        if successes else 0.0
    )

    return {
        "total_suppliers": len(suppliers),
        "calibrated": len(successes),
        "failed": len(results) - len(successes),
        "avg_accuracy": round(avg_acc, 1),
        "results": results,
    }
