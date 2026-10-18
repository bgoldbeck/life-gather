[CmdletBinding()]
param(
    # Omitting this switch builds/tests only. Publishing requires another prompt.
    [switch]$Publish,
    # Optional convenience: require the release commit to be the remote main tip.
    [switch]$PublishLatest,
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$imageName = 'ghcr.io/bgoldbeck/life-gather'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed (exit $LASTEXITCODE). Release stopped."
    }
}

function Get-CheckedOutput {
    param([string]$Executable, [string[]]$Arguments)
    $result = & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed (exit $LASTEXITCODE)." }
    return ($result -join "`n").Trim()
}

function Show-ImageSize {
    param([string]$Reference)
    $found = & docker image ls --quiet $Reference
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect local images.' }
    if (-not $found) {
        Write-Host "No local size available for $Reference; no image was pulled."
        return
    }
    $disk = Get-CheckedOutput docker @('image', 'ls', '--format', '{{.Size}}', $Reference)
    $bytes = Get-CheckedOutput docker @('image', 'inspect', '--format', '{{.Size}}', $Reference)
    Write-Host "Image: $Reference"
    Write-Host "Docker image-list size: $disk; inspect size: $bytes bytes."
    Write-Host 'These are local engine measurements, not an exact compressed download/upload size.'
    Write-Host 'Only missing registry layers are uploaded; the transfer may be much smaller.'
}

function Confirm-Operation {
    param([string]$Question)
    return (Read-Host "$Question [y/N]") -match '^(?i:y|yes)$'
}

Push-Location $repoRoot
$probeName = $null
$authDirectory = $null
try {
    if ($PublishLatest -and -not $Publish) { throw '-PublishLatest requires -Publish.' }
    foreach ($command in @('git', 'uv', 'npm', 'docker')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Install $command and put it on PATH first."
        }
    }
    $dirty = Get-CheckedOutput git @('status', '--porcelain')
    if ($dirty) { throw 'Commit or safely stash your changes first. Nothing was built or uploaded.' }
    $revision = Get-CheckedOutput git @('rev-parse', 'HEAD')
    if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Expected a full Git commit SHA.' }
    $branch = Get-CheckedOutput git @('branch', '--show-current')
    $commitTag = "${imageName}:sha-$revision"
    $latestTag = "${imageName}:latest"

    Invoke-Checked docker @('info', '--format', '{{.OSType}}')
    $osType = Get-CheckedOutput docker @('info', '--format', '{{.OSType}}')
    if ($osType -ne 'linux') { throw 'Switch Docker to the Linux engine first.' }
    Write-Host "Release revision: $revision ($branch)"
    Show-ImageSize $latestTag

    # Publishing has extra preflight checks, but code is never pushed or merged here.
    $ghExecutable = $null
    if ($Publish) {
        $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
        if ($ghCommand) { $ghExecutable = $ghCommand.Source }
        else {
            $cachedGh = Join-Path ([IO.Path]::GetTempPath()) 'lifegather-github-cli/bin/gh.exe'
            if (Test-Path -LiteralPath $cachedGh) { $ghExecutable = $cachedGh }
        }
        if (-not $ghExecutable) { throw 'Install GitHub CLI (gh) and run gh auth login first.' }
        Invoke-Checked $ghExecutable @('auth', 'status', '--hostname', 'github.com')
        # Read the advertised main ref without modifying the checkout or remote.
        $advertised = Get-CheckedOutput git @('ls-remote', 'https://github.com/bgoldbeck/life-gather.git', 'refs/heads/main')
        $remoteMain = ($advertised -split '\s+')[0]
        if ($PublishLatest -and ($branch -ne 'main' -or $remoteMain -ne $revision)) {
            throw 'Publishing latest requires a clean main checkout matching GitHub main. Push/merge source separately first.'
        }
    }

    Write-Host 'Running local checks. Dependency setup may download missing packages.'
    Push-Location (Join-Path $repoRoot 'backend')
    try {
        Invoke-Checked uv @('sync', '--locked')
        Invoke-Checked uv @('run', '--locked', 'pytest')
        Invoke-Checked uv @('run', '--locked', 'ruff', 'check', '.')
        Invoke-Checked uv @('run', '--locked', 'ruff', 'format', '--check', '.')
        Invoke-Checked uv @('run', '--locked', 'mypy')
    } finally { Pop-Location }
    Push-Location (Join-Path $repoRoot 'frontend')
    try {
        Invoke-Checked npm @('ci', '--no-audit', '--no-fund')
        Invoke-Checked npm @('test')
        Invoke-Checked npm @('run', 'lint')
        Invoke-Checked npm @('run', 'typecheck')
        Invoke-Checked npm @('run', 'format:check')
        Invoke-Checked npm @('run', 'build')
    } finally { Pop-Location }
    Invoke-Checked docker @('compose', 'config', '--quiet')
    Invoke-Checked docker @('compose', '-f', 'deploy/compose.image.yaml', 'config', '--quiet')
    if ($CheckOnly) { Write-Host 'Checks passed. No image built or uploaded.'; return }

    if (-not (Confirm-Operation 'Build the Linux image now? Docker may download base layers')) {
        Write-Host 'Build deferred. Nothing uploaded.'
        return
    }
    Invoke-Checked docker @(
        'build', '--platform', 'linux/amd64',
        '--label', 'org.opencontainers.image.source=https://github.com/bgoldbeck/life-gather',
        '--label', "org.opencontainers.image.revision=$revision",
        '--tag', $commitTag, '.'
    )
    Show-ImageSize $commitTag

    $probeName = 'lifegather-release-' + [guid]::NewGuid().ToString('N')
    Invoke-Checked docker @(
        'run', '--detach', '--pull=never', '--name', $probeName,
        '--read-only', '--tmpfs', '/tmp:size=64m,mode=1777',
        '--tmpfs', '/data:size=64m,uid=10001,gid=10001,mode=0700',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', $commitTag
    )
    $healthy = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        $status = Get-CheckedOutput docker @('inspect', '--format', '{{.State.Health.Status}}', $probeName)
        if ($status -eq 'healthy') { $healthy = $true; break }
        if ($status -eq 'unhealthy') { break }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw 'The isolated test container did not become healthy. Nothing uploaded.' }
    $smoke = @'
