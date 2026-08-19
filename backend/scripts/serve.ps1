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

$listen = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
if ($Lan) {
    Write-Host 'Listening on the local network as well as localhost.' -ForegroundColor Yellow
}

Write-Host "API on http://${listen}:${Port}  (health: /health, readiness: /health/db)"
& $python -m uvicorn app.main:app --host $listen --port $Port
