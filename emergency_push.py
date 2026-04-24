# -*- coding: utf-8 -*-
"""
emergency_push.py — إرسال تحديث طارئ فوري لجميع الأجهزة
يُفعّل force_update=true في version.json ويرفعه لـ GitHub.
الأجهزة ستكتشفه خلال 5 دقائق وتُحدَّث تلقائياً.
"""
import os, sys, json, re, subprocess, datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def run_cmd(cmd, desc):
    print(f"⏳ {desc}...", end=" ", flush=True)
    result = subprocess.run(cmd, shell=True, cwd=BASE, capture_output=True, text=True)
    if result.returncode == 0:
        print("✅")
        return True
    else:
        print("❌")
        print(f"   {result.stderr.strip()}")
        return False

def get_version():
    path = os.path.join(BASE, "constants.py")
    with open(path, "r", encoding="utf-8") as f:
        m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", f.read())
    return m.group(1) if m else "0.0.0"

def bump_patch(ver):
    parts = ver.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)

def update_constants(new_ver):
    path = os.path.join(BASE, "constants.py")
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(r"APP_VERSION\s*=\s*['\"].*?['\"]", f"APP_VERSION         = '{new_ver}'", txt)
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)

def main():
    os.system("chcp 65001 >nul 2>&1")
    print("\n" + "="*55)
    print("  🚨 DarbStu — إرسال تحديث طارئ")
    print("="*55 + "\n")

    current = get_version()
    new_ver = bump_patch(current)

    print(f"📌 الإصدار الحالي: {current}")
    print(f"📦 الإصدار الجديد: {new_ver}")
    notes = input("\n📋 سبب التحديث الطارئ: ").strip() or "تحديث طارئ عاجل"

    confirm = input(f"\n⚠️  سيصل التحديث لجميع الأجهزة خلال 5 دقائق. تأكيد؟ (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ تم الإلغاء.")
        return

    print("\n" + "-"*40)

    # 1. تحديث constants.py
    update_constants(new_ver)
    print(f"✅ constants.py → {new_ver}")

    # 2. version.json مع force_update=true
    v_path = os.path.join(BASE, "version.json")
    data = {
        "version": new_ver,
        "notes": notes,
        "force_update": True,
        "download_url": "https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip",
        "release_date": datetime.date.today().isoformat()
    }
    with open(v_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ version.json → force_update: true")

    # 3. Git
    run_cmd("git pull origin main --rebase", "مزامنة مع GitHub")
    run_cmd("git add -A", "إضافة الملفات")
    run_cmd(f'git commit -m "emergency v{new_ver}: {notes}"', "حفظ")
    ok = run_cmd("git push origin main", "رفع إلى GitHub")

    if ok:
        print(f"\n{'🚨'*20}")
        print(f"  ✅ التحديث الطارئ v{new_ver} تم رفعه!")
        print(f"  ⏱️  الأجهزة ستتحدث خلال 5 دقائق تلقائياً")
        print(f"{'🚨'*20}\n")
    else:
        print("\n❌ فشل الرفع — تحقق من الاتصال.")

    input("اضغط Enter للخروج...")

if __name__ == "__main__":
    main()
