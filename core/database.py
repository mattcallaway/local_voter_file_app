import sqlite3
import json

class Database:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                state TEXT,
                county TEXT,
                import_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS voters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                first_name TEXT,
                last_name TEXT,
                address TEXT,
                city TEXT,
                state TEXT,
                zip TEXT,
                age INTEGER,
                sex TEXT,
                party TEXT,
                phone TEXT,
                precinct TEXT,
                polling_location TEXT,
                voting_history TEXT,
                raw_data TEXT,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        c.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS voters_fts 
            USING fts5(
                first_name, 
                last_name, 
                address, 
                city, 
                zip, 
                content='voters', 
                content_rowid='id'
            )
        ''')
        
        # Triggers to keep FTS table in sync
        c.executescript('''
            CREATE TRIGGER IF NOT EXISTS voters_ai AFTER INSERT ON voters BEGIN
                INSERT INTO voters_fts(rowid, first_name, last_name, address, city, zip)
                VALUES (new.id, new.first_name, new.last_name, new.address, new.city, new.zip);
            END;
            
            CREATE TRIGGER IF NOT EXISTS voters_ad AFTER DELETE ON voters BEGIN
                INSERT INTO voters_fts(voters_fts, rowid, first_name, last_name, address, city, zip)
                VALUES ('delete', old.id, old.first_name, old.last_name, old.address, old.city, old.zip);
            END;
            
            CREATE TRIGGER IF NOT EXISTS voters_au AFTER UPDATE ON voters BEGIN
                INSERT INTO voters_fts(voters_fts, rowid, first_name, last_name, address, city, zip)
                VALUES ('delete', old.id, old.first_name, old.last_name, old.address, old.city, old.zip);
                INSERT INTO voters_fts(rowid, first_name, last_name, address, city, zip)
                VALUES (new.id, new.first_name, new.last_name, new.address, new.city, new.zip);
            END;
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                color TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS voter_tags (
                voter_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (voter_id, tag_id),
                FOREIGN KEY (voter_id) REFERENCES voters(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                criteria TEXT,
                is_static BOOLEAN DEFAULT 1
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS list_voters (
                list_id INTEGER,
                voter_id INTEGER,
                PRIMARY KEY (list_id, voter_id),
                FOREIGN KEY (list_id) REFERENCES lists(id),
                FOREIGN KEY (voter_id) REFERENCES voters(id)
            )
        ''')
        
        self.conn.commit()

    def query(self, sql, args=()):
        c = self.conn.cursor()
        c.execute(sql, args)
        return [dict(row) for row in c.fetchall()]

    def execute(self, sql, args=()):
        c = self.conn.cursor()
        c.execute(sql, args)
        self.conn.commit()
        return c.lastrowid
