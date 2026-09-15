@echo off
setlocal enabledelayedexpansion
title InvestIQ Launcher
echo ====================================================
echo               Starting InvestIQ...
echo ====================================================
echo.

:: 1. Locate repository directory safely
cd /d "%~dp0"
set "REPO_DIR=%cd%"

:: 2. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo (Make sure to check "Add Python to PATH" during installation)
    echo Or run setup.bat first.
    pause
    exit /b 1
)

:: 3. Detect virtual environment (.venv or venv)
if exist ".venv\Scripts\activate.bat" (
    set "VENV_DIR=.venv"
) else if exist "venv\Scripts\activate.bat" (
    set "VENV_DIR=venv"
) else (
    echo [ERROR] Virtual environment not found!
    echo Please run setup.bat first to create the virtual environment and install dependencies.
    pause
    exit /b 1
)

:: 4. Check backend/.env
if not exist "backend\.env" (
    echo [ERROR] backend\.env not found!
    echo Please run setup.bat or copy backend\.env.example to backend\.env.
    pause
    exit /b 1
)

:: 5. Check if dependencies are installed
call "%VENV_DIR%\Scripts\activate.bat"
python -c "import flask, flask_sqlalchemy, requests, dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Required dependencies are missing in %VENV_DIR%!
    echo Please run setup.bat to install required packages.
    pause
    exit /b 1
)

:: 6. Check whether ports 3000 and 5000 are in use
netstat -ano | findstr /R /C:":5000 .*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Port 5000 is already active. Assuming backend is running or listening.
) else (
    echo [1/3] Starting Flask backend server on port 5000...
    start "InvestIQ Backend" cmd /k "cd /d ""%REPO_DIR%\backend"" && call ""%REPO_DIR%\%VENV_DIR%\Scripts\activate.bat"" && python app.py"
)

netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Port 3000 is already active. Assuming frontend is running.
) else (
    echo [2/3] Starting Frontend web server on port 3000...
    start "InvestIQ Frontend" cmd /k "cd /d ""%REPO_DIR%"" && call ""%REPO_DIR%\%VENV_DIR%\Scripts\activate.bat"" && python -m http.server 3000"
)

:: 7. Poll /api/health until backend is ready (up to 30 attempts, 1 sec interval)
echo [3/3] Waiting for InvestIQ backend health check at http://127.0.0.1:5000/api/health...
set "HEALTH_OK=0"
for /l %%i in (1,1,30) do (
    powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/health' -TimeoutSec 2; if ($r.success -eq $true) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 (
        set "HEALTH_OK=1"
        goto :BackendReady
    )
    timeout /t 1 /nobreak >nul
)

:BackendReady
if "%HEALTH_OK%"=="1" (
    echo [SUCCESS] Backend is healthy and ready!
    echo Opening InvestIQ at http://localhost:3000 ...
    start http://localhost:3000
    echo.
    echo ====================================================
    echo  InvestIQ is active!
    echo  Backend:  http://127.0.0.1:5000
    echo  Frontend: http://localhost:3000
    echo  Keep the server terminal windows open while in use.
    echo ====================================================
) else (
    echo.
    echo [ERROR] Backend health check failed to respond within 30 seconds.
    echo Please check the "InvestIQ Backend" terminal window for error logs.
)

pause
