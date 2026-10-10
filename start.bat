@echo off
setlocal
title Drawing-based PWD Cost Estimation
cd /d "%~dp0"

echo.
echo   =====================================================
echo     Drawings -^> Quantities -^> PWD Rates -^> Cost
echo   =====================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.10+ was not found on PATH. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    pause
    exit /b 1
  )
)

echo [2/3] Installing / verifying dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed. Check your internet connection and retry.
  pause
  exit /b 1
)

echo [3/3] Starting server (first run trains the ML models, ~30-60 s)...
echo.
echo     Open  http://127.0.0.1:8000   (opens automatically)
echo     Press Ctrl+C in this window to stop.
echo.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 180;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health -TimeoutSec 2 | Out-Null; Start-Process 'http://127.0.0.1:8000'; break}catch{Start-Sleep 1}}"
cd backend
"..\.venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
