# Recreate the standalone preview with one-click test login. Never deletes volumes.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([string[]]$Arguments)
    $output = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker $($Arguments[0]) failed; stopped." }
    return $output
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install/start Docker Desktop first.'
}
if ((Invoke-Docker @('info', '--format', '{{.OSType}}')) -ne 'linux') {
    throw 'Start Docker Desktop with the Linux engine.'
}
$image = 'ghcr.io/bgoldbeck/life-gather:latest'
$existing = @(Invoke-Docker @('container', 'ls', '--all', '--quiet', '--filter', 'name=^/lifegather-preview(-v[0-9]+\.[0-9]+\.[0-9]+)?$'))
if ($existing.Count -gt 1) { throw 'Multiple preview containers found. Stopped rather than choose one or change storage.' }
if ($existing.Count -eq 1) {
    $details = @(Invoke-Docker @('inspect', $existing[0]) | ConvertFrom-Json)[0]
    $mounts = @($details.Mounts)
    if ($mounts.Count -ne 1 -or $mounts[0].Destination -ne '/data' -or
        $mounts[0].Type -ne 'volume' -or $mounts[0].Name -ne 'lifegather-preview-data') {
        throw 'Different storage configuration found. Stopped to protect your data.'
    }
    foreach ($setting in $details.Config.Env) {
        if ($setting -notlike 'LIFEGATHER_*') { continue }
        if ($setting -match '^LIFEGATHER_[A-Z_]+=$' -or
            $setting -match '^LIFEGATHER_DATABASE_URL=postgresql://lifegather:[a-f0-9]{32}@lifegather-preview-db:5432/lifegather$' -or
            $setting -match '^LIFEGATHER_(DATA_DIR=/data|STATIC_DIR=/app/static|APP_NAME=LifeGather|BUILD_REVISION=[a-f0-9]*|TEST_LOGIN_ENABLED=(true|false|1|0)|PUBLIC_URL=http://127\.0\.0\.1:8787)$') {
            continue
        }
        throw 'Custom LifeGather settings found. Stopped rather than discard them; use Compose or preserve those settings manually.'
    }
}

Write-Host 'Downloading the latest image first. This can use internet bandwidth.'
Invoke-Docker @('pull', $image) | Out-Host
$imageDetails = @(Invoke-Docker @('image', 'inspect', $image) | ConvertFrom-Json)[0]
$imageVersion = $imageDetails.Config.Labels.'org.opencontainers.image.version'
$imageId = $imageDetails.Id
if ($imageVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or $imageId -notmatch '^sha256:[a-f0-9]{64}$') {
    throw 'The downloaded image has no valid application version/immutable ID. Existing containers were not changed.'
}
$containerName = 'lifegather-preview-v' + $imageVersion

# PostgreSQL sidecar with its own volume. Reused, never recreated or deleted.
$network = 'lifegather-preview'
$database = 'lifegather-preview-db'
if (-not @(Invoke-Docker @('network', 'ls', '--quiet', '--filter', "name=^$network$"))) {
    Invoke-Docker @('network', 'create', $network) | Out-Host
}
$databaseIds = @(Invoke-Docker @('container', 'ls', '--all', '--quiet', '--filter', "name=^/$database$"))
if ($databaseIds.Count -eq 1) {
    $databaseDetails = @(Invoke-Docker @('inspect', $databaseIds[0]) | ConvertFrom-Json)[0]
    $passwordSetting = @($databaseDetails.Config.Env | Where-Object { $_ -match '^POSTGRES_PASSWORD=[a-f0-9]{32}$' })
    if ($passwordSetting.Count -ne 1) { throw 'The preview database has a different configuration. Stopped to protect your data.' }
    $password = $passwordSetting[0].Substring('POSTGRES_PASSWORD='.Length)
    Invoke-Docker @('start', $databaseIds[0]) | Out-Host
} else {
    $password = [guid]::NewGuid().ToString('N')
    Invoke-Docker @(
        'run', '-d', '--name', $database, '--network', $network,
        '-v', 'lifegather-preview-db-data:/var/lib/postgresql/data',
        '-e', 'POSTGRES_DB=lifegather', '-e', 'POSTGRES_USER=lifegather',
        '-e', "POSTGRES_PASSWORD=$password",
        '-e', 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C',
        '--restart', 'unless-stopped', 'pgvector/pgvector:pg17'
    ) | Out-Host
}
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    & docker exec $database pg_isready --host 127.0.0.1 --username lifegather *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'The preview database did not start. The existing app container was not changed.' }
if ($existing.Count -eq 1) {
    Invoke-Docker @('stop', $existing[0]) | Out-Host
    Invoke-Docker @('rm', $existing[0]) | Out-Host
}
Invoke-Docker @(
    'run', '-d', '--name', $containerName, '--pull', 'never',
    '-p', '127.0.0.1:8787:8787', '-v', 'lifegather-preview-data:/data',
    '--network', $network,
    '-e', "LIFEGATHER_DATABASE_URL=postgresql://lifegather:$password@${database}:5432/lifegather",
    '-e', 'LIFEGATHER_TEST_LOGIN_ENABLED=true', '--restart', 'unless-stopped', $imageId
) | Out-Host
Write-Host ''
Write-Host "Started $containerName from image $imageId. Open http://127.0.0.1:8787/ after the app becomes healthy."
Write-Host 'Sign out if needed, then click Continue as test user.'
Write-Host 'Your lifegather-preview-data and lifegather-preview-db-data volumes were preserved. Use test data only.'
