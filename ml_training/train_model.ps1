$ErrorActionPreference = "Stop"

if (!(Test-Path -Path ".venv")) {
    Write-Host "Setting up ML environment..."
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

python -m pip install -r requirements-ml.txt

Write-Host "Running training..."
if (!(Test-Path "data/raw/prices.csv") -or !(Test-Path "data/raw/benchmark.csv")) {
    Write-Host "Training was not performed because real data is unavailable." -ForegroundColor Yellow
    exit 0
}

python src/train.py --prices data/raw/prices.csv --benchmark data/raw/benchmark.csv
Write-Host "Next action: Deploy model or check reports/backtest.json" -ForegroundColor Green
