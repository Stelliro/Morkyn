@echo off
setlocal
cd /d "%~dp0"

REM Pass-through args: local | lan | vpn [port] | play
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Morkyn.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Morkyn launcher stopped with error code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
