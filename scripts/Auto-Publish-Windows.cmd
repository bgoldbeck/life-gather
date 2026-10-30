@echo off
rem Double-click: set up (or repair) automatic publishing and start a first run.
rem   Auto-Publish-Windows.cmd status   show whether it is on and the latest log
rem   Auto-Publish-Windows.cmd off      turn it off
set "option="
if /i "%~1"=="status" set "option=-Status"
if /i "%~1"=="off" set "option=-Unregister"
if not "%~1"=="" if not defined option (
    echo Usage: %~nx0 [status^|off]
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Register-AutoPublish.ps1" %option%
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" echo Automatic publishing was not changed. Read the error above.
pause
exit /b %result%
