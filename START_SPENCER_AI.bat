@echo off
setlocal
cd /d "%~dp0"

set "SPENCER_PY=C:\Users\krish\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%SPENCER_PY%" set "SPENCER_PY=python"

start "Spencer AI Quote Server" /min cmd /k ""%SPENCER_PY%" "%~dp0spencer_quote_server.py""
cd /d "%~dp0frontend"
start "Spencer AI Website" /min cmd /k "npm run dev"
timeout /t 3 >nul
start "" "http://localhost:5175"
endlocal
