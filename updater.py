# -*- coding: utf-8 -*-
"""
updater.py — نظام التحديث التلقائي (متعدد الملفات)
يحمّل حزمة ZIP من GitHub ويستبدل ملفات الكود فقط،
دون المساس بمجلد data أو my-whatsapp-server أو أي بيانات مستخدم.
"""
import os, sys, io, zipfile, shutil, threading, subprocess
import urllib.request
import tkinter as tk
from tkinter import ttk
from constants import APP_VERSION, UPDATE_URL, BASE_DIR

# رابط ZIP الكامل للمشروع (فرع main)
_ZIP_FALLBACK = "https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip"

# المسارات المحمية — لن تُلمس أثناء التحديث
_PROTECTED = {
    "data", "my-whatsapp-server", "my-whatsapp-server/",
    "__pycache__", ".git", ".github",
    "Output", "build", "dist",
}

# الامتدادات التي يجب تحديثها
_UPDATE_EXTS = {".py", ".txt", ".json", ".iss", ".bat", ".spec", ".ico"}

# ملفات JSON التي يجب تجاهلها (بيانات مستخدم)
_SKIP_FILES = {
    "data/config.json",
    "data/students.json",
    "data/users.json",
    "data/teachers.json",
}


def check_for_updates(root_widget=None, silent=True):
    """
    يتحقق من وجود إصدار جديد على GitHub.
    silent=True : يُخطر فقط عند وجود تحديث.
    silent=False: يُظهر النتيجة دائماً.
    """
    def _check():
        try:
            import json as _j
            with urllib.request.urlopen(UPDATE_URL, timeout=5) as r:
                data = _j.loads(r.read().decode())
            latest  = data.get("version", "0.0.0")
            notes   = data.get("notes", "")
            dl_url  = data.get("download_url", "") or _ZIP_FALLBACK

            def _ver(v):
                return tuple(int(x) for x in str(v).split("."))

            if _ver(latest) > _ver(APP_VERSION):
                if root_widget:
                    root_widget.after(0, lambda: _show_update_dialog(latest, notes, dl_url))
            else:
                if not silent and root_widget:
                    root_widget.after(0, _show_no_update_dialog)
        except Exception as e:
            if not silent and root_widget:
                root_widget.after(0, lambda: _show_error_dialog(str(e)))

    threading.Thread(target=_check, daemon=True).start()


