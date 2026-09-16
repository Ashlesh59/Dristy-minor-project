$ErrorActionPreference = "Stop"

$DB_PATH = "..\backend\database\investiq.db"
$OUT_PATH = "data\raw\prices.csv"

if (-not (Test-Path $DB_PATH)) {
    Write-Host "Error: Database not found at $DB_PATH" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Error: Virtual environment not found. Run test_model.ps1 to set it up." -ForegroundColor Red
    exit 1
}

& .\.venv\Scripts\Activate.ps1
python src/export_from_db.py --database $DB_PATH --output $OUT_PATH

Write-Host "Next action: Run .\audit_training_data.ps1 to verify the dataset." -ForegroundColor Green
