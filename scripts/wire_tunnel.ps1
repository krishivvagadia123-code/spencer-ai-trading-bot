# Bring up the Cloudflare quick tunnel AND auto-wire the live site to it.
#
# Quick-tunnel URLs are ephemeral — they change on every restart/reboot, which
# breaks the live Vercel site until webapp/public/spencer-config.json is updated
# and pushed. This script does that whole dance in one shot:
#   1. (re)start cloudflared against the local backend (:8787)
#   2. detect the new https://<...>.trycloudflare.com URL
#   3. if it changed, update spencer-config.json, commit, and push (Vercel redeploys)
#   4. verify the tunnel actually reaches the backend
#
# Run this once after a reboot or whenever the live site loses its data.
# (The permanent fix is a NAMED tunnel — needs a Cloudflare domain + login.)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log = Join-Path $root "cloudflared.log"
$config = Join-Path $root "webapp\public\spencer-config.json"

if (-not (Test-Path $cf)) { throw "cloudflared not found at $cf (install: winget install Cloudflare.cloudflared)" }

# Warn if the backend isn't up — the tunnel would point at nothing.
if (-not (Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Warning "Backend :8787 is not running. Start it (RUN_SPENCER_SERVER.bat) first, then re-run this."
}

# Restart cloudflared fresh.
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 1
if (Test-Path $log) { Remove-Item $log -Force -ErrorAction SilentlyContinue }
Start-Process -FilePath $cf -ArgumentList "tunnel","--url","http://localhost:8787" `
    -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError "$log.err"

# Detect the URL (up to ~40s).
$url = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep 2
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue
        if ($m) { $url = $m.Matches[-1].Value; break }
    }
    $e = "$log.err"
    if (Test-Path $e) {
        $m2 = Select-String -Path $e -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue
        if ($m2) { $url = $m2.Matches[-1].Value; break }
    }
}
if (-not $url) { throw "Could not detect tunnel URL after 40s. Check $log" }
Write-Host "Tunnel URL: $url"

# Verify it reaches the backend.
try {
    $h = Invoke-WebRequest "$url/api/health" -TimeoutSec 8 -UseBasicParsing
    Write-Host "Backend reachable through tunnel: HTTP $($h.StatusCode)"
} catch {
    Write-Warning "Tunnel up but backend not reachable yet: $($_.Exception.Message)"
}

# Update spencer-config.json only if the URL changed.
$current = ""
if (Test-Path $config) { try { $current = (Get-Content $config -Raw | ConvertFrom-Json).apiBase } catch {} }
if ($current -eq $url) {
    Write-Host "spencer-config.json already points here — nothing to push."
} else {
    "{`n  `"apiBase`": `"$url`"`n}`n" | Set-Content -Path $config -Encoding utf8 -NoNewline
    Set-Location $root
    git add "webapp/public/spencer-config.json"
    git commit -m "Re-point live site to current tunnel URL" | Out-Null
    git push origin main
    Write-Host "Pushed. Vercel will redeploy in ~15s; live site reconnects automatically."
}
Write-Host "Done. Keep this window's tunnel process alive for the live site to stay connected."
