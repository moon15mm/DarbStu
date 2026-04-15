# -*- coding: utf-8 -*-
"""
DarbPublish.py — مولد التحديث المطور لـ DarbStu
يقوم بمزامنة الإصدار ونشر التعديلات على GitHub بذكاء.
"""
import os, sys, json, re, subprocess, datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def print_banner():
    print("\n" + "="*60)
    print("      🚀 DarbStu — نظام النشر والتحديث المطور")
    print("="*60 + "\n")

def run_cmd(cmd, desc):
    print(f"⏳ {desc}...", end=" ", flush=True)
    try:
        result = subprocess.run(cmd, shell=True, cwd=BASE, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅")
            return True, result.stdout
        else:
            print("❌")
            print(f"\n[خطأ] {result.stderr}")
            return False, result.stderr
    except Exception as e:
        print("❌")
        print(f"\n[استثناء] {e}")
        return False, str(e)

def get_actual_version():
    """يجلب الإصدار الحالي من ملف constants.py مباشرة."""
    path = os.path.join(BASE, "constants.py")
    if not os.path.exists(path): return "0.0.0"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", content)
    return match.group(1) if match else "0.0.0"

def update_version_files(new_ver, notes):
    """تحديث ملفات التحديث محلياً."""
    # 1. constants.py
    c_path = os.path.join(BASE, "constants.py")
    with open(c_path, "r", encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(r"APP_VERSION\s*=\s*['\"].*?['\"]", f"APP_VERSION         = '{new_ver}'", txt)
    with open(c_path, "w", encoding="utf-8") as f:
        f.write(txt)

    # 2. version.json
    v_path = os.path.join(BASE, "version.json")
    data = {
        "version": new_ver,
        "notes": notes,
        "download_url": "https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip",
        "release_date": datetime.date.today().isoformat()
    }
    with open(v_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 3. installer.iss (لـ Inno Setup)
    i_path = os.path.join(BASE, "installer.iss")
    if os.path.exists(i_path):
        with open(i_path, "r", encoding="utf-8") as f:
            iss = f.read()
        iss = re.sub(r'#define AppVersion\s+"[^"]+"', f'#define AppVersion   "{new_ver}"', iss)
        with open(i_path, "w", encoding="utf-8") as f:
            f.write(iss)

def main():
    os.system("chcp 65001 >nul")
    print_banner()

    # التحقق من وجود Git
    ok, _ = run_cmd("git --version", "التحقق من Git")
    if not ok:
        input("\n[خطأ] يجب تثبيت Git أولاً. اضغط Enter للخروج...")
        return

    # جلب الإصدار الحالي
    current = get_actual_version()
    print(f"📌 الإصدار الحالي المكتشف: {current}")

    # طلب البيانات الجديدة
    new_ver = input("\n📝 أدخل رقم الإصدار الجديد (مثلاً 3.0.0): ").strip()
    if not new_ver:
        print("⚠️ تم إلغاء العملية: لم يتم إدخال رقم إصدار.")
        return

    notes = input("📋 ملاحظات التحديث (اختياري): ").strip()
    if not notes: notes = "تحسينات عامة وإصلاح أخطاء"

    print("\n" + "-"*40)
    
    # 1. تحديث الملفات محلياً
    print("🛠️ جاري تحديث الملفات المحلية...")
    try:
        update_version_files(new_ver, notes)
        print("✅ تم تحديث constants.py و version.json")
    except Exception as e:
        print(f"❌ فشل تحديث الملفات: {e}")
        return

    # 2. مزامنة مع GitHub
    print("\n☁️ جاري المزامنة مع GitHub...")
    
    # محاولة Pull لتجنب التعارض
    run_cmd("git pull origin main --rebase", "سحب التعديلات الأخيرة (Pull)")

    # إضافة كافة التغييرات
    run_cmd("git add -A", "إضافة الملفات للمستودع")

    # Commit
    commit_msg = f"release v{new_ver}: {notes}"
    ok, _ = run_cmd(f'git commit -m "{commit_msg}"', "حفظ التغييرات (Commit)")
    if not ok:
        print("⚠️ قد لا توجد تغييرات جديدة للحفظ.")

    # Push
    ok, _ = run_cmd("git push origin main", "رفع الملفات إلى GitHub (Push)")
    
    if ok:
        print("\n" + "🏁" * 20)
        print(f"🎉 تم نشر الإصدار {new_ver} بنجاح!")
        print("📢 سيصل التحديث للمستخدمين تلقائياً عند فتح البرنامج.")
        print("-" * 40)
        print("💡 تذكير هام:")
        print("إذا كنت توزع البرنامج كملف EXE مجمع، يُفضل تشغيل build.bat الآن")
        print("لبناء نسخة جديدة تحتوي على التحديثات الجوهرية.")
        print("🏁" * 20)
    else:
        print("\n❌ فشل الرفع لـ GitHub. يرجى التحقق من اتصال الإنترنت وصلاحيات الحساب.")

    input("\nاضغط Enter للخروج...")

if __name__ == "__main__":
    main()
