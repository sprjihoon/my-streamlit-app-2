"""
backend/app/main.py - FastAPI 메인 애플리케이션
───────────────────────────────────────────────────
logic/ 모듈을 감싸는 얇은 API 레이어.

실행 방법:
    # 개발
    uvicorn backend.app.main:app --reload --port 8000
    
    # 프로덕션
    gunicorn backend.app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import health_router, calculate_router, upload_router, vendors_router, rates_router, insights_router, invoices_router, auth_router, logs_router
from backend.app.config import settings

# FastAPI 앱 생성
app = FastAPI(
    title=settings.APP_NAME,
    description="인보이스 계산 및 관리 API",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,  # 프로덕션에서 docs 비활성화 가능
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS 설정 (환경변수 기반)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.CORS_ALLOW_HEADERS.split(",") if settings.CORS_ALLOW_HEADERS != "*" else ["*"],
)


# 라우터 등록
app.include_router(health_router)
app.include_router(calculate_router)
app.include_router(upload_router)
app.include_router(vendors_router)
app.include_router(rates_router)
app.include_router(insights_router)
app.include_router(invoices_router)
app.include_router(auth_router)
app.include_router(logs_router)


# 루트 엔드포인트
@app.get("/")
async def root():
    """API 루트."""
    return {
        "name": "Billing API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# 앱 시작 이벤트
@app.on_event("startup")
async def startup_event():
    """앱 시작 시 DB 테이블 확인."""
    from logic import ensure_tables
    ensure_tables()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

