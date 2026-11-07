#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Local service endpoints
$BaseUrl   = "http://127.0.0.1:8765"
$OllamaUrl = "http://127.0.0.1:11434"
$ComfyUrl  = "http://127.0.0.1:8188"
$LogDir    = Join-Path $PSScriptRoot ".logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return ""
    }

    $keyPattern = [regex]::Escape($Key)
    $line = Get-Content -LiteralPath $FilePath |
        Where-Object { $_ -match "^\s*$keyPattern\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return ""
    }

    $value = ($line -split "=", 2)[1]
    return $value.Trim().Trim('"').Trim("'")
}

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $lines = @()
    if (Test-Path -LiteralPath $FilePath) {
        $lines = @(Get-Content -LiteralPath $FilePath)
    }

    $keyPattern = [regex]::Escape($Key)
    $pattern = "^\s*$keyPattern\s*="
    $found = $false
    $updated = @(
        foreach ($line in $lines) {
            if ($line -match $pattern) {
                $found = $true
                "{0}={1}" -f $Key, $Value
            }
            else {
                $line
            }
        }
    )

    if (-not $found) {
        $updated += "{0}={1}" -f $Key, $Value
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($FilePath, [string[]]$updated, $utf8NoBom)
}

function Test-Endpoint {
    param([Parameter(Mandatory = $true)][string]$Url)

    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 3 -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host "--- $Message ---" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " Self-improving Media Pipeline v0.3" -ForegroundColor Cyan
Write-Host " Local AI + ComfyUI + Content Pipeline" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "Python was not found. Install Python 3.11 or later and enable PATH integration."
}

# Create .env from the example file when needed
$envPath = Join-Path $PSScriptRoot ".env"
$envExamplePath = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path -LiteralPath $envPath)) {
    if (-not (Test-Path -LiteralPath $envExamplePath)) {
        throw ".env and .env.example are both missing. Restore the project configuration files."
    }

    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 1) Find and start Ollama
# -----------------------------------------------------------------------------
Write-Section "1/6 - Checking Ollama"

$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaPath = $null

if ($ollamaCommand) {
    if ($ollamaCommand.Source) {
        $ollamaPath = $ollamaCommand.Source
    }
    elseif ($ollamaCommand.Definition) {
        $ollamaPath = $ollamaCommand.Definition
    }
}

if (-not $ollamaPath) {
    $ollamaCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        "C:\Program Files\Ollama\ollama.exe"
    )

    foreach ($candidate in $ollamaCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            $ollamaPath = $candidate
            break
        }
    }
}

if (-not $ollamaPath -or -not (Test-Path -LiteralPath $ollamaPath)) {
    throw "Ollama executable was not found. Install Ollama for Windows or add ollama.exe to PATH."
}

if (-not (Test-Endpoint -Url "$OllamaUrl/api/tags")) {
    Write-Host "Ollama is not responding. Starting Ollama service..." -ForegroundColor Yellow
    Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden | Out-Null

    $ollamaReady = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        Start-Sleep -Seconds 2
        if (Test-Endpoint -Url "$OllamaUrl/api/tags") {
            $ollamaReady = $true
            break
        }
    }

    if (-not $ollamaReady) {
        throw "Ollama did not respond within 90 seconds. Check Ollama and port 11434."
    }
}
else {
    Write-Host "Ollama is already running." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 2) Detect an installed model and save it to .env
# -----------------------------------------------------------------------------
Write-Section "2/6 - Detecting installed Ollama models"

$modelOutput = @(& $ollamaPath list 2>$null)
if ($LASTEXITCODE -ne 0) {
    $modelOutput = @()
}

$installedModels = @()
if ($modelOutput.Count -gt 1) {
    foreach ($line in ($modelOutput | Select-Object -Skip 1)) {
        $parts = ([string]$line).Trim() -split "\s+"
        if ($parts.Count -gt 0) {
            $modelName = $parts[0].Trim()
            if ($modelName -and $modelName -match ":") {
                $installedModels += $modelName
            }
        }
    }
}

$configuredModel = Get-EnvValue -FilePath $envPath -Key "OLLAMA_MODEL"
$selectedModel = $null

