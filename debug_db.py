import sqlite3, csv
try:
    con = sqlite3.connect('absences.db')
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM student_results")
    rows = cur.fetchall()
    with open('results_debug.csv', 'w', encoding='utf-8-sig', newline='') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for r in rows:
                writer.writerow(dict(r))
        else:
            f.write("Table is empty")
    con.close()
    print("Exported results_debug.csv")
except Exception as e:
    with open('results_debug.csv', 'w', encoding='utf-8') as f:
        f.write(f"Error: {e}")
