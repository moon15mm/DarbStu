# -*- coding: utf-8 -*-
"""
cleanup_trial_data.py — تفريغ بيانات التجربة
يحذف: تحويلات المعلمين، الإنذارات، التعاميم، الاستفسارات، الجلسات الإرشادية
يبقي: الغياب، التأخر، الجداول، المستخدمين، الإعدادات
"""
import os, sys, sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
DB_PATH  = os.path.join(BASE_DIR, "absences.db")

TABLES_TO_CLEAR = [
    ("student_referrals",   "تحويلات المعلمين"),
    ("counselor_referrals", "تحويلات الموجه"),
    ("counselor_alerts",    "الإنذارات"),
    ("circulars",           "التعاميم"),
    ("circular_reads",      "قراءات التعاميم"),
    ("academic_inquiries",  "الاستفسارات الأكاديمية"),
    ("counselor_sessions",  "الجلسات الإرشادية"),
]

if not os.path.exists(DB_PATH):
    print(f"❌ لم يُعثر على قاعدة البيانات في: {DB_PATH}")
    input("اضغط Enter للخروج...")
    sys.exit(1)

print(f"قاعدة البيانات: {DB_PATH}\n")
print("الجداول التي ستُفرَّغ:")
for tbl, name in TABLES_TO_CLEAR:
    print(f"  • {name} ({tbl})")

confirm = input("\nهل أنت متأكد؟ اكتب 'نعم' للمتابعة: ").strip()
if confirm != "نعم":
    print("تم الإلغاء.")
    input("اضغط Enter للخروج...")
    sys.exit(0)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

for tbl, name in TABLES_TO_CLEAR:
    try:
        cur.execute(f"DELETE FROM {tbl}")
        count = cur.rowcount
        print(f"  ✅ {name}: حُذف {count} سجل")
    except sqlite3.OperationalError:
        print(f"  ⚠️  {name}: الجدول غير موجود (تجاهل)")

con.commit()
con.close()

print("\n✅ تم تفريغ البيانات بنجاح.")
input("اضغط Enter للخروج...")
