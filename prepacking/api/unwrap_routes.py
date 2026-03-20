from __future__ import annotations

from fastapi import APIRouter, Query

from prepacking.models.schemas import PPUnwrapRequest
from prepacking.services.unwrap.restore_service import restore_to_stock
from prepacking.services.unwrap.unwrap_service import get_unwrap_history, unwrap_stock

router = APIRouter(prefix="/pp/unwrap", tags=["prepacking-unwrap"])


@router.post("/")
def post_unwrap(body: PPUnwrapRequest) -> dict:
    return unwrap_stock(
        body.stock_id,
        body.unwrap_qty,
        reason=body.reason,
        return_to_stock=body.return_to_stock,
        return_location=body.return_location,
        unwrap_by=body.unwrap_by,
    )


@router.get("/history")
def unwrap_history(supplier_name: str | None = None, limit: int = 100) -> list[dict]:
    return get_unwrap_history(supplier_name=supplier_name, limit=limit)


@router.post("/{unwrap_id}/restore")
def post_restore(
    unwrap_id: int,
    restore_location: str = Query(""),
    restored_by: str = Query(""),
) -> dict:
    return restore_to_stock(unwrap_id, restore_location=restore_location, restored_by=restored_by)
