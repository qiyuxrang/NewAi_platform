@echo off
setlocal
pushd "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-enterprise.ps1" %*
set "taskExit=%errorlevel%"
if not "%taskExit%"=="0" echo Project stop failed. See the error above. Existing data is retained.
pause
popd
exit /b %taskExit%
