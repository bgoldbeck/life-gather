@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Register-AutoPublish.ps1" %*
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" echo Automatic publishing was not set up. Read the error above.
pause
exit /b %result%
