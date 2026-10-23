[CmdletBinding()]
param([switch]$StatusOnly)

function Update-HelperPath {
    # Pick up programs installed in this session without requiring a new terminal.
    $paths = @($env:PATH, [Environment]::GetEnvironmentVariable('PATH', 'Machine'), [Environment]::GetEnvironmentVariable('PATH', 'User'))
    $paths += @("$env:ProgramFiles/Git/cmd", "$env:ProgramFiles/Docker/Docker/resources/bin", "$env:ProgramFiles/GitHub CLI")
    $env:PATH = ((($paths -join ';') -split ';' | Where-Object { $_ } | Select-Object -Unique) -join ';')
}

function Get-HelperState {
    $ErrorActionPreference = 'Continue'
    $rows = @()
    foreach ($item in @(
        @{ Name = 'Git'; Command = 'git'; Required = 'Build' },
        @{ Name = 'Docker'; Command = 'docker'; Required = 'Build' },
        @{ Name = 'GitHub CLI'; Command = 'gh'; Required = 'Publish only' }
    )) {
        $present = [bool](Get-Command $item.Command -ErrorAction SilentlyContinue)
        $rows += [pscustomobject]@{ Component = $item.Name; Status = $(if ($present) { 'READY' } else { 'MISSING' }); Detail = $item.Required }
    }
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $engine = & docker info --format '{{.OSType}}' 2>$null
        $ready = $LASTEXITCODE -eq 0 -and ($engine -join '').Trim() -eq 'linux'
        $rows += [pscustomobject]@{ Component = 'Linux engine'; Status = $(if ($ready) { 'READY' } else { 'ACTION NEEDED' }); Detail = 'Start Docker Desktop / switch to Linux containers' }
        foreach ($plugin in @('compose', 'buildx')) {
            & docker $plugin version *> $null
            $rows += [pscustomobject]@{ Component = "Docker $plugin"; Status = $(if ($LASTEXITCODE -eq 0) { 'READY' } else { 'MISSING' }); Detail = 'Included with Docker Desktop' }
        }
    }
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        & gh auth status --hostname github.com *> $null
        $signedIn = $LASTEXITCODE -eq 0
        $rows += [pscustomobject]@{ Component = 'GitHub sign-in'; Status = $(if ($signedIn) { 'SIGNED IN' } else { 'ACTION NEEDED' }); Detail = 'Publish only; package scope is checked before release' }
    }
    return $rows
}

function Install-HelperComponent {
    param([ValidateSet('Git', 'Docker', 'GitHub')][string]$Component)
    $packages = @{
        Git = @('Git.Git', 'https://git-scm.com/downloads/win')
        Docker = @('Docker.DockerDesktop', 'https://docs.docker.com/desktop/setup/install/windows-install/')
        GitHub = @('GitHub.cli', 'https://cli.github.com/')
    }
    $package = $packages[$Component]
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Windows App Installer (winget) is unavailable. Install $Component from: $($package[1])" -ForegroundColor Yellow
        return
    }
    Write-Host "Installing $Component using winget. Download/install progress follows; Windows may request elevation." -ForegroundColor Cyan
    if ($Component -eq 'Docker') { Write-Host 'Docker may require WSL/virtualization setup and a Windows restart. Finish those steps in Docker Desktop.' }
    & winget install --id $package[0] --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Installation did not finish successfully (exit $LASTEXITCODE). Resolve the installer message and retry. $($package[1])" }
    Update-HelperPath
}

function Connect-HelperGitHub {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI from Setup first.' }
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & gh auth status --hostname github.com *> $null
    $authExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPreference
    if ($authExit -eq 0) {
        & gh auth refresh --hostname github.com --scopes write:packages
    } else {
        & gh auth login --hostname github.com --web --scopes write:packages
    }
    if ($LASTEXITCODE -ne 0) { throw 'GitHub authorization failed or was canceled. Retry Sign in before publishing.' }
}

