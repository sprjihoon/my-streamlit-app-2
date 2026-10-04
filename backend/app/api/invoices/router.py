"""Invoice API router. Prefix and tags stay the same."""
from fastapi import APIRouter

router = APIRouter(prefix="/invoices", tags=["invoices"])
