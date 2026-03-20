from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from prepacking.models.schemas import PPStockUseRequest
from prepacking.services.stock.prepack_stock_service import (
    get_active_stock,
    update_stock_status,
    use_stock,
)
from prepacking.services.stock.stock_status_service import get_expiring_stock, get_stock_summary

router = APIRouter(prefix="/pp/stock", tags=["prepacking-stock"])


class PPStockStatusBody(BaseModel):
    status: str


@router.get("/")
def list_stock(supplier_name: str | None = None) -> list[dict]:
    return get_active_stock(supplier_name)


@router.get("/summary")
def stock_summary(supplier_name: str | None = None) -> dict:
    return get_stock_summary(supplier_name)


@router.get("/expiring")
def expiring_stock(days_ahead: int = 2) -> list[dict]:
    return get_expiring_stock(days_ahead)


@router.patch("/{stock_id}/use")
def patch_use_stock(stock_id: int, body: PPStockUseRequest) -> dict:
    return use_stock(stock_id, body.use_qty)


@router.patch("/{stock_id}/status")
def patch_stock_status(stock_id: int, body: PPStockStatusBody) -> dict:
    ok = update_stock_status(stock_id, body.status)
    return {"ok": ok, "prepack_stock_id": stock_id, "status": body.status}
