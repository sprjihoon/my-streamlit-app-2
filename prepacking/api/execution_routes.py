from __future__ import annotations

from fastapi import APIRouter

from prepacking.models.schemas import PPExecutionRequest
from prepacking.services.execution.execution_service import execute_prepacking, get_executions

router = APIRouter(prefix="/pp/executions", tags=["prepacking-executions"])


@router.post("/")
def post_execution(body: PPExecutionRequest) -> dict:
    return execute_prepacking(
        body.recommendation_id,
        body.executed_qty,
        executed_by=body.executed_by,
        location_code=body.location_code,
        memo=body.memo,
    )


@router.get("/")
def list_executions(
    supplier_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    return get_executions(
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
    )
