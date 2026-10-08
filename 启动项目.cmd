@echo off
setlocal
pushd "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-enterprise.ps1" %*
set "taskExit=%errorlevel%"
if not "%taskExit%"=="0" echo Project startup failed. See the error above and .runtime\enterprise logs.
pause
popd
exit /b %taskExit%
