# 전체 시스템 실행 스크립트 (PowerShell)
# ──────────────────────────────────────────────

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Billing System - Full Stack Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 프로젝트 루트로 이동
Set-Location $PSScriptRoot

# 백엔드 시작
Write-Host "[1/2] Starting FastAPI Backend (Port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000"

Write-Host "Waiting for backend to start..."
Start-Sleep -Seconds 3

# 프론트엔드 시작
Write-Host ""
Write-Host "[2/2] Starting Next.js Frontend (Port 3000)..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Services Started:" -ForegroundColor Green
Write-Host "  - Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  - API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  - Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Green

