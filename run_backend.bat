@echo off
echo Starting Backend Server...
cd /d "%~dp0"
pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause

