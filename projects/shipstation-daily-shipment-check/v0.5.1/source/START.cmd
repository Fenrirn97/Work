@echo off
setlocal
cd /d "%~dp0"

set "APP_HOME=%LOCALAPPDATA%\ShipStationDailyCheck"
set "VENV=%APP_HOME%\venv"
if not exist "%APP_HOME%" mkdir "%APP_HOME%" >nul 2>nul

set "PY_CMD=py -3"
py -3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
if errorlevel 1 (
  set "PY_CMD=python"
  python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.11 or newer, then reopen START.cmd.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
  )
)

if not exist "%VENV%\Scripts\python.exe" (
  echo Preparing the app in a short Windows path...
  %PY_CMD% -m venv "%VENV%"
  if errorlevel 1 goto setup_error
)

"%VENV%\Scripts\python.exe" -c "import requests, openpyxl, playwright" >nul 2>nul
if errorlevel 1 (
  echo Installing required Python packages. Internet is needed for this first step.
  set "PIP_NO_CACHE_DIR=1"
  "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto setup_error
)

echo Starting ShipStation Daily Shipment Check...
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
echo Setup did not finish. Check the internet connection, Python installation, and folder permissions.
echo The virtual environment is intentionally stored at:
echo %VENV%
echo This short path avoids Windows long-filename errors from deeply nested folders.
pause
exit /b 1
