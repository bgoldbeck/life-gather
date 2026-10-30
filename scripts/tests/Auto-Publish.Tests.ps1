# Offline checks for Auto-Publish.ps1: a local bare repository stands in for
# GitHub and stub publisher/Docker scripts record calls, so nothing is built,
# uploaded or scheduled. Run:
# powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tests\Auto-Publish.Tests.ps1
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$source = Join-Path (Split-Path -Parent $PSScriptRoot) 'Auto-Publish.ps1'
$shell = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lifegather auto-publish tests ' + [guid]::NewGuid().ToString('N'))
$state = Join-Path $testRoot 'state'
$calls = Join-Path $testRoot 'calls.txt'
$bare = Join-Path $testRoot 'remote.git'
$seed = Join-Path $testRoot 'seed'
$passed = 0

function Invoke-Git([string[]]$Arguments) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $value = & git -c commit.gpgsign=false @Arguments 2>&1 } finally { $ErrorActionPreference = $saved }
    if ($LASTEXITCODE -ne 0) { throw "Fixture git failed: $($Arguments -join ' '): $value" }
    return ($value -join "`n").Trim()
}
function New-Commit([string]$Text) {
    Set-Content -LiteralPath (Join-Path $seed 'change.txt') -Value $Text
    $null = Invoke-Git @('-C', $seed, 'add', '.')
    $null = Invoke-Git @('-C', $seed, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--quiet', '-m', $Text)
    $null = Invoke-Git @('-C', $seed, 'push', '--quiet', 'origin', 'HEAD:refs/heads/main')
    return Invoke-Git @('-C', $seed, 'rev-parse', 'HEAD')
}
function Invoke-AutoPublish([string[]]$Extra = @()) {
    $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $source,
        '-StateDirectory', $state, '-Publisher', (Join-Path $testRoot 'publisher.ps1'),
        '-Docker', (Join-Path $testRoot 'docker.ps1'), '-SourceUrl', $bare) + $Extra
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $null = & $shell @arguments 2>&1 } finally { $ErrorActionPreference = $saved }
    return $LASTEXITCODE
}
function Read-Calls { if (Test-Path -LiteralPath $calls) { return (Get-Content -LiteralPath $calls) -join '|' } return '' }
function Read-State([string]$Name) {
    $path = Join-Path $state $Name
    if (Test-Path -LiteralPath $path) { return (Get-Content -LiteralPath $path -Raw).Trim() }
    return ''
}
function Assert-True([string]$Name, [bool]$Condition) {
    if (-not $Condition) { throw "FAIL: $Name" }
    $script:passed++
}

New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    $null = Invoke-Git @('init', '--quiet', '--bare', $bare)
    $null = Invoke-Git @('init', '--quiet', $seed)
    $null = Invoke-Git @('-C', $seed, 'remote', 'add', 'origin', $bare)
    # Stubs: the publisher records its switches and fails when asked to.
    Set-Content -LiteralPath (Join-Path $testRoot 'publisher.ps1') -Value @"
param([switch]`$Publish, [switch]`$PublishLatest)
Add-Content -LiteralPath '$calls' -Value ('publish' + `$(if (`$Publish) {' -Publish'}) + `$(if (`$PublishLatest) {' -PublishLatest'}))
Write-Host 'publisher output'
if (`$env:STUB_PUBLISH_FAIL) { throw 'publisher fixture failure' }
"@
    Set-Content -LiteralPath (Join-Path $testRoot 'docker.ps1') -Value "if (-not `$env:STUB_DOCKER_DOWN) { 'linux' }"

    $first = New-Commit 'one'
    $env:STUB_DOCKER_DOWN = '1'
    Assert-True 'docker down exits 0' ((Invoke-AutoPublish) -eq 0)
    Assert-True 'docker down: publisher not run' ((Read-Calls) -eq '')
    Remove-Item Env:STUB_DOCKER_DOWN

    Assert-True 'new commit publishes' ((Invoke-AutoPublish) -eq 0)
    Assert-True 'publishes latest' ((Read-Calls) -eq 'publish -Publish -PublishLatest')
    Assert-True 'records the published commit' ((Read-State 'last-published-revision') -eq $first)
    $log = Get-Content -LiteralPath (Join-Path $state 'auto-publish.log') -Raw
    Assert-True 'logs publisher output and result' ($log -match 'publisher output' -and $log -match 'Result: OK')

    Remove-Item -LiteralPath $calls
    Assert-True 'up to date exits 0' ((Invoke-AutoPublish) -eq 0)
    Assert-True 'up to date: publisher not run' ((Read-Calls) -eq '')

    $second = New-Commit 'two'
    $env:STUB_PUBLISH_FAIL = '1'
    Assert-True 'failed publish exits 1' ((Invoke-AutoPublish) -eq 1)
    Assert-True 'records the failed commit' ((Read-State 'last-failed-revision') -eq $second)
    Assert-True 'failure keeps the last published commit' ((Read-State 'last-published-revision') -eq $first)
    Remove-Item -LiteralPath $calls
    Assert-True 'failed commit waits' ((Invoke-AutoPublish) -eq 0)
    Assert-True 'failed commit is not retried at once' ((Read-Calls) -eq '')
    (Get-Item -LiteralPath (Join-Path $state 'last-failed-revision')).LastWriteTimeUtc = [DateTime]::UtcNow.AddHours(-7)
    $null = Invoke-AutoPublish
    Assert-True 'failed commit is retried after six hours' ((Read-Calls) -eq 'publish -Publish -PublishLatest')
    Remove-Item Env:STUB_PUBLISH_FAIL
    Remove-Item -LiteralPath $calls
    Assert-True '-Force retries at once' ((Invoke-AutoPublish @('-Force')) -eq 0)
    Assert-True 'success clears the failure' (-not (Test-Path -LiteralPath (Join-Path $state 'last-failed-revision')))
    Assert-True 'success records the commit' ((Read-State 'last-published-revision') -eq $second)

    $null = New-Commit 'three'
    Remove-Item -LiteralPath $calls
    $mutex = New-Object Threading.Mutex($true, 'Local\LifeGather-AutoPublish')
    try {
        Assert-True 'held lock exits 0' ((Invoke-AutoPublish) -eq 0)
        Assert-True 'held lock: publisher not run' ((Read-Calls) -eq '')
    } finally { $mutex.ReleaseMutex(); $mutex.Dispose() }

    Write-Host "Auto-Publish.ps1: $passed checks passed."
} finally {
    Remove-Item Env:STUB_DOCKER_DOWN, Env:STUB_PUBLISH_FAIL -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
