@echo off
REM FastAPI 백엔드 실행 스크립트
REM ─────────────────────────────

echo Starting FastAPI Backend...
echo.

REM 프로젝트 루트로 이동
cd /d "%~dp0"

REM Python 환경 확인
python --version
echo.

REM 의존성 설치 (처음 실행 시)
REM pip install -r backend\requirements.txt

REM FastAPI 서버 실행
echo Starting server on http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.

uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

