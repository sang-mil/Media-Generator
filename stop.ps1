#requires -Version 5.1
$ErrorActionPreference = "Stop"
$pidFile = Join-Path $PSScriptRoot ".app.pid"
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "저장된 앱 프로세스가 없습니다. 이미 종료되었을 수 있습니다."
    exit 0
}
$appPid = 0
try { $appPid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim() } catch { $appPid = 0 }
if ($appPid -gt 0) {
    $proc = Get-Process -Id $appPid -ErrorAction SilentlyContinue
    if ($proc) {
        $cmd = Get-CimInstance Win32_Process -Filter "ProcessId = $appPid" -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.CommandLine -match "uvicorn app\.main:app") {
            Stop-Process -Id $appPid -Force
            Write-Host "Self-improving Media Pipeline을 종료했습니다." -ForegroundColor Green
        } else {
            Write-Warning "PID $appPid가 앱 서버인지 확인할 수 없어 종료하지 않았습니다."
        }
    } else {
        Write-Host "앱 프로세스가 이미 종료되었습니다."
    }
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Ollama와 ComfyUI 서비스는 종료하지 않았습니다."
