[CmdletBinding()]
param(
    # Omitting this switch builds/tests only. This switch authorizes publishing.
    [switch]$Publish,
    # Optional convenience: require the release commit to be the remote main tip.
    [switch]$PublishLatest,
    [switch]$CheckOnly,
    # Explicitly start the browser sign-in/scope repair when publishing needs it.
    [switch]$RepairAuthentication,
    [Parameter(DontShow)][switch]$SourceUpdated
)

# Keep the bootstrap ahead of all publisher implementation and metadata reads.
# Reload once after fast-forward so updated scripts/configuration are actually used.
$ErrorActionPreference = 'Stop'
try {
    if ($PublishLatest -and -not $Publish) { throw '-PublishLatest requires -Publish.' }
    $sourceChanged = & (Join-Path $PSScriptRoot 'Update-ReleaseSource.ps1') -RepositoryRoot (Split-Path -Parent $PSScriptRoot) -PublishLatest:$PublishLatest -AlreadyUpdated:$SourceUpdated
    if ($sourceChanged) {
        Write-Host 'Reloading updated release script before verification/build.'
        $restartOptions = @{}
        foreach ($key in $PSBoundParameters.Keys) { $restartOptions[$key] = $PSBoundParameters[$key] }
        $restartOptions['SourceUpdated'] = $true
        & $PSCommandPath @restartOptions
        return
    }
} catch {
    Write-Host "Source preflight failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Result: FAILED. No further build or upload will run.'
    throw
}

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$imageName = 'ghcr.io/bgoldbeck/life-gather'
$releaseTimer = [Diagnostics.Stopwatch]::StartNew()
$currentStage = 'Preflight'
$releaseOutcome = 'FAILED'

function Write-Stage {
    param([string]$Name)
    $script:currentStage = $Name
    Write-Host ("`n[{0}] Stage: {1}" -f (Get-Date -Format 'HH:mm:ss'), $Name) -ForegroundColor Cyan
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    Write-Host ("[{0}] > {1} {2}" -f (Get-Date -Format 'HH:mm:ss'), $Executable, ($Arguments -join ' '))
    $commandTimer = [Diagnostics.Stopwatch]::StartNew()
    & $Executable @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed (exit $LASTEXITCODE). Release stopped."
    }
    Write-Host ("{0} completed in {1:N1}s" -f $Executable, $commandTimer.Elapsed.TotalSeconds)
}

function Get-CheckedOutput {
    param([string]$Executable, [string[]]$Arguments)
    Write-Host ("[{0}] Checking: {1} {2}" -f (Get-Date -Format 'HH:mm:ss'), $Executable, ($Arguments -join ' '))
    $result = & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed (exit $LASTEXITCODE)." }
    return ($result -join "`n").Trim()
}

# Throwaway PostgreSQL (with pgvector) for backend tests and the container smoke.
$postgresImage = 'pgvector/pgvector:pg17'
function Start-TestDatabase {
    param([string]$Name, [string]$Password, [string[]]$Options)
    Invoke-Checked docker (@(
        'run', '--detach', '--name', $Name,
        '--env', "POSTGRES_PASSWORD=$Password",
        '--env', 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C'
    ) + $Options + @($postgresImage))
    # TCP readiness: the image's initialization server listens on a socket only.
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $Name pg_isready --host 127.0.0.1 --username postgres *> $null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw 'The temporary PostgreSQL database did not become ready. Release stopped.'
}

function Remove-TestContainer {
    param([string]$Name)
    & docker rm --force --volumes $Name | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Warning "Remove leftover test container $Name manually." }
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

