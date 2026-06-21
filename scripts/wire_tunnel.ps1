# Bring up the Cloudflare quick tunnel AND auto-wire the live site to it.
#
# Quick-tunnel URLs are ephemeral - they change on every restart/reboot, which
# breaks the live Vercel site until webapp/public/spencer-config.json is updated
# and pushed. Worse, a quick tunnel sometimes hands out a URL whose DNS never
# provisions. So this script: (re)starts the tunnel, and only AFTER the new URL
# is actually reachable does it update spencer-config.json + commit + push. If a
# URL never comes alive, it re-rolls a fresh tunnel (up to 3 attempts).
#
# Run this once after a reboot or whenever the live site loses its data.
# (The permanent fix is a NAMED tunnel - needs a Cloudflare domain + login.)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log = Join-Path $root "cloudflared.log.err"
$config = Join-Path $root "webapp\public\spencer-config.json"

if (-not (Test-Path $cf)) { throw "cloudflared not found at $cf (install: winget install Cloudflare.cloudflared)" }

if (-not (Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Warning "Backend :8787 is not running. Start it (RUN_SPENCER_SERVER.bat) first, then re-run this."
}

$workingUrl = $null
for ($attempt = 1; $attempt -le 3 -and -not $workingUrl; $attempt++) {
    Write-Host "Tunnel attempt $attempt..."
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
    Remove-Item $log -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $cf -ArgumentList "tunnel","--url","http://localhost:8787" `
        -WindowStyle Hidden -RedirectStandardOutput "$($root)\cloudflared.out" -RedirectStandardError $log

    # Detect the URL from cloudflared's stderr log.
    $url = $null
    for ($i = 0; $i -lt 15 -and -not $url; $i++) {
        Start-Sleep 2
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue
            if ($m) { $url = $m.Matches[-1].Value }
        }
    }
    if (-not $url) { Write-Host "  no URL yet; re-rolling."; continue }
    Write-Host "  got $url - waiting for it to become reachable..."

    # Poll until the URL is actually reachable (DNS provisioned), up to ~60s.
    for ($j = 0; $j -lt 20; $j++) {
        Start-Sleep 3
        try {
            $h = Invoke-WebRequest "$url/api/health" -TimeoutSec 5 -UseBasicParsing
            if ($h.StatusCode -eq 200) { $workingUrl = $url; break }
        } catch {}
    }
    if ($workingUrl) { Write-Host "  reachable: $workingUrl" }
    else { Write-Host "  $url never resolved; re-rolling." }
}

if (-not $workingUrl) { throw "Could not get a working tunnel after 3 attempts. Try again, or set up a named tunnel." }

# Update spencer-config.json only if the URL changed, then commit + push.
$current = ""
if (Test-Path $config) { try { $current = (Get-Content $config -Raw | ConvertFrom-Json).apiBase } catch {} }
if ($current -eq $workingUrl) {
    Write-Host "spencer-config.json already points here - nothing to push."
} else {
    ([ordered]@{ apiBase = $workingUrl } | ConvertTo-Json) | Set-Content -Path $config -Encoding utf8
    Set-Location $root
    git add "webapp/public/spencer-config.json"
    git commit -m "Re-point live site to current tunnel URL" | Out-Null
    git push origin main
    Write-Host "Pushed. Vercel redeploys in ~15s; live site reconnects automatically."
}
Write-Host "DONE - working tunnel: $workingUrl . Keep the tunnel window open."
