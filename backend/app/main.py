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

from backend.app.api import health_router, calculate_router, upload_router, vendors_router, rates_router, insights_router, invoices_router, auth_router, logs_router, estimate_router
from backend.app.api.settings import router as settings_router
from backend.app.api.vendor_charges import router as vendor_charges_router
from backend.app.api.storage import router as storage_router
from backend.app.api.naver_works_webhook import router as naver_works_router
from backend.app.api.work_log import router as work_log_router
from backend.app.api.repair_log import router as repair_log_router, ensure_repair_tables
from backend.app.api.defect_log import router as defect_log_router, ensure_defect_tables
from backend.app.api.estimate_analytics import router as estimate_analytics_router
from backend.app.api.invoice_analytics import router as invoice_analytics_router
from backend.app.api.wp_analytics import router as wp_analytics_router
from backend.app.api.leave import router as leave_router
from backend.app.api.receipt import router as receipt_router
from backend.app.api.certificates import router as certificates_router
from backend.app.api.billing_invoice import router as billing_invoice_router, ensure_tables as ensure_billing_tables
from backend.app.api.kpost_pickup import router as kpost_pickup_router, ensure_pickup_tables
from backend.app.api.inbound import router as inbound_router, ensure_inbound_tables
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
    expose_headers=["Content-Disposition"],
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
app.include_router(settings_router)
app.include_router(vendor_charges_router)
app.include_router(storage_router)
app.include_router(naver_works_router)
app.include_router(work_log_router)
app.include_router(repair_log_router)
app.include_router(defect_log_router)
app.include_router(estimate_router)
app.include_router(estimate_analytics_router)
app.include_router(invoice_analytics_router)
app.include_router(wp_analytics_router)
app.include_router(leave_router)
app.include_router(receipt_router)
app.include_router(certificates_router)
app.include_router(billing_invoice_router)
app.include_router(kpost_pickup_router)
app.include_router(inbound_router)


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
    """앱 시작 시 DB 테이블 확인 및 스케줄러 시작."""
    import logging as _logging
    import os as _os
    from pathlib import Path as _Path
    from backend.app.config import settings as _settings

    _log = _logging.getLogger("startup")

    # ── UPLOAD_DIR 쓰기 가능 여부 확인 ──────────────────────────────
    _upload_dir = _Path(_settings.UPLOAD_DIR)
    try:
        _upload_dir.mkdir(parents=True, exist_ok=True)
        _probe = _upload_dir / ".write_probe"
        _probe.write_text("ok")
        _probe.unlink()
        _log.info("[UPLOAD_DIR] OK — 쓰기 가능: %s", _upload_dir)
    except Exception as _e:
        _log.error("[UPLOAD_DIR] 쓰기 불가 — %s: %s", _upload_dir, _e)

    # ── Railway 영구 볼륨 경고 ───────────────────────────────────────
    _data_dir = _upload_dir.parent  # /app/data
    _is_ephemeral = not _os.path.ismount(str(_data_dir))
    if _is_ephemeral:
        _log.warning(
            "[UPLOAD_DIR] 경고: %s 가 마운트된 영구 볼륨이 아닌 것으로 보입니다. "
            "Railway에서 재시작 시 파일이 삭제될 수 있습니다. "
            "Railway Dashboard > Service > Volumes > Add Volume (Mount: /app/data) 설정을 확인하세요.",
            _data_dir,
        )
    else:
        _log.info("[UPLOAD_DIR] 영구 볼륨 마운트 감지: %s", _data_dir)

    from logic import ensure_tables
    ensure_tables()
    # 연차 테이블 초기화
    from backend.app.api.leave import ensure_leave_tables
    ensure_leave_tables()
    from backend.app.api.receipt import ensure_receipt_tables
    ensure_receipt_tables()
    ensure_repair_tables()
    ensure_defect_tables()
    ensure_billing_tables()
    ensure_pickup_tables()
    ensure_inbound_tables()
    # 스케줄러 시작 (평일 오전 10시 인사)
    from backend.app.services.scheduler import start_scheduler
    start_scheduler()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