function Get-PublishIdentity {
    param([string]$GhExecutable, [switch]$RepairAuthentication)
    # Read only the login and response headers. Never retrieve or print a token here.
    # auth status alone does not prove that the credential has package scopes.
    $identity = Get-CheckedOutput $GhExecutable @('api', '--include', '--hostname', 'github.com', 'user', '--jq', '.login')
    $scopeHeader = [regex]::Match($identity, '(?im)^x-oauth-scopes:[ \t]*([^\r\n]*)')
    $scopes = @()
    if ($scopeHeader.Success) {
        $scopes = @($scopeHeader.Groups[1].Value -split ',' | ForEach-Object { $_.Trim() })
    }
    if ($scopes -notcontains 'write:packages') {
        if ($RepairAuthentication) {
            Write-Host 'Starting GitHub scope recovery. Complete the authorization in your browser.'
            Invoke-Checked $GhExecutable @('auth', 'refresh', '--hostname', 'github.com', '--scopes', 'write:packages')
            return Get-PublishIdentity $GhExecutable
        }
        throw 'GitHub credential is missing a confirmed write:packages scope. Run gh auth refresh --hostname github.com --scopes write:packages, or rerun this publisher with -RepairAuthentication to start browser recovery. GHCR requires a compatible OAuth token or a personal access token (classic); repository write permission alone is insufficient. Nothing was uploaded.'
    }
    $login = ($identity.Trim() -split '\r?\n')[-1].Trim()
    if ($login -notmatch '^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$') {
        throw 'Unable to determine the authenticated GitHub account safely.'
    }
    return $login
}