import json, os, shutil, urllib.request
from pathlib import Path
assert os.getuid() == 10001
assert shutil.which('node') is None
base = 'http://127.0.0.1:8787'
with urllib.request.urlopen(base + '/health') as r:
    assert json.load(r) == {'status': 'ok'}
with urllib.request.urlopen(base + '/') as r:
    assert b'<title>LifeGather</title>' in r.read()
with urllib.request.urlopen(base + '/brand/lifegather-icon.png') as r:
    assert r.read(8) == b'\x89PNG\r\n\x1a\n'
with urllib.request.urlopen(base + '/auth/session') as r:
    assert json.load(r) == {
        'configured': False,
        'test_login_enabled': False,
        'email_password_enabled': False,
        'email_delivery_enabled': False,
        'user': None,
        'csrf_token': None,
    }
assert Path('/data/auth.sqlite3').is_file()
probe = Path('/data/.release-probe')
probe.write_text('synthetic check')
probe.unlink()
print('Container health, UI, auth migration, user, and private storage verified.')
'@
    $smoke | & docker exec --interactive $probeName python -
    if ($LASTEXITCODE -ne 0) { throw 'Container smoke test failed. Nothing uploaded.' }
    Invoke-Checked docker @('rm', '--force', $probeName)
    $probeName = $null
    if (-not $Publish) {
        Write-Host "Build and checks passed: $commitTag. No upload requested."
        return
    }

    # Source may have been edited during the checks/build: reject before publishing.
    if ((Get-CheckedOutput git @('status', '--porcelain')) -or
        (Get-CheckedOutput git @('rev-parse', 'HEAD')) -ne $revision) {
        throw 'Source changed during release. Nothing uploaded; rerun from a clean commit.'
    }
    Show-ImageSize $commitTag
    $destination = if ($PublishLatest) { "$commitTag and $latestTag" } else { $commitTag }
    if (-not (Confirm-Operation "Upload $destination now? This can use your internet bandwidth")) {
        Write-Host 'Upload deferred. Verified image remains available locally.'
        return
    }

    # Keep registry credentials out of the user's persistent Docker configuration.
    # JSON avoids nested Go-template quotes being stripped by Windows PowerShell.
    $contextJson = Get-CheckedOutput docker @('context', 'inspect')
    $contexts = @(ConvertFrom-Json -InputObject $contextJson)
    $endpoint = $contexts[0].Endpoints.docker.Host
    if ($env:DOCKER_HOST) { $endpoint = $env:DOCKER_HOST }
    $authDirectory = Join-Path ([IO.Path]::GetTempPath()) ('lifegather-registry-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $authDirectory | Out-Null
    $dockerAuth = @('--config', $authDirectory, '--host', $endpoint)
    $registryToken = & $ghExecutable auth token --hostname github.com 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $registryToken) { throw 'GitHub token unavailable.' }
    try {
        $registryToken | & docker @dockerAuth login ghcr.io --username bgoldbeck --password-stdin
        if ($LASTEXITCODE -ne 0) { throw 'Registry login failed; check write:packages permission.' }
    } finally { $registryToken = $null }
    Invoke-Checked docker ($dockerAuth + @('push', $commitTag))
    if ($PublishLatest) {
        # Recheck remote main before changing the shared latest tag.
        $advertised = Get-CheckedOutput git @('ls-remote', 'https://github.com/bgoldbeck/life-gather.git', 'refs/heads/main')
        if (($advertised -split '\s+')[0] -ne $revision) {
            throw 'GitHub main moved; commit image uploaded, but latest was not changed.'
        }
        Invoke-Checked docker @('tag', $commitTag, $latestTag)
        Invoke-Checked docker ($dockerAuth + @('push', $latestTag))
    }
    Write-Host "Published $destination. TrueNAS must pull and redeploy to use it."
    Write-Host 'Existing package visibility is unchanged; verify public access for first publication.'
} finally {
    if ($probeName) {
        & docker rm --force $probeName | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Warning "Remove leftover test container $probeName manually." }
    }
    if ($authDirectory) {
        # Remove only these exact per-run paths, without recursive filesystem deletion.
        $configFile = Join-Path $authDirectory 'config.json'
        if (Test-Path -LiteralPath $configFile) {
            Remove-Item -LiteralPath $configFile -Force
        }
        Remove-Item -LiteralPath $authDirectory
    }
    Pop-Location
}
