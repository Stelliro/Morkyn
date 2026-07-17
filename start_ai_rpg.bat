@echo off
setlocal

cd /d "%~dp0"

if /i "%~1"=="local" set "AI_RPG_LAUNCH_MODE=local"
if /i "%~1"=="machine" set "AI_RPG_LAUNCH_MODE=local"
if /i "%~1"=="lan" set "AI_RPG_LAUNCH_MODE=network"
if /i "%~1"=="network" set "AI_RPG_LAUNCH_MODE=network"
if /i "%~1"=="web" set "AI_RPG_LAUNCH_MODE=network"
if /i "%~1"=="vpn" set "AI_RPG_LAUNCH_MODE=vpn"
if /i "%~1"=="tunnel" set "AI_RPG_LAUNCH_MODE=vpn"
if /i "%~1"=="tailscale" set "AI_RPG_LAUNCH_MODE=vpn"
if /i "%~1"=="wireguard" set "AI_RPG_LAUNCH_MODE=vpn"
if /i "%~1"=="zerotier" set "AI_RPG_LAUNCH_MODE=vpn"

if /i "%AI_RPG_LAUNCH_MODE%"=="vpn" if not "%~2"=="" set "AI_RPG_APP_PORT=%~2"

if not defined AI_RPG_LAUNCH_MODE if defined AI_RPG_APP_HOST set "AI_RPG_LAUNCH_MODE=custom"

if not defined AI_RPG_LAUNCH_MODE (
    echo.
    echo Morkyn launch mode:
    echo   1. This machine only  ^(http://127.0.0.1:8000^)
    echo   2. Local network / phone  ^(same Wi-Fi/LAN^)
    echo   3. VPN / virtual network  ^(Tailscale/WireGuard/ZeroTier/etc.^)
    echo.
    choice /C 123 /N /M "Choose 1, 2, or 3: "
    if errorlevel 3 (
        set "AI_RPG_LAUNCH_MODE=vpn"
    ) else if errorlevel 2 (
        set "AI_RPG_LAUNCH_MODE=network"
    ) else (
        set "AI_RPG_LAUNCH_MODE=local"
    )
)

if /i "%AI_RPG_LAUNCH_MODE%"=="vpn" if not defined AI_RPG_APP_PORT (
    echo.
    set "VPN_PORT="
    set /P "VPN_PORT=VPN app port [8000]: "
    if defined VPN_PORT (
        set "AI_RPG_APP_PORT=%VPN_PORT%"
    ) else (
        set "AI_RPG_APP_PORT=8000"
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ai_rpg.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Launcher stopped with error code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
