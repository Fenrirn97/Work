@echo off
setlocal EnableExtensions
set "RUNTIME_ROOT=%LOCALAPPDATA%\SSC\v043"
set "VENV=%RUNTIME_ROOT%\venv"
echo This will rebuild only the short Python/Playwright runtime used by v0.4.7.
echo Program files and ShipStation settings are not deleted.
echo.
if exist "%VENV%" rmdir /s /q "%VENV%"
call "%~dp0START.cmd"
