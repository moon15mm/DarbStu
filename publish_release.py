# -*- coding: utf-8 -*-
"""
publish_release.py — سكريبت نشر إصدار جديد إلى مستودع DarbStu-Release

الاستخدام:
  python publish_release.py [--version 3.5.0] [--notes "ملاحظات الإصدار"]

ما يفعله:
  1. ينسخ ملفات DarbStu_Dist إلى مجلد release_output المحلي
  2. يُحدّث version.json بالإصدار والتاريخ
  3. يطبع أوامر git الجاهزة للنشر إلى moon15mm/DarbStu-Release

متطلبات:
  - وجود مجلد DarbStu_Dist على نفس مستوى DarbStu
  - تثبيت git مسبقاً
"""
import os, sys, json, shutil, datetime, argparse

# ─── مسارات ────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DIST_DIR     = os.path.join(os.path.dirname(SCRIPT_DIR), "DarbStu_Dist")
OUTPUT_DIR   = os.path.join(SCRIPT_DIR, "release_output")
RELEASE_REPO = "moon15mm/DarbStu-Release"

# الملفات والمجلدات المستثناة من النسخ (بيانات مستخدم + مخرجات البناء)
EXCLUDE_DIRS = {
    "data", "__pycache__", ".git", ".github",
    "my-whatsapp-server", "Output", "build", "dist",
    "release_output",
}
EXCLUDE_FILES = {
    ".darb_license", ".darb_trial", ".setup_done",
    "_darb_restart.bat",
}
# الامتدادات المسموح بنسخها فقط
ALLOW_EXTS = {
    ".py", ".txt", ".json", ".bat", ".spec",
    ".ico", ".html", ".css", ".js", ".iss",
}


def _copy_dist(src: str, dst: str):
    """ينسخ ملفات DarbStu_Dist إلى dst مع تطبيق قواعد الاستثناء."""
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)

    copied = 0
    for root, dirs, files in os.walk(src):
        # استثنِ المجلدات المحظورة (تعديل في المكان يوقف os.walk)
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        rel_root = os.path.relpath(root, src)

        for fname in files:
            if fname in EXCLUDE_FILES:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOW_EXTS:
                continue

            src_file = os.path.join(root, fname)
            dst_file = os.path.join(dst, rel_root, fname)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1

    return copied


def _read_version(dist_dir: str) -> dict:
    vfile = os.path.join(dist_dir, "version.json")
    with open(vfile, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_version(dst: str, version: str, notes: str):
    vdata = {
        "version": version,
        "notes": notes,
        "download_url": f"https://github.com/{RELEASE_REPO}/archive/refs/heads/main.zip",
        "release_date": datetime.date.today().isoformat(),
    }
    with open(os.path.join(dst, "version.json"), "w", encoding="utf-8") as f:
        json.dump(vdata, f, ensure_ascii=False, indent=2)
    return vdata


def main():
    parser = argparse.ArgumentParser(description="نشر إصدار DarbStu-Release")
    parser.add_argument("--version", default="", help="رقم الإصدار (مثال: 3.5.0)")
    parser.add_argument("--notes",   default="", help="ملاحظات الإصدار")
    args = parser.parse_args()

    # ─── التحقق من وجود مجلد DarbStu_Dist ────────────────────────
    if not os.path.isdir(DIST_DIR):
        print(f"[ERROR] مجلد DarbStu_Dist غير موجود: {DIST_DIR}")
        sys.exit(1)

    # ─── قراءة الإصدار الحالي ─────────────────────────────────────
    cur = _read_version(DIST_DIR)
    version = args.version.strip() or cur.get("version", "0.0.0")
    notes   = args.notes.strip()   or cur.get("notes",   "")

    print(f"\n{'='*55}")
    print(f"  نشر الإصدار  {version}  →  {RELEASE_REPO}")
    print(f"{'='*55}")
    print(f"  المصدر : {DIST_DIR}")
    print(f"  الهدف  : {OUTPUT_DIR}\n")

    # ─── نسخ الملفات ──────────────────────────────────────────────
    count = _copy_dist(DIST_DIR, OUTPUT_DIR)
    print(f"[1/3]  تم نسخ {count} ملف إلى release_output/")

    # ─── تحديث version.json ───────────────────────────────────────
    vdata = _write_version(OUTPUT_DIR, version, notes)
    print(f"[2/3]  version.json محدَّث: {vdata['version']} ({vdata['release_date']})")

    # ─── طباعة أوامر git الجاهزة ─────────────────────────────────
    print(f"\n[3/3]  نفِّذ الأوامر التالية لرفع الإصدار:")
    print(f"""
  # (مرة واحدة فقط) — استنساخ مستودع التوزيع إلى release_output:
  cd "{os.path.dirname(OUTPUT_DIR)}"
  git clone https://github.com/{RELEASE_REPO}.git release_output

  # ثم في كل إصدار جديد:
  cd "{OUTPUT_DIR}"
  git add -A
  git commit -m "release v{version}: {notes[:60]}"
  git push origin main
""")
    print("="*55)
    print("  انتهى — release_output/ جاهز للرفع على GitHub")
    print("="*55 + "\n")


if __name__ == "__main__":
    main()
