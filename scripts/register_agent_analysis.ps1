# Registers SpencerAgentAnalysis: once per weekday after the close, runs the
# local (Ollama) market analyst on RELIANCE and writes workflow/analysis_latest.json,
# which the backend serves at GET /api/analysis and the dashboard's "AI Research
# View" panel displays. This is what makes the live site's AI opinion refresh daily.
#
# RESEARCH ONLY. The producer never trades and never touches the deployment gate;
# it writes a research opinion the UI labels as "not a trade, not a signal".
# Requires Ollama running locally (the model is qwen2.5:7b-instruct).
#
# The producer lives in the separate research-tools venv (it imports TradingAgents),
# but writes its JSON into THIS repo's workflow/ folder.
#
# Operator action: run this once (same as the other register_*.ps1 scripts).

$ErrorActionPreference = "Stop"

$AgentDir   = "C:\Users\krish\research-tools\TradingAgents"
$AgentPy    = "C:\Users\krish\research-tools\tradingagents-env\Scripts\python.exe"
$AgentScript = Join-Path $AgentDir "spencer_agent_analysis.py"
$TaskName   = "SpencerAgentAnalysis"

if (-not (Test-Path $AgentPy))     { throw "research venv python not found at $AgentPy" }
if (-not (Test-Path $AgentScript)) { throw "agent producer not found at $AgentScript" }

# Keep the Ollama model warm so the multi-step run doesn't reload it each call.
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c set OLLAMA_KEEP_ALIVE=30m&& set PYTHONIOENCODING=utf-8&& `"$AgentPy`" `"$AgentScript`"" `
    -WorkingDirectory $AgentDir

# 16:30 local, after the 15:30 IST close and after the collector/dry-run tasks.
$Trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "16:30"

# Same battery-resilient settings as the other Spencer tasks.
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Spencer daily AI research view (Ollama market analyst -> workflow/analysis_latest.json -> /api/analysis). Paper-only, research opinion." `
    -Force | Out-Null

Write-Host "Registered '$TaskName': weekdays 16:30, writes workflow/analysis_latest.json."
Write-Host "The dashboard 'AI Research View' will refresh each trading day (Ollama must be running)."
