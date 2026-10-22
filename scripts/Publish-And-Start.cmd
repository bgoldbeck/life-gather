@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Publish-And-Start.ps1"
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" (
    echo Publish and start failed. Read the error and failed stage above.
    pause
)
exit /b %result%
