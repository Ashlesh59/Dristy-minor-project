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
    [switch]$ConfirmProductionWrite,
    [switch]$FullSnapshot,
    [switch]$ConfirmDeactivation
)

$ErrorActionPreference = "Stop"

if (-not $env:DATABASE_URL) {
    Write-Host "ERROR: DATABASE_URL is not set in the environment. Production seeding requires a Postgres URL." -ForegroundColor Red
    exit 1
}

if (-not ($env:DATABASE_URL.StartsWith("postgres://") -or $env:DATABASE_URL.StartsWith("postgresql://"))) {
    Write-Host "ERROR: Only Postgres URLs are allowed for production seeding." -ForegroundColor Red
    exit 1
}

$env:FLASK_DEBUG = "False"
# Dummy variables to satisfy app factory config checks (safe since this is a CLI script)
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

if ($FullSnapshot) {
    $commandArgs += "--full-snapshot"
}

if ($ConfirmDeactivation) {
    $commandArgs += "--confirm-deactivation"
}

# Run the seeder
cd $rootDir
$pythonBin = if (Test-Path "$rootDir\venv\Scripts\python.exe") { "$rootDir\venv\Scripts\python.exe" } else { "python" }
& $pythonBin $commandArgs
