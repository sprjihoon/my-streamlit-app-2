"""
backend/app/api/health.py - 헬스체크 엔드포인트
───────────────────────────────────────────────
서비스 상태 확인용 엔드포인트.
"""

from fastapi import APIRouter

from backend.app.models import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    서비스 헬스체크.
    
    Returns:
        서비스 상태 및 버전 정보
    """
    return HealthResponse(status="ok", version="1.0.0")

