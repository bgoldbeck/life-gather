$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'Registry-Release.ps1')
if (-not ('LifeGatherRegistryHttpError' -as [type])) {
    Add-Type @'
public class LifeGatherRegistryHttpError : System.Exception {
    private int code;
    public LifeGatherRegistryHttpError(int code) { this.code = code; }
    public object Response { get { return new LifeGatherRegistryResponse(code); } }
}
public class LifeGatherRegistryResponse {
    public int StatusCode { get; private set; }
    public LifeGatherRegistryResponse(int code) { StatusCode = code; }
}
'@
}
$script:Status = 200
$script:Index = $false
$script:Architecture = 'amd64'
$script:BadDigest = $false
$script:Retag = $false
function Invoke-WebRequest {
    param($Uri, $Headers, $Method, $Body, $ContentType, [switch]$UseBasicParsing, $TimeoutSec, $ErrorAction)
    if ($script:Status -ne 200) { throw [LifeGatherRegistryHttpError]::new($script:Status) }
    if ($Method -eq 'PUT') {
        if ($Body -isnot [byte[]] -or [Text.Encoding]::UTF8.GetString($Body) -notmatch 'mediaType') { throw 'Retag must copy original UTF8 manifest bytes' }
        $script:Retag = $true
    }
    $digest = 'sha256:' + ('a' * 64)
    if ($script:BadDigest) { $digest = 'invalid' }
    $bodyText = '{"mediaType":"application/vnd.oci.image.manifest.v1+json","config":{"digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}'
    if ($script:Index -and $Uri -like '*/manifests/latest') {
        $bodyText = '{"mediaType":"application/vnd.oci.image.index.v1+json","manifests":[{"platform":{"os":"linux","architecture":"amd64"},"digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}]}'
    }
    if ($Uri -like '*/blobs/*') {
        $bodyText = '{"os":"linux","architecture":"' + $script:Architecture + '","config":{"Labels":{"org.opencontainers.image.revision":"dddddddddddddddddddddddddddddddddddddddd","org.opencontainers.image.version":"0.93.0"}}}'
    }
    # GHCR serves JSON blobs as application/octet-stream: PS5 gives byte[].
    [pscustomobject]@{ Content = [Text.Encoding]::UTF8.GetBytes($bodyText); Headers = @{ 'Docker-Content-Digest' = $digest } }
}
foreach ($code in @(401, 403, 429, 500)) {
    $script:Status = $code
    $failed = $false
    try { $null = Get-ReleaseRegistryImage latest @{} } catch { $failed = $_.Exception.Message -match 'GHCR metadata request failed' }
    if (-not $failed) { throw "HTTP $code must stop the release, never skip or build" }
}
$script:Status = 404
if ($null -ne (Get-ReleaseRegistryImage latest @{})) { throw 'HTTP404 must be a cache miss' }
Write-Host 'PASS: HTTP401/403/429/500 stop; HTTP404 alone is missing'
$script:Status = 200
foreach ($index in @($false, $true)) {
    $script:Index = $index
    $image = Get-ReleaseRegistryImage latest @{}
    if ($image.Revision -ne ('d' * 40) -or $image.Digest -ne ('sha256:' + ('a' * 64))) { throw 'Registry labels/digest incorrect' }
    Set-ReleaseRegistryLatest $image @{}
    if (-not $script:Retag) { throw 'Expected registry manifest copy' }
}
Write-Host 'PASS: plain/index manifests, binary JSON and exact manifest retag'
$script:Architecture = 'arm64'
$failed = $false
try { $null = Get-ReleaseRegistryImage latest @{} } catch { $failed = $true }
if (-not $failed) { throw 'Wrong architecture must stop' }
$script:Architecture = 'amd64'
$script:BadDigest = $true
$failed = $false
try { $null = Get-ReleaseRegistryImage latest @{} } catch { $failed = $true }
if (-not $failed) { throw 'Invalid digest must stop' }
Write-Host 'PASS: unsupported architecture and malformed digest stop publication'
