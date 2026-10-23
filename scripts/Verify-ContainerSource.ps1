# Shared by the guarded publisher and the terminal helper. No host Python/Node.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
function Invoke-VerificationDocker {
    param([string[]]$Arguments)
    Write-Host ("[{0}] docker {1}" -f (Get-Date -Format 'HH:mm:ss'), ($Arguments -join ' '))
    & docker @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Container source verification failed. Release stopped.' }
}
Push-Location -LiteralPath $root
try {
    # Bind mounts refer to the daemon's filesystem; refuse remote engines.
    $context = & docker context inspect
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Docker context.' }
    $endpoint = @(ConvertFrom-Json ($context -join "`n"))[0].Endpoints.docker.Host
    if ($env:DOCKER_HOST) { $endpoint = $env:DOCKER_HOST }
    if ($endpoint -notmatch '^(npipe:|unix:)') {
        throw 'Verification needs a local Linux Docker engine (Docker Desktop on Windows); remote Docker bind mounts are unsupported.'
    }
    $socketSource = '/var/run/docker.sock'
    if ($endpoint.StartsWith('unix://')) { $socketSource = $endpoint.Substring(7) }
    if ($root.Contains(',') -or $socketSource.Contains(',')) { throw 'Docker bind mounts require a checkout/socket path without commas.' }
    $databaseImage = & docker image ls --quiet pgvector/pgvector:pg17
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the test database image.' }
    if (-not $databaseImage) {
        Write-Host 'Downloading the test database image for this first run.'
        Invoke-VerificationDocker @('pull', 'pgvector/pgvector:pg17')
    }
    $report = Join-Path $root ('test-results/release-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $report -Force | Out-Null
    Write-Host "Reports: $report"
    Write-Host 'Verification uses disposable containers and the local Docker socket; no host Python, uv, Node or npm is required.'
    $controllerIdFile = Join-Path $report 'controller-image.id'
    $frontendIdFile = Join-Path $report 'frontend-image.id'
    Invoke-VerificationDocker @('build', '--load', '--progress=plain', '--platform', 'linux/amd64', '--iidfile', $controllerIdFile, '-f', 'scripts/Dockerfile.release-controller', '-t', 'lifegather-release-controller:local', '.')
    $controllerImage = (Get-Content -LiteralPath $controllerIdFile -Raw).Trim()
    if ($controllerImage -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid verification controller image ID.' }
    Invoke-VerificationDocker @(
        'run', '--rm', '--init', '--platform', 'linux/amd64',
        '--mount', "type=bind,source=$root,target=/workspace,readonly",
        '--mount', "type=bind,source=$report,target=/results",
        '--mount', "type=bind,source=$socketSource,target=/var/run/docker.sock",
        $controllerImage, '--output', '/results'
    )
    Invoke-VerificationDocker @('build', '--load', '--progress=plain', '--platform', 'linux/amd64', '--iidfile', $frontendIdFile, '-f', 'scripts/Dockerfile.frontend-checks', '-t', 'lifegather-frontend-checks:local', '.')
    $frontendImage = (Get-Content -LiteralPath $frontendIdFile -Raw).Trim()
    if ($frontendImage -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid frontend verification image ID.' }
    Invoke-VerificationDocker @('run', '--rm', '--init', '--network', 'none', '--platform', 'linux/amd64', $frontendImage)
} finally { Pop-Location }
