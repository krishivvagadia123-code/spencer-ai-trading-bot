$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SnapshotScript = Join-Path $ProjectRoot "scripts\daily_price_snapshot.py"
$TaskName = "SpencerDailySnapshot"

if (-not (Test-Path $PythonExe)) {
    throw "Project venv python not found at $PythonExe"
}

if (-not (Test-Path $SnapshotScript)) {
    throw "Snapshot script not found at $SnapshotScript"
}

$TaskRun = "`"$PythonExe`" `"$SnapshotScript`""
schtasks.exe /Create `
    /TN $TaskName `
    /SC DAILY `
    /ST 18:00 `
    /TR $TaskRun `
    /F | Out-Null

Write-Host "Registered scheduled task '$TaskName' for 18:00 local time (IST on this host)."
Write-Host "Action: $PythonExe $SnapshotScript"
