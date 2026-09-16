<#
.SYNOPSIS
Seeds the InvestIQ Neon Postgres production database with NSE CM-UDiFF Bhavcopy market data.

.DESCRIPTION
This script sets up safety checks, verifies PostgreSQL environment variables,
and runs the production market data seeder.

.EXAMPLE
.\scripts\seed_production_market.ps1 -DryRun
.\scripts\seed_production_market.ps1 -ConfirmProductionWrite
#>

param (
    [switch]$DryRun,
    [switch]$ConfirmProductionWrite,
    [string]$File,
    [string]$Directory = "data\raw\nse\bhavcopy",
    [switch]$Strict,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $env:DATABASE_URL -and -not $env:POSTGRES_URL) {
    Write-Host "ERROR: DATABASE_URL or POSTGRES_URL is not set in the environment." -ForegroundColor Red
    Write-Host "Production market data seeding requires a valid Postgres URL." -ForegroundColor Red
    exit 1
}

$dbUrl = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { $env:POSTGRES_URL }
if (-not ($dbUrl.StartsWith("postgres://") -or $dbUrl.StartsWith("postgresql://"))) {
    Write-Host "ERROR: Only Postgres URLs are allowed for production seeding." -ForegroundColor Red
    exit 1
}

$env:FLASK_DEBUG = "False"
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "cli-override-secret-key" }
if (-not $env:GEMINI_API_KEY) { $env:GEMINI_API_KEY = "cli-override-gemini-key" }
if (-not $env:CORS_ALLOWED_ORIGINS) { $env:CORS_ALLOWED_ORIGINS = "http://localhost" }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptDir

$commandArgs = @("-m", "backend.cli.seed_production_market")

if ($File) {
    $commandArgs += @("--file", $File)
} else {
    $commandArgs += @("--directory", (Join-Path $rootDir $Directory))
}

if ($DryRun) {
    $commandArgs += "--dry-run"
} elseif ($ConfirmProductionWrite) {
    $commandArgs += "--confirm-production-write"
} else {
    Write-Host "ERROR: You must specify either -DryRun or -ConfirmProductionWrite" -ForegroundColor Red
    exit 1
}

if ($Strict) {
    $commandArgs += "--strict"
}
if ($Force) {
    $commandArgs += "--force"
}

cd $rootDir
$pythonBin = if (Test-Path "$rootDir\venv\Scripts\python.exe") { "$rootDir\venv\Scripts\python.exe" } else { "python" }
& $pythonBin $commandArgs
