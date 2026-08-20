# A backup of the department's database.
#
# This matters more here than in most deployments. The decision is that the
# data lives on a machine Sieger owns and nowhere else -- which is a perfectly
# good decision, but it means there is exactly one copy of every project,
# release, task and timesheet the department has recorded. One failed disk and
# the work is gone, with nothing to restore from.
#
# So: a dump, taken on a schedule, kept for a while, and written somewhere the
# original disk failing does not also destroy.
#
#   .\scripts\backup-db.ps1                          # dump to ..\backups
#   .\scripts\backup-db.ps1 -Destination E:\Backups  # dump to another drive
#   .\scripts\backup-db.ps1 -KeepDays 30
#
# -Destination should be a DIFFERENT physical disk from the database, or a
# network share. A backup sitting beside the thing it is backing up survives
# an accidental DROP but not a dead drive, and the dead drive is the failure
# that actually loses a department its year.

param(
    [string]$Destination,
    [int]$KeepDays = 14
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (-not $Destination) {
    $Destination = Join-Path (Split-Path (Get-Location) -Parent) 'backups'
}

$logDir = Join-Path (Get-Location) 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "{0} {1,-7} {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -Path (Join-Path $logDir 'backup.log') -Value $line -Encoding utf8
    Write-Host $line
}

# ---------------------------------------------------------------------------
# Where the database is
# ---------------------------------------------------------------------------
# Read from .env rather than taking connection details as parameters, so the
# backup can never quietly end up pointing at a different database from the
# one the application is actually using.

if (-not (Test-Path '.env')) { Write-Log 'No .env; cannot find the database.' 'FATAL'; exit 1 }

$envLine = Select-String -Path '.env' -Pattern '^\s*DATABASE_URL\s*=\s*(.+)$' |
    Select-Object -First 1
if (-not $envLine) { Write-Log 'No DATABASE_URL in .env.' 'FATAL'; exit 1 }

$url = $envLine.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
$parsed = [regex]::Match($url, '^postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)$')
if (-not $parsed.Success) {
    Write-Log "DATABASE_URL is not in the expected form; cannot parse it." 'FATAL'
    exit 1
}

$dbUser = $parsed.Groups[1].Value
$dbPass = [uri]::UnescapeDataString($parsed.Groups[2].Value)
$dbHost = $parsed.Groups[3].Value
$dbPort = $parsed.Groups[4].Value
$dbName = $parsed.Groups[5].Value

$pgDump = 'pg_dump'
if (-not (Get-Command $pgDump -ErrorAction SilentlyContinue)) {
    # The usual Windows install location, since PostgreSQL does not add itself
    # to PATH and a scheduled task gets a barer PATH than a login shell does.
    $candidate = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $candidate) { Write-Log 'pg_dump not found.' 'FATAL'; exit 1 }
    $pgDump = $candidate.FullName
}

# ---------------------------------------------------------------------------
# Take the dump
# ---------------------------------------------------------------------------

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$outFile = Join-Path $Destination "designops_$stamp.dump"

Write-Log "Dumping $dbName from ${dbHost}:${dbPort} to $outFile"

# -F c is the custom format: compressed, and restorable selectively with
# pg_restore, which plain SQL is not.
$env:PGPASSWORD = $dbPass
try {
    & $pgDump -h $dbHost -p $dbPort -U $dbUser -d $dbName -F c -f $outFile 2>&1 |
        ForEach-Object { Write-Log $_ 'PG_DUMP' }
    $code = $LASTEXITCODE
}
finally {
    # Never leave the password sitting in the environment of whatever runs next.
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

if ($code -ne 0) { Write-Log "pg_dump exited $code; backup FAILED." 'FATAL'; exit 1 }

# A pg_dump that fails partway can still leave a file behind, so the exit code
# alone is not proof. A real dump of this schema is comfortably over 20 KB;
# anything smaller means an empty or truncated database, which is worth failing
# loudly for rather than rotating good backups out in favour of it.
$size = (Get-Item $outFile).Length
if ($size -lt 20KB) {
    Write-Log ("Dump is only $size bytes, which is too small to be the real " +
               'database. Keeping it for inspection but treating this as a failure.') 'FATAL'
    exit 1
}

Write-Log ("Backup complete: {0:n1} MB" -f ($size / 1MB))

# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------
# Only ever removes files this script's own naming produced, so pointing
# -Destination at a folder that holds anything else cannot delete it.

$cutoff = (Get-Date).AddDays(-$KeepDays)
$old = Get-ChildItem $Destination -Filter 'designops_*.dump' -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff }

foreach ($file in $old) {
    Write-Log "Removing backup older than $KeepDays days: $($file.Name)"
    Remove-Item $file.FullName -Force
}

$remaining = @(Get-ChildItem $Destination -Filter 'designops_*.dump' -ErrorAction SilentlyContinue)
Write-Log "$($remaining.Count) backup(s) retained in $Destination"
