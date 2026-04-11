import csv
import json
import sqlite3

class Importer:
    def __init__(self, db):
        self.db = db

    def get_columns(self, file_path):
        """Read the first row of a CSV and return column headers."""
        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                return next(reader, [])
        except Exception as e:
            return []

    def import_file(self, file_path, state, county, mapping):
        """
        mapping is a dict: { 'csv_header_name': 'normalized_sql_column' }
        where normalized_sql_column is one of:
        first_name, last_name, address, city, state, zip, age, sex, party, phone, precinct, polling_location, history_*, custom_*
        """
        try:
            # 1. Register file
            c = self.db.conn.cursor()
            c.execute('INSERT INTO files (filename, state, county) VALUES (?, ?, ?)', (file_path, state, county))
            file_id = c.lastrowid

            # Prepare to map correctly
            sql_cols = ["first_name", "last_name", "address", "city", "state", "zip", "age", "sex", "party", "phone", "precinct", "polling_location"]
            
            # Read and ingest
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                rows_to_insert = []
                for row in reader:
                    sql_row = {col: None for col in sql_cols}
                    sql_row['voting_history'] = {}
                    
                    # Store entire raw row as well
                    sql_row['raw_data'] = row
                    
                    for original_col, value in row.items():
                        if not original_col:
                            continue
                        mapped_target = mapping.get(original_col, None)
                        
                        if mapped_target in sql_cols:
                            sql_row[mapped_target] = value
                        elif mapped_target and mapped_target.startswith('history_'):
                            # it's a voting history column
                            h_key = mapped_target.replace('history_', '')
                            sql_row['voting_history'][h_key] = value
                            
                    # Prepare tuple for insertion
                    tup = (
                        file_id,
                        sql_row['first_name'],
                        sql_row['last_name'],
                        sql_row['address'],
                        sql_row['city'],
                        sql_row['state'],
                        sql_row.get('zip'),
                        sql_row['age'],
                        sql_row['sex'],
                        sql_row['party'],
                        sql_row['phone'],
                        sql_row['precinct'],
                        sql_row['polling_location'],
                        json.dumps(sql_row['voting_history']),
                        json.dumps(sql_row['raw_data'])
                    )
                    rows_to_insert.append(tup)
                    
                    # chunking at 10k
                    if len(rows_to_insert) >= 10000:
                        c.executemany('''
                            INSERT INTO voters 
                            (file_id, first_name, last_name, address, city, state, zip, age, sex, party, phone, precinct, polling_location, voting_history, raw_data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', rows_to_insert)
                        rows_to_insert.clear()

                # any remaining
                if rows_to_insert:
                    c.executemany('''
                        INSERT INTO voters 
                        (file_id, first_name, last_name, address, city, state, zip, age, sex, party, phone, precinct, polling_location, voting_history, raw_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', rows_to_insert)

            self.db.conn.commit()
            return {"status": "success", "file_id": file_id}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

