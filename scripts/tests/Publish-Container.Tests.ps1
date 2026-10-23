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
if ($args[0] -eq 'auth' -and $args[1] -eq 'status' -and $global:LifeGatherReleaseTest.NoAuth) {
    $global:LASTEXITCODE = 1
    return
}
if ($args[0] -eq 'auth' -and $args[1] -in @('login', 'refresh')) {
    $global:LifeGatherReleaseTest.AuthRepairs++
    if ($global:LifeGatherReleaseTest.AuthRepairFailure) {
        $global:LASTEXITCODE = 1
        return
    }
    $global:LifeGatherReleaseTest.NoAuth = $false
    $global:LifeGatherReleaseTest.Scopes = 'repo, write:packages'
}
if ($args[0] -eq 'api') {
    'HTTP/2.0 200 OK'
    if (-not $global:LifeGatherReleaseTest.NoScopeHeader) {
        'X-OAuth-Scopes: ' + $global:LifeGatherReleaseTest.Scopes
    }
    ''
    $global:LifeGatherReleaseTest.RegistryUser
}
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
        'rev-parse' {
            if ($args[1] -eq 'origin/main') { $global:LifeGatherReleaseTest.Remote }
            else { $global:LifeGatherReleaseTest.Head }
        }
        'branch' { $global:LifeGatherReleaseTest.Branch }
        'config' { 'https://github.com/bgoldbeck/life-gather.git' }
        'update-index' { }
        'fetch' {
            $global:LifeGatherReleaseTest.Fetches++
            if ($global:LifeGatherReleaseTest.FetchFailure) { $global:LASTEXITCODE = 1 }
            if ($global:LifeGatherReleaseTest.DirtyAfterFetch) { $global:LifeGatherReleaseTest.Dirty = $true }
            if ($global:LifeGatherReleaseTest.MoveAgain -and $global:LifeGatherReleaseTest.Fetches -gt 1) {
                $global:LifeGatherReleaseTest.Remote = 'c' * 40
            }
        }
        'merge-base' {
            $behind = $args[2] -eq 'HEAD'
            if (($behind -and $global:LifeGatherReleaseTest.Relation -ne 'behind') -or
                (-not $behind -and $global:LifeGatherReleaseTest.Relation -ne 'ahead')) {
                $global:LASTEXITCODE = 1
            }
        }
        'merge' {
            if ($args[1] -ne '--ff-only' -or $args[2] -ne 'origin/main') { throw 'Only fast-forward of fetched main is allowed' }
            $global:LifeGatherReleaseTest.Head = $global:LifeGatherReleaseTest.Remote
            $global:LifeGatherReleaseTest.Updates++
        }
        'ls-remote' { ($global:LifeGatherReleaseTest.Remote + "`trefs/heads/main") }
        default { throw 'Unexpected git command' }
    }
}
function global:uv {
    $global:LifeGatherReleaseTest.Checks++
    $global:LASTEXITCODE = 0
    if ($args -contains '../scripts/run_backend_tests.py') {
        $global:LifeGatherReleaseTest.BackendRuns++
        if ($global:LifeGatherReleaseTest.BackendFailure) { $global:LASTEXITCODE = 1 }
    }
}
function global:npm { $global:LifeGatherReleaseTest.Checks++; $global:LASTEXITCODE = 0 }
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
            if ($global:LifeGatherReleaseTest.ContainerBuilder -and
                $arguments[-1] -like '*:sha-*' -and
                -not $global:LifeGatherReleaseTest.ImageLoaded) { return }
            if ($arguments[1] -eq 'inspect') { '53723398' }
            elseif ($arguments -contains '--quiet') { 'fixture-image' }
            else { '222MB' }
        }
        'compose' { }
        'build' {
            if ($arguments -notcontains '--progress=plain') {
                throw 'Build must show readable plain progress'
            }
            if ($arguments -notcontains ('APP_REVISION=' + $global:LifeGatherReleaseTest.Head) -or
                -not ($arguments | Where-Object { $_ -match '^org.opencontainers.image.version=\d+\.\d+\.\d+$' })) {
                throw 'Build must embed the revision and application version label'
            }
            $global:LifeGatherReleaseTest.Builds++
            $global:LifeGatherReleaseTest.ImageLoaded =
                -not $global:LifeGatherReleaseTest.ContainerBuilder -or $arguments -contains '--load'
            if ($global:LifeGatherReleaseTest.SwitchAccount) {
                $global:LifeGatherReleaseTest.RegistryUser = 'changed-account'
            }
            if ($global:LifeGatherReleaseTest.BuildFailure) { $global:LASTEXITCODE = 1 }
        }
        'run' {
            if ($arguments[-1] -eq 'pgvector/pgvector:pg17') {
                if ($arguments -notcontains 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C') {
                    throw 'Test databases must use byte-order collation'
                }
                $global:LifeGatherReleaseTest.Databases++
                return 'fixture-database'
            }
            if ($arguments -notcontains '--network') { throw 'Smoke container must use the private database network' }
            if (-not $global:LifeGatherReleaseTest.ImageLoaded) {
                $global:LASTEXITCODE = 125
                return
            }
            'fixture-container'
        }
        'inspect' { 'healthy' }
        'exec' {
            if ($arguments -contains 'pg_isready') { return }
            $script = $input -join "`n"
            if ($script -notmatch '8787' -or $script -notmatch 'alembic_version') { throw 'Smoke checks missing' }
            if ($script -notmatch "'email_password_enabled': False" -or
                $script -notmatch "'email_delivery_enabled': False") {
                throw 'Smoke checks must verify unconfigured email authentication'
            }
        }
        'rm' { }
        'port' { '127.0.0.1:55432' }
        'network' { }
        'context' {
            if ($arguments -contains '--format') {
                throw 'Use JSON context inspection to avoid Windows quote stripping'
            }
            '[{"Endpoints":{"docker":{"Host":"npipe:////./pipe/dockerDesktopLinuxEngine"}}}]'
        }
        'login' {
            $null = $input | Out-String
            $username = $arguments[[array]::IndexOf($arguments, '--username') + 1]
            if ($username -ne $global:LifeGatherReleaseTest.RegistryUser) {
                throw 'Docker login must use the preflight authenticated account'
            }
        }
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
        [int]$ExpectedPushes = 0, [bool]$ExpectFailure = $false,
        [string]$Scopes = 'repo, write:packages', [bool]$NoScopeHeader = $false,
        [string]$RegistryUser = 'bgoldbeck', [string]$ExpectedMessage = '',
        [bool]$SwitchAccount = $false,
        [string]$Relation = 'diverged', [string]$Branch = 'main',
        [bool]$FetchFailure = $false, [bool]$MoveAgain = $false,
        [bool]$NoAuth = $false, [int]$ExpectedUpdates = 0, [int]$ExpectedAuthRepairs = 0,
        [bool]$AuthRepairFailure = $false, [bool]$DirtyAfterFetch = $false,
        [bool]$ContainerBuilder = $false, [bool]$BackendFailure = $false
    )
    $queue = New-Object 'System.Collections.Generic.Queue[string]'
    foreach ($answer in $Answers) { $queue.Enqueue($answer) }
    $global:LifeGatherReleaseTest = @{
        Dirty = $Dirty; BuildFailure = $BuildFailure; Remote = $Remote
        Answers = $queue; Builds = 0; Pushes = 0; Checks = 0; SwitchAccount = $SwitchAccount
        Scopes = $Scopes; NoScopeHeader = $NoScopeHeader; RegistryUser = $RegistryUser
        Head = ('a' * 40); Branch = $Branch; Relation = $Relation; FetchFailure = $FetchFailure
        Fetches = 0; Updates = 0; MoveAgain = $MoveAgain; NoAuth = $NoAuth; AuthRepairs = 0
        AuthRepairFailure = $AuthRepairFailure; DirtyAfterFetch = $DirtyAfterFetch
        ContainerBuilder = $ContainerBuilder; ImageLoaded = $false; Databases = 0
        BackendFailure = $BackendFailure; BackendRuns = 0
    }
    $failed = $false
    $captured = New-Object System.Text.StringBuilder
    try { & $publisher @Flags 6>&1 | ForEach-Object { [void]$captured.AppendLine($_.ToString()) } }
    catch {
        $failed = $true
        [void]$captured.AppendLine($_.Exception.Message)
        if (-not $ExpectFailure) { Write-Host $_.Exception.Message }
    }
    $output = $captured.ToString()
    if ($failed -ne $ExpectFailure -or
        $global:LifeGatherReleaseTest.Builds -ne $ExpectedBuilds -or
        $global:LifeGatherReleaseTest.Pushes -ne $ExpectedPushes) {
        throw "FAIL: $Name (failure=$failed builds=$($global:LifeGatherReleaseTest.Builds) pushes=$($global:LifeGatherReleaseTest.Pushes))"
    }
    if (-not $ExpectFailure -and $global:LifeGatherReleaseTest.BackendRuns -ne 1) { throw 'Must run Linux backend verification exactly once' }
    if ($output -match 'synthetic-token') { throw 'Registry token leaked in logs' }
    if (-not $ExpectFailure -and $global:LifeGatherReleaseTest.Databases -ne $ExpectedBuilds) {
        throw "FAIL: $Name must test against temporary PostgreSQL databases"
    }
    if ($global:LifeGatherReleaseTest.Updates -ne $ExpectedUpdates -or
        $global:LifeGatherReleaseTest.AuthRepairs -ne $ExpectedAuthRepairs) {
        throw "FAIL: $Name unexpected source update or authentication repair"
    }
    if ($ExpectFailure -and -not $BackendFailure -and $ExpectedBuilds -eq 0 -and $global:LifeGatherReleaseTest.Checks -ne 0) {
        throw 'Preflight refusal must happen before backend/frontend checks'
    }
    if ($ExpectedMessage -and -not $output.Contains($ExpectedMessage)) {
        throw "FAIL: $Name must explain '$ExpectedMessage'"
    }
    if ($Flags.Publish -and -not $Flags.RepairAuthentication -and ($NoScopeHeader -or $Scopes -notmatch '(?:^|,\s*)write:packages(?:\s*,|$)') -and
        $global:LifeGatherReleaseTest.Checks -ne 0) {
        throw 'Missing scope must fail before backend/frontend verification, not just before building'
    }
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
    Test-Release 'failed Linux shard cannot build or publish' -Flags @{ Publish = $true; PublishLatest = $true } -BackendFailure $true -ExpectFailure $true -ExpectedMessage 'Release stopped'
    Test-Release 'dirty checkout stops early' -Dirty $true -ExpectFailure $true
    Test-Release 'check-only never builds' -Flags @{ CheckOnly = $true }
    Test-Release 'build-only never pushes' -ExpectedBuilds 1
    Test-Release 'container builder loads its image for isolated smoke' -ContainerBuilder $true -ExpectedBuilds 1
    Test-Release 'failed build never pushes' -Flags @{ Publish = $true } -BuildFailure $true -ExpectedBuilds 1 -ExpectFailure $true
    Test-Release 'missing package scope stops before build' -Flags @{ Publish = $true } -Scopes 'gist, read:org, repo, workflow' -ExpectFailure $true -ExpectedMessage 'gh auth refresh --hostname github.com --scopes write:packages'
    Test-Release 'missing scope header fails closed' -Flags @{ Publish = $true } -NoScopeHeader $true -ExpectFailure $true -ExpectedMessage 'write:packages'
    Test-Release 'similar scope name is insufficient' -Flags @{ Publish = $true } -Scopes 'repo, write:packages-other' -ExpectFailure $true -ExpectedMessage 'write:packages'
    Test-Release 'unmerged latest is rejected' -Flags @{ Publish = $true; PublishLatest = $true } -Remote ('b' * 40) -ExpectFailure $true
    Test-Release 'scoped commit tag uploads' -Flags @{ Publish = $true } -ExpectedBuilds 1 -ExpectedPushes 1
    Test-Release 'scoped latest uploads both tags' -Flags @{ Publish = $true; PublishLatest = $true } -ExpectedBuilds 1 -ExpectedPushes 2
    Test-Release 'collaborator uses its actual login' -Flags @{ Publish = $true } -RegistryUser 'synthetic-collaborator' -ExpectedBuilds 1 -ExpectedPushes 1 -ExpectedMessage 'synthetic-collaborator'
    Test-Release 'changed account cannot upload' -Flags @{ Publish = $true } -SwitchAccount $true -ExpectedBuilds 1 -ExpectFailure $true -ExpectedMessage 'account changed during the build'
    Test-Release 'clean main updates then reloads before building' -Flags @{ Publish = $true; PublishLatest = $true } -Remote ('b' * 40) -Relation 'behind' -ExpectedUpdates 1 -ExpectedBuilds 1 -ExpectedPushes 2 -ExpectedMessage 'Reloading updated release script'
    Test-Release 'local main ahead is protected' -Remote ('b' * 40) -Relation 'ahead' -ExpectFailure $true -ExpectedMessage 'local-only commits'
    Test-Release 'diverged main is protected' -Remote ('b' * 40) -ExpectFailure $true -ExpectedMessage 'diverged'
    Test-Release 'fetch failure stops before checks' -FetchFailure $true -ExpectFailure $true -ExpectedMessage 'fetch'
    Test-Release 'second remote advance does not loop' -Remote ('b' * 40) -Relation 'behind' -MoveAgain $true -ExpectedUpdates 1 -ExpectFailure $true -ExpectedMessage 'moved again'
    Test-Release 'feature builds keep their selected revision' -Branch 'feature/synthetic' -Remote ('b' * 40) -ExpectedBuilds 1
    Test-Release 'latest refuses feature checkout before building' -Flags @{ Publish = $true; PublishLatest = $true } -Branch 'feature/synthetic' -ExpectFailure $true -ExpectedMessage 'main'
    Test-Release 'missing login explains optional recovery' -Flags @{ Publish = $true } -NoAuth $true -ExpectFailure $true -ExpectedMessage '-RepairAuthentication'
    Test-Release 'explicit login recovery continues' -Flags @{ Publish = $true; RepairAuthentication = $true } -NoAuth $true -ExpectedAuthRepairs 1 -ExpectedBuilds 1 -ExpectedPushes 1
    Test-Release 'explicit scope recovery continues' -Flags @{ Publish = $true; RepairAuthentication = $true } -Scopes 'repo' -ExpectedAuthRepairs 1 -ExpectedBuilds 1 -ExpectedPushes 1
    Test-Release 'denied authentication repair never builds' -Flags @{ Publish = $true; RepairAuthentication = $true } -NoAuth $true -AuthRepairFailure $true -ExpectedAuthRepairs 1 -ExpectFailure $true -ExpectedMessage 'Release stopped'
    Test-Release 'edits arriving during fetch prevent update' -Remote ('b' * 40) -Relation 'behind' -DirtyAfterFetch $true -ExpectFailure $true -ExpectedMessage 'checkout changed'
} finally {
    foreach ($name in @('Get-Command', 'git', 'uv', 'npm', 'Read-Host', 'docker')) {
        Remove-Item -LiteralPath "Function:\$name"
    }
    Remove-Item -LiteralPath $global:LifeGatherFakeGh
    Remove-Item -LiteralPath $testRoot
    Remove-Variable LifeGatherFakeGh, LifeGatherReleaseTest -Scope Global -ErrorAction SilentlyContinue
}
