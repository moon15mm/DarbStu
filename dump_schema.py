import sqlite3, json
con = sqlite3.connect('absences.db')
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in cur.fetchall()]
res = {}
for t in tables:
    cur.execute(f"PRAGMA table_info({t});")
    res[t] = [c[1] for c in cur.fetchall()]
with open("db_schema.json", "w") as f:
    json.dump(res, f, indent=2)
con.close()
