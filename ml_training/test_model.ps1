$ErrorActionPreference = "Stop"

if (!(Test-Path -Path ".venv")) {
    Write-Host "Setting up ML environment..."
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

python -m pip install -r requirements-ml.txt

Write-Host "Running tests..."
python -m unittest discover tests -v
Write-Host "Next action: Run .\export_training_data.ps1 to generate dataset if tests pass." -ForegroundColor Green
