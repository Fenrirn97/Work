@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0runtime\python.exe" (
    echo Starting Inventory Count with the bundled Python runtime...
    "%~dp0runtime\python.exe" server.py --open
    goto :finished
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 server.py --open
    goto :finished
)

where python >nul 2>nul
if not errorlevel 1 (
    python server.py --open
    goto :finished
)

echo.
echo The bundled Python runtime is missing, and Python 3 was not found on this PC.
echo Download the complete portable ZIP again, then extract every file before running it.
echo The runtime\python.exe file must remain beside this launcher.
echo.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo.
    echo The Inventory Web App stopped because of an error.
    pause
)
endlocal
