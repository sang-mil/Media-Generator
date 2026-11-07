#requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$envPath = Join-Path $PSScriptRoot ".env"
$examplePath = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path -LiteralPath $envPath)) {
    if (-not (Test-Path -LiteralPath $examplePath)) {
        throw ".env와 .env.example을 모두 찾을 수 없습니다. 프로젝트 루트에서 실행하세요."
    }
    Copy-Item -LiteralPath $examplePath -Destination $envPath
}

$backupPath = Join-Path $PSScriptRoot ".env.image-quality.backup"
Copy-Item -LiteralPath $envPath -Destination $backupPath -Force

$settings = [ordered]@{
    COMFYUI_CHECKPOINT = "v1-5-pruned-emaonly.safetensors"
    COMFYUI_TIMEOUT = "900"
    COMFYUI_WIDTH = "512"
    COMFYUI_HEIGHT = "640"
    COMFYUI_STEPS = "28"
    COMFYUI_CFG = "6.0"
    COMFYUI_SAMPLER = "dpmpp_2m"
    COMFYUI_SCHEDULER = "karras"
    COMFYUI_HIRES_ENABLED = "true"
    COMFYUI_HIRES_SCALE = "1.5"
    COMFYUI_HIRES_METHOD = "bislerp"
    COMFYUI_HIRES_STEPS = "12"
    COMFYUI_HIRES_CFG = "5.5"
    COMFYUI_HIRES_DENOISE = "0.28"
    COMFYUI_SEED_MODE = "shared"
}

$lines = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $envPath | ForEach-Object {
    [void]$lines.Add($_)
}

foreach ($key in $settings.Keys) {
    $pattern = "^\s*$([regex]::Escape([string]$key))="
    $foundIndex = -1

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $foundIndex = $i
            break
        }
    }

    $newLine = "${key}=$($settings[$key])"
    if ($foundIndex -ge 0) {
        $lines[$foundIndex] = $newLine
    }
    else {
        [void]$lines.Add($newLine)
    }
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($envPath, $lines.ToArray(), $utf8NoBom)

Write-Host "이미지 품질 설정을 .env에 적용했습니다." -ForegroundColor Green
Write-Host "백업: $backupPath"
Write-Host "체크포인트: $($settings.COMFYUI_CHECKPOINT)"
Write-Host "기본 해상도: $($settings.COMFYUI_WIDTH)x$($settings.COMFYUI_HEIGHT)"
Write-Host "2차 잠재 업스케일: $($settings.COMFYUI_HIRES_ENABLED) / $($settings.COMFYUI_HIRES_SCALE)x"
