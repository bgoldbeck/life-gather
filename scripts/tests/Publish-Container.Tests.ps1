# Offline control-flow tests: no Docker, network, credentials, or registry writes.
$ErrorActionPreference = 'Stop'
$publisher = Join-Path (Split-Path -Parent $PSScriptRoot) 'Publish-Container.ps1'
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile($publisher, [ref]$null, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lifegather-release-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$global:LifeGatherFakeGh = Join-Path $testRoot 'gh.ps1'
Set-Content -LiteralPath $global:LifeGatherFakeGh -Value @'
if ($args[0] -eq 'auth' -and $args[1] -eq 'token') { 'synthetic-token' }
$global:LASTEXITCODE = 0
'@

function global:Get-Command {
    [CmdletBinding()]
    param([string]$Name)
    if ($Name -eq 'gh') { return [pscustomobject]@{ Source = $global:LifeGatherFakeGh } }
    Microsoft.PowerShell.Core\Get-Command $Name -ErrorAction SilentlyContinue
}
function global:git {
    $global:LASTEXITCODE = 0
    switch ($args[0]) {
        'status' { if ($global:LifeGatherReleaseTest.Dirty) { ' M fixture.txt' } }
        'rev-parse' { 'a' * 40 }
        'branch' { 'main' }
        'ls-remote' { ($global:LifeGatherReleaseTest.Remote + "`trefs/heads/main") }
        default { throw 'Unexpected git command' }
    }
}
function global:uv { $global:LASTEXITCODE = 0 }
function global:npm { $global:LASTEXITCODE = 0 }
function global:Read-Host {
    param([string]$Prompt)
    if ($global:LifeGatherReleaseTest.Answers.Count -eq 0) { throw "Unexpected prompt: $Prompt" }
    $global:LifeGatherReleaseTest.Answers.Dequeue()
}
function global:docker {
    $global:LASTEXITCODE = 0
    $arguments = @($args)
    if ($arguments[0] -eq '--config') { $arguments = @($arguments | Select-Object -Skip 4) }
    switch ($arguments[0]) {
        'info' { 'linux' }
        'image' {
            if ($arguments[1] -eq 'inspect') { '53723398' }
            elseif ($arguments -contains '--quiet') { 'fixture-image' }
            else { '222MB' }
        }
        'compose' { }
        'build' {
            if ($arguments -notcontains '--progress=plain') {
                throw 'Build must show readable plain progress'
            }
            if ($arguments -notcontains ('APP_REVISION=' + ('a' * 40)) -or
                -not ($arguments | Where-Object { $_ -match '^org.opencontainers.image.version=\d+\.\d+\.\d+$' })) {
                throw 'Build must embed the revision and application version label'
            }
            $global:LifeGatherReleaseTest.Builds++
            if ($global:LifeGatherReleaseTest.BuildFailure) { $global:LASTEXITCODE = 1 }
        }
        'run' { 'fixture-container' }
        'inspect' { 'healthy' }
        'exec' {
            $script = $input -join "`n"
            if ($script -notmatch '8787' -or $script -notmatch 'auth.sqlite3') { throw 'Smoke checks missing' }
            if ($script -notmatch "'email_password_enabled': False" -or
                $script -notmatch "'email_delivery_enabled': False") {
                throw 'Smoke checks must verify unconfigured email authentication'
            }
        }
        'rm' { }
        'context' {
            if ($arguments -contains '--format') {
                throw 'Use JSON context inspection to avoid Windows quote stripping'
            }
            '[{"Endpoints":{"docker":{"Host":"npipe:////./pipe/dockerDesktopLinuxEngine"}}}]'
        }
        'login' { $null = $input | Out-String }
        'push' { $global:LifeGatherReleaseTest.Pushes++ }
        'tag' { }
        default { throw "Unexpected docker command: $arguments" }
    }
}

function Test-Release {
    param(
        [string]$Name, [hashtable]$Flags = @{}, [string[]]$Answers,
        [bool]$Dirty = $false, [bool]$BuildFailure = $false,
        [string]$Remote = ('a' * 40), [int]$ExpectedBuilds = 0,
        [int]$ExpectedPushes = 0, [bool]$ExpectFailure = $false
    )
    $queue = New-Object 'System.Collections.Generic.Queue[string]'
    foreach ($answer in $Answers) { $queue.Enqueue($answer) }
    $global:LifeGatherReleaseTest = @{
        Dirty = $Dirty; BuildFailure = $BuildFailure; Remote = $Remote
        Answers = $queue; Builds = 0; Pushes = 0
    }
    $failed = $false
    $captured = New-Object System.Text.StringBuilder
    try { & $publisher @Flags 6>&1 | ForEach-Object { [void]$captured.AppendLine($_.ToString()) } }
    catch { $failed = $true; if (-not $ExpectFailure) { Write-Host $_.Exception.Message } }
    $output = $captured.ToString()
    if ($failed -ne $ExpectFailure -or
        $global:LifeGatherReleaseTest.Builds -ne $ExpectedBuilds -or
        $global:LifeGatherReleaseTest.Pushes -ne $ExpectedPushes) {
        throw "FAIL: $Name (failure=$failed builds=$($global:LifeGatherReleaseTest.Builds) pushes=$($global:LifeGatherReleaseTest.Pushes))"
    }
    if ($output -match 'synthetic-token') { throw 'Registry token leaked in logs' }
    $expectedResult = if ($ExpectFailure) { 'FAILED' }
        elseif ($Flags.CheckOnly) { 'CHECKS PASSED' }
        elseif ($ExpectedBuilds -eq 0) { 'BUILD DEFERRED' }
        elseif ($ExpectedPushes -gt 0) { 'PUBLISHED' }
        elseif ($Flags.Publish) { 'UPLOAD DEFERRED' }
        else { 'BUILT (no upload)' }
    if (-not $output.Contains("Result: $expectedResult")) {
        throw "FAIL: $Name must show explicit result '$expectedResult'"
    }
    if ($Dirty -and -not $output.Contains('fixture.txt')) { throw 'Dirty-source refusal must name the uncommitted paths' }
    if (-not $ExpectFailure -and $ExpectedBuilds -gt 0 -and
        ($output -notmatch 'Stage: Build' -or $output -notmatch 'completed in')) {
        throw 'Expected named stages and command elapsed-time output'
    }
    Write-Host "PASS: $Name"
}

try {
    $launcher = Get-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'Publish-Container.cmd') -Raw
    if ($launcher -notmatch '-Publish -PublishLatest' -or $launcher -notmatch '%~dp0Publish-Container.ps1' -or $launcher -notmatch 'exit /b %result%') {
        throw 'Launcher must preserve the guarded publisher flags and exit code'
    }
    Test-Release 'dirty checkout stops early' -Dirty $true -ExpectFailure $true
    Test-Release 'check-only never builds' -Flags @{ CheckOnly = $true }
    Test-Release 'declining build stops' -Answers @('n')
    Test-Release 'build-only never pushes' -Answers @('y') -ExpectedBuilds 1
    Test-Release 'failed build never pushes' -Flags @{ Publish = $true } -Answers @('y') -BuildFailure $true -ExpectedBuilds 1 -ExpectFailure $true
    Test-Release 'declining upload retains build' -Flags @{ Publish = $true } -Answers @('y', 'n') -ExpectedBuilds 1
    Test-Release 'unmerged latest is rejected' -Flags @{ Publish = $true; PublishLatest = $true } -Remote ('b' * 40) -ExpectFailure $true
    Test-Release 'approved commit tag uploads' -Flags @{ Publish = $true } -Answers @('y', 'y') -ExpectedBuilds 1 -ExpectedPushes 1
    Test-Release 'approved latest uploads both tags' -Flags @{ Publish = $true; PublishLatest = $true } -Answers @('y', 'y') -ExpectedBuilds 1 -ExpectedPushes 2
} finally {
    foreach ($name in @('Get-Command', 'git', 'uv', 'npm', 'Read-Host', 'docker')) {
        Remove-Item -LiteralPath "Function:\$name"
    }
    Remove-Item -LiteralPath $global:LifeGatherFakeGh
    Remove-Item -LiteralPath $testRoot
    Remove-Variable LifeGatherFakeGh, LifeGatherReleaseTest -Scope Global -ErrorAction SilentlyContinue
}
