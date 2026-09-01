@echo off
echo =================================================================
echo Starting Sentinel - Oil Spill Detection & Maritime Intelligence
echo =================================================================
echo [1/2] Launching Backend API on http://localhost:8000 ...
start "Sentinel Backend API" cmd /k "%~dp0start-backend.bat"

echo [2/2] Launching Frontend Web App on http://localhost:3000 ...
start "Sentinel Frontend Web App" cmd /k "%~dp0start-frontend.bat"

echo.
echo Both services are launching!
echo   - Backend API Docs: http://localhost:8000/docs
echo   - Frontend App:     http://localhost:3000
echo.
