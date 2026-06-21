@echo off
rem One-click: bring up the Cloudflare tunnel and re-point the live site to it.
rem Run this after a reboot, or whenever the live site stops showing data.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\wire_tunnel.ps1"
echo.
echo Leave this window open - closing it drops the tunnel and the live site loses data.
pause