if ($configuredModel) {
    foreach ($installedModel in $installedModels) {
        if ($installedModel -eq $configuredModel -or
            $installedModel.StartsWith(($configuredModel -split ":")[0] + ":")) {
            $selectedModel = $installedModel
            break
        }
    }
}

if (-not $selectedModel) {
    $preferredModels = @(
        "gemma4:26b",
        "gemma4:12b",
        "qwen3.5:9b",
        "qwen3.8:27b-q4_K_M",
        "qwen3.8-code-api:latest",
        "qwen3.8-code-api",
        "qwen3.8-opencode:latest",
        "qwen2.5-coder:7b",
        "qwen2.5:7b"
    )

    foreach ($preferredModel in $preferredModels) {
        if ($installedModels -contains $preferredModel) {
            $selectedModel = $preferredModel
            break
        }
    }
}

if (-not $selectedModel -and $installedModels.Count -gt 0) {
    $selectedModel = $installedModels[0]
}

if ($selectedModel) {
    Set-EnvValue -FilePath $envPath -Key "OLLAMA_MODEL" -Value $selectedModel
    Write-Host ("Selected model: {0}" -f $selectedModel) -ForegroundColor Green
}
else {
    Write-Warning "No Ollama model is installed. The application can start, but AI generation will not work until a model is installed."
    $pullChoice = Read-Host "Download qwen2.5:7b now? (Y/N)"

    if ($pullChoice -match "^(Y|YES)$") {
        & $ollamaPath pull "qwen2.5:7b"
        if ($LASTEXITCODE -ne 0) {
            throw "Ollama model download failed."
        }

        $selectedModel = "qwen2.5:7b"
        Set-EnvValue -FilePath $envPath -Key "OLLAMA_MODEL" -Value $selectedModel
        Write-Host "Installed and selected qwen2.5:7b." -ForegroundColor Green
    }
    else {
        Write-Warning "Continuing without a selected Ollama model."
    }
}

# -----------------------------------------------------------------------------
# 3) Start ComfyUI when configured
# -----------------------------------------------------------------------------
Write-Section "3/6 - Checking ComfyUI"

$comfyAutoStart = Get-EnvValue -FilePath $envPath -Key "COMFYUI_AUTO_START"
if ([string]::IsNullOrWhiteSpace($comfyAutoStart)) {
    $comfyAutoStart = "true"
}

$comfyDir = Get-EnvValue -FilePath $envPath -Key "COMFYUI_DIR"
if ([string]::IsNullOrWhiteSpace($comfyDir)) {
    $defaultComfy = Join-Path $HOME "codes\ComfyUI_windows_portable\ComfyUI_windows_portable"
    if (Test-Path -LiteralPath $defaultComfy) {
        $comfyDir = $defaultComfy
    }
}

$comfyEnabled = @("true", "1", "yes", "on") -contains $comfyAutoStart.Trim().ToLowerInvariant()

