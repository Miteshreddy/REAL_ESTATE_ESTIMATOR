@echo off
setlocal
title PWD Estimator
cd /d "%~dp0"
echo.
echo   =====================================================
echo     PWD Estimator  -  Drawings to PWD cost estimate
echo   =====================================================
echo.

rem ---- 1. Python 3.12 (installed automatically when missing) ----
set "PYEXE="
py -3.12 -c "import sys" >nul 2>nul && set "PYEXE=py -3.12"
if not defined PYEXE (
  for /f "delims=" %%v in ('python -c "import sys;print(sys.version_info[:2] in [(3,10),(3,11),(3,12)])" 2^>nul') do if "%%v"=="True" set "PYEXE=python"
)
if not defined PYEXE (
  echo [setup] Python 3.12 not found - installing it with winget ^(one time^)...
  winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
  echo [ERROR] Could not install Python automatically. Install Python 3.12 from https://www.python.org/downloads/ ^(tick "Add to PATH"^) and run start.bat again.
  pause
  exit /b 1
)

rem ---- 2. Private environment for the app ----
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating the app environment...
  %PYEXE% -m venv .venv
  if errorlevel 1 ( echo [ERROR] Could not create the environment. & pause & exit /b 1 )
)

rem ---- 3. One-time setup: libraries, Llama engine, model files, SearXNG ----
if not exist ".setup_done" (
  ".venv\Scripts\python.exe" tools\setup_local.py
  if errorlevel 1 ( echo [ERROR] Setup failed - check the messages above and run start.bat again. & pause & exit /b 1 )
)

rem ---- 4. Run ----
".venv\Scripts\python.exe" tools\run_local.py
pause
