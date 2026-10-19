# Real Git integration fixtures: all commits/remotes are temporary local files.
# Git URL rewrites keep the canonical origin configuration without network access.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$scriptsRoot = Split-Path -Parent $PSScriptRoot
$sourceHelper = Join-Path $scriptsRoot 'Update-ReleaseSource.ps1'
$publisher = Join-Path $scriptsRoot 'Publish-Container.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lifegather-source-tests-' + [guid]::NewGuid().ToString('N'))
$bare = Join-Path $testRoot 'remote.git'
$seed = Join-Path $testRoot 'seed'
$canonical = 'https://github.com/bgoldbeck/life-gather.git'

function Invoke-FixtureGit {
    param([string]$Directory, [string[]]$Arguments)
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $value = & git -c commit.gpgsign=false -C $Directory @Arguments 2>&1
        $nativeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($nativeExit -ne 0) { throw "Fixture git failed: $($Arguments -join ' '): $value" }
    return ($value -join "`n").Trim()
}
function New-FixtureClone {
    param([string]$Name)
    $directory = Join-Path $testRoot $Name
    $null = Invoke-FixtureGit $testRoot @('clone', '--quiet', '--branch', 'main', $bare, $directory)
    $null = Invoke-FixtureGit $directory @('config', 'user.name', 'Synthetic release test')
    $null = Invoke-FixtureGit $directory @('config', 'user.email', 'release@example.test')
    $null = Invoke-FixtureGit $directory @('config', 'remote.origin.url', $canonical)
    $localTransport = $bare.Replace('\', '/')
    $null = Invoke-FixtureGit $directory @('config', "url.$localTransport.insteadOf", $canonical)
    return $directory
}
function Commit-FixtureChange {
    param([string]$Directory, [string]$Text)
    Set-Content -LiteralPath (Join-Path $Directory 'fixture.txt') -Value $Text
    $null = Invoke-FixtureGit $Directory @('add', 'fixture.txt')
    $null = Invoke-FixtureGit $Directory @('commit', '--quiet', '-m', $Text)
}
function Assert-SourceStops {
    param([string]$Directory, [string]$Message, [switch]$Latest)
    $before = Invoke-FixtureGit $Directory @('rev-parse', 'HEAD')
    $staging = Invoke-FixtureGit $Directory @('diff', '--cached', '--name-only')
    $failed = $false
    try { $null = & $sourceHelper -RepositoryRoot $Directory -PublishLatest:$Latest }
    catch {
        $failed = $true
        if (-not $_.Exception.Message.Contains($Message)) { throw }
    }
    if (-not $failed) { throw "Expected source stop: $Message" }
    if ((Invoke-FixtureGit $Directory @('rev-parse', 'HEAD')) -ne $before -or
        (Invoke-FixtureGit $Directory @('diff', '--cached', '--name-only')) -ne $staging -or
        (Invoke-FixtureGit $Directory @('stash', 'list'))) {
        throw 'Source recovery changed protected commits/staging or created a stash'
    }
    Write-Host "PASS: $Message protects local work"
}

New-Item -ItemType Directory -Path $testRoot, $seed | Out-Null
try {
    $null = Invoke-FixtureGit $testRoot @('init', '--quiet', '--bare', '--initial-branch=main', $bare)
    $null = Invoke-FixtureGit $seed @('init', '--quiet', '--initial-branch=main')
    $null = Invoke-FixtureGit $seed @('config', 'user.name', 'Synthetic release test')
    $null = Invoke-FixtureGit $seed @('config', 'user.email', 'release@example.test')
    New-Item -ItemType Directory -Path (Join-Path $seed 'scripts') | Out-Null
    Copy-Item -LiteralPath $publisher -Destination (Join-Path $seed 'scripts/Publish-Container.ps1')
    Copy-Item -LiteralPath $sourceHelper -Destination (Join-Path $seed 'scripts/Update-ReleaseSource.ps1')
    Set-Content -LiteralPath (Join-Path $seed 'fixture.txt') -Value 'first'
    $null = Invoke-FixtureGit $seed @('add', 'fixture.txt', 'scripts')
    $null = Invoke-FixtureGit $seed @('commit', '--quiet', '-m', 'Initial synthetic source')
    $null = Invoke-FixtureGit $seed @('remote', 'add', 'origin', $bare)
    $null = Invoke-FixtureGit $seed @('push', '--quiet', 'origin', 'main')
    $behind = New-FixtureClone 'behind'
    $diverged = New-FixtureClone 'diverged'
    $reload = New-FixtureClone 'reload'
    $missingHelper = New-FixtureClone 'missing-helper'
    # Replace the publisher in the remote fixture. If old implementation executes
    # instead of reloading, it will reach real Docker commands and fail this test.
    @'
[CmdletBinding()]
param([switch]$Publish, [switch]$PublishLatest, [switch]$RepairAuthentication, [switch]$SourceUpdated)
if (-not $SourceUpdated) { throw 'Updated publisher was not reloaded with the loop guard' }
[pscustomobject]@{ marker='updated-script-loaded'; publish=[bool]$Publish; latest=[bool]$PublishLatest; repair=[bool]$RepairAuthentication } | ConvertTo-Json -Compress
'@ | Set-Content -LiteralPath (Join-Path $seed 'scripts/Publish-Container.ps1')
    Set-Content -LiteralPath (Join-Path $seed 'fixture.txt') -Value 'second'
    $null = Invoke-FixtureGit $seed @('add', 'fixture.txt', 'scripts/Publish-Container.ps1')
    $null = Invoke-FixtureGit $seed @('commit', '--quiet', '-m', 'Updated synthetic publisher')
    $null = Invoke-FixtureGit $seed @('push', '--quiet', 'origin', 'main')
    $remoteHead = Invoke-FixtureGit $seed @('rev-parse', 'HEAD')

    if (-not (& $sourceHelper -RepositoryRoot $behind -PublishLatest)) { throw 'Behind main did not update' }
    if ((Invoke-FixtureGit $behind @('rev-parse', 'HEAD')) -ne $remoteHead -or
        (Get-Content -LiteralPath (Join-Path $behind 'fixture.txt') -Raw).Trim() -ne 'second') {
        throw 'Fast-forward did not preserve expected commit and content'
    }
    Write-Host 'PASS: real fast-forward updates files to the exact remote commit'
    if (& $sourceHelper -RepositoryRoot $behind -PublishLatest -AlreadyUpdated) { throw 'Up-to-date source updated twice' }
    Write-Host 'PASS: up-to-date main does not create another update'

    $loaded = & (Join-Path $reload 'scripts/Publish-Container.ps1') -Publish -PublishLatest -RepairAuthentication
    $result = ($loaded -join "`n") | ConvertFrom-Json
    if ($result.marker -ne 'updated-script-loaded' -or -not $result.publish -or -not $result.latest -or -not $result.repair) {
        throw 'Reload did not preserve publishing/authentication options'
    }
    Write-Host 'PASS: updated publisher is actually reloaded once with original flags'

    Remove-Item -LiteralPath (Join-Path $missingHelper 'scripts/Update-ReleaseSource.ps1')
    $failed = $false
    try { $null = & (Join-Path $missingHelper 'scripts/Publish-Container.ps1') -CheckOnly }
    catch { $failed = $true }
    if (-not $failed) { throw 'A missing source helper must not bypass source checks' }
    Write-Host 'PASS: missing helper fails closed before publisher implementation'

    foreach ($mode in @('tracked', 'staged', 'untracked')) {
        $dirty = New-FixtureClone ('dirty-' + $mode)
        $name = if ($mode -eq 'untracked') { 'private-untracked.txt' } else { 'fixture.txt' }
        $path = Join-Path $dirty $name
        Set-Content -LiteralPath $path -Value 'preserve my local changes'
        if ($mode -eq 'staged') { $null = Invoke-FixtureGit $dirty @('add', $name) }
        $hash = (Get-FileHash -LiteralPath $path).Hash
        Assert-SourceStops $dirty 'Commit or safely stash'
        if ((Get-FileHash -LiteralPath $path).Hash -ne $hash) { throw 'Dirty file content changed' }
    }
    $ahead = New-FixtureClone 'ahead'
    Commit-FixtureChange $ahead 'Local-only commit'
    Assert-SourceStops $ahead 'local-only commits'
    Commit-FixtureChange $diverged 'Diverged local commit'
    Assert-SourceStops $diverged 'diverged'

    $feature = New-FixtureClone 'feature'
    $null = Invoke-FixtureGit $feature @('switch', '--quiet', '-c', 'feature/synthetic')
    Commit-FixtureChange $feature 'Feature change'
    $head = Invoke-FixtureGit $feature @('rev-parse', 'HEAD')
    if (& $sourceHelper -RepositoryRoot $feature) { throw 'Feature source was updated' }
    if ((Invoke-FixtureGit $feature @('rev-parse', 'HEAD')) -ne $head) { throw 'Feature commit changed' }
    Write-Host 'PASS: feature commit builds preserve their branch and revision'
    Assert-SourceStops $feature 'main branch' -Latest

    $detached = New-FixtureClone 'detached'
    $null = Invoke-FixtureGit $detached @('switch', '--quiet', '--detach')
    if (& $sourceHelper -RepositoryRoot $detached) { throw 'Detached source was updated' }
    Write-Host 'PASS: detached commit builds preserve selected revision'
    Assert-SourceStops $detached 'main branch' -Latest

    $wrong = New-FixtureClone 'wrong-origin'
    $null = Invoke-FixtureGit $wrong @('config', 'remote.origin.url', 'https://example.invalid/other.git')
    Assert-SourceStops $wrong 'Origin must point'
    $unavailable = New-FixtureClone 'unavailable'
    $missing = (Join-Path $testRoot 'missing-remote.git').Replace('\', '/')
    $null = Invoke-FixtureGit $unavailable @('config', '--unset-all', "url.$($bare.Replace('\', '/')).insteadOf")
    $null = Invoke-FixtureGit $unavailable @('config', "url.$missing.insteadOf", $canonical)
    Assert-SourceStops $unavailable 'fetch failed'
} finally {
    # Verify the resolved recursive cleanup target is our exact temporary root.
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        -not ([IO.Path]::GetFileName($resolved)).StartsWith('lifegather-source-tests-')) {
        throw 'Refusing cleanup outside the verified temporary fixture root'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
