$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SnapshotScript = Join-Path $ProjectRoot "scripts\daily_price_snapshot.py"
$IntradayScript = Join-Path $ProjectRoot "scripts\intraday_history.py"
$RunnerScript = Join-Path $ProjectRoot "scripts\run_daily_market_data.ps1"
$TaskName = "SpencerDailySnapshot"

if (-not (Test-Path $PythonExe)) {
    throw "Project venv python not found at $PythonExe"
}

if (-not (Test-Path $SnapshotScript)) {
    throw "Snapshot script not found at $SnapshotScript"
}

if (-not (Test-Path $IntradayScript)) {
    throw "Intraday history script not found at $IntradayScript"
}

if (-not (Test-Path $RunnerScript)) {
    throw "Daily market data runner not found at $RunnerScript"
}

# Register via the ScheduledTasks cmdlets, not schtasks.exe: the project path
# contains a space ("AI TRADE") and schtasks /TR quoting mangles it.
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerScript`"" `
    -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "18:00"
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Description "Spencer daily market data: EOD snapshot + intraday history (paper-only research)." `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' for 18:00 local time (IST on this host)."
Write-Host "Action: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$RunnerScript`""
Write-Host "Runner executes: $PythonExe $SnapshotScript, then $PythonExe $IntradayScript"
