@echo off
setlocal enabledelayedexpansion
title InvestIQ Setup
echo ====================================================
echo             InvestIQ Setup ^& Initialization
echo ====================================================
echo.

:: 1. Locate repository directory safely
cd /d "%~dp0"
set "REPO_DIR=%cd%"

:: 2. Verify Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo Ensure you check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [1/4] Found Python %PY_VER%

:: 3. Create virtual environment
if not exist ".venv\" if not exist "venv\" (
    echo [2/4] Creating virtual environment (.venv)...
    python -m venv .venv
    set "VENV_DIR=.venv"
) else (
    if exist ".venv\" (
        set "VENV_DIR=.venv"
    ) else (
        set "VENV_DIR=venv"
    )
    echo [2/4] Virtual environment found at %VENV_DIR%
)

:: 4. Install dependencies
echo [3/4] Installing backend dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
pip install --quiet -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies. Please check your internet connection.
    pause
    exit /b 1
)

:: 5. Create backend/.env if missing (never overwrite)
echo [4/4] Configuring environment variables...
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
        echo [INFO] Created backend\.env from template.
    ) else (
        echo [WARNING] backend\.env.example not found.
    )
) else (
    echo [INFO] backend\.env already exists. Preserving existing configuration.
)

echo.
echo ====================================================
echo  API Key Configuration (Optional for Market Data/AI)
echo ====================================================
echo  To configure API keys:
echo  1. Open backend\.env in a text editor.
echo  2. Set ALPHA_VANTAGE_API_KEY (from https://www.alphavantage.co/)
echo  3. Set GEMINI_API_KEY (from https://aistudio.google.com/)
echo ====================================================
echo.

:: 6. Optional: Import NSE Master Companies if EQUITY_L.csv exists
if exist "data\raw\nse\EQUITY_L.csv" (
    echo [OPTIONAL] Found data\raw\nse\EQUITY_L.csv.
    echo Importing NSE listed companies into local database...
    python -m backend.cli.sync_companies --source nse --file data\raw\nse\EQUITY_L.csv
    echo [SUCCESS] NSE master company import completed.
) else (
    echo [INFO] No data\raw\nse\EQUITY_L.csv found. Skipping automatic NSE import.
    echo (You can run `python -m backend.cli.sync_companies --source nse --file path/to/EQUITY_L.csv` anytime)
)

:: 7. Optional: Import NSE Bhavcopy Market Data if directory exists
if exist "data\raw\nse\bhavcopy\" (
    echo [OPTIONAL] Found data\raw\nse\bhavcopy\ directory.
    echo Importing historical Bhavcopy price data into local database...
    python -m backend.cli.sync_market_data --directory data\raw\nse\bhavcopy
    echo [SUCCESS] NSE Bhavcopy price synchronization completed.
)

echo.
echo ====================================================
echo  Setup Complete!
echo  You can now launch the application by running run.bat
echo ====================================================
pause
