#!/bin/bash
# Pristmax Desktop Launcher for Linux/macOS

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Pristmax Desktop"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.10+ from https://python.org"
    exit 1
fi

# Check dependencies
if ! python3 -c "import flask" &> /dev/null; then
    echo "Installing dependencies..."
    pip3 install flask flask-cors pyyaml
fi

echo "Starting Pristmax Desktop..."
echo ""
echo "Open your browser and go to: http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo ""

python3 main.py --host 0.0.0.0 --port 5000
