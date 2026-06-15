# Registers SpencerIntradayCollect: runs the intraday candle collector every 30
# minutes during NSE market hours (09:30-15:30 IST, Mon-Fri) so the 15m session
# data updates live through the day instead of only at the 18:00 batch.
#
# The collector is idempotent and only stores final, boundary-aligned candles,
# so extra runs are harmless. Operator action: run this once.

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Script = Join-Path $ProjectRoot "scripts\intraday_history.py"
$TaskName = "SpencerIntradayCollect"

if (-not (Test-Path $PythonExe)) { throw "venv python not found at $PythonExe" }
if (-not (Test-Path $Script)) { throw "intraday collector not found at $Script" }

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$Script`"" `
    -WorkingDirectory $ProjectRoot

# Fire at 09:30, then repeat every 30 min for 6 hours (through ~15:30), weekdays.
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "09:30"
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "09:30" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 6)).Repetition

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Description "Spencer intraday 15m collector - every 30 min during market hours (paper-only research)." `
    -Force | Out-Null

Write-Host "Registered '$TaskName': every 30 min, 09:30-15:30 IST, Mon-Fri."
Write-Host "The 15m session count now updates live during the trading day."
