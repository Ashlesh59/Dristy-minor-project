$ErrorActionPreference = "Stop"

Write-Host "Setting up ML environment..."
if (-not (Test-Path ".venv")) {
    py -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ml.txt

Write-Host "Running tests..."
python -m unittest discover tests -v
