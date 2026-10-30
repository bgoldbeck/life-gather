# Unattended Windows counterpart of auto-publish.sh, run by the Task Scheduler
# task that Register-AutoPublish.ps1 creates. Each run checks GitHub main; when
# it has a commit not yet published from this PC, it runs the normal publisher
# (Publish-Container.ps1 -Publish -PublishLatest), which verifies, builds,
# smoke-tests and uploads, or skips a commit GHCR already has (for example one
# the TrueNAS auto-publisher uploaded). It never starts or changes the preview.
#
# Never prompts. Quiet runs (nothing new, Docker not running, another run in
# progress) exit 0 without logging. Results go to auto-publish.log in the state
# folder. A failed commit is retried after -RetryHours, or at once with -Force.
[CmdletBinding()]
param(
    [int]$RetryHours = 6,
    [switch]$Force,
    [string]$StateDirectory = (Join-Path $env:LOCALAPPDATA 'LifeGather\auto-publish'),
    # Test seams; the defaults are the real publisher, Docker and GitHub.
    [Parameter(DontShow)][string]$Publisher = (Join-Path $PSScriptRoot 'Publish-Container.ps1'),
    [Parameter(DontShow)][string]$Docker = 'docker',
    [Parameter(DontShow)][string]$SourceUrl = 'https://github.com/bgoldbeck/life-gather.git'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$null = New-Item -ItemType Directory -Force -Path $StateDirectory
$logFile = Join-Path $StateDirectory 'auto-publish.log'

function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}
function Read-State([string]$Name) {
    $path = Join-Path $StateDirectory $Name
    if (Test-Path -LiteralPath $path) { return (Get-Content -LiteralPath $path -Raw).Trim() }
    return ''
}
function Write-State([string]$Name, [string]$Value) {
    Set-Content -LiteralPath (Join-Path $StateDirectory $Name) -Value $Value -Encoding ASCII
}
function Invoke-Quiet([string]$Executable, [string[]]$Arguments) {
    # Native stderr must not become a terminating error under 'Stop'.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Executable @Arguments 2>$null
        return [pscustomobject]@{ Ok = ($LASTEXITCODE -eq 0); Output = (@($output) -join "`n").Trim() }
    } catch {
        return [pscustomobject]@{ Ok = $false; Output = '' }
    } finally { $ErrorActionPreference = $previous }
}

# Overlapping scheduled runs exit at once while an earlier run holds this.
$mutex = New-Object Threading.Mutex($false, 'Local\LifeGather-AutoPublish')
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) } catch {
        # A run that crashed leaves the mutex abandoned; this run now owns it.
        $inner = $_.Exception
        while ($inner -and -not ($inner -is [Threading.AbandonedMutexException])) { $inner = $inner.InnerException }
        if (-not $inner) { throw }
        $owned = $true
    }
    if (-not $owned) { exit 0 }

    Write-State 'last-check' ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))
    # Docker Desktop starts with the user's session; try again next run.
    if ((Invoke-Quiet $Docker @('info', '--format', '{{.OSType}}')).Output -ne 'linux') { exit 0 }
    $remote = Invoke-Quiet 'git' @('ls-remote', $SourceUrl, 'refs/heads/main')
    $target = ($remote.Output -split '\s+')[0]
    if (-not $remote.Ok -or $target -notmatch '^[0-9a-f]{40}$') { exit 0 }

    if (-not $Force) {
        if ($target -eq (Read-State 'last-published-revision')) { exit 0 }
        $failedFile = Join-Path $StateDirectory 'last-failed-revision'
        if ($target -eq (Read-State 'last-failed-revision') -and
            (Get-Item -LiteralPath $failedFile).LastWriteTimeUtc -gt [DateTime]::UtcNow.AddHours(-$RetryHours)) {
            exit 0
        }
    }

    if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 20MB) {
        Move-Item -LiteralPath $logFile -Destination "$logFile.1" -Force
    }
    Write-Log "Run started for GitHub main $target."
    # A child process, so the publisher's own 'exit'/throw cannot end this run
    # before the result is recorded. Its output is appended to the log.
    $shell = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    $stdout = Join-Path $StateDirectory 'publisher.out'
    $stderr = Join-Path $StateDirectory 'publisher.err'
    $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $Publisher), '-Publish', '-PublishLatest')
    $process = Start-Process -FilePath $shell -ArgumentList $arguments -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    foreach ($file in @($stdout, $stderr)) {
        if (Test-Path -LiteralPath $file) {
            Get-Content -LiteralPath $file | Add-Content -LiteralPath $logFile -Encoding UTF8
            Remove-Item -LiteralPath $file -Force
        }
    }
    if ($process.ExitCode -eq 0) {
        Write-State 'last-published-revision' $target
        Remove-Item -LiteralPath (Join-Path $StateDirectory 'last-failed-revision') -Force -ErrorAction SilentlyContinue
        Write-Log 'Result: OK.'
        exit 0
    }
    Write-State 'last-failed-revision' $target
    Write-Log "Result: FAILED (publisher exit $($process.ExitCode)). Retrying in $RetryHours hours, or run with -Force."
    [Console]::Error.WriteLine("LifeGather auto-publish failed. See $logFile")
    exit 1
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
