$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Create .venv and install requirements-app.txt first."
}

Set-Location $Root
& $Python -m scripts.start_defensive_forward --db runtime/trader.db --capital 500
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Forward paper is active. Keep this window open."
Write-Host "Dashboard: http://127.0.0.1:8765"
& $Python -m trader --db runtime/trader.db serve
