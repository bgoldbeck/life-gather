# Publish the commit tag plus latest, then recreate the test-login preview from it.
# Reuses both existing scripts unchanged; any failure stops before the next step.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    & (Join-Path $PSScriptRoot 'Publish-Container.ps1') -Publish -PublishLatest
} catch {
    Write-Host 'Publish failed. The preview was not started or changed.' -ForegroundColor Red
    throw
}
Write-Host "`nPublish finished. Starting the test-login preview from latest."
& (Join-Path $PSScriptRoot 'Start-Test-Login.ps1')