Push-Location $repoRoot
$probeName = $null
$testDatabase = $null
$smokeDatabase = $null
$smokeNetwork = $null
# Random per run; only ever used by the throwaway test containers.
$testPassword = [guid]::NewGuid().ToString('N')
$authDirectory = $null
try {
    Write-Stage 'Preflight'
    Write-Host "Workspace: $repoRoot"
    Write-Host 'Verbose progress is enabled. Registry credentials and stdin are never logged.'
    if ($PublishLatest -and -not $Publish) { throw '-PublishLatest requires -Publish.' }
    foreach ($command in @('git', 'uv', 'npm', 'docker')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Install $command and put it on PATH first."
        }
    }
    $dirty = Get-CheckedOutput git @('status', '--porcelain')
    if ($dirty) {
        Write-Host "Uncommitted paths (file contents are not shown):`n$dirty"
        throw 'Commit or safely stash your changes first. Nothing was built or uploaded.'
    }
    $revision = Get-CheckedOutput git @('rev-parse', 'HEAD')
    if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Expected a full Git commit SHA.' }
    $versionSource = Get-Content -LiteralPath (Join-Path $repoRoot 'backend/src/lifegather/version.py') -Raw
    $versionMatch = [regex]::Match($versionSource, '__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"')
    if (-not $versionMatch.Success) { throw 'Expected a valid application version.' }
    $appVersion = $versionMatch.Groups[1].Value
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
    $registryUser = $null
    if ($Publish) {
        $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
        if ($ghCommand) { $ghExecutable = $ghCommand.Source }
        else {
            $cachedGh = Join-Path ([IO.Path]::GetTempPath()) 'lifegather-github-cli/bin/gh.exe'
            if (Test-Path -LiteralPath $cachedGh) { $ghExecutable = $cachedGh }
        }
        if (-not $ghExecutable) { throw 'Install GitHub CLI (gh) and run gh auth login first.' }
        $savedPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $authentication = & $ghExecutable auth status --hostname github.com 2>&1
            $authExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedPreference }
        if ($authExit -ne 0) {
            if (-not $RepairAuthentication) {
                throw 'GitHub sign-in is unavailable. Run gh auth login --hostname github.com --web --scopes write:packages, or rerun this publisher with -RepairAuthentication. Complete GitHub authorization in your browser.'
            }
            Write-Host 'Starting GitHub sign-in recovery. Complete the authorization in your browser.'
            Invoke-Checked $ghExecutable @('auth', 'login', '--hostname', 'github.com', '--web', '--scopes', 'write:packages')
        } else { $authentication | Out-Host }
        $registryUser = Get-PublishIdentity $ghExecutable -RepairAuthentication:$RepairAuthentication
        Write-Host "Publishing account: $registryUser; write:packages scope confirmed."
        Write-Host 'The account must also have write access to bgoldbeck/life-gather in GHCR; scope alone does not grant package access.'
        # Read the advertised main ref without modifying the checkout or remote.
        $advertised = Get-CheckedOutput git @('ls-remote', 'https://github.com/bgoldbeck/life-gather.git', 'refs/heads/main')
        $remoteMain = ($advertised -split '\s+')[0]
        if ($PublishLatest -and ($branch -ne 'main' -or $remoteMain -ne $revision)) {
            throw 'Publishing latest requires a clean main checkout matching GitHub main. Push/merge source separately first.'
        }
    }

    Write-Stage 'Backend verification'
    Write-Host 'Dependency setup may download missing packages.'
    Push-Location (Join-Path $repoRoot 'backend')
    try {
        Invoke-Checked uv @('sync', '--locked')
        Write-Host 'Running the full backend suite in four isolated Linux/PostgreSQL shards; elapsed progress and slow-test logs are reported.'
        Invoke-Checked uv @('run', '--locked', 'python', '../scripts/run_backend_tests.py')
        Invoke-Checked uv @('run', '--locked', 'ruff', 'check', '.')
        Invoke-Checked uv @('run', '--locked', 'ruff', 'format', '--check', '.')
        Invoke-Checked uv @('run', '--locked', 'mypy')
    } finally { Pop-Location }
    Write-Stage 'Frontend verification'
    Push-Location (Join-Path $repoRoot 'frontend')
    try {
        Invoke-Checked npm @('ci', '--no-audit', '--no-fund')
        Invoke-Checked npm @('test')
        Invoke-Checked npm @('run', 'lint')
        Invoke-Checked npm @('run', 'typecheck')
        Invoke-Checked npm @('run', 'format:check')
        Invoke-Checked npm @('run', 'build')
    } finally { Pop-Location }
    Write-Stage 'Compose validation'
    $configuredPassword = $env:LIFEGATHER_DB_PASSWORD
    if (-not $configuredPassword) { $env:LIFEGATHER_DB_PASSWORD = 'composevalidation' }
    try {
        Invoke-Checked docker @('compose', 'config', '--quiet')
        Invoke-Checked docker @('compose', '-f', 'deploy/compose.image.yaml', 'config', '--quiet')
    } finally {
        if ($configuredPassword) { $env:LIFEGATHER_DB_PASSWORD = $configuredPassword }
        else { Remove-Item Env:LIFEGATHER_DB_PASSWORD -ErrorAction SilentlyContinue }
    }
    if ($CheckOnly) {
        $releaseOutcome = 'CHECKS PASSED'
        Write-Host 'Checks passed. No image built or uploaded.'
        return
    }

    Write-Stage 'Build'
    Invoke-Checked docker @(
        'build', '--load', '--progress=plain', '--platform', 'linux/amd64',
        '--label', 'org.opencontainers.image.source=https://github.com/bgoldbeck/life-gather',
        '--label', "org.opencontainers.image.revision=$revision",
        '--label', "org.opencontainers.image.version=$appVersion",
        '--build-arg', "APP_REVISION=$revision",
        '--tag', $commitTag, '.'
    )
    Show-ImageSize $commitTag

    Write-Stage 'Isolated container smoke verification'
    $probeName = 'lifegather-release-' + [guid]::NewGuid().ToString('N')
    # An internal network: the database is reachable by the app only, no internet.
    $smokeNetwork = $probeName + '-net'
    Invoke-Checked docker @('network', 'create', '--internal', $smokeNetwork)
    $smokeDatabase = $probeName + '-db'
    Start-TestDatabase $smokeDatabase $testPassword @('--network', $smokeNetwork, '--network-alias', 'db')
    Invoke-Checked docker @(
        'run', '--detach', '--pull=never', '--name', $probeName,
        '--network', $smokeNetwork,
        '--env', "LIFEGATHER_DATABASE_URL=postgresql://postgres:$testPassword@db:5432/postgres",
        '--read-only', '--tmpfs', '/tmp:size=64m,mode=1777',
        '--tmpfs', '/data:size=64m,uid=10001,gid=10001,mode=0700',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', $commitTag
    )
    $healthy = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        $status = Get-CheckedOutput docker @('inspect', '--format', '{{.State.Health.Status}}', $probeName)
        Write-Host "Health check $($attempt + 1)/45: $status"
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
    status = json.load(r)
    build = status.pop('build')
    assert status == {
        'configured': False,
        'test_login_enabled': False,
        'email_password_enabled': False,
        'email_delivery_enabled': False,
        'bot_check_site_key': None,
        'terms': None,
        'user': None,
        'csrf_token': None,
    }
