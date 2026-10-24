@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Home-Network.ps1"
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" (
    echo Home network setup failed. Read the error above.
    pause
)
exit /b %result%
