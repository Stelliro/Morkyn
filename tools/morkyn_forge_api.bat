@echo off
REM =============================================================================
REM Morkyn-owned Forge launcher — does NOT modify your Forge/WebUI install.
REM Sets API-only flags in THIS process only, then calls the install's webui.bat.
REM
REM Usage:
REM   set MORKYN_FORGE_ROOT=D:\ForgeSD
REM   set MORKYN_FORGE_EXTRA_ARGS=--xformers --always-offload-from-vram
REM   tools\morkyn_forge_api.bat
REM =============================================================================

setlocal EnableExtensions

if not defined MORKYN_FORGE_ROOT (
  echo MORKYN_FORGE_ROOT is not set.
  echo Set it to your Forge pack root ^(e.g. D:\ForgeSD^) or the webui folder.
  exit /b 1
)

set "PACK=%MORKYN_FORGE_ROOT%"
if exist "%PACK%\webui\webui.bat" (
  set "WEBUI=%PACK%\webui"
  set "PACKROOT=%PACK%"
) else if exist "%PACK%\webui.bat" (
  set "WEBUI=%PACK%"
  for %%I in ("%PACK%\..") do set "PACKROOT=%%~fI"
) else (
  echo Could not find webui.bat under "%PACK%"
  exit /b 1
)

REM Portable env (Python 3.10, PATH) — read-only call, never rewrite install files.
if exist "%PACKROOT%\environment.bat" call "%PACKROOT%\environment.bat"

if not defined PYTHON (
  if exist "%PACKROOT%\system\python\python.exe" set "PYTHON=%PACKROOT%\system\python\python.exe"
)
set SKIP_VENV=1
set VENV_DIR=-

set "CKPT_DIR="
if exist "%PACKROOT%\models\Stable-diffusion" set "CKPT_DIR=%PACKROOT%\models\Stable-diffusion"
if not defined CKPT_DIR if exist "%WEBUI%\models\Stable-diffusion" set "CKPT_DIR=%WEBUI%\models\Stable-diffusion"

REM Headless API only — overrides COMMANDLINE_ARGS for this process only.
set "COMMANDLINE_ARGS=--api --nowebui"
if defined CKPT_DIR set "COMMANDLINE_ARGS=%COMMANDLINE_ARGS% --ckpt-dir %CKPT_DIR%"
if defined MORKYN_FORGE_EXTRA_ARGS set "COMMANDLINE_ARGS=%COMMANDLINE_ARGS% %MORKYN_FORGE_EXTRA_ARGS%"

echo Morkyn Forge API launch ^(install files untouched^)
echo   PACKROOT=%PACKROOT%
echo   WEBUI=%WEBUI%
echo   PYTHON=%PYTHON%
echo   COMMANDLINE_ARGS=%COMMANDLINE_ARGS%
echo.

cd /d "%WEBUI%"
call webui.bat
endlocal
