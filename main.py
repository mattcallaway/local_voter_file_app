import os
import sys
import webview
from core.api import AppAPI
from core.database import Database

def main():
    # Initialize Database (SQLite will be created locally in an app_data or current dir)
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voter_data.db")
    db = Database(db_path)
    
    # Initialize API interface exposed to Javascript
    api = AppAPI(db)
    
    # Resolve the path to the front-end folder
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    entry_html = os.path.join(web_dir, "index.html")
    
    # Create the Desktop window
    # Easy to set default size
    webview.create_window(
        title="Voter File Organizer",
        url=entry_html,
        js_api=api,
        width=1200,
        height=800,
        min_size=(800, 600),
        background_color='#1E1E1E' # default dark slate
    )
    
    # debug=True only when running from source, not when frozen as a .exe
    webview.start(debug=not getattr(sys, 'frozen', False))

if __name__ == '__main__':
    main()
