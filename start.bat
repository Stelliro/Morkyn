@echo off
setlocal EnableExtensions

REM Morkyn bootstrapper (Windows).
REM Drop this file into an empty folder and double-click it.
REM Run "start.bat --help" for the options.

set "REPO_URL=https://github.com/Stelliro/Morkyn.git"
if defined MORKYN_REPO_URL set "REPO_URL=%MORKYN_REPO_URL%"
set "BRANCH=main"
if defined MORKYN_BRANCH set "BRANCH=%MORKYN_BRANCH%"

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "WANT_FULL=0"
set "UPDATE_MODE=ask"
set "PASSTHRU="

REM --- options -------------------------------------------------------------
:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--full" goto opt_full
if /i "%~1"=="--update" goto opt_update
if /i "%~1"=="-u" goto opt_update
if /i "%~1"=="--no-update" goto opt_noupdate
if /i "%~1"=="--help" goto show_help
if /i "%~1"=="-h" goto show_help
if /i "%~1"=="/?" goto show_help
set "PASSTHRU=%PASSTHRU% %~1"
shift
goto parse

:opt_full
set "WANT_FULL=1"
shift
goto parse

:opt_update
set "UPDATE_MODE=always"
shift
goto parse

:opt_noupdate
set "UPDATE_MODE=never"
shift
goto parse

:show_help
echo Morkyn bootstrapper (Windows).
echo.
echo Drop this file into an empty folder and double-click it.
echo.
echo   First run  : clones the repo into .\Morkyn, installs dependencies, starts.
echo   Later runs : checks for updates, asks before applying them, then starts.
echo   Offline    : skips the update check and starts what is already on disk.
echo.
echo Options:
echo   --full         also install llama-cpp-python (only needed for the
echo                  built-in GGUF server; Ollama and cloud APIs do not need it)
echo   --update       apply an available update without asking
echo   --no-update    skip the update check entirely
echo   --help         show this text
echo.
echo Anything else is passed straight through to Morkyn.bat, so
echo   start.bat lan 8123
echo works the same way it does on the normal launcher.
echo.
echo Environment overrides:
echo   MORKYN_REPO_URL, MORKYN_BRANCH, MORKYN_DIR, MORKYN_PYTHON
exit /b 0

:parsed

REM --- where does the checkout live? ----------------------------------------
set "REPO_DIR=%SCRIPT_DIR%\Morkyn"
if defined MORKYN_DIR set "REPO_DIR=%MORKYN_DIR%"
if exist "%SCRIPT_DIR%\app\main.py" if exist "%SCRIPT_DIR%\requirements.txt" set "REPO_DIR=%SCRIPT_DIR%"

echo ------------------------------------------------------------
echo  Morkyn launcher
echo ------------------------------------------------------------
echo   folder : %REPO_DIR%

REM --- git -------------------------------------------------------------------
where git >nul 2>&1
if errorlevel 1 goto no_git

if exist "%REPO_DIR%\.git" goto have_repo
if exist "%REPO_DIR%" goto not_a_repo

echo.
echo   no copy found - downloading Morkyn (this happens once)
git clone "%REPO_URL%" "%REPO_DIR%"
if errorlevel 1 goto clone_failed
echo   downloaded
goto ready

REM --- update check ----------------------------------------------------------
:have_repo
if "%UPDATE_MODE%"=="never" goto skipped_check

echo.
echo   checking for updates...
git -C "%REPO_DIR%" fetch --tags --prune origin >nul 2>&1
if errorlevel 1 goto offline

set "REMOTE_REF=origin/%BRANCH%"
git -C "%REPO_DIR%" rev-parse --verify --quiet "%REMOTE_REF%" >nul 2>&1
if errorlevel 1 set "REMOTE_REF=origin/master"

set "AHEAD=0"
set "BEHIND=0"
for /f "tokens=1,2" %%a in ('git -C "%REPO_DIR%" rev-list --left-right --count "HEAD...%REMOTE_REF%" 2^>nul') do (
    set "AHEAD=%%a"
    set "BEHIND=%%b"
)

if "%BEHIND%"=="0" goto up_to_date

set "DIRTY="
for /f "delims=" %%a in ('git -C "%REPO_DIR%" status --porcelain 2^>nul') do set "DIRTY=1"
if defined DIRTY goto dirty_skip
if not "%AHEAD%"=="0" goto ahead_skip

echo.
echo   An update is available - %BEHIND% new change^(s^):
git -C "%REPO_DIR%" log --oneline --no-decorate -n 8 "HEAD..%REMOTE_REF%"
echo.

if "%UPDATE_MODE%"=="always" goto do_update

set "ANSWER="
set /p "ANSWER=  Update now? [Y/n] "
if /i "%ANSWER%"=="n" goto skip_update
if /i "%ANSWER%"=="no" goto skip_update

:do_update
git -C "%REPO_DIR%" merge --ff-only "%REMOTE_REF%"
if errorlevel 1 goto update_failed
echo   updated
goto ready

:skip_update
echo   skipped - starting your current copy
goto ready

:up_to_date
echo   already up to date
goto ready

:skipped_check
echo   update check skipped
goto ready

