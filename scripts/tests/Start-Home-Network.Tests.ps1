# Offline checks only: firewall, network, Docker and prompt commands are stubs, and
# the preview script is replaced by a stub in a temporary copy.
$ErrorActionPreference = 'Stop'
$source = Join-Path (Split-Path -Parent $PSScriptRoot) 'Start-Home-Network.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lifegather home network tests ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$stubs = @('net', 'Start-Process', 'Read-Host', 'Get-NetConnectionProfile', 'Set-NetConnectionProfile',
    'Get-NetFirewallRule', 'Remove-NetFirewallRule', 'New-NetFirewallRule', 'Disable-NetFirewallRule',
    'Invoke-WebRequest', 'Start-Sleep', 'docker', 'Get-NetIPConfiguration')
function global:Add-HomeCall { param([string]$Call) $global:HomeFixture.Calls.Add($Call) }
function global:net { $global:LASTEXITCODE = [int](-not $global:HomeFixture.Admin) }
function global:Start-Process {
    param($FilePath, $Verb, [switch]$Wait, [switch]$PassThru, [string[]]$ArgumentList)
    Add-HomeCall "elevate $FilePath $Verb $($ArgumentList -join ' ')"; [pscustomobject]@{ ExitCode = 0 }
}
function global:Read-Host { param([string]$Prompt) Add-HomeCall "ask $Prompt"; $global:HomeFixture.Answer }
function global:Get-NetConnectionProfile {
    [pscustomobject]@{ Name = 'Home Wi-Fi'; InterfaceIndex = 7; NetworkCategory = $global:HomeFixture.Category }
}
function global:Set-NetConnectionProfile { param($InterfaceIndex, $NetworkCategory) Add-HomeCall "profile $InterfaceIndex $NetworkCategory" }
function global:Get-NetFirewallRule {
    param($Name, $Direction, $Action, $Enabled)
    if ($Name) { if ($global:HomeFixture.RuleExists) { [pscustomobject]@{ Name = $Name } }; return }
    [pscustomobject]@{ Name = 'docker-block'; DisplayName = 'Docker Desktop Backend' }
    [pscustomobject]@{ Name = 'other-block'; DisplayName = 'Some game' }
}
function global:Remove-NetFirewallRule { param($Name) Add-HomeCall "remove $Name" }
function global:New-NetFirewallRule {
    param($Name, $DisplayName, $Description, $Direction, $Action, $Protocol, $LocalPort, $Profile, $RemoteAddress)
    Add-HomeCall "allow $Name $Direction $Action $Protocol $LocalPort $Profile $RemoteAddress"
}
function global:Disable-NetFirewallRule { param($Name) Add-HomeCall "disable $Name" }
function global:Invoke-WebRequest { if (-not $global:HomeFixture.Healthy) { throw 'refused' }; [pscustomobject]@{ StatusCode = 200 } }
function global:Start-Sleep {}
function global:docker {
    $global:LASTEXITCODE = 0
    Add-HomeCall "docker $($args -join ' ')"
    if ($args[0] -eq 'container') { 'preview-id' }
}
function global:Get-NetIPConfiguration {
    [pscustomobject]@{ IPv4DefaultGateway = 'gateway'; IPv4Address = [pscustomobject]@{ IPAddress = '192.168.1.111' } }
    [pscustomobject]@{ IPv4DefaultGateway = $null; IPv4Address = [pscustomobject]@{ IPAddress = '172.20.0.1' } }
}
function Test-HomeNetwork {
    param([string]$Name, [bool]$Admin = $true, [string]$Answer = 'y', [string]$Category = 'Public',
          [bool]$RuleExists = $false, [bool]$Healthy = $true, [bool]$StartFails = $false,
          [bool]$ExpectedFailure = $false, [string[]]$Expected = @(), [string[]]$Forbidden = @())
    $global:HomeFixture = @{
        Admin = $Admin; Answer = $Answer; Category = $Category; RuleExists = $RuleExists; Healthy = $Healthy
        StartFails = $StartFails; Calls = [Collections.Generic.List[string]]::new()
    }
    $failed = $false
    $global:LASTEXITCODE = 0
    $output = try { & $script 6>&1 | Out-String } catch { $failed = $true; '' }
    if ($LASTEXITCODE -ne 0) { $failed = $true }
    if ($failed -ne $ExpectedFailure) { throw "Unexpected result: $Name" }
    $calls = $global:HomeFixture.Calls
    foreach ($pattern in $Expected) {
        if (-not ($calls | Where-Object { $_ -match $pattern })) { throw "${Name}: missing '$pattern' in $($calls -join ' | ')" }
    }
    foreach ($pattern in $Forbidden) {
        if ($calls | Where-Object { $_ -match $pattern }) { throw "${Name}: unexpected '$pattern' in $($calls -join ' | ')" }
    }
    Write-Host "PASS: $Name"
    return $output
}
try {
    Copy-Item -LiteralPath $source -Destination $testRoot
    $script = Join-Path $testRoot 'Start-Home-Network.ps1'
    Set-Content -LiteralPath (Join-Path $testRoot 'Start-Test-Login.ps1') -Value (
        "param([switch]`$HomeNetwork)`nAdd-HomeCall ('start' + `$(if (`$HomeNetwork) {' -HomeNetwork'}))`n" +
        "if (`$global:HomeFixture.StartFails) { throw 'start fixture failure' }")

    $output = Test-HomeNetwork 'sets up the firewall and home network preview' -Expected @(
        '^profile 7 Private$', '^allow LifeGather-Home-Network Inbound Allow TCP 8787 Private LocalSubnet$',
        '^disable docker-block$', '^start -HomeNetwork$', '^docker exec -it preview-id python -m lifegather.setup_account$'
    ) -Forbidden @('^remove ', '^disable other-block$', '^elevate ')
    if ($output -notmatch 'http://192\.168\.1\.111:8787' -or $output -match '172\.20\.0\.1') { throw 'Must show only the Wi-Fi address' }
    Test-HomeNetwork 'replaces its own rule instead of adding a second one' -RuleExists $true -Expected @(
        '^remove LifeGather-Home-Network$', '^allow LifeGather-Home-Network ') | Out-Null
    Test-HomeNetwork 'leaves a network public, docker rules and sign-ins alone when told no' -Answer 'n' -Expected @(
        '^allow ', '^start -HomeNetwork$') -Forbidden @('^profile ', '^disable ', 'setup_account') | Out-Null
    Test-HomeNetwork 'does not ask about a private network' -Category 'Private' -Forbidden @(
        '^profile ', 'ask .*public') | Out-Null
    Test-HomeNetwork 'asks Windows for administrator rights first' -Admin $false -Expected @(
        '^elevate .*RunAs.*-Elevated') -Forbidden @('^allow ', '^start ', '^profile ') | Out-Null
    Test-HomeNetwork 'stops when the preview does not start' -StartFails $true -ExpectedFailure $true -Forbidden @(
        'setup_account') | Out-Null
    Test-HomeNetwork 'stops when the preview never becomes healthy' -Healthy $false -ExpectedFailure $true -Forbidden @(
        'setup_account') | Out-Null
} finally {
    foreach ($name in $stubs + 'Add-HomeCall') { Remove-Item "Function:global:$name" -ErrorAction SilentlyContinue }
    Remove-Variable HomeFixture -Scope Global -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
