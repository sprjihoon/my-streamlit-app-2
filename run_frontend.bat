@echo off
REM Next.js 프론트엔드 실행 스크립트
REM ─────────────────────────────────

echo Starting Next.js Frontend...
echo.

REM 프론트엔드 폴더로 이동
cd /d "%~dp0frontend"

REM node_modules 확인 및 설치
if not exist "node_modules" (
    echo Installing dependencies...
    npm install
)

echo.
echo Starting development server on http://localhost:3000
echo.

npm run dev
