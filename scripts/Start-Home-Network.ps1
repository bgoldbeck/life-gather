# Let phones on your home Wi-Fi reach the Windows preview: treat the Wi-Fi as a
# private network, allow port 8787 from the local network only in Windows
# Firewall, then restart the preview in home network mode. Never deletes volumes.
[CmdletBinding()]
param([switch]$Elevated)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$port = 8787
$ruleName = 'LifeGather-Home-Network'

function Confirm-Choice {
    param([string]$Question)
    return (Read-Host "$Question (Y/N)") -match '^\s*[Yy]'
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdministrator = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdministrator) {
    if ($Elevated) { throw 'Windows did not give administrator rights. Nothing was changed.' }
    Write-Host 'Windows will ask whether LifeGather may change the firewall. Click Yes.'
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), '-Elevated')
    if ($process.ExitCode -ne 0) { throw 'Home network setup did not finish. Read the error in the other window.' }
    exit 0
}

try {
    foreach ($network in @(Get-NetConnectionProfile)) {
        if ($network.NetworkCategory -ne 'Public') { continue }
        if (Confirm-Choice "Windows treats the network '$($network.Name)' as public, which blocks phones. Is it your own home network?") {
            Set-NetConnectionProfile -InterfaceIndex $network.InterfaceIndex -NetworkCategory Private
            Write-Host "'$($network.Name)' is now a private network."
        } else {
            Write-Host "Left '$($network.Name)' public. Phones on it can't reach LifeGather."
        }
    }

    if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -Name $ruleName }
    New-NetFirewallRule -Name $ruleName -DisplayName 'LifeGather (home network)' `
        -Description 'Lets phones on the home network open LifeGather. Private networks and the local subnet only.' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private -RemoteAddress LocalSubnet | Out-Null
    Write-Host "Windows Firewall now allows port $port from your home network only."

    # Clicking Cancel on Docker Desktop's first firewall prompt leaves block rules,
    # and a block rule wins over the allow rule above.
    foreach ($rule in @(Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -match 'docker' })) {
        if (Confirm-Choice "The firewall rule '$($rule.DisplayName)' blocks Docker, so phones can't connect. Turn it off?") {
            Disable-NetFirewallRule -Name $rule.Name
        }
    }

    & (Join-Path $PSScriptRoot 'Start-Test-Login.ps1') -HomeNetwork

    $healthy = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        try {
            if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$port/health").StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) { throw 'LifeGather did not start. Check the preview in Docker Desktop.' }

    $container = @(& docker container ls --quiet --filter 'name=^/lifegather-preview-v')[0]
    if (Confirm-Choice 'Create an email-and-password sign-in for your phone now? (Skip if you already have one)') {
        & docker exec -it $container python -m lifegather.setup_account
        if ($LASTEXITCODE -ne 0) { Write-Host 'The sign-in was not created. Run Start-Home-Network again to retry.' }
    }

    $addresses = @(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } |
        ForEach-Object { $_.IPv4Address.IPAddress })
    Write-Host ''
    Write-Host 'Done. In the LifeGather app on your phone, type:' -ForegroundColor Green
    foreach ($address in $addresses) { Write-Host "    http://${address}:$port" -ForegroundColor Green }
    Write-Host 'This PC keeps using http://127.0.0.1:8787. To go back to one-click test login on this PC only, run Start-Test-Login.'
} catch {
    Write-Host $_ -ForegroundColor Red
    if ($Elevated) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
if ($Elevated) { Read-Host 'Press Enter to close' | Out-Null }
