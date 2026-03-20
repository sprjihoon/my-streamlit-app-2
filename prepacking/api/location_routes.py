from __future__ import annotations

from fastapi import APIRouter

from prepacking.models.schemas import PPLocationCreate, PPMoveStockRequest
from prepacking.services.location.location_history_service import get_history
from prepacking.services.location.location_service import create_location, get_locations, move_stock

router = APIRouter(prefix="/pp/locations", tags=["prepacking-locations"])


@router.post("/")
def post_location(body: PPLocationCreate) -> dict:
    ok = create_location(
        body.location_code,
        location_name=body.location_name,
        zone=body.zone,
        location_type=body.location_type,
        max_capacity=body.max_capacity,
    )
    return {"ok": ok, "location_code": body.location_code}


@router.get("/")
def list_locations(zone: str | None = None, active_only: bool = True) -> list[dict]:
    return get_locations(zone=zone, active_only=active_only)


@router.post("/move")
def post_move(body: PPMoveStockRequest) -> dict:
    ok = move_stock(
        body.stock_id,
        body.from_location,
        body.to_location,
        body.qty,
        moved_by=body.moved_by,
        reason=body.reason,
    )
    return {"ok": ok}


@router.get("/history")
def location_history(
    stock_id: int | None = None,
    location_code: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return get_history(stock_id=stock_id, location_code=location_code, limit=limit)
