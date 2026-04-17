import csv
import json
import re
import sqlite3
import traceback


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
            print(f"[importer] Could not read columns from {file_path}: {e}")
            return []

    def import_file(self, file_path, state, county, mapping):
        try:
            c = self.db.conn.cursor()

            # Explicit transaction — ensures one disk sync for the entire import
            # regardless of how many executemany batches we use
            c.execute("BEGIN")

            # 1. Register file
            c.execute(
                'INSERT INTO files (filename, state, county) VALUES (?, ?, ?)',
                (file_path, state, county)
            )
            file_id = c.lastrowid

            sql_cols = [
                "first_name", "middle_name", "last_name", "suffix",
                "city", "state", "zip", "age", "sex", "party", "phone",
                "precinct", "polling_location"
            ]

            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                rows_to_insert = []
                for row in reader:
                    sql_row = {col: None for col in sql_cols}
                    sql_row['voting_history'] = {}
                    sql_row['districts'] = {}
                    sql_row['phones'] = []
                    address_parts = []

                    sql_row['raw_data'] = dict(row)

                    for original_col, value in row.items():
                        if not original_col or not value:
                            continue

                        value = str(value).strip()
                        if not value:
                            continue

                        mapped_target = mapping.get(original_col, None)

                        if mapped_target in sql_cols:
                            sql_row[mapped_target] = value
                        elif mapped_target == 'address_part':
                            address_parts.append(value)
                        elif mapped_target == 'history_Election':
                            col_lower = original_col.lower()
                            t = "Unknown"
                            if "general" in col_lower:
                                t = "General"
                            elif "primary" in col_lower:
                                t = "Primary"
                            elif "municipal" in col_lower:
                                t = "Municipal"
                            elif "special" in col_lower:
                                t = "Special"
                            elif "recall" in col_lower:
                                t = "Recall"

                            y_match = re.search(r'(20\d{2}|\d{2})', col_lower)
                            election_year = ""
                            if y_match:
                                y = y_match.group(1)
                                if len(y) == 2:
                                    y = "20" + y
                                election_year = y

                            key = f"{t} {election_year}".strip()
                            sql_row['voting_history'][key] = value

                        elif mapped_target and mapped_target.startswith('district_'):
                            d_key = mapped_target.replace('district_', '')
                            sql_row['districts'][d_key] = value

                        elif mapped_target and mapped_target.startswith('phone_'):
                            sql_row['phones'].append({
                                "source_column": original_col,
                                "value": value,
                                "mapped_type": mapped_target
                            })
                            if mapped_target == 'phone_number' and not sql_row['phone']:
                                sql_row['phone'] = value

                    final_address = " ".join(address_parts)

                    tup = (
                        file_id,
                        sql_row['first_name'],
                        sql_row['middle_name'],
                        sql_row['last_name'],
                        sql_row['suffix'],
                        final_address,
                        sql_row['city'],
                        sql_row['state'],
                        sql_row.get('zip'),
                        sql_row['age'],
                        sql_row['sex'],
                        sql_row['party'],
                        sql_row['phone'],
                        sql_row['precinct'],
                        sql_row['polling_location'],
                        json.dumps(sql_row['districts']),
                        json.dumps(sql_row['phones']),
                        json.dumps(sql_row['voting_history']),
                        json.dumps(sql_row['raw_data'])
                    )
                    rows_to_insert.append(tup)

                    if len(rows_to_insert) >= 10000:
                        c.executemany('''
                            INSERT INTO voters
                            (file_id, first_name, middle_name, last_name, suffix,
                             address, city, state, zip, age, sex, party, phone,
                             precinct, polling_location, districts, phones,
                             voting_history, raw_data)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', rows_to_insert)
                        rows_to_insert.clear()

                if rows_to_insert:
                    c.executemany('''
                        INSERT INTO voters
                        (file_id, first_name, middle_name, last_name, suffix,
                         address, city, state, zip, age, sex, party, phone,
                         precinct, polling_location, districts, phones,
                         voting_history, raw_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', rows_to_insert)

            self.db.conn.commit()
            return {"status": "success", "file_id": file_id}

        except Exception as e:
            traceback.print_exc()
            try:
                self.db.conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e)}
