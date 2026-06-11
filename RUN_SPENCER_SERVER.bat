@echo off
cd /d "%~dp0"
set "PY=C:\Users\krish\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PY%" (
  "%PY%" -u spencer_quote_server.py >> spencer_server.log 2>&1
) else (
  python -u spencer_quote_server.py >> spencer_server.log 2>&1
)
