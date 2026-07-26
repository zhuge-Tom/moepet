param(
    [switch]$SkipAppDependencies,
    [switch]$InstallCpuTts,
    [switch]$InstallSbv2
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

function Test-Sbv2Package {
    $required = @(
        "vendor\style_bert_vits2\server_moepet.py",
        "vendor\style_bert_vits2\style_bert_vits2\tts_model.py",
        "vendor\style_bert_vits2\runtime\python.exe",
        "vendor\style_bert_vits2\model_assets\noir\noir.onnx",
        "vendor\style_bert_vits2\model_assets\noir\config.json",
        "vendor\style_bert_vits2\model_assets\noir\style_vectors.npy",
        "vendor\style_bert_vits2\bert\deberta-v2-large-japanese-char-wwm-onnx\model_fp16.onnx",
        "vendor\style_bert_vits2\bert\deberta-v2-large-japanese-char-wwm-onnx\tokenizer.json"
    )
    foreach ($relativePath in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) { return $false }
    }
    return $true
}

function Test-CpuTtsPackage {
    $required = @(
        "vendor\gpt_sovits_cpu\api_v2.py",
        "vendor\gpt_sovits_cpu\python-runtime\cpython-3.10.9-windows-x86_64-none\python.exe",
        "vendor\gpt_sovits_cpu\requirements-moepet-cpu.txt",
        "vendor\gpt_sovits_cpu\GPT_SoVITS\pretrained_models\chinese-hubert-base",
        "voice_assets\noir\noir-e15.ckpt",
        "voice_assets\noir\noir_e8_s968.pth",
        "voice_assets\noir\reference.wav",
        "voice_assets\noir\reference.txt"
    )
    foreach ($relativePath in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) { return $false }
    }
    return $true
}

if (-not $SkipAppDependencies) {
    $appPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $appPython)) {
        & py -3.11 -m venv (Join-Path $ProjectRoot ".venv")
    }
    & $appPython -m pip install --upgrade pip
    & $appPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

if ($InstallCpuTts) {
    $assetUrl = "https://github.com/zhuge-Tom/moepet/releases/download/tts-assets-v2/moepet-tts-cpu-v2.zip"
    $expectedHash = "6ea8f030f51386418823cf4dd0591828ddee3de9e4613da59839b9b934346d9a"
    $archive = Join-Path ([System.IO.Path]::GetTempPath()) "moepet-tts-cpu-v2.zip"
    if (-not (Test-CpuTtsPackage)) {
        Write-Host "Downloading GPT-SoVITS CPU compatibility package..."
        Invoke-WebRequest -Uri $assetUrl -OutFile $archive
        $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            Remove-Item -LiteralPath $archive -Force
            throw "Downloaded CPU TTS package checksum mismatch."
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $ProjectRoot -Force
        Remove-Item -LiteralPath $archive -Force
        if (-not (Test-CpuTtsPackage)) {
            throw "CPU TTS package extraction is incomplete."
        }
    } else {
        Write-Host "GPT-SoVITS CPU compatibility package is already installed."
    }
    $runtimePython = Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\python-runtime\cpython-3.10.9-windows-x86_64-none\python.exe"
    $ttsPython = Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        throw "CPU package did not contain the portable Python runtime."
    }
    if (-not (Test-Path -LiteralPath $ttsPython)) {
        & $runtimePython -m venv (Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\.venv")
    }
    & $ttsPython -m pip install --upgrade pip
    & $ttsPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    & $ttsPython -m pip install -r (Join-Path $ProjectRoot "vendor\gpt_sovits_cpu\requirements-moepet-cpu.txt")
    Write-Host "GPT-SoVITS CPU compatibility package is ready."
}

if ($InstallSbv2) {
    $assetUrl = "https://github.com/zhuge-Tom/moepet/releases/download/sbv2-assets-v1/moepet-sbv2-noir-v1.zip"
    $expectedHash = "a8fc8bdb4a7b25d6b3175717f945de246d2d3fa23c4041d3ece7fc0e7f3f6ccf"
    $archive = Join-Path ([System.IO.Path]::GetTempPath()) "moepet-sbv2-noir-v1.zip"
    if (-not (Test-Sbv2Package)) {
        Write-Host "Downloading Style-Bert-VITS2 Noir assets (about 800 MB)..."
        Invoke-WebRequest -Uri $assetUrl -OutFile $archive
        $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            Remove-Item -LiteralPath $archive -Force
            throw "Downloaded SBV2 package checksum mismatch."
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $ProjectRoot -Force
        Remove-Item -LiteralPath $archive -Force
        if (-not (Test-Sbv2Package)) {
            throw "SBV2 package extraction is incomplete."
        }
    } else {
        Write-Host "Style-Bert-VITS2 assets are already installed."
    }
    # The package bundles a portable Python runtime with all inference
    # dependencies preinstalled; nothing else to build.
    Write-Host "Style-Bert-VITS2 local voice is ready."
}

Write-Host "Moepet setup completed. Run: .\.venv\Scripts\python.exe main.py"
Write-Host "Local voice: default Style-Bert-VITS2 assets install with -InstallSbv2; GPT-SoVITS remains available with -InstallCpuTts."
