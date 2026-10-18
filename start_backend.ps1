# start_backend.ps1
# Modo desenvolvimento: PostgreSQL no Docker + backend no Windows (hot reload).
# Para rodar o backend também em container:  docker compose --profile app up -d --build

$Root       = $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$BackendDir = Join-Path $Root "backend"

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERRO: .venv nao encontrado em $VenvPython" -ForegroundColor Red
    Write-Host "Execute primeiro: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# O backend em container usa a mesma porta (8010); para o modo dev ele precisa estar parado
docker compose -f (Join-Path $Root "docker-compose.yml") stop backend 2>$null | Out-Null

Write-Host "Subindo PostgreSQL (docker compose)..." -ForegroundColor Cyan
docker compose -f (Join-Path $Root "docker-compose.yml") up -d --wait db
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: nao foi possivel iniciar o PostgreSQL. O Docker Desktop esta aberto?" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  API:  http://127.0.0.1:8010" -ForegroundColor Green
Write-Host "  Docs: http://127.0.0.1:8010/docs" -ForegroundColor Green
Write-Host ""

# Migracoes do Alembic rodam automaticamente no startup
& $VenvPython -m uvicorn main:app --reload --host 127.0.0.1 --port 8010 --app-dir $BackendDir
