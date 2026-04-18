import sqlite3, pdfplumber, re, os, sys
sys.path.insert(0, r'C:\Users\maher\Desktop\DarbStu')
from pdf_generator import parse_results_pdf, save_results_to_db

pdf_path = r'C:\Users\maher\Desktop\DarbStu\data\results\results_2026.pdf'
if not os.path.exists(pdf_path):
    print("ملف PDF غير موجود"); input(); exit()

print("جارٍ إعادة استيراد النتائج...")
students = parse_results_pdf(pdf_path)
print(f"عدد الطلاب المستخرجين: {len(students)}")

# اعرض أول 3 نتائج
for s in students[:3]:
    print(f"  {s['identity_no']} | {s['student_name']} | GPA: {repr(s['gpa'])}")

# احفظ في قاعدة البيانات
inserted, _ = save_results_to_db(students, "2026")
print(f"\nتم تحديث {inserted} سجل في قاعدة البيانات")

# تحقق من الطالب المحدد
db = r'C:\Users\maher\Desktop\DarbStu\absences.db'
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("SELECT identity_no, gpa, class_rank FROM student_results WHERE identity_no='1148023912'")
row = cur.fetchone()
con.close()
print(f"\nبيانات الطالب 1148023912: {row}")

input("\nاضغط Enter للخروج...")
