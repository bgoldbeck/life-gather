# Metadata-only GHCR operations. Never log authorization headers or response tokens.
function Invoke-ReleaseRegistryRequest {
    param([string]$Uri, [hashtable]$Headers, [string]$Method = 'GET', [string]$Body, [string]$ContentType, [switch]$AllowMissing)
    $request = @{ Uri = $Uri; Headers = $Headers; Method = $Method; UseBasicParsing = $true; TimeoutSec = 45; ErrorAction = 'Stop' }
    if ($Body) { $request.Body = [Text.Encoding]::UTF8.GetBytes($Body); $request.ContentType = $ContentType }
    try {
        $result = Invoke-WebRequest @request
        $content = $result.Content
        if ($content -is [byte[]]) { $content = [Text.Encoding]::UTF8.GetString($content) }
        return [pscustomobject]@{ Content = $content; Headers = $result.Headers }
    }
    catch {
        $responseProperty = $_.Exception.PSObject.Properties['Response']
        $response = if ($responseProperty) { $responseProperty.Value } else { $null }
        # A failed login, timeout or ambiguous error is never a cache miss.
        if ($AllowMissing -and $response -and [int]$response.StatusCode -eq 404) { return $null }
        throw 'GHCR metadata request failed. Check registry access/network and retry; publication stopped.'
    }
}

function New-ReleaseRegistrySession {
    param([string]$GhExecutable, [string]$Login)
    $token = & $GhExecutable auth token --hostname github.com 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'GitHub token unavailable for registry check.' }
    try {
        $basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${Login}:$token"))
        $response = Invoke-ReleaseRegistryRequest -Uri 'https://ghcr.io/token?service=ghcr.io&scope=repository%3Abgoldbeck%2Flife-gather%3Apull%2Cpush' -Headers @{ Authorization = "Basic $basic" }
        $bearer = (ConvertFrom-Json $response.Content).token
        if (-not $bearer) { throw 'Registry authentication returned no access token.' }
        return @{ Authorization = "Bearer $bearer"; Accept = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' }
    } finally { $token = $null; $basic = $null; $bearer = $null }
}

function Get-ReleaseRegistryImage {
    param([string]$Tag, [hashtable]$Headers)
    $base = 'https://ghcr.io/v2/bgoldbeck/life-gather'
    $response = Invoke-ReleaseRegistryRequest -Uri "$base/manifests/$Tag" -Headers $Headers -AllowMissing
    if ($null -eq $response) { return $null }
    $raw = $response.Content
    if ($raw -is [byte[]]) { $raw = [Text.Encoding]::UTF8.GetString($raw) }
    $manifest = ConvertFrom-Json $raw
    $digest = [string]$response.Headers['Docker-Content-Digest']
    if ($digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'GHCR returned no valid manifest digest. Release stopped.' }
    $mediaType = $manifest.mediaType
    if ($mediaType -in @('application/vnd.oci.image.index.v1+json', 'application/vnd.docker.distribution.manifest.list.v2+json')) {
        $children = @($manifest.manifests | Where-Object { $_.platform.os -eq 'linux' -and $_.platform.architecture -eq 'amd64' })
        if ($children.Count -ne 1 -or $children[0].digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Expected exactly one Linux/amd64 registry image.' }
        $child = Invoke-ReleaseRegistryRequest -Uri "$base/manifests/$($children[0].digest)" -Headers $Headers
        $manifest = ConvertFrom-Json $child.Content
    }
    if ($manifest.mediaType -notin @('application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json') -or
        $manifest.config.digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Unsupported registry image manifest. Release stopped.' }
    $config = Invoke-ReleaseRegistryRequest -Uri "$base/blobs/$($manifest.config.digest)" -Headers $Headers
    $metadata = ConvertFrom-Json $config.Content
    if ($metadata.os -ne 'linux' -or $metadata.architecture -ne 'amd64') { throw 'Registry image is not Linux/amd64.' }
    $labels = $metadata.config.Labels
    return [pscustomobject]@{
        Digest = $digest; Raw = $raw; MediaType = $mediaType
        Revision = $labels.'org.opencontainers.image.revision'
        Version = $labels.'org.opencontainers.image.version'
    }
}

function Set-ReleaseRegistryLatest {
    param($Image, [hashtable]$Headers)
    $null = Invoke-ReleaseRegistryRequest -Uri 'https://ghcr.io/v2/bgoldbeck/life-gather/manifests/latest' -Headers $Headers -Method PUT -Body $Image.Raw -ContentType $Image.MediaType
    $latest = Get-ReleaseRegistryImage -Tag latest -Headers $Headers
    if ($null -eq $latest -or $latest.Digest -ne $Image.Digest) { throw 'Unable to verify latest after updating its registry manifest.' }
}
