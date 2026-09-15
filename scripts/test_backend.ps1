# scripts/test_backend.ps1
# Cross-platform Windows PowerShell test launcher for InvestIQ Phase 0

$ErrorActionPreference = "Stop"

# 1. Locate repository root relative to script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "backend"
$DevDbPath = Join-Path $BackendDir "database\investiq.db"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  InvestIQ Phase 0: Isolated Backend Test Runner" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Repository Root: $RepoRoot"
Write-Host "Backend Dir:     $BackendDir"

# 2. Locate Python executable
$PythonExe = $null
$CandidatePaths = @(
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    (Join-Path $RepoRoot "venv\Scripts\python.exe"),
    "python.exe"
)

foreach ($path in $CandidatePaths) {
    if (Test-Path $path) {
        $PythonExe = (Resolve-Path $path).Path
        break
    }
}

if (-not $PythonExe) {
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $PythonExe = $cmd.Source
    }
}

if (-not $PythonExe) {
    Write-Error "Could not find Python executable. Please create a virtualenv (.venv or venv) or install Python."
    exit 1
}

Write-Host "Python Executable: $PythonExe"

function Get-FileHashShared {
    param([string]$Path)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $fileStream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $hashBytes = $sha256.ComputeHash($fileStream)
        return [System.BitConverter]::ToString($hashBytes).Replace("-", "")
    } finally {
        $fileStream.Close()
        $sha256.Dispose()
    }
}

# 3. Development Database Integrity Check (Pre-Test)
$PreHash = $null
$PreSize = $null
if (Test-Path $DevDbPath) {
    $PreHash = Get-FileHashShared -Path $DevDbPath
    $PreSize = (Get-Item -Path $DevDbPath).Length
    Write-Host "Pre-Test DB Hash: $PreHash (Size: $PreSize bytes)" -ForegroundColor Yellow
} else {
    Write-Host "Development database does not exist yet (clean slate)." -ForegroundColor Yellow
}

# 4. Set Test Sentinel and Environment
$env:INVESTIQ_TEST_RUN = "1"
$env:PYTHONPATH = $BackendDir

Write-Host "`nRunning test suite in backend directory..." -ForegroundColor Cyan

# 5. Execute Unittest Suite
Push-Location $BackendDir
try {
    & $PythonExe -m unittest discover tests
    $TestExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:INVESTIQ_TEST_RUN = $null
}

# 6. Development Database Integrity Check (Post-Test)
Write-Host "`nVerifying development database integrity..." -ForegroundColor Cyan
if ($PreHash) {
    if (-not (Test-Path $DevDbPath)) {
        Write-Error "CRITICAL SAFETY FAILURE: Development database was deleted during test run!"
        exit 1
    }
    $PostHash = Get-FileHashShared -Path $DevDbPath
    $PostSize = (Get-Item -Path $DevDbPath).Length
    Write-Host "Post-Test DB Hash: $PostHash (Size: $PostSize bytes)"

    if ($PreHash -ne $PostHash -or $PreSize -ne $PostSize) {
        Write-Error "CRITICAL SAFETY FAILURE: Development database ($DevDbPath) was modified during test run!"
        exit 1
    }
    Write-Host "SUCCESS: Development database remained 100% untouched and unchanged." -ForegroundColor Green
}

if ($TestExitCode -eq 0) {
    Write-Host "`nAll automated tests passed successfully." -ForegroundColor Green
} else {
    Write-Host "`nTest suite failed with exit code $TestExitCode" -ForegroundColor Red
}

exit $TestExitCode
