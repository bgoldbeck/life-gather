# Offline menu/setup checks. No real installers, credentials or Docker operations.
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'Container-Helper.ps1')
$script:Available = @()
$script:Engine = 'linux'
$script:Auth = 0
$script:InstallExit = 0
$script:Calls = [Collections.Generic.List[string]]::new()
function Get-Command {
    param([string]$Name, $ErrorAction)
    if ($Name -in $script:Available) { [pscustomobject]@{ Source = $Name } }
}
function docker {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'info') { $script:Engine }
}
function gh { $global:LASTEXITCODE = $script:Auth; $script:Calls.Add('gh ' + ($args -join ' ')) }
function winget { $global:LASTEXITCODE = $script:InstallExit; $script:Calls.Add('winget ' + ($args -join ' ')) }
function Update-HelperPath { }

$state = @(Get-HelperState)
if (@($state | Where-Object Status -eq 'MISSING').Count -ne 3) { throw 'Fresh machine must identify three missing tools, including optional GitHub CLI' }
Write-Host 'PASS: missing prerequisites are visible without executing them'
$script:Available = @('git', 'docker')
$script:Engine = 'windows'
$state = @(Get-HelperState)
if (($state | Where-Object Component -eq 'Linux engine').Status -ne 'ACTION NEEDED') { throw 'Windows engine must need action' }
$failed = $false
try { Invoke-HelperRelease Build } catch { $failed = $true }
if (-not $failed) { throw 'Unavailable Linux engine must block builds' }
Write-Host 'PASS: Windows engine blocks builds with recovery guidance'

$script:Calls.Clear()
Install-HelperComponent Git
if ($script:Calls.Count) { throw 'Missing winget must not execute an installer' }
$script:Available += 'winget'
Install-HelperComponent GitHub
if ($script:Calls[-1] -notmatch 'install --id GitHub.cli --exact --source winget') { throw 'Setup must use the exact official package ID' }
$script:InstallExit = 7
$failed = $false
try { Install-HelperComponent Docker } catch { $failed = $_.Exception.Message -match 'exit 7' }
if (-not $failed) { throw 'Installer failure must be reported' }
Write-Host 'PASS: setup has a download fallback and preserves installer failure'

$script:Available += 'gh'
$script:Auth = 1
$failed = $false
try { Connect-HelperGitHub } catch { $failed = $true }
if (-not $failed -or $script:Calls[-1] -notmatch 'auth login.*--web.*write:packages') { throw 'Login must use browser authorization and surface cancellation' }
$script:Auth = 0
Connect-HelperGitHub
if ($script:Calls[-1] -notmatch 'auth refresh.*write:packages') { throw 'Existing login must offer scope recovery' }
Write-Host 'PASS: browser login, canceled login and scope recovery'

# Exercise the real menu loop, replacing only its terminal input and actions.
$script:Choices = [Collections.Generic.Queue[string]]::new()
@('invalid', '4', '', '5', '', '6', '', '7', 'cancel', '', '7', 'REBUILD', '', '0') | ForEach-Object { $script:Choices.Enqueue($_) }
function Read-Host { param($Prompt); if (-not $script:Choices.Count) { throw 'Unexpected menu input' }; $script:Choices.Dequeue() }
function Invoke-HelperRelease { param($Action); $script:Calls.Add("release $Action"); if ($Action -eq 'Check') { throw 'synthetic verification failure' } }
$script:Calls.Clear()
$captured = Show-HelperMenu 6>&1 | Out-String
if ((($script:Calls | Where-Object { $_ -like 'release *' }) -join '|') -ne 'release Check|release Build|release Publish|release Force') { throw ('Unexpected menu actions: ' + ($script:Calls -join '|')) }
if ($captured -notmatch 'Action failed' -or $captured -notmatch 'Force rebuild canceled') { throw 'Menu must retain errors and cancellations' }
Write-Host 'PASS: invalid input, verify/build/publish/force routing, cancellation and recovery after failure'
