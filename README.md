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

This section will walk you through exactly how to get the application running on your Windows computer for the first time.

### Step 1: Install Python
If you don't already have Python installed, you'll need it to run the backend of the app!
1. Go to [Python.org](https://www.python.org/downloads/) and click the big yellow button to download the latest Windows installer.
2. Open the downloaded file.
3. 🛑 **CRITICAL STEP:** At the very bottom of the installation window, check the box that says **"Add python.exe to PATH"**.
4. Click "Install Now" and wait for it to finish.

### Step 2: Download the Application
1. Download this entire folder (if you are on GitHub, click the green "Code" button and select "Download ZIP").
2. Extract/Unzip the folder somewhere on your computer (like your Documents or Desktop).

### Step 3: Run the Setup
1. Open up the **Command Prompt** on Windows (Press the Windows Key, type `cmd`, and press Enter).
2. "Change Directory" into the folder where you saved the app by typing `cd` followed by a space, and then the path to the folder. *(Pro-tip: You can type `cd `, and then drag and drop the application folder directly into the black box!)*. Press Enter.
3. Install the required modules by typing this exactly and pressing Enter:
   ```bash
   pip install -r requirements.txt
   ```
   *Wait a minute for the computer to download the background pieces.*

### Step 4: Open the App
Whenever you want to run the app, just open your command prompt in this folder and type:
   ```bash
   python main.py
   ```
**That's it!** A beautiful desktop window will instantly pop open and you can begin importing your files!

---

## 📦 How to Package it as a `.exe` (For Advanced Users)

If you are a campaign manager and want to email this program as a single double-clickable `.exe` file to a volunteer so they don't have to install Python, you can "bundle" it easily!

1. Open your command prompt in the app folder.
2. Install the PyInstaller bundling tool:
   ```bash
   pip install pyinstaller
   ```
3. Run the packager command:
   ```bash
   pyinstaller --noconsole --onefile --add-data "web;web" main.py
   ```
4. Once it finishes, look inside the newly created `dist` folder. You will find `main.exe` (you can rename it to `CivicData.exe`). You can move this single file anywhere, put it on a flash drive, and send it to friends!
