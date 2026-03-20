from __future__ import annotations

from fastapi import APIRouter

from prepacking.models.schemas import PPAnalysisRequest
from prepacking.services.analysis.repeat_combination_service import analyze_repeat_combinations
from prepacking.services.analysis.repeat_sku_service import analyze_repeat_skus
from prepacking.services.analysis.weekday_pattern_service import analyze_weekday_patterns

router = APIRouter(prefix="/pp/analysis", tags=["prepacking-analysis"])


@router.post("/repeat-skus")
def post_repeat_skus(body: PPAnalysisRequest) -> list[dict]:
    return analyze_repeat_skus(
        body.supplier_name,
        body.date_from,
        body.date_to,
        body.min_count,
    )


@router.post("/repeat-combinations")
def post_repeat_combinations(body: PPAnalysisRequest) -> list[dict]:
    return analyze_repeat_combinations(
        body.supplier_name,
        body.date_from,
        body.date_to,
        body.min_count,
    )


@router.post("/weekday-patterns")
def post_weekday_patterns(body: PPAnalysisRequest) -> dict:
    return analyze_weekday_patterns(
        body.supplier_name,
        body.date_from,
        body.date_to,
    )
