@echo off
cd /d "%~dp0"
rem Prefer the project venv (has the deps); fall back to the codex runtime, then PATH python.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\krish\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -u spencer_quote_server.py >> spencer_server.log 2>&1
