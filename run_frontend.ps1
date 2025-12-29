# Next.js 프론트엔드 실행 스크립트 (PowerShell)
# ─────────────────────────────────────────────

Write-Host "Starting Next.js Frontend..." -ForegroundColor Green
Write-Host ""

# 프론트엔드 폴더로 이동
Set-Location "$PSScriptRoot\frontend"

# node_modules 확인 및 설치
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    npm install
}

Write-Host ""
Write-Host "Starting development server on http://localhost:3000" -ForegroundColor Cyan
Write-Host ""

npm run dev

