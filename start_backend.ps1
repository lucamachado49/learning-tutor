# start_backend.ps1
# Inicia o backend FastAPI usando o .venv correto da pasta raiz.
# Execute a partir de qualquer pasta dentro do projeto.

$VenvPython = "C:\Users\Lucas\Downloads\language\.venv\Scripts\python.exe"
$BackendDir = "C:\Users\Lucas\Downloads\language\backend"

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERRO: .venv nao encontrado em $VenvPython" -ForegroundColor Red
    Write-Host "Execute primeiro: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Language Tutor — Backend (FastAPI)   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  URL: http://127.0.0.1:8000           " -ForegroundColor Green
Write-Host "  Docs: http://127.0.0.1:8000/docs     " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Roda uvicorn com o python do .venv (garante pacotes corretos)
& $VenvPython -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 --app-dir $BackendDir
