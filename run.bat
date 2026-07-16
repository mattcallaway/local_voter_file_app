@echo off
setlocal enabledelayedexpansion

echo ====================================================
echo CivicData - Quick Start Launcher (Windows)
echo ====================================================

:: 1. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your system!
    echo Please download and install Python from: https://www.python.org/downloads/
    echo Make sure to check the box "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

:: 2. Check virtual environment
if not exist .venv (
    echo [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

:: 3. Activate virtual environment and install dependencies
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Installing/Checking requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

:: 4. Start the application
echo [INFO] Starting CivicData...
python main.py
if %errorlevel% neq 0 (
    echo [WARNING] Application exited with error code %errorlevel%
    pause
)

deactivate
