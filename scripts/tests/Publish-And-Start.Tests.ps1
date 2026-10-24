# Offline checks only: the real publisher and preview scripts are replaced by
# stubs in a temporary copy, so no Docker, credential or registry access occurs.
$ErrorActionPreference = 'Stop'
$source = Join-Path (Split-Path -Parent $PSScriptRoot) 'Publish-And-Start.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lifegather publish-start tests ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    Copy-Item -LiteralPath $source -Destination $testRoot
    $combined = Join-Path $testRoot 'Publish-And-Start.ps1'
    $stub = {
        param([string]$Name)
        "param([switch]`$Publish, [switch]`$PublishLatest, [switch]`$KeepMode)`n" +
        "`$global:PublishStartCalls.Add('$Name' + `$(if (`$Publish) {' -Publish'}) + `$(if (`$PublishLatest) {' -PublishLatest'}) + `$(if (`$KeepMode) {' -KeepMode'}))`n" +
        "if (`$global:PublishStartFail -eq '$Name') { throw '$Name fixture failure' }`n"
    }
    Set-Content -LiteralPath (Join-Path $testRoot 'Publish-Container.ps1') -Value (& $stub 'publish')
    Set-Content -LiteralPath (Join-Path $testRoot 'Start-Test-Login.ps1') -Value (& $stub 'start')
    foreach ($case in @(
        @{ Fail=''; Failed=$false; Calls='publish -Publish -PublishLatest|start -KeepMode' },
        @{ Fail='publish'; Failed=$true; Calls='publish -Publish -PublishLatest' },
        @{ Fail='start'; Failed=$true; Calls='publish -Publish -PublishLatest|start -KeepMode' }
    )) {
        $global:PublishStartCalls = [Collections.Generic.List[string]]::new()
        $global:PublishStartFail = $case.Fail
        $failed = $false
        try { & $combined 6>$null } catch { $failed = $true }
        if ($failed -ne $case.Failed) { throw "Unexpected result when failing '$($case.Fail)'" }
        if (($global:PublishStartCalls -join '|') -ne $case.Calls) {
            throw "Unexpected calls when failing '$($case.Fail)': $($global:PublishStartCalls -join '|')"
        }
        Write-Host "PASS: failing '$($case.Fail)' ran $($case.Calls)"
    }
} finally {
    Remove-Variable -Name PublishStartCalls, PublishStartFail -Scope Global -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
