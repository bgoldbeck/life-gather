@echo off
if "%~1"=="" goto menu
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Publish-Container.ps1" %*
goto result
:menu
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Container-Helper.ps1"
:result
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" (
    echo Release failed. Read the error and failed stage above.
    pause
)
exit /b %result%
