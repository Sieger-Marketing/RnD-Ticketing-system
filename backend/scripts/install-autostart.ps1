# Make the portal outlive the person who started it.
#
# Run once, elevated, on whichever machine holds the database.
#
#   .\scripts\install-autostart.ps1
#   .\scripts\install-autostart.ps1 -BackupTo E:\Backups
#   .\scripts\install-autostart.ps1 -Uninstall
#
# What it changes, and why each one is needed:
#
#   1. A startup task for the API.       Without it the portal exists only for
#                                        as long as somebody keeps a terminal
#                                        window open, and a reboot leaves the
#                                        database up, the tunnel up, and the
#                                        portal down.
#   2. A nightly database backup.        The data is on this machine and
#                                        nowhere else.
#   3. Sleep and lid-close disabled.     A sleeping machine serves nothing.
#
# The tasks run as SYSTEM. That is deliberate: SYSTEM needs no stored password,
# so setting this up never involves writing anybody's credentials into Task
# Scheduler, and it survives the user logging off. The database is reached with
# the password already in backend\.env, so SYSTEM has the access it needs
# without being granted anything new.

param(
    [string]$BackupTo,
    [string]$BackupAt = '20:00',
    [string]$SweepAt  = '06:30',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$API_TASK    = 'DesignOps API'
$BACKUP_TASK = 'DesignOps Database Backup'
$SWEEP_TASK  = 'DesignOps Nightly Refresh'

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ''
    Write-Host '  This script has to run as Administrator.' -ForegroundColor Red
    Write-Host '  Registering a startup task and changing power settings both require it.'
    Write-Host ''
    Write-Host '  Open PowerShell with "Run as administrator", then:' -ForegroundColor Yellow
    Write-Host "    cd $(Get-Location)"
    Write-Host '    .\scripts\install-autostart.ps1'
    Write-Host ''
    exit 1
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

if ($Uninstall) {
    foreach ($name in @($API_TASK, $BACKUP_TASK)) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "Removed scheduled task: $name" -ForegroundColor Green
        }
        else {
            Write-Host "Not present: $name"
        }
    }
    Write-Host ''
    Write-Host 'Power settings left as they are -- change them back with:' -ForegroundColor Yellow
    Write-Host '  powercfg /change standby-timeout-ac 30'
    Write-Host ''
    Write-Host 'The API is no longer started at boot. Nothing is serving until you' -ForegroundColor Yellow
    Write-Host 'run .\scripts\serve.ps1 yourself.'
    exit 0
}

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------
# Checked before anything is registered, so a missing piece is one message now
# rather than a task that fails silently at every boot.

$backendDir = (Get-Location).Path
$runService = Join-Path $backendDir 'scripts\run-service.ps1'
$backupScript = Join-Path $backendDir 'scripts\backup-db.ps1'

foreach ($required in @($runService, $backupScript, (Join-Path $backendDir '.env'),
                        (Join-Path $backendDir '.venv\Scripts\python.exe'))) {
    if (-not (Test-Path $required)) {
        Write-Host "Missing: $required" -ForegroundColor Red
        exit 1
    }
}

if (-not $BackupTo) {
    $BackupTo = Join-Path (Split-Path $backendDir -Parent) 'backups'
    Write-Host ''
    Write-Host '  Backups will go to a folder on this same machine:' -ForegroundColor Yellow
    Write-Host "    $BackupTo"
    Write-Host '  That protects against a mistaken delete, but NOT against this disk' -ForegroundColor Yellow
    Write-Host '  failing -- which is the failure that loses the department its year.'
    Write-Host '  Re-run with -BackupTo pointed at another drive or a network share.'
    Write-Host ''
}

# ---------------------------------------------------------------------------
# 1. The API, at boot
# ---------------------------------------------------------------------------

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$runService`"" `
    -WorkingDirectory $backendDir

$trigger = New-ScheduledTaskTrigger -AtStartup

