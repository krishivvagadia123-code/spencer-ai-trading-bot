@echo off
title Spencer (editable app, port 5180)
color 0B
echo ==========================================
echo   SPENCER - EDITABLE LOCAL APP (port 5180)
echo ==========================================
echo.
echo Live data comes from your backend on 127.0.0.1:8787
echo (start that first via Run_Spencer_2026.bat if needed).
echo.
echo Opening http://localhost:5180/ ...
echo (Your other app on http://localhost:5175/ is untouched.)
echo.
cd /d "%~dp0"
start http://localhost:5180/
npm run dev
pause
