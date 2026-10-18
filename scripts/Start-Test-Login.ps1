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
$containerName = 'lifegather-preview'
$image = 'ghcr.io/bgoldbeck/life-gather:latest'
$existing = Invoke-Docker @('container', 'ls', '--all', '--quiet', '--filter', 'name=^/lifegather-preview$')
if ($existing) {
    $details = @(Invoke-Docker @('inspect', $containerName) | ConvertFrom-Json)[0]
    $mounts = @($details.Mounts)
    if ($mounts.Count -ne 1 -or $mounts[0].Destination -ne '/data' -or
        $mounts[0].Type -ne 'volume' -or $mounts[0].Name -ne 'lifegather-preview-data') {
        throw 'Different storage configuration found. Stopped to protect your data.'
    }
    foreach ($setting in $details.Config.Env) {
        if ($setting -notlike 'LIFEGATHER_*') { continue }
        if ($setting -match '^LIFEGATHER_[A-Z_]+=$' -or
            $setting -match '^LIFEGATHER_(DATA_DIR=/data|STATIC_DIR=/app/static|APP_NAME=LifeGather|BUILD_REVISION=[a-f0-9]*|TEST_LOGIN_ENABLED=(true|false|1|0)|PUBLIC_URL=http://127\.0\.0\.1:8787)$') {
            continue
        }
        throw 'Custom LifeGather settings found. Stopped rather than discard them; use Compose or preserve those settings manually.'
    }
}

Write-Host 'Downloading the latest image first. This can use internet bandwidth.'
Invoke-Docker @('pull', $image) | Out-Host
if ($existing) {
    Invoke-Docker @('stop', $containerName) | Out-Host
    Invoke-Docker @('rm', $containerName) | Out-Host
}
Invoke-Docker @(
    'run', '-d', '--name', $containerName, '--pull', 'never',
    '-p', '127.0.0.1:8787:8787', '-v', 'lifegather-preview-data:/data',
    '-e', 'LIFEGATHER_TEST_LOGIN_ENABLED=true', '--restart', 'unless-stopped', $image
) | Out-Host
Write-Host ''
Write-Host 'Started. Open http://127.0.0.1:8787/ after the app becomes healthy.'
Write-Host 'Sign out if needed, then click Continue as test user.'
Write-Host 'Your lifegather-preview-data volume was preserved. Use test data only.'
