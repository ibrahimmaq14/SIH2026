@echo off
echo =================================================================
echo Starting Sentinel Oil Spill Detection - Backend (FastAPI)
echo =================================================================
cd /d "%~dp0backend"
py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
