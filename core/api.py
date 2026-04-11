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
                if v and str(v).strip() != "":
                    if k.startswith('district_'):
                        d_key = k.replace('district_', '')
                        conditions.append(f"json_extract(v.districts, '$.{d_key}') LIKE ?")
                        args.append(f"%{v}%")
                    elif k == 'history_math':
                        # v = {"elections": ["General 2024", "Primary 2022"], "threshold": 2}
                        # We build a math query using json_extract
                        elections = v.get('elections', [])
                        threshold = int(v.get('threshold', 0))
                        
                        if len(elections) > 0 and threshold > 0:
                            cases = []
                            for el in elections:
                                # Count if election key exists and is not empty
                                cases.append(f"(CASE WHEN json_extract(v.voting_history, '$.\"{el}\"') IS NOT NULL AND json_extract(v.voting_history, '$.\"{el}\"') != '' THEN 1 ELSE 0 END)")
                            math_str = " + ".join(cases)
                            conditions.append(f"({math_str}) >= ?")
                            args.append(threshold)
                    elif k == 'in_list':
                        conditions.append(f"v.id IN (SELECT voter_id FROM list_voters WHERE list_id = ?)")
                        args.append(v)
                    elif k == 'has_tag':
                        conditions.append(f"v.id IN (SELECT voter_id FROM voter_tags WHERE tag_id = ?)")
                        args.append(v)
                    else:
                        conditions.append(f"v.{k} LIKE ?")
                        args.append(f"%{v}%")

        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)

        base_sql += " LIMIT ? OFFSET ?"
        args.extend([limit, offset])

        results = self.db.query(base_sql, tuple(args))
        
        # Parse JSON blocks for frontend
        for r in results:
            for json_col in ['voting_history', 'raw_data', 'custom_data']:
                if r.get(json_col):
                    try:
                        r[json_col] = json.loads(r[json_col])
                    except:
                        r[json_col] = {}
                else:
                    r[json_col] = {}

        return results

    def get_elections(self):
        """Get all distinct elections registered in the DB."""
        # Querying keys from JSON objects across table. SQLite json_each is perfect.
        sql = "SELECT DISTINCT key FROM voters, json_each(voting_history) WHERE key IS NOT NULL ORDER BY key DESC"
        results = self.db.query(sql)
        return [r['key'] for r in results]

    def get_tags(self):
        return self.db.query("SELECT * FROM tags ORDER BY name ASC")

    def bulk_add_tag(self, voter_ids, tag_id):
        c = self.db.conn.cursor()
        tups = [(v_id, tag_id) for v_id in voter_ids]
        c.executemany("INSERT OR IGNORE INTO voter_tags (voter_id, tag_id) VALUES (?, ?)", tups)
        self.db.conn.commit()
        return {"status": "success"}

    def bulk_update_custom_data(self, voter_ids, key, value):
        c = self.db.conn.cursor()
        tups = [(value, v_id) for v_id in voter_ids]
        c.executemany(f"UPDATE voters SET custom_data = json_set(COALESCE(custom_data, '{{}}'), '$.{key}', ?) WHERE id = ?", tups)
        self.db.conn.commit()
        return {"status": "success"}



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
