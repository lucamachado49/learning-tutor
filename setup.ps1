# Setup do AI Language Tutor (Windows PowerShell)
# Execucao: .\setup.ps1

param(
    [switch]$SkipOllama,
    [switch]$SkipModels,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   AI Language Tutor — Setup Automatico    " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Verificar Python
# ---------------------------------------------------------------------------
Write-Host "[1/5] Verificando Python..." -ForegroundColor Yellow
try {
    $pyVersion = & $PythonExe --version 2>&1
    Write-Host "      OK: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "      ERRO: Python nao encontrado. Instale em https://python.org" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Criar ambiente virtual
# ---------------------------------------------------------------------------
Write-Host "[2/5] Criando ambiente virtual (.venv)..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    & $PythonExe -m venv .venv
    Write-Host "      Ambiente criado." -ForegroundColor Green
} else {
    Write-Host "      Ambiente .venv ja existe, pulando." -ForegroundColor DarkGray
}

# Ativa o venv
$activateScript = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
    Write-Host "      Venv ativado." -ForegroundColor Green
} else {
    Write-Host "      Nao foi possivel ativar o venv automaticamente." -ForegroundColor Yellow
    Write-Host "      Execute manualmente: .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 3. Instalar dependencias Python
# ---------------------------------------------------------------------------
Write-Host "[3/5] Instalando dependencias Python..." -ForegroundColor Yellow
pip install --upgrade pip --quiet
pip install -r requirements.txt

Write-Host "      Dependencias instaladas." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Verificar / instalar Ollama
# ---------------------------------------------------------------------------
if (-not $SkipOllama) {
    Write-Host "[4/5] Verificando Ollama..." -ForegroundColor Yellow
    $ollamaInstalled = $null
    try {
        $ollamaInstalled = Get-Command ollama -ErrorAction SilentlyContinue
    } catch {}

    if ($ollamaInstalled) {
        Write-Host "      Ollama encontrado: $($ollamaInstalled.Source)" -ForegroundColor Green
        Write-Host "      Baixando modelo padrao (qwen2.5:7b)..." -ForegroundColor Yellow
        Write-Host "      (Isso pode levar varios minutos na primeira vez)" -ForegroundColor DarkGray
        ollama pull qwen2.5:7b
        Write-Host "      Modelo baixado." -ForegroundColor Green
    } else {
        Write-Host "      Ollama NAO encontrado." -ForegroundColor Red
        Write-Host "      Instale em: https://ollama.com/download" -ForegroundColor Yellow
        Write-Host "      Apos instalar, execute:" -ForegroundColor Yellow
        Write-Host "        ollama serve" -ForegroundColor White
        Write-Host "        ollama pull qwen2.5:7b" -ForegroundColor White
    }
} else {
    Write-Host "[4/5] Ollama: pulado (--SkipOllama)." -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# 5. Baixar modelos Piper TTS
# ---------------------------------------------------------------------------
if (-not $SkipModels) {
    Write-Host "[5/5] Baixando modelos Piper TTS (todos os idiomas)..." -ForegroundColor Yellow
    Write-Host "      Espanhol, Ingles, Italiano, Russo..." -ForegroundColor DarkGray
    python download_models.py
    Write-Host "      Modelos Piper TTS prontos." -ForegroundColor Green
} else {
    Write-Host "[5/5] Modelos Piper: pulado (--SkipModels)." -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# Pronto!
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "   Setup concluido com sucesso!            " -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para iniciar a aplicacao:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. (Se necessario) Inicie o Ollama:" -ForegroundColor White
Write-Host "       ollama serve" -ForegroundColor Yellow
Write-Host ""
Write-Host "  2. Ative o ambiente virtual:" -ForegroundColor White
Write-Host "       .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. Execute a aplicacao:" -ForegroundColor White
Write-Host "       .\start_backend.ps1  (e: cd frontend; npm run dev)" -ForegroundColor Yellow
Write-Host ""
