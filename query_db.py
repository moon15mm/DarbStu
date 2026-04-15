import sqlite3
con = sqlite3.connect('absences.db')
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
print("Tables:", tables)

cur.execute("PRAGMA table_info(student_referrals);")
print("student_referrals:", cur.fetchall())

cur.execute("PRAGMA table_info(users);")
print("users:", cur.fetchall())

cur.execute("SELECT * FROM users;")
print("Users Data:", cur.fetchall())
con.close()
