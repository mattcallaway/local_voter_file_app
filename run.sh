#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "===================================================="
echo "CivicData - Quick Start Launcher (macOS / Linux)"
echo "===================================================="

# 1. Check Python
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python was not found on your system!"
    echo "Please install Python 3 using your package manager or from https://www.python.org/downloads/"
    exit 1
fi

# 2. Check OS and prompt for system-level dependencies
OS_TYPE="$(uname -s)"
if [ "$OS_TYPE" = "Linux" ]; then
    echo "[INFO] Detected Linux..."
    # Check for debian/ubuntu package manager
    if command -v apt-get &>/dev/null; then
        # Check if webkit2gtk is installed
        if ! dpkg -s gir1.2-webkit2-4.0 &>/dev/null && ! dpkg -s gir1.2-webkit2-4.1 &>/dev/null; then
            echo "[WARNING] It looks like you are missing WebKit2GTK system libraries."
            echo "They are required for pywebview to run on Linux (GTK)."
            echo "You can install them by running:"
            echo "    sudo apt-get update"
            echo "    sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1"
            echo ""
            read -p "Would you like this script to try installing them now? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo apt-get update && sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 || true
            fi
        fi
    elif command -v dnf &>/dev/null; then
        echo "[INFO] For Fedora/RHEL, make sure webkit2gtk3 or webkit2gtk4.0 is installed."
    elif command -v pacman &>/dev/null; then
        echo "[INFO] For Arch Linux, make sure webkit2gtk is installed."
    fi
elif [ "$OS_TYPE" = "Darwin" ]; then
    echo "[INFO] Detected macOS..."
fi

# 3. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment (.venv)..."
    $PYTHON_CMD -m venv .venv
fi

# 4. Activate virtual environment and install dependencies
echo "[INFO] Activating virtual environment..."
source .venv/bin/activate

echo "[INFO] Installing/Checking requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Start the application
echo "[INFO] Starting CivicData..."
python main.py

deactivate
