@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_COMMAND=py -3"
) else (
    set "PYTHON_COMMAND=python"
)

%PYTHON_COMMAND% --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 or newer is required.
    echo Download it from https://www.python.org/downloads/
    if /I not "%~1"=="/quiet" pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    %PYTHON_COMMAND% -m venv .venv
    if errorlevel 1 goto :setup_failed
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :setup_failed

echo Preparing the editable API key TXT file...
".venv\Scripts\python.exe" -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from amazon_data_extractor.credentials import ensure_api_key_file; ensure_api_key_file(Path.cwd())"
if errorlevel 1 goto :setup_failed

echo Setup complete.
echo Open brightdata_api_key.txt, replace the placeholder with your key, and save.
if /I not "%~1"=="/quiet" pause
exit /b 0

:setup_failed
echo Setup failed. Review the message above.
if /I not "%~1"=="/quiet" pause
exit /b 1
