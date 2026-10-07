@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    call SETUP.bat /quiet
    if errorlevel 1 (
        echo The program could not be set up.
        pause
        exit /b 1
    )
)

start "" http://127.0.0.1:5050
".venv\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo Amazon Data Extractor stopped because of an error.
    pause
)

endlocal