# One-time setup for unattended Windows publishing. Creates (or updates) the
# Task Scheduler task "LifeGather auto-publish", which runs Auto-Publish.ps1
# when you sign in and every -IntervalMinutes while you are signed in. It runs
# as you, without administrator rights, because Docker Desktop and the GitHub
# CLI sign-in belong to your Windows session. -Unregister removes the task.
#
# Use a dedicated clone with main checked out and no local edits: the publisher
# refuses a dirty or non-main checkout, so a working copy would fail each run.
[CmdletBinding()]
param(
    [ValidateRange(5, 1440)][int]$IntervalMinutes = 15,
    [switch]$Unregister,
    [string]$TaskName = 'LifeGather auto-publish'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed the scheduled task '$TaskName' (if it existed). Nothing else was changed."
    return
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$problems = @()
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { $problems += 'Install Git and put it on PATH.' }
elseif ((git -C $repoRoot branch --show-current) -ne 'main' -or (git -C $repoRoot status --porcelain)) {
    $problems += "$repoRoot must be a clean checkout of main. Use a dedicated clone for publishing."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    $problems += 'Install GitHub CLI, then run: gh auth login --hostname github.com --web --scopes write:packages'
} else {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $null = gh auth status --hostname github.com 2>&1
    $signedIn = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    if (-not $signedIn) {
        $problems += 'Sign in to GitHub CLI: gh auth login --hostname github.com --web --scopes write:packages'
    }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { $problems += 'Install Docker Desktop (Linux containers).' }
if ($problems) {
    $problems | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    throw 'Fix the problems above and run this again. No task was created.'
}

$script = Join-Path $PSScriptRoot 'Auto-Publish.ps1'
$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $repoRoot `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $user),
    (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes))
)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$null = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal `
    -Settings $settings -Force `
    -Description 'Builds, tests and publishes new LifeGather commits from GitHub main to GHCR. Never changes running containers.'

Write-Host "Scheduled '$TaskName': at sign-in and every $IntervalMinutes minutes while you are signed in."
Write-Host "Log: $(Join-Path $env:LOCALAPPDATA 'LifeGather\auto-publish\auto-publish.log')"
Write-Host "Run it now: Start-ScheduledTask -TaskName '$TaskName'. Remove it: .\scripts\Register-AutoPublish.ps1 -Unregister"