function Invoke-HelperRelease {
    param([ValidateSet('Check', 'Build', 'Publish', 'Force')][string]$Action)
    $state = @(Get-HelperState)
    $missing = @($state | Where-Object { $_.Detail -ne 'Publish only' -and $_.Component -notlike 'GitHub*' -and $_.Status -ne 'READY' })
    if ($missing.Count) { throw 'Build requirements are not ready. Use Setup, then Refresh status.' }
    $options = @{}
    switch ($Action) {
        Check { $options.CheckOnly = $true }
        Publish { $options.Publish = $true; $options.PublishLatest = $true; $options.RepairAuthentication = $true }
        Force { $options.Publish = $true; $options.PublishLatest = $true; $options.RepairAuthentication = $true; $options.ForceRebuild = $true }
    }
    & (Join-Path $PSScriptRoot 'Publish-Container.ps1') @options
}

function Show-HelperMenu {
    :menuLoop do {
        Write-Host "`n============================================================" -ForegroundColor Cyan
        Write-Host ' LifeGather - Container builder' -ForegroundColor Cyan
        Write-Host "============================================================`n"
        Get-HelperState | Format-Table Component, Status, Detail -AutoSize | Out-Host
        Write-Host 'Python, uv, Node and npm run in Docker. No developer installs.'
        Write-Host 'First verification downloads cached test images/dependencies.'
        Write-Host 'Build checks use disposable containers; your running app stays as-is.'
        Write-Host "`n  1  Refresh status`n  2  Setup / install components`n  3  GitHub sign-in / fix package permission`n  4  Verify only`n  5  Build locally (no upload)`n  6  Build & publish latest (skip if already published)`n  7  Force rebuild & publish latest`n  0  Exit`n"
        $choice = Read-Host 'Choose'
        $timer = [Diagnostics.Stopwatch]::StartNew()
        try {
            switch ($choice) {
                '0' { return }
                '1' { Update-HelperPath; continue menuLoop }
                '2' {
                    Write-Host "`n  G  Install Git`n  D  Install Docker Desktop`n  H  Install GitHub CLI (publish only)`n  S  Start Docker Desktop`n  0  Back"
                    switch ((Read-Host 'Setup action').ToUpperInvariant()) {
                        G { Install-HelperComponent Git }
                        D { Install-HelperComponent Docker }
                        H { Install-HelperComponent GitHub }
                        S {
                            $desktop = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
                            if (-not (Test-Path -LiteralPath $desktop)) { throw 'Docker Desktop was not found. Install it first.' }
                            Start-Process -FilePath $desktop -WindowStyle Hidden
                            Write-Host 'Docker Desktop is starting. Complete any setup there, then refresh status.'
                        }
                        '0' { continue menuLoop }
                        default { Write-Host 'Unknown setup action. Choose G, D, H, S or 0.' }
                    }
                }
                '3' { Connect-HelperGitHub }
                '4' { Invoke-HelperRelease Check }
                '5' { Invoke-HelperRelease Build }
                '6' { Invoke-HelperRelease Publish }
                '7' {
                    Write-Host 'This rebuilds the current revision and replaces its registry tags.' -ForegroundColor Yellow
                    if ((Read-Host 'Type REBUILD to continue') -ceq 'REBUILD') { Invoke-HelperRelease Force }
                    else { Write-Host 'Force rebuild canceled.' }
                }
                default { Write-Host 'Choose a number from 0 to 7.' -ForegroundColor Yellow; continue menuLoop }
            }
            Write-Host ("`nAction finished ({0:N1}s)." -f $timer.Elapsed.TotalSeconds) -ForegroundColor Green
        } catch {
            Write-Host ("`nAction failed ({0:N1}s): {1}" -f $timer.Elapsed.TotalSeconds, $_.Exception.Message) -ForegroundColor Red
            Write-Host 'Fix the reported problem and retry. The menu remains available.'
        }
        [void](Read-Host 'Press Enter to return to the menu')
    } while ($true)
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    Update-HelperPath
    if ($StatusOnly) { Get-HelperState | Format-Table -AutoSize }
    else { Show-HelperMenu }
}
