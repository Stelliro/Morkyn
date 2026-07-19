@echo off
REM Compatibility shim — use Morkyn.bat
cd /d "%~dp0"
call "%~dp0Morkyn.bat" %*
exit /b %ERRORLEVEL%
