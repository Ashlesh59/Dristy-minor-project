@echo off
title InvestIQ Launcher
echo ====================================================
echo               Starting InvestIQ...
echo ====================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo (Make sure to check "Add Python to PATH" during installation)
    pause
    exit /b 1
)

:: 2. Check virtual environment
if not exist "venv\" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
)

:: 3. Install requirements
echo [2/4] Checking and installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
pip install --quiet -r backend\requirements.txt

:: 4. Check backend .env file
if not exist "backend\.env" (
    echo.
    echo [NOTICE] backend\.env not found. Creating from .env.example...
    copy backend\.env.example backend\.env >nul
    echo Please make sure your API keys are added in backend\.env for live AI data.
)

:: 5. Start Backend Server in background window
echo [3/4] Starting Flask backend server on port 5000...
start "InvestIQ Backend" cmd /k "call venv\Scripts\activate.bat && cd backend && python app.py"

:: 6. Start Frontend Server in background window
echo [4/4] Starting Frontend web server on port 3000...
start "InvestIQ Frontend" cmd /k "call venv\Scripts\activate.bat && python -m http.server 3000"

:: 7. Wait 2 seconds and open browser
timeout /t 2 /nobreak >nul
echo.
echo Opening InvestIQ at http://localhost:3000...
start http://localhost:3000

echo ====================================================
echo  InvestIQ is running!
echo  Keep the server windows open while using the app.
echo ====================================================
pause
