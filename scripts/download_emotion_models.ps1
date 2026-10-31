param(
    [string]$Proxy = '',
    [ValidateRange(1, 3600)][int]$TimeoutSeconds = 60,
    [ValidateRange(0, 20)][int]$Retries = 5
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$downloadPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $downloadPython -PathType Leaf)) {
    throw "Project Python was not found: $downloadPython"
}

# Requests does not automatically inherit the Windows system proxy here.
if (-not $Proxy) {
    $settings = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($settings.ProxyEnable -eq 1 -and $settings.ProxyServer) {
        $server = [string]$settings.ProxyServer
        if ($server -match '(?:^|;)https=([^;]+)') {
            $server = $Matches[1]
        } elseif ($server -match '(?:^|;)http=([^;]+)') {
            $server = $Matches[1]
        } elseif ($server.Contains('=')) {
            $server = ''
        }
        if ($server) {
            $Proxy = if ($server.Contains('://')) { $server } else { 'http://' + $server }
        }
    }
}

if ($Proxy) {
    $proxyUri = [Uri]$Proxy
    if (-not $proxyUri.IsAbsoluteUri -or $proxyUri.Scheme -notin @('http', 'https', 'socks5', 'socks5h')) {
        throw 'Specify an HTTP or SOCKS proxy URL.'
    }
    Write-Host ('Proxy: {0}://{1}:{2}' -f $proxyUri.Scheme, $proxyUri.Host, $proxyUri.Port)
} else {
    Write-Host 'No proxy selected; downloading directly.'
}

& $downloadPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('gdown') else 1)"
if ($LASTEXITCODE -ne 0) {
    & $downloadPython -m pip install gdown
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install gdown.' }
}

$ignoreFile = Join-Path $projectRoot '.gitignore'
$ignoreLines = @()
if (Test-Path -LiteralPath $ignoreFile) { $ignoreLines = @(Get-Content -LiteralPath $ignoreFile) }
foreach ($rule in '/models/midi-emotion/', '/models/emo-disentanger/') {
    if ($rule -notin $ignoreLines) { Add-Content -LiteralPath $ignoreFile -Value $rule -Encoding UTF8 }
}

$downloads = @(
    @{
        Name = 'midi-emotion'
        Id = '1ZEG6iUjoEHprjdltfgOsCNvS6RNyzmr2'
        Path = 'models\midi-emotion\continuous_concat.tar.gz'
        Bytes = 538669483L
    },
    @{
        Name = 'EMO-Disentanger'
        Id = '15Gc8PWbkoOeXCTrpDMKsgptoL17u49QG'
        Path = 'models\emo-disentanger\best_weight.zip'
        Bytes = 2236506726L
    }
)

$failures = @()
foreach ($item in $downloads) {
    try {
        $targetPath = Join-Path $projectRoot $item.Path
        $partialPath = $targetPath + '.part'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null

        if (Test-Path -LiteralPath $targetPath) {
            if ((Get-Item -LiteralPath $targetPath).Length -ne $item.Bytes) {
                throw "Existing file has an unexpected size; preserved: $targetPath"
            }
            Write-Host "Already complete: $($item.Name)" -ForegroundColor Green
            continue
        }

        $existing = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -eq 'python.exe' -and $_.CommandLine -match '-m gdown' -and
            $_.CommandLine.Contains($item.Id)
        })
        if ($existing.Count) { throw "A download of $($item.Name) is already running. Let it finish or stop it before retrying." }

        $complete = (Test-Path -LiteralPath $partialPath -PathType Leaf) -and
            ((Get-Item -LiteralPath $partialPath).Length -eq $item.Bytes)
        if (-not $complete) {
            Write-Host "Downloading / resuming: $($item.Name)" -ForegroundColor Cyan
            $downloadArgs = @('-m', 'gdown', $item.Id, '-O', $partialPath,
                '--continue', '--timeout', [string]$TimeoutSeconds,
                '--retries', [string]$Retries, '--no-cookies')
            if ($Proxy) { $downloadArgs += @('--proxy', $Proxy) }
            & $downloadPython @downloadArgs
            if ($LASTEXITCODE -ne 0) { throw "Download failed; partial data is preserved: $($item.Name)" }
        }

        if (-not (Test-Path -LiteralPath $partialPath -PathType Leaf)) { throw "Download output is missing: $partialPath" }
        if ((Get-Item -LiteralPath $partialPath).Length -ne $item.Bytes) {
            throw "File size differs from the verified metadata; preserved: $partialPath"
        }
        Move-Item -LiteralPath $partialPath -Destination $targetPath
        Write-Host "Complete: $targetPath" -ForegroundColor Green
    } catch {
        $failures += $item.Name
        Write-Warning $_.Exception.Message
    }
}

if ($failures.Count) { throw ('Incomplete downloads: ' + ($failures -join ', ') + '. Rerun this script to resume.') }
Write-Host 'Both archives passed the expected-size checks. Models have not been extracted or activated.' -ForegroundColor Green
