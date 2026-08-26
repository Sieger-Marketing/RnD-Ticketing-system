# The portal, supervised.
#
# This is what the startup task runs. It is deliberately NOT serve.ps1:
# serve.ps1 is the interactive script a person runs and watches, so it may
# stop and ask for something, and it builds the frontend with npm if the
# build is missing. Neither is safe at boot, under SYSTEM, with nobody
# looking -- npm is usually not on SYSTEM's PATH, and a script that blocks
# on a prompt at startup is a portal that never comes up.
#
# So this one does three things and nothing else: bring the schema up to
# date, serve, and if the server ever exits, start it again.
#
#   .\scripts\run-service.ps1              # normal
#   .\scripts\run-service.ps1 -Port 8080

param(
    [int]$Port = 8000,
    [string]$ListenAddress = '127.0.0.1'
)

Set-Location (Join-Path $PSScriptRoot '..')

$logDir = Join-Path (Get-Location) 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "{0} {1,-7} {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    $file = Join-Path $logDir ("service-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
    Add-Content -Path $file -Value $line -Encoding utf8
    Write-Host $line
}

Write-Log "Starting Design Operations API on ${ListenAddress}:${Port}"

$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Log "No virtualenv at $python. Create it with: python -m venv .venv" 'FATAL'
    exit 1
}
if (-not (Test-Path '.env')) {
    Write-Log "No .env in $(Get-Location). The API cannot start without DATABASE_URL." 'FATAL'
    exit 1
}

# Schema first. The app assumes the tables its models describe, and starting
# against an older database fails later, deeper and less legibly. A failure
# here is fatal on purpose: serving a half-migrated database would hand people
# 500s that look like application bugs.
Write-Log 'Applying migrations'
& $python -m alembic upgrade head 2>&1 | ForEach-Object { Write-Log $_ 'ALEMBIC' }
if ($LASTEXITCODE -ne 0) {
    Write-Log 'Migrations failed; not starting. Fix the database, then restart the task.' 'FATAL'
    exit 1
}

# Then the rows the schema implies: permissions, role bundles, default settings.
# Migrations move the schema and leave these behind, so a permission added to a
# role bundle in Python was never actually granted, and a new default setting
# never appeared on the settings screen -- while the code kept working, because
# it falls back to the default. Additive and idempotent; a no-op on the runs
# where nothing changed. Non-fatal on purpose: a stale role bundle is worth a
# warning, not a department without a portal.
Write-Log 'Applying bootstrap (permissions, roles, settings)'
& $python (Join-Path $PSScriptRoot 'bootstrap_db.py') 2>&1 | ForEach-Object { Write-Log $_ 'BOOTSTRAP' }
if ($LASTEXITCODE -ne 0) {
    Write-Log 'Bootstrap failed; starting anyway. Roles or settings may be stale.' 'WARN'
}

# The supervision loop.
#
# A crash at 03:00 must not mean the department finds the portal down at 09:00,
# so the server is simply started again. The backoff exists to tell two
# situations apart: a process that died once, and one that cannot start at all
# (a port already taken, a database that has gone away). Restarting the second
# kind in a tight loop writes a gigabyte of log and fixes nothing, so repeated
# fast failures back off and eventually stop, leaving the reason at the end of
# the log where somebody can read it.
$consecutiveFast = 0
$maxConsecutiveFast = 5

while ($true) {
    $startedAt = Get-Date
    & $python -m uvicorn app.main:app --host $ListenAddress --port $Port 2>&1 |
        ForEach-Object { Write-Log $_ 'UVICORN' }

    $ranFor = (Get-Date) - $startedAt
    Write-Log ("Server exited after {0:n0}s (exit code {1})" -f $ranFor.TotalSeconds, $LASTEXITCODE) 'WARN'

    if ($ranFor.TotalSeconds -lt 30) {
        $consecutiveFast++
        if ($consecutiveFast -ge $maxConsecutiveFast) {
            Write-Log ("Exited within 30s on $maxConsecutiveFast consecutive attempts. " +
                       'Something is wrong that restarting will not fix -- check the ' +
                       'UVICORN lines above. Giving up so the cause stays readable.') 'FATAL'
            exit 1
        }
        $delay = [Math]::Min(60, [Math]::Pow(2, $consecutiveFast))
        Write-Log "Restarting in ${delay}s (fast-failure $consecutiveFast/$maxConsecutiveFast)" 'WARN'
        Start-Sleep -Seconds $delay
    }
    else {
        # It ran for a while, so this is a crash rather than a broken
        # configuration. Come straight back up.
        $consecutiveFast = 0
        Write-Log 'Restarting' 'WARN'
        Start-Sleep -Seconds 2
    }
}
