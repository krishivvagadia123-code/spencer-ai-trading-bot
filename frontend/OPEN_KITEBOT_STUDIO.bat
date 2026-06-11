@echo off
REM Opens the new React/Vite Spencer AI UI.
set FRONTEND_DIR=C:\Users\krish\OneDrive\Desktop\AI TRADE\frontend
cd /d "%FRONTEND_DIR%"

if not exist "node_modules" (
    echo Installing website packages...
    npm.cmd install --cache .\.npm-cache
)

echo Starting Spencer AI at http://127.0.0.1:5173/
start "Spencer AI Server" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm.cmd run dev -- --host 127.0.0.1 --port 5173"
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:5173/"
