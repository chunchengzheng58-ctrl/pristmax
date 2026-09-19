@echo off
REM Pristmax Desktop Launcher
REM Usage: Double-click this file or run from command line

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Check dependencies
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install flask flask-cors pyyaml
)

echo Starting Pristmax Desktop...
echo.
echo Open your browser and go to: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

python main.py --host 0.0.0.0 --port 5000

pause
