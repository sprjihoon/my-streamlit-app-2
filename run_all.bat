@echo off
REM 전체 시스템 실행 스크립트 (백엔드 + 프론트엔드)
REM ──────────────────────────────────────────────

echo ========================================
echo   Billing System - Full Stack Start
echo ========================================
echo.

REM 프로젝트 루트로 이동
cd /d "%~dp0"

echo [1/2] Starting FastAPI Backend (Port 8000)...
start "FastAPI Backend" cmd /k "uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000"

echo Waiting for backend to start...
timeout /t 3 /nobreak > nul

echo.
echo [2/2] Starting Next.js Frontend (Port 3000)...
cd frontend
if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)
start "Next.js Frontend" cmd /k "npm run dev"

echo.
echo ========================================
echo   Services Started:
echo   - Backend:  http://localhost:8000
echo   - API Docs: http://localhost:8000/docs
echo   - Frontend: http://localhost:3000
echo ========================================
echo.
echo Press any key to exit (services will continue running)...
pause > nul

