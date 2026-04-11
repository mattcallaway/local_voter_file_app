# Local Voter File App

A lightweight, powerful desktop application to import, search, tag, and export large voter files in CSV format locally. Built for speed, offline usage, and large dataset handling.

## Installation & Running (For Novices)

1. **Install Python**: Download and install Python from [python.org](https://python.org). Make sure to check the box "Add Python to PATH" during installation.
2. **Open Command Prompt / Terminal**.
3. **Navigate to this folder** (e.g., `cd path/to/local_voter_file_app`).
4. **Install Requirements**:
   ```bash
   pip install -r requirements.txt
   ```
5. **Run the App**:
   ```bash
   python main.py
   ```
   *The app will open as a native desktop window.*

## Packaging into an `.exe` (For Distribution)

If you want to package the application into a single `.exe` file that can be sent to other Windows machines (who don't have Python installed), run:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the executable:
   ```bash
   pyinstaller --noconsole --onefile --add-data "web;web" main.py
   ```
3. The packaged `.exe` will be found in the `dist` folder. Simply double-click to run!
