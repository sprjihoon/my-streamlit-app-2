from __future__ import annotations

from fastapi import APIRouter

from prepacking.ai.ai_log_service import get_ai_usage_summary
from prepacking.services.report.prepack_report_service import get_overview_report
from prepacking.services.report.validation_report_service import get_validation_report

router = APIRouter(prefix="/pp/reports", tags=["prepacking-reports"])


@router.get("/overview")
def report_overview(supplier_name: str | None = None, days: int = 30) -> dict:
    return get_overview_report(supplier_name=supplier_name, days=days)


@router.get("/validation")
def report_validation(supplier_name: str | None = None, days: int = 30) -> dict:
    return get_validation_report(supplier_name=supplier_name, days=days)


@router.get("/ai-usage")
def report_ai_usage(days: int = 30) -> dict:
    return get_ai_usage_summary(days=days)