with urllib.request.urlopen(base + '/api/version') as r:
    assert json.load(r) == build
assert build['version'] == '__RELEASE_VERSION__'
assert build['revision'] == '__RELEASE_REVISION__'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['LIFEGATHER_DATABASE_URL'].replace('postgresql://', 'postgresql+psycopg://', 1))
with engine.connect() as connection:
    assert connection.scalar(text('SELECT count(*) FROM alembic_version')) == 1
    assert connection.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")) == 1
    assert connection.scalar(text('SELECT count(*) FROM users')) == 0
engine.dispose()
probe = Path('/data/.release-probe')
probe.write_text('synthetic check')
probe.unlink()
print('Container health, UI, PostgreSQL migration, user, and private storage verified.')
'@
    $smoke = $smoke.Replace('__RELEASE_VERSION__', $appVersion).Replace('__RELEASE_REVISION__', $revision)
    $smoke | & docker exec --interactive $probeName python -
    if ($LASTEXITCODE -ne 0) { throw 'Container smoke test failed. Nothing uploaded.' }
    Invoke-Checked docker @('rm', '--force', $probeName)
    $probeName = $null
    Remove-TestContainer $smokeDatabase
    $smokeDatabase = $null
    Invoke-Checked docker @('network', 'rm', $smokeNetwork)
    $smokeNetwork = $null
    if (-not $Publish) {
        Write-Host "Build and checks passed: $commitTag. No upload requested."
        $releaseOutcome = 'BUILT (no upload)'
        return
    }

    # Ensure source has not changed during the release.
    $finalStatus = Get-CheckedOutput git @('status', '--porcelain')
    $finalRevision = Get-CheckedOutput git @('rev-parse', 'HEAD')

    if ($finalStatus -or $finalRevision -ne $revision) {
        if ($finalStatus) {
            Write-Host "Files changed during release:" -ForegroundColor Yellow
            Write-Host $finalStatus
        }

        if ($finalRevision -ne $revision) {
            Write-Host "Git HEAD changed: $revision -> $finalRevision" -ForegroundColor Yellow
        }

        throw 'Source changed during release. Nothing uploaded; rerun from a clean commit.'
    }
    Write-Stage 'Upload preflight and image size'
    Show-ImageSize $commitTag
    $destination = if ($PublishLatest) { "$commitTag and $latestTag" } else { $commitTag }


    Write-Stage 'Registry sign-in and upload'
    if ((Get-PublishIdentity $ghExecutable) -ne $registryUser) {
        throw 'GitHub account changed during the build. Nothing uploaded; rerun with the intended account.'
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
        $registryToken | & docker @dockerAuth login ghcr.io --username $registryUser --password-stdin
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
    $releaseOutcome = 'PUBLISHED'
} catch {
    Write-Host "Release failed during stage '${currentStage}'. $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    Write-Stage 'Cleanup'
    if ($probeName) {
        & docker rm --force $probeName | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Warning "Remove leftover test container $probeName manually." }
    }
    foreach ($leftover in @($testDatabase, $smokeDatabase)) {
        if ($leftover) { Remove-TestContainer $leftover }
    }
    if ($smokeNetwork) {
        & docker network rm $smokeNetwork | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Warning "Remove leftover test network $smokeNetwork manually." }
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
    Write-Host ("Result: {0}. Elapsed: {1:N1}s. Existing running containers were not changed." -f $releaseOutcome, $releaseTimer.Elapsed.TotalSeconds)
}
