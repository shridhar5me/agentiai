import sqlite3
import json

def init_db(path):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS screenings(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    con.commit()
    con.close()

def save_evaluation(path, record):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("INSERT INTO screenings(data) VALUES(?)", (json.dumps(record),))
    con.commit()
    con.close()

def fetch_history(path, limit=100):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("SELECT data, created_at FROM screenings ORDER BY id ASC")
    rows = cur.fetchall()
    con.close()
    out = []
    for r in rows:
        try:
            out.append((json.loads(r[0]), r[1]))
        except Exception:
            out.append((r[0], r[1]))
    return out
