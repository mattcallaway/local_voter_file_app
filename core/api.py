import webview
import threading
from core.importer import Importer
import json

class AppAPI:
    def __init__(self, db):
        self.db = db
        self.importer = Importer(db)

    def select_file(self):
        """Opens a native file dialog to select a CSV."""
        window = webview.windows[0]
        result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=('CSV Files (*.csv)',))
        if result and len(result) > 0:
            file_path = result[0]
            # get columns
            cols = self.importer.get_columns(file_path)
            return {"file_path": file_path, "columns": cols}
        return None

    def start_import(self, file_path, state, county, mapping):
        """Spawns import in a thread so UI doesn't freeze."""
        # mapping comes as a dict from JS
        result = self.importer.import_file(file_path, state, county, mapping)
        return result

    def search_voters(self, query=None, filters=None, limit=100, offset=0):
        """
        query: string for fts5 global search
        filters: dict for structured column matching e.g. {"party": "DEM"}
        """
        # Build SQL dynamically
        base_sql = "SELECT * FROM voters"
        conditions = []
        args = []

        if query:
            # use FTS index for fast text matching
            base_sql = "SELECT v.* FROM voters v JOIN voters_fts f ON v.id = f.rowid"
            conditions.append("voters_fts MATCH ?")
            # wildcard for prefix matching
            args.append(f"{query}*")

        if filters:
            for k, v in filters.items():
                if v and v.strip() != "":
                    conditions.append(f"v.{k} LIKE ?")
                    # wildcard around it
                    args.append(f"%{v}%")

        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)

        base_sql += " LIMIT ? OFFSET ?"
        args.extend([limit, offset])

        results = self.db.query(base_sql, tuple(args))
        
        # Parse JSON blocks for frontend
        for r in results:
            if r.get('voting_history'):
                try:
                    r['voting_history'] = json.loads(r['voting_history'])
                except:
                    r['voting_history'] = {}
            if r.get('raw_data'):
                try:
                    r['raw_data'] = json.loads(r['raw_data'])
                except:
                    r['raw_data'] = {}

        return results

    def get_stats(self):
        """Get dashboard stats"""
        total_voters = self.db.query("SELECT COUNT(*) as count FROM voters")[0]['count']
        files = self.db.query("SELECT * FROM files ORDER BY import_date DESC")
        return {"total_voters": total_voters, "files": files}
    
    def create_list(self, name, criteria=None, is_static=True, voter_ids=None):
        c = self.db.conn.cursor()
        c.execute("INSERT INTO lists (name, criteria, is_static) VALUES (?, ?, ?)", 
                  (name, json.dumps(criteria) if criteria else None, is_static))
        list_id = c.lastrowid
        
        if is_static and voter_ids:
            # insert selected voters
            tups = [(list_id, v_id) for v_id in voter_ids]
            c.executemany("INSERT INTO list_voters (list_id, voter_id) VALUES (?, ?)", tups)
        
        self.db.conn.commit()
        return {"status": "success"}
    
    def get_lists(self):
        return self.db.query("SELECT * FROM lists ORDER BY id DESC")
