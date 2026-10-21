# Offline checks only: no real Docker commands or running-container changes.
$ErrorActionPreference = 'Stop'
$launcher = Join-Path (Split-Path -Parent $PSScriptRoot) 'Start-Test-Login.ps1'
function global:docker {
    $global:LASTEXITCODE = 0
    $arguments = @($args)
    $global:TestLoginFixture.Calls.Add(($arguments -join ' '))
    switch ($arguments[0]) {
        'info' { 'linux' }
        'container' { if ($global:TestLoginFixture.Exists) { 'fixture-id' }; if ($global:TestLoginFixture.Multiple) {'second-fixture-id'} }
        'image' {
            @(@{Id=('sha256:' + ('a' * 64)); Config=@{Labels=@{'org.opencontainers.image.version'=$global:TestLoginFixture.ImageVersion}}}) | ConvertTo-Json -Depth 6 -Compress
        }
        'inspect' {
            @(@{
                Mounts = @(@{ Destination='/data'; Type='volume'; Name=$global:TestLoginFixture.Volume })
                Config = @{ Env=$global:TestLoginFixture.Environment }
            }) | ConvertTo-Json -Depth 5 -Compress
        }
        'pull' { if ($global:TestLoginFixture.PullFails) { $global:LASTEXITCODE=1 } }
        'stop' {}
        'rm' {}
        'run' { 'fixture-container' }
        default { throw "Unexpected Docker command: $arguments" }
    }
}
function Test-Launcher {
    param([string]$Name, [bool]$Exists=$true, [bool]$PullFails=$false,
          [string]$Volume='lifegather-preview-data', [string[]]$Environment=@(),
          [bool]$ExpectedFailure=$false, [string]$ImageVersion='0.59.0', [bool]$Multiple=$false)
    $global:TestLoginFixture=@{
        Exists=$Exists; PullFails=$PullFails; Volume=$Volume; Environment=$Environment
        Calls=[Collections.Generic.List[string]]::new(); ImageVersion=$ImageVersion; Multiple=$Multiple
    }
    $failed=$false
    try { & $launcher 6>$null } catch { $failed=$true }
    if ($failed -ne $ExpectedFailure) { throw "Unexpected result: $Name" }
    $calls=$global:TestLoginFixture.Calls
    if ($ExpectedFailure) {
        if ($calls | Where-Object { $_ -match '^(stop|rm|run) ' }) {
            throw "Preflight failure changed a container: $Name"
        }
    } else {
        $run=@($calls | Where-Object { $_ -match '^run ' })
        if ($run.Count -ne 1 -or $run[0] -notmatch 'LIFEGATHER_TEST_LOGIN_ENABLED=true' -or
            $run[0] -notmatch 'lifegather-preview-data:/data' -or
            $run[0] -notmatch '127.0.0.1:8787:8787' -or
            $run[0] -notmatch ('--name lifegather-preview-v' + [regex]::Escape($ImageVersion)) -or
            $run[0] -notmatch ('sha256:' + ('a' * 64))) { throw "Incorrect startup: $Name" }
        if ($Exists -and $calls.IndexOf('pull ghcr.io/bgoldbeck/life-gather:latest') -gt
            $calls.IndexOf('stop fixture-id')) { throw 'Must pull before stopping' }
    }
    if ($calls | Where-Object { $_ -match '^volume (rm|prune)' }) { throw 'Must preserve volumes' }
    Write-Host "PASS: $Name"
}
try {
    Test-Launcher 'replace existing preview'
    Test-Launcher 'first launch' -Exists $false
    Test-Launcher 'names the pulled version, independently of source' -ImageVersion '0.60.2'
    Test-Launcher 'invalid image version leaves app running' -ImageVersion 'unknown/latest' -ExpectedFailure $true
    Test-Launcher 'multiple previews are protected' -Multiple $true -ExpectedFailure $true
    Test-Launcher 'failed download leaves app running' -PullFails $true -ExpectedFailure $true
    Test-Launcher 'different data volume is protected' -Volume 'other-data' -ExpectedFailure $true
    Test-Launcher 'custom credentials are not discarded' -Environment @('LIFEGATHER_GOOGLE_CLIENT_SECRET=synthetic-secret') -ExpectedFailure $true
} finally {
    Remove-Item Function:global:docker
    Remove-Variable TestLoginFixture -Scope Global
}
