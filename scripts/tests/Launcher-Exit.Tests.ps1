# Actual cmd.exe control-flow checks. Substitute only the PowerShell child call;
# never start Docker, access credentials or publish images from these fixtures.
$ErrorActionPreference = 'Stop'
$scriptsRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('lifegather helper exit tests ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$fixtures = [Collections.Generic.List[string]]::new()
try {
    foreach ($name in @('Publish-Container', 'Start-Test-Login')) {
        $source = Get-Content -LiteralPath (Join-Path $scriptsRoot ($name + '.cmd')) -Raw
        $child = [regex]::new('(?m)^powershell\.exe [^\r\n]+')
        if ($child.Matches($source).Count -ne 1) { throw "Expected one PowerShell child in $name" }
        foreach ($code in @(0, 7)) {
            $fixture = Join-Path $testRoot ("$name-$code.cmd")
            $fixtures.Add($fixture)
            $child.Replace($source, "cmd.exe /d /c exit $code", 1) | Set-Content -LiteralPath $fixture -Encoding ASCII
            $process = [Diagnostics.Process]::new()
            $process.StartInfo.FileName = $env:ComSpec
            $process.StartInfo.Arguments = '/d /c ""' + $fixture + '""'
            $process.StartInfo.UseShellExecute = $false
            $process.StartInfo.CreateNoWindow = $true
            $process.StartInfo.RedirectStandardInput = $true
            $process.StartInfo.RedirectStandardOutput = $true
            $process.StartInfo.RedirectStandardError = $true
            try {
                [void]$process.Start()
                $exited = $process.WaitForExit(1500)
                if ($code -eq 0 -and -not $exited) {
                    throw "${name}: success still waits for keyboard input"
                }
                if ($code -ne 0 -and $exited) {
                    throw "${name}: failure closed before the error could be inspected"
                }
                if (-not $exited) {
                    $process.StandardInput.WriteLine('x')
                    $process.StandardInput.Close()
                    if (-not $process.WaitForExit(3000)) { throw "$name did not exit after input" }
                }
                $output = $process.StandardOutput.ReadToEnd() + $process.StandardError.ReadToEnd()
                if ($process.ExitCode -ne $code) { throw "$name lost the child exit code $code" }
                if ($code -ne 0 -and $output -notmatch '(?i)failed') { throw "$name did not explain failure" }
                Write-Host "PASS: $name child=$code preserves status and expected input behavior"
            } finally {
                if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
                $process.Dispose()
            }
        }
    }
} finally {
    foreach ($fixture in $fixtures) {
        if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Force }
    }
    Remove-Item -LiteralPath $testRoot
}
