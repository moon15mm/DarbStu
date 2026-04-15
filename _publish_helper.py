# -*- coding: utf-8 -*-
"""
_publish_helper.py
نشر تحديث DarbStu على GitHub
"""
import re, json, sys, os, subprocess, datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def run(cmd):
    result = subprocess.run(cmd, shell=True, cwd=BASE)
    return result.returncode == 0

def get_current_version():
    try:
        r = subprocess.run(
            f'"{sys.executable}" -c "from constants import APP_VERSION; print(APP_VERSION)"',
            shell=True, cwd=BASE, capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return "غير معروف"

def update_files(new_ver, notes):
    # constants.py
    path = os.path.join(BASE, "constants.py")
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(r"APP_VERSION\s*=\s*['\"].*?['\"]", f"APP_VERSION         = '{new_ver}'", txt)
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)

    # version.json
    data = {
        "version":      new_ver,
        "notes":        notes,
        "download_url": "https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip",
        "release_date": datetime.date.today().isoformat()
    }
    with open(os.path.join(BASE, "version.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # installer.iss
    iss_path = os.path.join(BASE, "installer.iss")
    if os.path.exists(iss_path):
        with open(iss_path, "r", encoding="utf-8") as f:
            iss_txt = f.read()
        iss_txt = re.sub(r'#define AppVersion\s+"[^"]+"', f'#define AppVersion   "{new_ver}"', iss_txt)
        with open(iss_path, "w", encoding="utf-8") as f:
            f.write(iss_txt)

def main():
    os.system("chcp 65001 >nul 2>&1")
    print()
    print("=" * 54)
    print("       DarbStu — نشر تحديث على GitHub")
    print("=" * 54)
    print()

    # التحقق من git
    if not run("git --version >nul 2>&1"):
        print("[خطأ] git غير مثبت!")
        input("\nاضغط Enter للخروج...")
        sys.exit(1)

    # التحقق من المستودع
    if not os.path.exists(os.path.join(BASE, ".git")):
        print("[إعداد] تهيئة مستودع git لأول مرة...")
        run("git init")
        run("git remote add origin https://github.com/moon15mm/DarbStu.git")
        run("git branch -M main")
        print()

    # الإصدار الحالي
    current = get_current_version()
    print(f"الإصدار الحالي: {current}")
    print()

    # اطلب الإصدار الجديد
    new_ver = input("أدخل رقم الإصدار الجديد (مثال: 2.8.0): ").strip()
    if not new_ver:
        print("[خطأ] يجب إدخال رقم الإصدار")
        input("\nاضغط Enter للخروج...")
        sys.exit(1)

    # اطلب ملاحظات التحديث
    notes = input("أدخل ملاحظات التحديث: ").strip()
    if not notes:
        notes = "تحسينات وإصلاح أخطاء"

    print()

    # [1/4] تحديث الملفات
    print("[1/4] تحديث constants.py و version.json ...")
    try:
        update_files(new_ver, notes)
        print("      ✓ تم")
    except Exception as e:
        print(f"[خطأ] {e}")
        input("\nاضغط Enter للخروج...")
        sys.exit(1)

    # [2/4] git add
    print("[2/4] إضافة الملفات ...")
    if not run("git add -A"):
        print("[خطأ] فشل git add")
        input("\nاضغط Enter للخروج...")
        sys.exit(1)
    print("      ✓ تم")

    # [3/4] commit
    print("[3/4] حفظ التغييرات (commit) ...")
    if not run(f'git commit -m "release v{new_ver}: {notes}"'):
        print("[تحذير] لا توجد تغييرات أو فشل الـ commit")
        print("        تحقق من: git config user.email / user.name")
        input("\nاضغط Enter للخروج...")
        sys.exit(1)
    print("      ✓ تم")

    # [4/4] push
    print("[4/4] رفع التغييرات على GitHub ...")
    if not run("git push -u origin main"):
        print()
        print("[تحذير] فشل الرفع. تحقق من:")
        print("  1. اتصالك بالإنترنت")
        print("  2. صلاحياتك على المستودع moon15mm/DarbStu")
        print("  3. إعداد GitHub token")
        input("\nاضغط Enter للخروج...")
        sys.exit(1)

    print()
    print("=" * 54)
    print(f"  ✅ تم نشر الإصدار {new_ver} بنجاح!")
    print("  سيتلقى المستخدمون إشعار التحديث تلقائياً.")
    print("=" * 54)
    print()
    input("اضغط Enter للخروج...")

if __name__ == "__main__":
    main()
