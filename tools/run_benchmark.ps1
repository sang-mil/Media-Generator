#requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "가상환경 Python을 찾지 못했습니다. 프로젝트 루트에서 .\run.ps1을 먼저 실행하세요."
}

Write-Host "Ollama 모델 비교 벤치마크를 시작합니다." -ForegroundColor Cyan
Write-Host "비교 모델: qwen3.8:27b-q4_K_M / gemma4:26b"
Write-Host "조건: baseline/technical-guarded x 웹툰/기술 설명 = 모델당 4회 생성"
Write-Host "ComfyUI 이미지 생성은 벤치마크 동안 실행하지 않는 것을 권장합니다." -ForegroundColor Yellow

& $python ".\tools\benchmark_models.py" `
    --qwen-model "qwen3.8:27b-q4_K_M" `
    --gemma-model "gemma4:26b" `
    --num-ctx 8192 `
    --num-predict 2200 `
    --temperature 0.5

if ($LASTEXITCODE -ne 0) {
    throw "벤치마크가 정상 완료되지 않았습니다. 위 오류와 설치 모델명을 확인하세요."
}
