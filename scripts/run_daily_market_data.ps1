$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SnapshotScript = Join-Path $ProjectRoot "scripts\daily_price_snapshot.py"
$IntradayScript = Join-Path $ProjectRoot "scripts\intraday_history.py"
$AuditScript = Join-Path $ProjectRoot "scripts\audit_data_integrity.py"
$AuditLogScript = Join-Path $ProjectRoot "scripts\append_daily_audit.py"
$AuditLog = Join-Path $ProjectRoot "workflow\logs\daily_audit.log"
$BrainScript = Join-Path $ProjectRoot "scripts\export_brain.py"

Set-Location $ProjectRoot

& $PythonExe $SnapshotScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $PythonExe $IntradayScript
$CollectionExitCode = $LASTEXITCODE
if ($CollectionExitCode -ne 0) {
    exit $CollectionExitCode
}

$AuditJson = & $PythonExe $AuditScript --json
$AuditExitCode = $LASTEXITCODE
$AuditJson | & $PythonExe $AuditLogScript --log $AuditLog --audit-exit-code $AuditExitCode

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Data-integrity audit result could not be appended to $AuditLog"
}

# Refresh the Obsidian primary brain from the latest state (read-only over the DB;
# best-effort — a brain-export hiccup never fails the data job).
& $PythonExe $BrainScript
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Brain export did not complete cleanly."
}

# Integrity failures are reported as ALERT lines but do not turn a successful
# snapshot/collection run into a failed scheduled job.
exit 0
