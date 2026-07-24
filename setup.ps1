param(
    [switch]$SkipAppDependencies,
    [switch]$SkipTtsDependencies
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ManifestPath = Join-Path $ProjectRoot "tts-assets.manifest.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$ReleaseUrl = "https://github.com/zhuge-Tom/moepet/releases/download/$($Manifest.release_tag)/$($Manifest.asset_name)"

function Test-TtsAssets {
    foreach ($entry in $Manifest.files) {
        $path = Join-Path $ProjectRoot ($entry.path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
        $item = Get-Item -LiteralPath $path
        if ($item.Length -ne [int64]$entry.size) { return $false }
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $entry.sha256) { return $false }
    }
    return $true
}

if (-not (Test-TtsAssets)) {
    $archive = Join-Path ([System.IO.Path]::GetTempPath()) $Manifest.asset_name
    Write-Host "Downloading Noir CPU voice assets..."
    Invoke-WebRequest -Uri $ReleaseUrl -OutFile $archive
    $archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($archiveHash -ne $Manifest.asset_sha256) {
        Remove-Item -LiteralPath $archive -Force
        throw "Downloaded TTS asset checksum mismatch."
    }
    Write-Host "Extracting voice assets..."
    Expand-Archive -LiteralPath $archive -DestinationPath $ProjectRoot -Force
    Remove-Item -LiteralPath $archive -Force
    if (-not (Test-TtsAssets)) {
        throw "TTS asset verification failed."
    }
}

if (-not $SkipAppDependencies) {
    $appPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $appPython)) {
        & py -3.11 -m venv (Join-Path $ProjectRoot ".venv")
    }
    & $appPython -m pip install --upgrade pip
    & $appPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

if (-not $SkipTtsDependencies) {
    $runtimePython = Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\python-runtime\cpython-3.10.9-windows-x86_64-none\python.exe"
    $ttsPython = Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        throw "The portable Python runtime is missing from the TTS release asset."
    }
    if (-not (Test-Path -LiteralPath $ttsPython)) {
        & $runtimePython -m venv (Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\.venv")
    }
    & $ttsPython -m pip install --upgrade pip
    & $ttsPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    & $ttsPython -m pip install -r (Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\requirements-moepet-cpu.txt")
}

Write-Host "Moepet setup completed. Run: .\.venv\Scripts\python.exe main.py"
