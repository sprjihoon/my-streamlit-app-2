# FastAPI 백엔드 실행 스크립트 (PowerShell)
# ─────────────────────────────────────────

Write-Host "Starting FastAPI Backend..." -ForegroundColor Green
Write-Host ""

# 프로젝트 루트로 이동
Set-Location $PSScriptRoot

# Python 환경 확인
python --version
Write-Host ""

# 의존성 설치 (처음 실행 시)
# pip install -r backend\requirements.txt

# FastAPI 서버 실행
Write-Host "Starting server on http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""

uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

