# Run the API as production, on the machine that holds the database.
#
# Bound to 127.0.0.1 on purpose. The database and the API are on the same
# machine, and the only thing that should reach the API from outside is the
# Tailscale Funnel in front of it -- which connects locally. Binding to
# 0.0.0.0 would additionally publish the API to every device on the office
# Wi-Fi, which is not something to switch on by accident.
#
#   .\scripts\serve.ps1            # normal run
#   .\scripts\serve.ps1 -Port 8080 # somewhere else
#   .\scripts\serve.ps1 -Lan       # also answer on the local network

param(
    [int]$Port = 8000,
    [switch]$Lan
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (-not (Test-Path '.env')) {
    Write-Error "No .env in $(Get-Location). Copy .env.example and set DATABASE_URL first."
}

$python = '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Error "No virtualenv at $python. Create it with: python -m venv .venv"
}

# Schema first. The app assumes the tables its models describe; starting
# against an older database fails later, deeper, and less legibly.
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Error 'Migrations failed; not starting.' }

# The API serves the built app, so a missing build means an API-only server
# and a confusing 404 at the root.
$dist = Join-Path (Split-Path (Get-Location) -Parent) 'frontend\dist\index.html'
if (-not (Test-Path $dist)) {
    Write-Host 'No built frontend found; building it now.' -ForegroundColor Yellow
    Push-Location (Join-Path (Split-Path (Get-Location) -Parent) 'frontend')
    npm install
    npm run build
    Pop-Location
}

$listen = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
if ($Lan) {
    Write-Host 'Listening on the local network as well as localhost.' -ForegroundColor Yellow
}

Write-Host "Serving on http://${listen}:${Port}  (health: /health, readiness: /health/db)"
# Report where this machine is actually reachable, rather than a hardcoded
# address. A baked-in tunnel name printed on a second machine is worse than no
# message at all: during a migration it tells you the wrong box is serving.
if ($Lan) {
    $lanIp = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
        Select-Object -First 1).IPAddress
    if ($lanIp) { Write-Host "The office reaches it at http://${lanIp}:${Port}" }
}
# Guarded twice over: this script runs with ErrorActionPreference = Stop, so on
# a machine with no tailscale on PATH an unguarded call is a terminating error
# and the portal never starts -- a startup message taking down the server it
# was describing.
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    try {
        $funnel = & tailscale funnel status 2>$null |
            Select-String -Pattern 'https://\S+\.ts\.net' | Select-Object -First 1
        if ($funnel) {
            Write-Host "Published at $($funnel.Matches[0].Value) while the Tailscale Funnel is on."
        }
    } catch { }
}
& $python -m uvicorn app.main:app --host $listen --port $Port
