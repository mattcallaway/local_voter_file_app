# CivicData: Local Voter File Manager

Welcome to **CivicData**! This is a simple, incredibly fast, and completely offline desktop application designed for political campaigns, organizers, and volunteers. It allows anyone to easily ingest massive spreadsheets of voter data, intelligently search them, and build actionable lists without needing an internet connection or a technical background.

---

## 🌟 What Does This App Do?

This app solves the headache of dealing with massive, messy voter CSV files. It acts as a personal, offline database that runs gracefully on your Windows PC. 

Here are the core features:
1. **Intelligent CSV Import:** You can upload any voter file spreadsheet (`.csv`). The app automatically reads your column headers and uses a "smart guess" algorithm to map them to standard fields (First Name, Address, Phone, etc.).
2. **Handles Any Data Layout:** Whether your file splits addresses into three columns (`mAddressLine1`, `mAddressLine2`), or has random districts (`CD 12`, `Supervisor 5`), the importer seamlessly groups them or saves them intelligently. We never discard your data!
3. **Instantly Search Hundreds of Thousands of Rows:** The app uses an advanced local indexing engine. Type a name or zip code in the quick search, and it filters instantly. You can also filter dynamically by exact district, party, or city.
4. **Build and Save Static Lists:** Check the boxes next to the voters you want and save them as a custom named list for easy exporting and organization.
5. **Completely Local & Private:** Unlike cloud-based voter software, your data never leaves your computer.

---

## 🛠️ How to Install and Run (For Beginners)

This app is cross-platform and runs on **Windows, macOS, and Linux**. 

### Quick Start (Automated Scripts)
We provide automated launchers that will check for Python, set up a local virtual environment (`.venv`), install all requirements, and start the app for you.

*   **Windows**: Double-click the file [run.bat](file:///c:/Users/Mathew%20C/OneDrive/Documents/VoterData_Offline/run.bat) (or run `run.bat` in Command Prompt).
*   **macOS & Linux**: Open your Terminal in this directory, make the launcher executable, and run it:
    ```bash
    chmod +x run.sh
    ./run.sh
    ```

---

### Manual Setup (Step-by-Step)

If you prefer to set up the application manually:

#### Step 1: Install Python
Ensure Python 3.8+ is installed on your system:
*   **Windows**: Download the installer from [Python.org](https://www.python.org/downloads/). **CRITICAL:** Check the box **"Add python.exe to PATH"** before clicking install.
*   **macOS**: Install Python via [Python.org](https://www.python.org/downloads/) or via Homebrew (`brew install python`).
*   **Linux**: Install Python and virtual environment headers using your package manager (e.g. `sudo apt install python3 python3-venv python3-pip`).

#### Step 2: Install System Dependencies (Linux Only)
`pywebview` requires native system webview libraries on Linux.
*   **Ubuntu / Debian / Mint**:
    ```bash
    sudo apt update
    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
    ```
    *(Note: If `gir1.2-webkit2-4.1` is not available, use `gir1.2-webkit2-4.0` instead)*
*   **Fedora / RedHat**:
    ```bash
    sudo dnf install python3-gobject gtk3 webkit2gtk4.0
    ```
*   **Arch Linux**:
    ```bash
    sudo pacman -S python-gobject gtk3 webkit2gtk
    ```

#### Step 3: Set Up a Virtual Environment & Install Requirements
Create a virtual environment to isolate project packages, then install dependencies:
```bash
# Create a virtual environment
python -m venv .venv

# Activate it (Windows)
.venv\Scripts\activate

# Activate it (macOS/Linux)
source .venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 4: Run the App
```bash
python main.py
```

---

## 📦 Packaging Standalone Executables (For Advanced Users)

If you want to bundle CivicData into a single, double-clickable app that runs without needing Python installed, you can build it using `pyinstaller`.

First, activate your virtual environment and install PyInstaller:
```bash
pip install pyinstaller
```

Then run the package command for your operating system:

*   **Windows (creates `.exe`)**:
    ```bash
    pyinstaller --noconsole --onefile --add-data "web;web" main.py
    ```
*   **macOS (creates a standalone `.app` bundle)**:
    ```bash
    pyinstaller --noconsole --windowed --add-data "web:web" main.py
    ```
*   **Linux (creates a standalone binary)**:
    ```bash
    pyinstaller --noconsole --onefile --add-data "web:web" main.py
    ```

> [!IMPORTANT]
> Note the syntax difference in the `--add-data` parameter: Windows uses a semicolon `;` as a separator, while macOS and Linux use a colon `:`.

Once finished, your standalone executable will be generated inside the newly created `dist/` directory.

