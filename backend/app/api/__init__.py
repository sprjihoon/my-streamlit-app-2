"""
backend/app/api - API 라우터 모듈
───────────────────────────────────
각 도메인별 API 엔드포인트 정의.
"""

from .health import router as health_router
from .calculate import router as calculate_router
from .upload import router as upload_router
from .vendors import router as vendors_router
from .rates import router as rates_router
from .insights import router as insights_router
from .invoices import router as invoices_router

__all__ = [
    "health_router",
    "calculate_router",
    "upload_router",
    "vendors_router",
    "rates_router",
    "insights_router",
    "invoices_router",
]

