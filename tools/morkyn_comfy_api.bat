@echo off
REM Morkyn-owned ComfyUI launcher — does not modify the Comfy install.
REM Usage: set MORKYN_COMFY_ROOT=D:\path\to\ComfyUI && tools\morkyn_comfy_api.bat

setlocal EnableExtensions

if not defined MORKYN_COMFY_ROOT (
  echo MORKYN_COMFY_ROOT is not set.
  exit /b 1
)

set "ROOT=%MORKYN_COMFY_ROOT%"
if exist "%ROOT%\comfyui\main.py" set "ROOT=%ROOT%\comfyui"
if exist "%ROOT%\ComfyUI\main.py" set "ROOT=%ROOT%\ComfyUI"
if not exist "%ROOT%\main.py" (
  echo main.py not found under "%MORKYN_COMFY_ROOT%"
  exit /b 1
)

set "PY=%ROOT%\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Morkyn Comfy API launch
echo   ROOT=%ROOT%
echo   PY=%PY%
echo.

cd /d "%ROOT%"
"%PY%" main.py --listen 127.0.0.1 --port 8188
endlocal