:offline
echo   could not reach GitHub - starting the copy you already have.
goto ready

:dirty_skip
echo   %BEHIND% update^(s^) available, but you have local changes.
echo   Commit or stash them to update. Starting your current copy.
goto ready

:ahead_skip
echo   %BEHIND% update^(s^) available, but your copy has %AHEAD% local commit^(s^).
echo   Merge by hand to update. Starting your current copy.
goto ready

:update_failed
echo   update failed - starting your current copy instead.
goto ready

REM --- python ----------------------------------------------------------------
:ready
cd /d "%REPO_DIR%"
if errorlevel 1 goto cd_failed

set "PY="
if defined MORKYN_PYTHON set "PY=%MORKYN_PYTHON%"
if defined PY goto have_py

REM The py launcher first: a bare "python" on PATH is often the Microsoft Store
REM stub, which opens the Store instead of running anything.
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_py

where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY goto no_python

:have_py
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto old_python

REM --- virtual environment ---------------------------------------------------
set "VENV=%REPO_DIR%\.venv"
set "VPY=%VENV%\Scripts\python.exe"
if exist "%VPY%" goto have_venv

echo.
echo   creating a private Python environment in .venv
%PY% -m venv "%VENV%"
if errorlevel 1 goto venv_failed
if not exist "%VPY%" goto venv_failed

REM --- dependencies ----------------------------------------------------------
:have_venv
set "NEED_DEPS=0"
"%VPY%" -c "import fastapi, uvicorn, pydantic" >nul 2>&1
if errorlevel 1 set "NEED_DEPS=1"
if "%WANT_FULL%"=="1" set "NEED_DEPS=1"
if "%NEED_DEPS%"=="0" goto launch

echo.
echo   installing dependencies (the first run takes a few minutes)
"%VPY%" -m pip install --upgrade pip >nul 2>&1
if "%WANT_FULL%"=="1" goto install_full

REM llama-cpp-python is only needed for the built-in GGUF server, and its CUDA
REM wheels are a large download that fails outright on machines with no matching
REM toolchain. Ollama and cloud APIs need none of it, so the default install
REM filters it out of the project's own pins rather than keeping a second copy
REM of the version numbers here. --full keeps it.
set "TRIMMED=%TEMP%\morkyn-requirements-%RANDOM%.txt"
"%VPY%" -c "import io,sys; src=io.open('requirements.txt',encoding='utf-8'); io.open(sys.argv[1],'w',encoding='utf-8').writelines([l for l in src if 'llama-cpp-python' not in l and '--extra-index-url' not in l])" "%TRIMMED%"
if errorlevel 1 goto trim_failed
"%VPY%" -m pip install -r "%TRIMMED%"
set "PIP_RC=%ERRORLEVEL%"
del "%TRIMMED%" >nul 2>&1
if not "%PIP_RC%"=="0" goto pip_failed
goto launch

:install_full
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed

REM --- run -------------------------------------------------------------------
:launch
set "PATH=%VENV%\Scripts;%PATH%"
echo.
if not exist "%REPO_DIR%\Morkyn.bat" goto launch_direct

call "%REPO_DIR%\Morkyn.bat" %PASSTHRU%
set "EXIT_CODE=%ERRORLEVEL%"
goto finished

:launch_direct
echo ------------------------------------------------------------
echo  Morkyn is starting
echo   open http://127.0.0.1:8000/ in your browser
echo   press Ctrl+C here to stop
echo ------------------------------------------------------------
echo.
"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
set "EXIT_CODE=%ERRORLEVEL%"

:finished
if not "%EXIT_CODE%"=="0" echo.
if not "%EXIT_CODE%"=="0" echo Morkyn stopped with error code %EXIT_CODE%.
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

REM --- failures --------------------------------------------------------------
:no_git
echo.
echo !! git was not found on PATH, and it is needed to download Morkyn.
echo.
echo    Install it with:  winget install --id Git.Git -e
echo    or download from: https://git-scm.com/download/win
echo.
echo    Then close this window, open a new one, and run this file again.
goto fail

:not_a_repo
echo.
echo !! "%REPO_DIR%" exists but is not a git checkout.
echo    Move or delete it, then run this file again.
goto fail

:clone_failed
echo.
echo !! download failed. Check your internet connection and try again.
goto fail

:cd_failed
echo.
echo !! could not enter "%REPO_DIR%".
goto fail

:no_python
echo.
echo !! Python was not found on PATH.
echo.
echo    Install it with:  winget install --id Python.Python.3.12 -e
echo    or download from: https://www.python.org/downloads/
echo.
echo    Tick "Add python.exe to PATH" in the installer.
goto fail

:old_python
echo.
echo !! Morkyn needs Python 3.11 or newer.
echo    Install a newer Python, then run this file again.
goto fail

:venv_failed
echo.
echo !! could not create the Python environment in "%VENV%".
goto fail

:trim_failed
echo.
echo !! could not prepare the dependency list.
goto fail

:pip_failed
echo.
echo !! dependency install failed.
echo    Scroll up for the reason pip gave.
goto fail

:fail
echo.
pause
exit /b 1