if ($comfyEnabled) {
    if (Test-Endpoint -Url "$ComfyUrl/system_stats") {
        Write-Host "ComfyUI is already running." -ForegroundColor Green
    }
    elseif ($comfyDir -and (Test-Path -LiteralPath $comfyDir)) {
        $comfyBat = Join-Path $comfyDir "run_nvidia_gpu.bat"

        if (Test-Path -LiteralPath $comfyBat) {
            Write-Host ("Starting ComfyUI from: {0}" -f $comfyDir) -ForegroundColor Yellow
            $comfyArguments = '/c "{0}"' -f $comfyBat

            Start-Process -FilePath $env:ComSpec `
                -ArgumentList $comfyArguments `
                -WorkingDirectory $comfyDir `
                -WindowStyle Minimized | Out-Null

            $comfyReady = $false
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                Start-Sleep -Seconds 2
                if (Test-Endpoint -Url "$ComfyUrl/system_stats") {
                    $comfyReady = $true
                    break
                }
            }

            if ($comfyReady) {
                Write-Host "ComfyUI is ready." -ForegroundColor Green
            }
            else {
                Write-Warning "ComfyUI did not become ready within 120 seconds. Image generation may be unavailable."
            }

            Set-EnvValue -FilePath $envPath -Key "COMFYUI_DIR" -Value $comfyDir
        }
        else {
            Write-Warning "run_nvidia_gpu.bat was not found in COMFYUI_DIR. Image generation may be unavailable."
        }
    }
    else {
        Write-Warning "ComfyUI directory was not found. Set COMFYUI_DIR in .env to enable automatic startup."
    }
}
else {
    Write-Host "ComfyUI auto-start is disabled by COMFYUI_AUTO_START." -ForegroundColor DarkYellow
}

# -----------------------------------------------------------------------------
# 4) Create the Python virtual environment when missing
# -----------------------------------------------------------------------------
Write-Section "4/6 - Checking Python virtual environment"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating .venv..." -ForegroundColor Yellow
    & python -m venv (Join-Path $PSScriptRoot ".venv")

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python virtual environment."
    }
}
else {
    Write-Host "Python virtual environment is ready." -ForegroundColor Green
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment Python executable was not created."
}

# -----------------------------------------------------------------------------
# 5) Install requirements only when requirements.txt changes
# -----------------------------------------------------------------------------
Write-Section "5/6 - Checking Python dependencies"

$requirementsPath = Join-Path $PSScriptRoot "requirements.txt"
if (-not (Test-Path -LiteralPath $requirementsPath)) {
    throw "requirements.txt was not found in the project directory."
}

$requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
$hashFile = Join-Path $PSScriptRoot ".venv\requirements.sha256"
$oldHash = ""

if (Test-Path -LiteralPath $hashFile) {
    $oldHash = (Get-Content -LiteralPath $hashFile -Raw).Trim()
}

if ($requirementsHash -ne $oldHash) {
    Write-Host "Installing or updating Python dependencies..." -ForegroundColor Yellow

    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }

    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Python dependencies."
    }

    Set-Content -LiteralPath $hashFile -Value $requirementsHash -Encoding ASCII
}
else {
    Write-Host "Python dependencies are unchanged. Skipping installation." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 6) Start the local application and open the browser
# -----------------------------------------------------------------------------
Write-Section "6/6 - Starting the local application"

if (Test-Endpoint -Url "$BaseUrl/api/health") {
    Write-Host "The application is already running. Opening the browser." -ForegroundColor Green
    Start-Process -FilePath $BaseUrl
    exit 0
}

$stdout = Join-Path $LogDir "app.stdout.log"
$stderr = Join-Path $LogDir "app.stderr.log"
$pidFile = Join-Path $PSScriptRoot ".app.pid"

if (Test-Path -LiteralPath $stderr) {
    Remove-Item -LiteralPath $stderr -Force
}
if (Test-Path -LiteralPath $stdout) {
    Remove-Item -LiteralPath $stdout -Force
}

$appArguments = @(
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8765"
)

$appProcess = Start-Process -FilePath $venvPython `
    -ArgumentList $appArguments `
    -WorkingDirectory $PSScriptRoot `
    -PassThru `
    -WindowStyle Minimized `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

Set-Content -LiteralPath $pidFile -Value $appProcess.Id -Encoding ASCII

$serverReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1

    if (Test-Endpoint -Url "$BaseUrl/api/health") {
        $serverReady = $true
        break
    }

    $appProcess.Refresh()
    if ($appProcess.HasExited) {
        break
    }
}

if (-not $serverReady) {
    $errorTail = ""
    if (Test-Path -LiteralPath $stderr) {
        $errorTail = (Get-Content -LiteralPath $stderr -Tail 30) -join [Environment]::NewLine
    }

    if (-not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
    }

    throw ("Application server did not start. Log: {0}`n{1}" -f $stderr, $errorTail)
}

Write-Host ""
Write-Host "Application is ready." -ForegroundColor Green
Write-Host ("Web UI:       {0}" -f $BaseUrl)
Write-Host ("API docs:     {0}/docs" -f $BaseUrl)
if ($selectedModel) {
    Write-Host ("Ollama model: {0}" -f $selectedModel)
}
else {
    Write-Host "Ollama model: not selected" -ForegroundColor Yellow
}
Write-Host ("Logs:         {0}" -f $LogDir)
Write-Host "Stop app:     .\stop.ps1 (Ollama and ComfyUI are left running)"

Start-Process -FilePath $BaseUrl
