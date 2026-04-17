import sqlite3
try:
    con = sqlite3.connect('absences.db')
    cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM student_results')
    count = cur.fetchone()[0]
    cur.execute('SELECT identity_no, student_name FROM student_results LIMIT 10')
    rows = cur.fetchall()
    with open('db_check.txt', 'w', encoding='utf-8') as f:
        f.write(f"Count: {count}\n")
        for r in rows:
            f.write(f"ID: {r[0]}, Name: {r[1]}\n")
    con.close()
except Exception as e:
    with open('db_check.txt', 'w', encoding='utf-8') as f:
        f.write(f"Error: {e}\n")
