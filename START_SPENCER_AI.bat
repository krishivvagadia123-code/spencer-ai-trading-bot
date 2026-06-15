@echo off
setlocal
cd /d "%~dp0"

set "SPENCER_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%SPENCER_PY%" set "SPENCER_PY=C:\Users\krish\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%SPENCER_PY%" set "SPENCER_PY=python"

powershell -NoProfile -Command "try { $graph=Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/brain/graph' -TimeoutSec 2; if ($graph.ok -and $null -ne $graph.nodes) { exit 0 } } catch {}; exit 1"
if errorlevel 1 (
  echo Refreshing Spencer backend with the current brain API...
  powershell -NoProfile -Command "$listeners=Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue; foreach ($listener in $listeners) { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue }"
  timeout /t 1 /nobreak >nul
  start "Spencer AI Quote Server" /min cmd /k ""%SPENCER_PY%" -u "%~dp0spencer_quote_server.py""
) else (
  echo Spencer backend and Obsidian brain API are ready.
)

cd /d "%~dp0webapp"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5180 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  start "Spencer AI Website" /min cmd /k "npm run dev"
)
timeout /t 3 >nul
start "" "http://localhost:5180"
endlocal
