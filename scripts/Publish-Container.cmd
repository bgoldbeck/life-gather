@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Publish-Container.ps1" -Publish -PublishLatest
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" echo Release failed. Read the error and failed stage above.
pause
exit /b %result%
