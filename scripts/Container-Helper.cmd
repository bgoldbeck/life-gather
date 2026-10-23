@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Container-Helper.ps1" %*
set "result=%ERRORLEVEL%"
if not "%result%"=="0" (
    echo Helper failed. Read the error above.
    pause
)
exit /b %result%