def _auto_update(latest, dl_url, win, status_lbl, btn):
    """
    يحمّل حزمة ZIP للمشروع، يستخرج ملفات الكود فقط،
    ثم يعيد تشغيل التطبيق تلقائياً.
    """
    import json as _j, time

    def _ui(text, color="#1565C0"):
        try:
            status_lbl.config(text=text, foreground=color)
            win.update_idletasks()
        except Exception:
            pass

    try:
        btn.config(state="disabled")

        # ١. تحديد رابط التحميل
        # إذا كان الرابط في version.json يشير إلى صفحة GitHub Releases
        # نستخدم رابط ZIP الفرع الثابت بدلاً منه
        url = dl_url
        if "releases/latest" in url or not url.endswith(".zip"):
            url = _ZIP_FALLBACK

        _ui("⬇️  جارٍ تحميل التحديث...")

        # ٢. تحميل ملف ZIP
        with urllib.request.urlopen(url, timeout=90) as resp:
            zip_bytes = resp.read()

        _ui("📦  جارٍ تثبيت الملفات...")

        # ٣. استخراج الملفات من ZIP
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()

            # GitHub يُغلف المحتوى داخل مجلد مثل "DarbStu-main/"
            prefix = ""
            if names:
                top = names[0].split("/")[0]
                if all(n.startswith(top + "/") or n == top + "/" for n in names[:5]):
                    prefix = top + "/"

            updated = 0
            skipped = 0

            for item in names:
                # احذف البادئة
                rel = item[len(prefix):] if prefix and item.startswith(prefix) else item

                # تجاهل المجلدات الفارغة
                if not rel or rel.endswith("/"):
                    continue

                # تجاهل المسارات المحمية
                top_dir = rel.split("/")[0]
                if top_dir in _PROTECTED:
                    skipped += 1
                    continue

                # تجاهل ملفات البيانات المحددة
                if rel in _SKIP_FILES:
                    skipped += 1
                    continue

                # تحديث ملفات الكود فقط
                ext = os.path.splitext(rel)[1].lower()
                if ext not in _UPDATE_EXTS:
                    skipped += 1
                    continue

                dest = os.path.join(BASE_DIR, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(item) as src:
                    content = src.read()
                with open(dest, "wb") as dst:
                    dst.write(content)
                updated += 1

        _ui(f"✅  تم تحديث {updated} ملف — سيُعاد التشغيل...", "green")
        time.sleep(2)

        # ٤. إعادة التشغيل من main.py
        main_file = os.path.join(BASE_DIR, "main.py")
        if sys.platform == "win32":
            subprocess.Popen(
                [sys.executable, main_file] + sys.argv[1:],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                cwd=BASE_DIR
            )
        else:
            subprocess.Popen(
                [sys.executable, main_file] + sys.argv[1:],
                cwd=BASE_DIR
            )

        time.sleep(1)

        # أغلق النافذة الحالية
        try:
            win.destroy()
        except Exception:
            pass
        try:
            import tkinter as _tk
            for w in _tk._default_root.winfo_children():
                try: w.destroy()
                except: pass
            _tk._default_root.quit()
            _tk._default_root.destroy()
        except Exception:
            pass

        os._exit(0)

    except Exception as e:
        _ui(f"❌  فشل التحديث: {e}", "red")
        btn.config(state="normal")


def _show_update_dialog(latest, notes, dl_url):
    """نافذة الإشعار بوجود تحديث مع زر تحديث تلقائي."""
    win = tk.Toplevel()
    win.title("🎉 يوجد تحديث جديد")
    win.geometry("480x320")
    win.resizable(False, False)
    win.grab_set()
    win.lift()
    win.attributes("-topmost", True)

    hdr = tk.Frame(win, bg="#1565C0", height=60)
    hdr.pack(fill="x"); hdr.pack_propagate(False)
    tk.Label(hdr, text="🎉  يوجد إصدار جديد من DarbStu",
             bg="#1565C0", fg="white",
             font=("Tahoma", 12, "bold")).pack(expand=True)

    body = ttk.Frame(win, padding=20); body.pack(fill="both", expand=True)

    ttk.Label(body, text=f"الإصدار الحالي:  {APP_VERSION}",
              font=("Tahoma", 10), foreground="#666").pack(anchor="e")
    ttk.Label(body, text=f"الإصدار الجديد:  {latest}",
              font=("Tahoma", 11, "bold"), foreground="#1565C0").pack(anchor="e", pady=(2, 8))

    if notes:
        ttk.Label(body, text="ما الجديد:", font=("Tahoma", 9, "bold")).pack(anchor="e")
        ttk.Label(body, text=notes, font=("Tahoma", 9),
                  foreground="#333", wraplength=420, justify="right").pack(anchor="e", pady=(0, 10))

    status_lbl = ttk.Label(body, text="", font=("Tahoma", 9))
    status_lbl.pack(anchor="e", pady=(0, 8))

    btn_row = ttk.Frame(body); btn_row.pack(fill="x")

    auto_btn = tk.Button(btn_row, text="⚡  تحديث تلقائي (موصى به)",
                         bg="#1565C0", fg="white",
                         font=("Tahoma", 10, "bold"),
                         relief="flat", cursor="hand2", pady=8)
    auto_btn.pack(side="right", padx=4)
    auto_btn.config(command=lambda: threading.Thread(
        target=_auto_update,
        args=(latest, dl_url, win, status_lbl, auto_btn),
        daemon=True).start())

    ttk.Button(btn_row, text="لاحقاً", command=win.destroy).pack(side="right", padx=4)


def _show_no_update_dialog():
    from tkinter import messagebox
    messagebox.showinfo("التحديث", f"✅  أنت تستخدم أحدث إصدار ({APP_VERSION})")


def _show_error_dialog(err):
    from tkinter import messagebox
    messagebox.showwarning("التحديث", "تعذّر التحقق من التحديثات:\n" + err)