# ExecutionTimeLimit 0 means "never kill it" -- the default is three days, and
# a portal that stops on the third day of a quiet week is a strange bug to
# have to find. RestartCount covers the case where the whole task dies rather
# than just the server inside it, which run-service.ps1 already handles.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

if (Get-ScheduledTask -TaskName $API_TASK -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $API_TASK -Confirm:$false
}
Register-ScheduledTask -TaskName $API_TASK -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description 'Serves the Design Operations portal. Starts at boot, restarts on failure.' | Out-Null

Write-Host "Registered: $API_TASK (at startup, as SYSTEM)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. The nightly backup
# ---------------------------------------------------------------------------

$backupAction = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ("-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$backupScript`" " +
               "-Destination `"$BackupTo`"") `
    -WorkingDirectory $backendDir

# StartWhenAvailable matters: a machine that was off at 20:00 should take the
# backup when it next comes up, not skip the day entirely.
$backupSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

if (Get-ScheduledTask -TaskName $BACKUP_TASK -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $BACKUP_TASK -Confirm:$false
}
Register-ScheduledTask -TaskName $BACKUP_TASK -Action $backupAction `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $BackupAt) `
    -Settings $backupSettings -Principal $principal `
    -Description "Nightly pg_dump of the design operations database to $BackupTo." | Out-Null

Write-Host "Registered: $BACKUP_TASK (daily at $BackupAt, to $BackupTo)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. The nightly re-rating
# ---------------------------------------------------------------------------
# Delay days and RAG colours are computed against today but stored on the row,
# so lists can filter and sort on them. Nothing about a release changes when it
# slips past its date overnight -- so nothing re-rates it, and it keeps showing
# yesterday's colour. Runs before the working day rather than after it, so the
# first person in sees today's picture.

$sweepScript = Join-Path $backendDir 'scripts\nightly_refresh.py'
$pythonExe   = Join-Path $backendDir '.venv\Scripts\python.exe'

$sweepAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "`"$sweepScript`"" `
    -WorkingDirectory $backendDir

$sweepSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

if (Get-ScheduledTask -TaskName $SWEEP_TASK -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $SWEEP_TASK -Confirm:$false
}
Register-ScheduledTask -TaskName $SWEEP_TASK -Action $sweepAction `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $SweepAt) `
    -Settings $sweepSettings -Principal $principal `
    -Description "Re-rate delay days and RAG health against today's date." | Out-Null

Write-Host "Registered: $SWEEP_TASK (daily at $SweepAt)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Stop the machine sleeping
# ---------------------------------------------------------------------------
# On AC only. Left alone on battery, because a laptop on battery that refuses
# to sleep flattens itself and is then off for longer than it would have been.

powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 15

# Lid close: "do nothing" on AC. This is the one that catches people out --
# every other setting can be right and closing the lid still takes the portal
# down mid-afternoon.
$SUB_BUTTONS = '4f971e89-eebd-4455-a8de-9e59040e7347'
$LID_ACTION  = '5ca83367-6e45-459f-a27b-476b1d01c936'
powercfg /setacvalueindex SCHEME_CURRENT $SUB_BUTTONS $LID_ACTION 0
powercfg /setactive SCHEME_CURRENT

Write-Host 'Power: sleep and hibernate disabled on AC, lid-close does nothing on AC.' -ForegroundColor Green

# ---------------------------------------------------------------------------

Write-Host ''
Write-Host 'Done. Start it now without rebooting:' -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName '$API_TASK'"
Write-Host ''
Write-Host 'Then check it came up:' -ForegroundColor Cyan
Write-Host '  curl http://127.0.0.1:8000/health/db'
Write-Host ''
Write-Host 'Prove the backup works before trusting it:' -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName '$BACKUP_TASK'"
Write-Host "  Get-Content .\logs\backup.log -Tail 20"
Write-Host ''
Write-Host 'Logs: backend\logs\service-<date>.log and backend\logs\backup.log'
