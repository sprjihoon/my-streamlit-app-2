from __future__ import annotations

from fastapi import APIRouter

from .analysis_routes import router as analysis_router
from .execution_routes import router as execution_router
from .location_routes import router as location_router
from .recommendation_routes import router as recommendation_router
from .report_routes import router as report_router
from .stock_routes import router as stock_router
from .upload_routes import router as upload_router
from .unwrap_routes import router as unwrap_router
from .validation_routes import router as validation_router
from .benchmark_routes import router as benchmark_router

prepacking_router = APIRouter()
prepacking_router.include_router(upload_router)
prepacking_router.include_router(analysis_router)
prepacking_router.include_router(recommendation_router)
prepacking_router.include_router(execution_router)
prepacking_router.include_router(stock_router)
prepacking_router.include_router(location_router)
prepacking_router.include_router(unwrap_router)
prepacking_router.include_router(validation_router)
prepacking_router.include_router(report_router)
prepacking_router.include_router(benchmark_router)
