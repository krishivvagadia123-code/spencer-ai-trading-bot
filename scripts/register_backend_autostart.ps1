# Registers SpencerBackend: keeps the quote/brain/analysis backend (:8787) alive.
#
# The backend is the only non-self-healing piece of the stack - if its process
# dies (reboot, crash, closed window), the live site loses data even though
# Tailscale (a service) stays up. This task starts it at login AND restarts it
# if it stops, so Spencer recovers on its own.
#
# Operator action: run this once (same as the other register_*.ps1 scripts).

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Script = Join-Path $ProjectRoot "spencer_quote_server.py"
$TaskName = "SpencerBackend"

if (-not (Test-Path $PythonExe)) { throw "venv python not found at $PythonExe" }
if (-not (Test-Path $Script)) { throw "backend not found at $Script" }

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-u `"$Script`"" `
    -WorkingDirectory $ProjectRoot

# Start at login, and also right now when registered.
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Long-running server: no time limit; restart on failure; survive battery.
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Spencer backend (:8787) - starts at login and restarts on failure. Paper-only." `
    -Force | Out-Null

# Kick it off now too (so you don't have to log out/in).
Start-ScheduledTask -TaskName $TaskName

Write-Host "Registered + started '$TaskName'. The backend now auto-starts at login and restarts if it dies."
Write-Host "Verify: curl http://127.0.0.1:8787/api/health  (expect 200)"
