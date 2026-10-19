@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Test-Login.ps1"
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" (
    echo Preview startup failed. Read the error above.
    pause
)
exit /b %result%
