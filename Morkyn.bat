@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM Morkyn opens in its own window (morkyn_app.py). Settings live in the game:
REM the main menu has Where / Engine / Pipeline, Settings has the rest.
REM Pass-through args: local | lan | vpn [port] | --browser | --console
REM The old terminal menu is still available: powershell -File Morkyn.ps1

set "PY=python"
where python >nul 2>nul || set "PY=py -3"

%PY% -c "import fastapi, uvicorn, pydantic" >nul 2>nul
if errorlevel 1 (
    echo Installing Morkyn's Python packages...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)

set "WINDOW=1"
%PY% -c "import webview" >nul 2>nul
if errorlevel 1 (
    echo Installing the Morkyn window ^(pywebview^)...
    %PY% -m pip install "pywebview>=6.2"
    %PY% -c "import webview" >nul 2>nul
    if errorlevel 1 set "WINDOW=0"
)

set "CONSOLE=0"
for %%A in (%*) do (
    if /i "%%~A"=="--console" set "CONSOLE=1"
    if /i "%%~A"=="console" set "CONSOLE=1"
)

REM Without the window, run here so this terminal shows the addresses and Ctrl+C stops it.
if "%WINDOW%"=="0" set "CONSOLE=1"
if "%CONSOLE%"=="1" (
    %PY% "%~dp0morkyn_app.py" %*
    set "EXIT_CODE=!ERRORLEVEL!"
    if not "!EXIT_CODE!"=="0" pause
    exit /b !EXIT_CODE!
)

REM pythonw has no console, so nothing is left open behind the window.
set "PYW="
for /f "usebackq delims=" %%P in (`%PY% -c "import os, sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"`) do set "PYW=%%P"
if defined PYW if exist "%PYW%" (
    start "" "%PYW%" "%~dp0morkyn_app.py" %*
    exit /b 0
)
%PY% "%~dp0morkyn_app.py" %*
exit /b %ERRORLEVEL%

:failed
echo.
echo Morkyn could not install its Python packages.
pause
exit /b 1
