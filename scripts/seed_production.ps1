<#
.SYNOPSIS
Seeds the InvestIQ Neon Postgres production database with NSE Equity Master data.

.DESCRIPTION
This script sets the production environment variables and calls the backend production
seeder. It requires the raw CSV file to be downloaded locally.

.EXAMPLE
.\scripts\seed_production.ps1 -DryRun
.\scripts\seed_production.ps1 -ConfirmProductionWrite
#>

param (
    [switch]$DryRun,
    [switch]$ConfirmProductionWrite
)

$ErrorActionPreference = "Stop"

# Set the placeholder database URL (Owner must replace this in their local environment)
# $env:DATABASE_URL = "postgresql://user:password@ep-cold-pond-123456.us-east-2.aws.neon.tech/neondb"
if (-not $env:DATABASE_URL) {
    Write-Host "WARNING: DATABASE_URL is not set in the environment. Seeding will run against local SQLite unless set." -ForegroundColor Yellow
}

$env:FLASK_DEBUG = "False"
# We need a SECRET_KEY and GEMINI_API_KEY to satisfy app.py startup checks, even for CLI commands
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "cli-override-secret-key" }
if (-not $env:GEMINI_API_KEY) { $env:GEMINI_API_KEY = "cli-override-gemini-key" }
if (-not $env:CORS_ALLOWED_ORIGINS) { $env:CORS_ALLOWED_ORIGINS = "http://localhost" }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptDir

# Path to the data file
$dataFile = Join-Path $rootDir "data\raw\nse\EQUITY_L.csv"

if (-not (Test-Path $dataFile)) {
    Write-Host "ERROR: Data file not found at $dataFile." -ForegroundColor Red
    Write-Host "Please download the EQUITY_L.csv file from NSE and save it to data/raw/nse/" -ForegroundColor Yellow
    exit 1
}

$commandArgs = @("-m", "backend.cli.seed_production", "--file", $dataFile)

if ($DryRun) {
    $commandArgs += "--dry-run"
} elseif ($ConfirmProductionWrite) {
    $commandArgs += "--confirm-production-write"
} else {
    Write-Host "ERROR: You must specify either -DryRun or -ConfirmProductionWrite" -ForegroundColor Red
    exit 1
}

# Run the seeder
cd $rootDir
python $commandArgs
