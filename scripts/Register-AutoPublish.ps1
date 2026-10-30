# Setup for unattended Windows publishing; Auto-Publish-Windows.cmd runs this.
# It makes everything ready, then creates (or updates) the Task Scheduler task
# "LifeGather auto-publish", which runs Auto-Publish.ps1 when you sign in and
# every -IntervalMinutes while you are signed in:
#
# 1. Clones GitHub main into a folder used only for publishing (-SourceDirectory),
#    so your own working copy and its edits are never involved.
# 2. Signs GitHub CLI in with the write:packages scope if needed (browser).
# 3. Checks Docker Desktop, registers the task and starts a first run.
#
# The task runs as you, without administrator rights, because Docker Desktop
# and the GitHub CLI sign-in belong to your Windows session.
# -Status shows the task and recent log lines; -Unregister removes the task.
[CmdletBinding()]
param(
    [ValidateRange(5, 1440)][int]$IntervalMinutes = 15,
    [switch]$Unregister,
    [switch]$Status,
    [string]$SourceDirectory = (Join-Path $env:LOCALAPPDATA 'LifeGather\publish-source'),
    [string]$TaskName = 'LifeGather auto-publish'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$sourceUrl = 'https://github.com/bgoldbeck/life-gather.git'
$logFile = Join-Path $env:LOCALAPPDATA 'LifeGather\auto-publish\auto-publish.log'

function Invoke-Native([string]$Executable, [string[]]$Arguments) {
    # Native stderr must not become a terminating error under 'Stop'.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Executable @Arguments 2>&1
        return [pscustomobject]@{ Ok = ($LASTEXITCODE -eq 0); Output = (@($output) -join "`n") }
    } finally { $ErrorActionPreference = $previous }
}
function Test-PackageScope {
    # Same check as the publisher: the token must carry write:packages.
    $identity = Invoke-Native 'gh' @('api', '--include', '--hostname', 'github.com', 'user', '--jq', '.login')
    $header = [regex]::Match($identity.Output, '(?im)^x-oauth-scopes:[ \t]*([^\r\n]*)')
    return $identity.Ok -and $header.Success -and
        (@($header.Groups[1].Value -split ',' | ForEach-Object { $_.Trim() }) -contains 'write:packages')
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Automatic publishing is off: removed the task '$TaskName'."
    Write-Host "The publishing folder $SourceDirectory was kept; delete it if you no longer need it."
    return
}
if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Host 'Automatic publishing is off (no scheduled task).'; return }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Automatic publishing is on. Last run: $($info.LastRunTime) (result $($info.LastTaskResult)). Next run: $($info.NextRunTime)."
    if (Test-Path -LiteralPath $logFile) {
        Write-Host "`nLast lines of $logFile`n"
        Get-Content -LiteralPath $logFile -Tail 25
    } else { Write-Host 'No publish has run yet.' }
    return
}

foreach ($tool in @(
    @{ Name = 'git'; Install = 'winget install --id Git.Git -e' },
    @{ Name = 'gh'; Install = 'winget install --id GitHub.cli -e' },
    @{ Name = 'docker'; Install = 'winget install --id Docker.DockerDesktop -e' }
)) {
    if (-not (Get-Command $tool.Name -ErrorAction SilentlyContinue)) {
        throw "$($tool.Name) is not installed. Install it (for example: $($tool.Install)), open a new window and run this again. Nothing was set up."
    }
}

Write-Host "1/3 Publishing folder: $SourceDirectory"
if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory '.git'))) {
    if ((Test-Path -LiteralPath $SourceDirectory) -and (Get-ChildItem -LiteralPath $SourceDirectory -Force)) {
        throw "$SourceDirectory exists and is not a Git clone. Move it away or pass -SourceDirectory. Nothing was set up."
    }
    $clone = Invoke-Native 'git' @('clone', '--branch', 'main', $sourceUrl, $SourceDirectory)
    if (-not $clone.Ok) { throw "git clone failed:`n$($clone.Output)" }
    Write-Host '    Cloned GitHub main.'
} else {
    $branch = (Invoke-Native 'git' @('-C', $SourceDirectory, 'branch', '--show-current')).Output.Trim()
    $dirty = (Invoke-Native 'git' @('-C', $SourceDirectory, 'status', '--porcelain')).Output.Trim()
    if ($branch -ne 'main' -or $dirty) {
        throw "$SourceDirectory must stay a clean checkout of main; it is used only for publishing. Fix or delete it, then run this again."
    }
    Write-Host '    Using the existing clone; each run updates it from GitHub main.'
}
$autoPublish = Join-Path $SourceDirectory 'scripts\Auto-Publish.ps1'
if (-not (Test-Path -LiteralPath $autoPublish)) {
    $pull = Invoke-Native 'git' @('-C', $SourceDirectory, 'pull', '--ff-only', '--quiet')
    if (-not $pull.Ok -or -not (Test-Path -LiteralPath $autoPublish)) {
        throw "The publishing folder has no scripts\Auto-Publish.ps1 even after updating. Delete $SourceDirectory and run this again."
    }
}

Write-Host '2/3 GitHub sign-in with package permission'
if (-not (Test-PackageScope)) {
    $signedIn = (Invoke-Native 'gh' @('auth', 'status', '--hostname', 'github.com')).Ok
    Write-Host '    A browser window opens. Approve access for GitHub CLI, then come back here.'
    # Interactive on purpose: setup is the one step a person is present for.
    if ($signedIn) { & gh auth refresh --hostname github.com --scopes write:packages }
    else { & gh auth login --hostname github.com --web --git-protocol https --scopes write:packages }
    if (-not (Test-PackageScope)) {
        throw 'GitHub CLI still lacks the write:packages permission. Run this again and approve it in the browser. Nothing was scheduled.'
    }
}
Write-Host '    Signed in with write:packages.'

Write-Host '3/3 Scheduled task'
if ((Invoke-Native 'docker' @('info', '--format', '{{.OSType}}')).Output.Trim() -ne 'linux') {
    Write-Host '    Docker Desktop is not running (or not using Linux containers). Runs are skipped until it is.' -ForegroundColor Yellow
    Write-Host '    Turn on Docker Desktop > Settings > General > "Start Docker Desktop when you sign in".' -ForegroundColor Yellow
}
$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $SourceDirectory `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$autoPublish`""
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
Start-ScheduledTask -TaskName $TaskName

Write-Host "`nDone. Automatic publishing is on: at sign-in and every $IntervalMinutes minutes while you are signed in."
Write-Host 'A first run has started in the background; a full build takes a while.'
Write-Host "Log: $logFile"
Write-Host 'Check on it: Auto-Publish-Windows.cmd status. Turn it off: Auto-Publish-Windows.cmd off'
