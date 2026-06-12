$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SnapshotScript = Join-Path $ProjectRoot "scripts\daily_price_snapshot.py"
$IntradayScript = Join-Path $ProjectRoot "scripts\intraday_history.py"

Set-Location $ProjectRoot

& $PythonExe $SnapshotScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $PythonExe $IntradayScript
exit $LASTEXITCODE
