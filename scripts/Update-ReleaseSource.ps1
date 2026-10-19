[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RepositoryRoot,
    [switch]$PublishLatest,
    [switch]$AlreadyUpdated
)

# This preflight runs before the publisher loads its functions or captures version
# metadata, so a fast-forward can safely reload the complete updated publisher.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

function Invoke-SourceGitProcess {
    param([string[]]$Arguments)
    $savedPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5 turns redirected native stderr into ErrorRecords,
        # even for successful Git warnings. Use the native exit code, not stderr.
        $ErrorActionPreference = 'Continue'
        $value = & git @Arguments 2>&1
        $nativeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    return [pscustomobject]@{ ExitCode = $nativeExit; Text = ($value -join "`n").Trim() }
}

function Read-SourceGit {
    param([string[]]$Arguments)
    Write-Host ("Source check: git {0}" -f ($Arguments -join ' '))
    $result = Invoke-SourceGitProcess $Arguments
    if ($result.ExitCode -ne 0) {
        throw "git $($Arguments[0]) failed. Check Git access/connectivity and retry; no build or upload was started."
    }
    return $result.Text
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Install Git and put it on PATH before running the publisher.'
}
Push-Location -LiteralPath $RepositoryRoot
try {
    Write-Host 'Checking release source before tests or builds.'
    # Refresh cached stat information only. Real edits still appear in status.
    $refresh = Invoke-SourceGitProcess @('update-index', '--refresh')
    if ($refresh.ExitCode -gt 1) {
        throw 'Unable to refresh the Git index. Check for another Git operation or index lock, then retry.'
    }
    $dirty = Read-SourceGit @('status', '--porcelain')
    if ($dirty) {
        Write-Host "Uncommitted paths (file contents are not shown):`n$dirty"
        throw 'Commit or safely stash your changes first. Nothing was built or uploaded.'
    }
    # Inspect the configured URL without printing embedded credentials. Normal
    # user-configured Git transport/authentication and URL rewrites remain in use.
    $origin = Read-SourceGit @('config', '--get', 'remote.origin.url')
    if ($origin -notmatch '^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)bgoldbeck/life-gather(?:\.git)?/?$') {
        throw 'Origin must point to bgoldbeck/life-gather on GitHub before automatic source recovery. Check git remote -v locally.'
    }
    $null = Read-SourceGit @('fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main')
    $head = Read-SourceGit @('rev-parse', 'HEAD')
    $remoteMain = Read-SourceGit @('rev-parse', 'origin/main')
    $branch = Read-SourceGit @('branch', '--show-current')
    if ($PublishLatest -and $branch -ne 'main') {
        throw 'Publishing latest requires the main branch. Switch to a clean main checkout and retry; feature branches are never switched or merged automatically.'
    }
    if ($branch -ne 'main') {
        Write-Host 'Keeping the selected feature/detached revision for this commit build.'
        return $false
    }
    if ($head -eq $remoteMain) {
        Write-Host 'Main already matches fetched GitHub main.'
        return $false
    }
    $behind = (Invoke-SourceGitProcess @('merge-base', '--is-ancestor', 'HEAD', 'origin/main')).ExitCode
    if ($behind -gt 1) { throw 'Unable to inspect Git ancestry; resolve the Git error before releasing.' }
    if ($behind -eq 0) {
        if ($AlreadyUpdated) {
            throw 'GitHub main moved again after the source update. Rerun when source is stable; no build or upload was started.'
        }
        # Recheck immediately before changing tracked files. Never hide/stash edits.
        if ((Read-SourceGit @('status', '--porcelain')) -or
            (Read-SourceGit @('rev-parse', 'HEAD')) -ne $head -or
            (Read-SourceGit @('branch', '--show-current')) -ne 'main') {
            throw 'The checkout changed during source preflight. Inspect your work and retry.'
        }
        Write-Host "Fast-forwarding clean main: $head -> $remoteMain"
        $null = Read-SourceGit @('merge', '--ff-only', 'origin/main')
        return $true
    }
    $ahead = (Invoke-SourceGitProcess @('merge-base', '--is-ancestor', 'origin/main', 'HEAD')).ExitCode
    if ($ahead -gt 1) { throw 'Unable to inspect Git ancestry; resolve the Git error before releasing.' }
    if ($ahead -eq 0) {
        throw 'Main contains local-only commits. Push/review/merge them separately before releasing; the publisher never resets or pushes source.'
    }
    throw 'Local main and GitHub main have diverged. Reconcile those commits manually; the publisher never resets, rebases or creates a merge commit.'
} finally {
    Pop-Location
}
