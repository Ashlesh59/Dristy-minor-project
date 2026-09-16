$ErrorActionPreference = "Stop"

$PRICES_PATH = "data\raw\prices.csv"
$BENCHMARK_PATH = "data\raw\benchmark.csv"
$OUT_PATH = "reports\dataset_audit.json"

if (-not (Test-Path $PRICES_PATH) -or -not (Test-Path $BENCHMARK_PATH)) {
    Write-Host "Error: Required CSV files missing in data\raw\" -ForegroundColor Red
    Write-Host "Please ensure prices.csv and benchmark.csv are present." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Error: Virtual environment not found. Run test_model.ps1 to set it up." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "reports")) {
    New-Item -ItemType Directory -Force -Path "reports" | Out-Null
}

& .\.venv\Scripts\Activate.ps1
python src/audit_dataset.py --prices $PRICES_PATH --benchmark $BENCHMARK_PATH --output $OUT_PATH

Write-Host "Next action: If audit is clean, run .\train_model.ps1" -ForegroundColor Green
