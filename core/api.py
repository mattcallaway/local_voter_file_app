import webview
import threading
import sqlite3
import re
import json
from core.importer import Importer

# Whitelist of allowed column names for dynamic filter building — prevents SQL injection
ALLOWED_FILTER_COLS = {'city', 'precinct', 'state', 'zip'}


class AppAPI:
    def __init__(self, db):
        self.db = db
        self.importer = Importer(db)
        self._elections_cache = None
        self._parties_cache = None

    def _invalidate_cache(self):
        """Invalidate cached lookups. Called after any import."""
        self._elections_cache = None
        self._parties_cache = None

    def select_file(self):
        """Opens a native file dialog to select a CSV."""
        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=('CSV Files (*.csv)',)
        )
        if result and len(result) > 0:
            file_path = result[0]
            cols = self.importer.get_columns(file_path)
            return {"file_path": file_path, "columns": cols}
        return None

    def start_import(self, file_path, state, county, mapping):
        """Run import and invalidate caches so election/party lists stay fresh."""
        result = self.importer.import_file(file_path, state, county, mapping)
        self._invalidate_cache()
        return result

    # ------------------------------------------------------------------
    # Shared filter/condition builder (used by both search and count)
    # ------------------------------------------------------------------
    def _build_filter_conditions(self, query, filters):
        conditions = []
        args = []

        if query:
            conditions.append("voters_fts MATCH ?")
            args.append(f"{query}*")

        if filters:
            for k, val in filters.items():
                # Skip empty / falsy values
                if val is None:
                    continue
                if isinstance(val, str) and not val.strip():
                    continue
                if isinstance(val, list) and not val:
                    continue

                if k == 'party':
                    if isinstance(val, list):
                        non_empty = [p for p in val if p and str(p).strip()]
                        if non_empty:
                            placeholders = ','.join(['?' for _ in non_empty])
                            conditions.append(f"v.party IN ({placeholders})")
                            args.extend(non_empty)
                    elif isinstance(val, str) and val.strip():
                        conditions.append("v.party LIKE ?")
                        args.append(f"%{val}%")

                elif k.startswith('district_'):
                    d_key = k.replace('district_', '')
                    conditions.append(f"json_extract(v.districts, '$.{d_key}') LIKE ?")
                    args.append(f"%{val}%")

                elif k == 'history_math':
                    # val = {"elections": [...], "threshold": 2, "mode": "at_least"|"exactly"}
                    elections = val.get('elections', [])
                    threshold = int(val.get('threshold', 0))
                    mode = val.get('mode', 'at_least')
                    if elections and threshold > 0:
                        cases = [
                            f"(CASE WHEN json_extract(v.voting_history, '$.\"{el}\"') IS NOT NULL "
                            f"AND json_extract(v.voting_history, '$.\"{el}\"') != '' THEN 1 ELSE 0 END)"
                            for el in elections
                        ]
                        math_str = " + ".join(cases)
                        operator = ">=" if mode == 'at_least' else "="
                        conditions.append(f"({math_str}) {operator} ?")
                        args.append(threshold)

                elif k == 'in_list':
                    conditions.append("v.id IN (SELECT voter_id FROM list_voters WHERE list_id = ?)")
                    args.append(val)

                elif k in ALLOWED_FILTER_COLS:
                    conditions.append(f"v.{k} LIKE ?")
                    args.append(f"%{val}%")

        return conditions, args

    # ------------------------------------------------------------------
    # Search — lightweight display columns only (no JSON parsing)
    # ------------------------------------------------------------------
    def search_voters(self, query=None, filters=None, limit=100, offset=0):
        """
        Returns display-only columns for the results table.
        Heavy JSON blobs are NOT parsed here — call get_voter_detail() for the modal.
        """
        select_cols = (
            "v.id, v.first_name, v.middle_name, v.last_name, v.suffix, "
            "v.address, v.city, v.party, v.age, v.precinct"
        )

        if query:
            base_sql = f"SELECT {select_cols} FROM voters v JOIN voters_fts f ON v.id = f.rowid"
        else:
            base_sql = f"SELECT {select_cols} FROM voters v"

        conditions, args = self._build_filter_conditions(query, filters)

        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)

        base_sql += " LIMIT ? OFFSET ?"
        args.extend([limit, offset])

        return self.db.query(base_sql, tuple(args))

    # ------------------------------------------------------------------
    # Voter detail — full record with all JSON parsed (modal use only)
    # ------------------------------------------------------------------
    def get_voter_detail(self, voter_id):
        """Fetch one voter's complete record with all JSON blobs parsed."""
        results = self.db.query("SELECT * FROM voters WHERE id = ?", (voter_id,))
        if not results:
            return None
        r = results[0]
        for json_col in ['voting_history', 'raw_data', 'custom_data', 'districts', 'phones']:
            if r.get(json_col):
                try:
                    r[json_col] = json.loads(r[json_col])
                except Exception as e:
                    print(f"[api] JSON parse error on {json_col} for voter {voter_id}: {e}")
                    r[json_col] = {} if json_col != 'phones' else []
            else:
                r[json_col] = {} if json_col != 'phones' else []
        return r

    # ------------------------------------------------------------------
    # Lookup lists — cached after first load, cleared on import
    # ------------------------------------------------------------------
    def get_elections(self):
        """Return all distinct election keys from voting_history JSON. Cached."""
        if self._elections_cache is not None:
            return self._elections_cache
        sql = (
            "SELECT DISTINCT key FROM voters, json_each(voting_history) "
            "WHERE key IS NOT NULL ORDER BY key DESC"
        )
        results = self.db.query(sql)
        self._elections_cache = [r['key'] for r in results]
        return self._elections_cache

    def get_parties(self):
        """Return all distinct party codes. Cached."""
        if self._parties_cache is not None:
            return self._parties_cache
        results = self.db.query(
            "SELECT DISTINCT party FROM voters "
            "WHERE party IS NOT NULL AND party != '' ORDER BY party ASC"
        )
        self._parties_cache = [r['party'] for r in results]
        return self._parties_cache

    # ------------------------------------------------------------------
    # Count (mirrors search_voters filter logic, returns int)
    # ------------------------------------------------------------------
    def count_voters(self, query=None, filters=None):
        """Return total count matching the same query/filter criteria as search_voters."""
        if query:
            base_sql = "SELECT COUNT(*) as count FROM voters v JOIN voters_fts f ON v.id = f.rowid"
        else:
            base_sql = "SELECT COUNT(*) as count FROM voters v"

        conditions, args = self._build_filter_conditions(query, filters)

        if conditions:
            base_sql += " WHERE " + " AND ".join(conditions)

        result = self.db.query(base_sql, tuple(args))
        return result[0]['count'] if result else 0

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------
    def bulk_update_custom_data(self, voter_ids, key, value):
        c = self.db.conn.cursor()
        tups = [(value, v_id) for v_id in voter_ids]
        c.executemany(
            f"UPDATE voters SET custom_data = json_set(COALESCE(custom_data, '{{}}'), '$.{key}', ?) WHERE id = ?",
            tups
        )
        self.db.conn.commit()
        return {"status": "success"}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    def get_stats(self):
        """Get dashboard stats."""
        total_voters = self.db.query("SELECT COUNT(*) as count FROM voters")[0]['count']
        files = self.db.query("SELECT * FROM files ORDER BY import_date DESC")
        return {"total_voters": total_voters, "files": files}

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------
    def create_list(self, name, criteria=None, is_static=True, voter_ids=None):
        c = self.db.conn.cursor()
        c.execute(
            "INSERT INTO lists (name, criteria, is_static) VALUES (?, ?, ?)",
            (name, json.dumps(criteria) if criteria else None, is_static)
        )
        list_id = c.lastrowid

        if is_static and voter_ids:
            tups = [(list_id, v_id) for v_id in voter_ids]
            c.executemany("INSERT INTO list_voters (list_id, voter_id) VALUES (?, ?)", tups)

        self.db.conn.commit()
        return {"status": "success"}

    def get_lists(self):
        return self.db.query("SELECT * FROM lists ORDER BY id DESC")
