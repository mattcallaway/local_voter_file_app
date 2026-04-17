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
        self._geocode_jobs = {}   # {list_id: {status, progress, total, message}}

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

                elif k == 'has_tag':
                    conditions.append("v.id IN (SELECT voter_id FROM voter_tags WHERE tag_id = ?)")
                    args.append(int(val))

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
        # Include current tags so modal can render them
        r['tags'] = self.get_voter_tags(voter_id)
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
    # Tag management
    # ------------------------------------------------------------------
    def get_tags(self):
        """Return all tags ordered by name."""
        return self.db.query("SELECT * FROM tags ORDER BY name ASC")

    def create_tag(self, name, color='#3182ce'):
        """Create a new tag. Returns the tag object or error on duplicate."""
        name = name.strip()
        if not name:
            return {"status": "error", "message": "Tag name cannot be empty"}
        try:
            tag_id = self.db.execute(
                "INSERT INTO tags (name, color) VALUES (?, ?)", (name, color)
            )
            return {"status": "success", "id": tag_id, "name": name, "color": color}
        except sqlite3.IntegrityError:
            return {"status": "error", "message": f"Tag '{name}' already exists"}

    def delete_tag(self, tag_id):
        """Delete a tag and remove it from all voters."""
        self.db.execute("DELETE FROM voter_tags WHERE tag_id = ?", (tag_id,))
        self.db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        return {"status": "success"}

    def get_voter_tags(self, voter_id):
        """Return all tags applied to a specific voter."""
        return self.db.query(
            "SELECT t.* FROM tags t "
            "JOIN voter_tags vt ON t.id = vt.tag_id "
            "WHERE vt.voter_id = ? ORDER BY t.name",
            (voter_id,)
        )

    def add_voter_tag(self, voter_id, tag_id):
        """Apply a single tag to a single voter."""
        try:
            self.db.execute(
                "INSERT OR IGNORE INTO voter_tags (voter_id, tag_id) VALUES (?, ?)",
                (int(voter_id), int(tag_id))
            )
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def remove_voter_tag(self, voter_id, tag_id):
        """Remove a single tag from a single voter."""
        self.db.execute(
            "DELETE FROM voter_tags WHERE voter_id = ? AND tag_id = ?",
            (int(voter_id), int(tag_id))
        )
        return {"status": "success"}

    def bulk_add_tag(self, voter_ids, tag_id):
        """Apply a tag to many voters at once."""
        c = self.db.conn.cursor()
        tups = [(int(v_id), int(tag_id)) for v_id in voter_ids]
        c.executemany(
            "INSERT OR IGNORE INTO voter_tags (voter_id, tag_id) VALUES (?, ?)", tups
        )
        self.db.conn.commit()
        return {"status": "success", "count": len(tups)}

    # ------------------------------------------------------------------
    # Bulk custom data
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

    def delete_file(self, file_id):
        """
        Delete an imported file and all associated voter records.
        Cascades through: voter_tags → list_voters → voters → files.
        The voters_ad trigger automatically cleans up FTS entries on each row delete.
        """
        file_id = int(file_id)
        c = self.db.conn.cursor()
        c.execute("BEGIN")
        # Remove tag associations for voters in this file
        c.execute(
            "DELETE FROM voter_tags WHERE voter_id IN (SELECT id FROM voters WHERE file_id = ?)",
            (file_id,)
        )
        # Remove list associations for voters in this file
        c.execute(
            "DELETE FROM list_voters WHERE voter_id IN (SELECT id FROM voters WHERE file_id = ?)",
            (file_id,)
        )
        # Delete the voters (the voters_ad trigger handles FTS cleanup per row)
        c.execute("DELETE FROM voters WHERE file_id = ?", (file_id,))
        # Delete the file record
        c.execute("DELETE FROM files WHERE id = ?", (file_id,))
        self.db.conn.commit()
        # Invalidate caches since available elections/parties may have changed
        self._invalidate_cache()
        return {"status": "success"}


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

    # ------------------------------------------------------------------
    # Canvass map — geocoding & map data
    # ------------------------------------------------------------------

    def get_list_map_data(self, list_id):
        """Return all voters in a list with their geocode columns and summary stats."""
        list_id = int(list_id)
        voters = self.db.query("""
            SELECT v.id, v.first_name, v.middle_name, v.last_name, v.suffix,
                   v.address, v.city, v.state, v.zip, v.party, v.age, v.sex,
                   v.phone, v.precinct, v.lat, v.lng,
                   v.geocode_status, v.geocode_confidence, v.geocode_address,
                   v.raw_data, v.voting_history
            FROM voters v
            JOIN list_voters lv ON v.id = lv.voter_id
            WHERE lv.list_id = ?
            ORDER BY v.geocode_address NULLS LAST, v.address, v.last_name
        """, (list_id,))

        # Parse raw_data so geocoder can fall back to it for address building
        for v in voters:
            if v.get('raw_data'):
                try:
                    v['raw_data'] = json.loads(v['raw_data'])
                except Exception:
                    v['raw_data'] = {}
            else:
                v['raw_data'] = {}

        total     = len(voters)
        geocoded  = sum(1 for v in voters if v.get('geocode_status') == 'matched')
        unmatched = sum(1 for v in voters if v.get('geocode_status') in ('unmatched', 'failed', 'no_address'))
        pending   = total - geocoded - unmatched

        return {
            'voters': voters,
            'stats': {
                'total':     total,
                'geocoded':  geocoded,
                'unmatched': unmatched,
                'pending':   pending,
            }
        }

    def geocode_list(self, list_id):
        """
        Start a background thread that geocodes un-geocoded voters in the list.
        JS should poll get_geocode_status() until status == 'done' or 'error'.
        """
        from core.geocoder import geocode_voters
        list_id = int(list_id)

        # Avoid double-starting
        job = self._geocode_jobs.get(list_id, {})
        if job.get('status') == 'running':
            return {'status': 'already_running', 'total': job.get('total', 0)}

        # Fetch only voters that still need geocoding
        voters = self.db.query("""
            SELECT v.id, v.address, v.city, v.state, v.zip,
                   v.lat, v.lng, v.geocode_status, v.geocode_address, v.raw_data
            FROM voters v
            JOIN list_voters lv ON v.id = lv.voter_id
            WHERE lv.list_id = ?
              AND (v.geocode_status IS NULL OR v.geocode_status != 'matched')
        """, (list_id,))

        for v in voters:
            if v.get('raw_data'):
                try:
                    v['raw_data'] = json.loads(v['raw_data'])
                except Exception:
                    v['raw_data'] = {}

        if not voters:
            return {'status': 'success', 'total': 0, 'geocoded': 0}

        self._geocode_jobs[list_id] = {
            'status': 'running', 'progress': 0,
            'total': len(voters), 'message': 'Starting…',
        }

        def _run():
            def cb(current, total, message):
                self._geocode_jobs[list_id].update({
                    'progress': current, 'total': total, 'message': message
                })
            try:
                geocode_voters(self.db, voters, progress_callback=cb)
                self._geocode_jobs[list_id]['status'] = 'done'
            except Exception as exc:
                self._geocode_jobs[list_id].update({'status': 'error', 'message': str(exc)})
                print(f'[api] geocode_list error: {exc}')

        threading.Thread(target=_run, daemon=True).start()
        return {'status': 'started', 'total': len(voters)}

    def get_geocode_status(self, list_id):
        """Poll-able progress endpoint for an in-flight geocoding job."""
        list_id = int(list_id)
        return self._geocode_jobs.get(
            list_id,
            {'status': 'idle', 'progress': 0, 'total': 0, 'message': ''}
        )

    def save_map_selection(self, name, voter_ids):
        """Save a geographic subset selected on the map as a new static list."""
        if not name or not voter_ids:
            return {'status': 'error', 'message': 'Name and voter IDs are required'}
        return self.create_list(name, criteria=None, is_static=1, voter_ids=voter_ids)

    def export_canvass_list(self, voter_ids):
        """
        Build a canvass-ready CSV: one row per voter, sorted by household (geocode_address),
        with sequential stop numbers so canvassers know door-knock order.
        Returns {'status', 'csv', 'count', 'stops'}.
        """
        import csv as _csv
        import io as _io

        if not voter_ids:
            return {'status': 'error', 'message': 'No voters selected'}

        placeholders = ','.join('?' for _ in voter_ids)
        voters = self.db.query(f"""
            SELECT v.id, v.first_name, v.middle_name, v.last_name, v.suffix,
                   v.address, v.city, v.state, v.zip, v.party, v.age, v.sex,
                   v.phone, v.precinct, v.lat, v.lng, v.geocode_address
            FROM voters v
            WHERE v.id IN ({placeholders})
            ORDER BY v.geocode_address NULLS LAST, v.address, v.last_name
        """, tuple(voter_ids))

        if not voters:
            return {'status': 'error', 'message': 'No voters found for given IDs'}

        output = _io.StringIO()
        fields = ['stop_num', 'household_address', 'first_name', 'middle_name',
                  'last_name', 'suffix', 'party', 'age', 'sex', 'phone',
                  'precinct', 'lat', 'lng', 'voter_id']
        writer = _csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()

        stop_num  = 0
        last_addr = None
        for v in voters:
            addr = v.get('geocode_address') or v.get('address') or ''
            if addr != last_addr:
                stop_num += 1
                last_addr = addr
            writer.writerow({
                'stop_num':         stop_num,
                'household_address': addr,
                'first_name':       v.get('first_name', ''),
                'middle_name':      v.get('middle_name', ''),
                'last_name':        v.get('last_name', ''),
                'suffix':           v.get('suffix', ''),
                'party':            v.get('party', ''),
                'age':              v.get('age', ''),
                'sex':              v.get('sex', ''),
                'phone':            v.get('phone', ''),
                'precinct':         v.get('precinct', ''),
                'lat':              v.get('lat', ''),
                'lng':              v.get('lng', ''),
                'voter_id':         v['id'],
            })

        return {
            'status': 'success',
            'csv':    output.getvalue(),
            'count':  len(voters),
            'stops':  stop_num,
        }
