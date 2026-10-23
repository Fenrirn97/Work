@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ShipStation Daily Shipment Check v0.4.7
echo Ship Date ranges + ShipStation printed status and time.
echo.

set "RUNTIME_ROOT=%LOCALAPPDATA%\SSC\v043"
set "VENV=%RUNTIME_ROOT%\venv"

if not exist "%RUNTIME_ROOT%" mkdir "%RUNTIME_ROOT%" >nul 2>nul

echo Checking Python...
set "PY_CMD="
py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"

if not defined PY_CMD (
  python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo.
  echo Python 3.11 or newer was not found.
  echo Install Python from https://www.python.org/downloads/windows/
  echo Then run START.cmd again.
  pause
  exit /b 1
)

set "REBUILD_VENV=0"
if not exist "%VENV%\Scripts\python.exe" set "REBUILD_VENV=1"
if exist "%VENV%\Scripts\python.exe" (
  "%VENV%\Scripts\python.exe" -c "import sys; print(sys.executable)" >nul 2>nul
  if errorlevel 1 set "REBUILD_VENV=1"
)

if "%REBUILD_VENV%"=="1" (
  if exist "%VENV%" (
    echo Old or broken Python environment detected. Rebuilding the short runtime...
    rmdir /s /q "%VENV%" >nul 2>nul
  ) else (
    echo Preparing the short runtime for first use...
  )
  %PY_CMD% -m venv "%VENV%"
  if errorlevel 1 goto setup_error
)

"%VENV%\Scripts\python.exe" -c "import requests, openpyxl, playwright" >nul 2>nul
if errorlevel 1 (
  echo Installing Python packages into %RUNTIME_ROOT% ...
  echo Internet is needed for this first step.
  "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto setup_error
)

"%VENV%\Scripts\python.exe" app.py
if errorlevel 1 goto runtime_error
exit /b 0

:runtime_error
echo.
echo The app stopped because of an error. Review the message above.
pause
exit /b 1

:setup_error
echo.
echo Setup did not finish.
echo Check your internet connection and folder permissions, then try again.
echo The runtime is stored at: %RUNTIME_ROOT%
pause
exit /b 1
