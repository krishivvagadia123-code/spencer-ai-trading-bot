# Registers SpencerDryRun: once per weekday after the NSE close, replays the
# active candidate over the latest collected session through the live paper
# engine (mode=dry-run). This is what makes the backend actually EXERCISE the
# engine unattended — every trading day produces a journaled live_paper run you
# can inspect, instead of the engine only ever running when invoked by hand.
#
# Paper-only and safe: dry-run requires no WALK_FORWARD PASS, never places a
# broker order, and writes only to the isolated live_paper_* tables. With a
# killed candidate it will simply journal 0 trades (the entry rule never fires) —
# that is the honest, expected outcome until a candidate graduates the ladder.
#
# Operator action: run this once (same as register_intraday_collector.ps1).

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Script = Join-Path $ProjectRoot "scripts\run_live_paper.py"
$Candidate = "candidates\SPNCR-002.json"
$TaskName = "SpencerDryRun"

if (-not (Test-Path $PythonExe)) { throw "venv python not found at $PythonExe" }
if (-not (Test-Path $Script)) { throw "live paper runner not found at $Script" }

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$Script`" --candidate $Candidate --mode dry-run" `
    -WorkingDirectory $ProjectRoot

# 16:00 local, after the 15:30 IST close, every weekday.
$Trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "16:00"

# Same battery-resilient settings as the collector.
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Spencer daily engine dry-run on the latest collected session (paper-only, journals to live_paper_* tables)." `
    -Force | Out-Null

Write-Host "Registered '$TaskName': weekdays 16:00, dry-run on the latest session."
Write-Host "Inspect results with: python scripts/run_live_paper.py --candidate $Candidate --mode dry-run"
