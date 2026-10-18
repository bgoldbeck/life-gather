@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Test-Login.ps1"
set "result=%ERRORLEVEL%"
echo.
pause
exit /b %result%
