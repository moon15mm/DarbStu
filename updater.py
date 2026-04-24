# -*- coding: utf-8 -*-
"""
updater.py — نظام التحديث التلقائي (متعدد الملفات)
يحمّل حزمة ZIP من GitHub ويستبدل ملفات الكود فقط،
دون المساس بمجلد data أو my-whatsapp-server أو أي بيانات مستخدم.
"""
import os, sys, io, zipfile, shutil, threading, subprocess, ssl
import urllib.request
import tkinter as tk
from tkinter import ttk
from constants import APP_VERSION, UPDATE_URL, BASE_DIR

# الـ EXE المجمّد على Windows لا يحمل شهادات SSL — نتجاوز التحقق
_SSL_CTX = ssl._create_unverified_context()

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


def _get_installed_version() -> str:
    """
    يقرأ الإصدار الفعلي من version.json المحلي إن وُجد،
    لأن الـ EXE يحتوي APP_VERSION مجمّداً ولا يتحدث بعد التحديث.
    """
    try:
        import json as _j
        vfile = os.path.join(BASE_DIR, "version.json")
        if os.path.exists(vfile):
            with open(vfile, "r", encoding="utf-8") as f:
                local_ver = _j.load(f).get("version", APP_VERSION)
            def _v(v):
                try: return tuple(int(x) for x in str(v).split("."))
                except: return (0,)
            if _v(local_ver) >= _v(APP_VERSION):
                return local_ver
    except Exception:
        pass
    return APP_VERSION


def check_for_updates(root_widget=None, silent=True):
    """
    يتحقق من وجود إصدار جديد على GitHub.
    silent=True : يُخطر فقط عند وجود تحديث.
    silent=False: يُظهر النتيجة دائماً.
    """
    def _check():
        try:
            import json as _j
            # حاول أولاً بدون تحقق SSL (يعمل على Windows EXE)، ثم الطريقة العادية
            try:
                with urllib.request.urlopen(UPDATE_URL, timeout=5, context=_SSL_CTX) as r:
                    data = _j.loads(r.read().decode())
            except Exception:
                with urllib.request.urlopen(UPDATE_URL, timeout=5) as r:
                    data = _j.loads(r.read().decode())
            latest  = data.get("version", "0.0.0")
            notes   = data.get("notes", "")
            dl_url  = data.get("download_url", "") or _ZIP_FALLBACK

            def _ver(v):
                return tuple(int(x) for x in str(v).split("."))

            current = _get_installed_version()
            if _ver(latest) > _ver(current):
                if root_widget:
                    root_widget.after(0, lambda: _show_update_dialog(latest, notes, dl_url))
            else:
                if not silent and root_widget:
                    root_widget.after(0, _show_no_update_dialog)
        except Exception as e:
            if not silent and root_widget:
                root_widget.after(0, lambda: _show_error_dialog(str(e)))

    threading.Thread(target=_check, daemon=True).start()


def _auto_update(latest, dl_url, win=None, status_lbl=None, btn=None):
    """
    يحمّل حزمة ZIP للمشروع، يستخرج ملفات الكود فقط،
    ثم يعيد تشغيل التطبيق تلقائياً.
    """
    import json as _j, time

    def _ui(text, color="#1565C0"):
        print(f"[UPDATE] {text}")
        if status_lbl:
            try:
                status_lbl.config(text=text, foreground=color)
                if win: win.update_idletasks()
            except Exception:
                pass

    try:
        if btn: btn.config(state="disabled")

        # ١. تحديد رابط التحميل
        url = dl_url
        if "releases/latest" in url or not url.endswith(".zip"):
            url = _ZIP_FALLBACK

        _ui("⬇️  جارٍ تحميل التحديث...")

        # ٢. تحميل ملف ZIP
        try:
            resp_obj = urllib.request.urlopen(url, timeout=90, context=_SSL_CTX)
        except Exception:
            resp_obj = urllib.request.urlopen(url, timeout=90)
        with resp_obj as resp:
            zip_bytes = resp.read()

        _ui("📦  جارٍ تثبيت الملفات...")

        # ٣. استخراج الملفات من ZIP
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            prefix = ""
            if names:
                top = names[0].split("/")[0]
                if all(n.startswith(top + "/") or n == top + "/" for n in names[:5]):
                    prefix = top + "/"

            updated = 0
            skipped = 0
            for item in names:
                rel = item[len(prefix):] if prefix and item.startswith(prefix) else item
                if not rel or rel.endswith("/"): continue
                top_dir = rel.split("/")[0]
                if top_dir in _PROTECTED:
                    skipped += 1; continue
                if rel in _SKIP_FILES:
                    skipped += 1; continue
                ext = os.path.splitext(rel)[1].lower()
                if ext not in _UPDATE_EXTS:
                    skipped += 1; continue

                dest = os.path.join(BASE_DIR, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(item) as src:
                    content = src.read()
                with open(dest, "wb") as dst:
                    dst.write(content)
                updated += 1

        _ui(f"✅  تم تحديث {updated} ملف — سيُعاد التشغيل...", "green")
        time.sleep(2)

        # ٤. إعادة التشغيل
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable] + sys.argv[1:]
        else:
            main_file = os.path.join(BASE_DIR, "main.py")
            cmd = [sys.executable, main_file] + sys.argv[1:]

        if sys.platform == "win32":
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, cwd=BASE_DIR)
        else:
            subprocess.Popen(cmd, cwd=BASE_DIR)

        time.sleep(1)
        if win:
            try: win.destroy()
            except: pass
        
        # محاولة إغلاق كل شيء والخروج
        try:
            import tkinter as _tk
            if _tk._default_root:
                _tk._default_root.quit()
        except:
            pass
        os._exit(0)

    except Exception as e:
        _ui(f"❌  فشل التحديث: {e}", "red")
        if btn: btn.config(state="normal")


def perform_silent_update(root_widget, latest, notes, dl_url):
    """تحديث صامت تماماً — تنزيل وتثبيت وإعادة تشغيل بدون أي نافذة."""
    threading.Thread(
        target=_auto_update,
        args=(latest, dl_url, None, None, None),
        daemon=True
    ).start()


def schedule_auto_update(root_widget):
    """جدولة فحص التحديثات التلقائي يومياً في ساعة محددة (بدقة متناهية)."""
    import datetime

    def _run_update_check():
        """ينفذ فحص التحديث الآن ثم يجدول الفحص التالي."""
        from config_manager import load_config
        cfg = load_config()
        if not cfg.get("auto_update_enabled", False):
            _schedule_next()
            return
        try:
            import json as _j
            try:
                with urllib.request.urlopen(UPDATE_URL, timeout=10, context=_SSL_CTX) as r:
                    data = _j.loads(r.read().decode())
            except Exception:
                with urllib.request.urlopen(UPDATE_URL, timeout=10) as r:
                    data = _j.loads(r.read().decode())
            latest  = data.get("version", "0.0.0")
            notes   = data.get("notes", "")
            dl_url  = data.get("download_url", "") or _ZIP_FALLBACK
            def _v(v): return tuple(int(x) for x in str(v).split("."))
            if _v(latest) > _v(_get_installed_version()):
                print(f"[AUTO-UPDATE] إصدار جديد {latest} — جارٍ عرض إشعار التحديث...")
                root_widget.after(0, lambda: perform_silent_update(root_widget, latest, notes, dl_url))
                return  # البرنامج سيُعاد تشغيله — لا نجدول مرة أخرى
            else:
                print(f"[AUTO-UPDATE] الإصدار محدّث ({_get_installed_version()})")
        except Exception as e:
            print(f"[AUTO-UPDATE-ERROR] {e}")
        _schedule_next()

    def _schedule_next():
        """يحسب الوقت المتبقي حتى الساعة المستهدفة ويجدوله بدقة."""
        from config_manager import load_config
        cfg = load_config()
        target_hour = cfg.get("auto_update_hour", 0)  # الافتراضي: منتصف الليل (00:00)
        now = datetime.datetime.now()
        target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        delay_ms = int((target - now).total_seconds() * 1000)
        print(f"[AUTO-UPDATE] الفحص التالي: {target.strftime('%Y-%m-%d %H:%M')} (بعد {delay_ms/3600000:.1f} ساعة)")
        root_widget.after(delay_ms, _run_update_check)

    # ابدأ الجدولة بعد دقيقتين من التشغيل
    root_widget.after(120_000, _schedule_next)


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

    ttk.Label(body, text=f"الإصدار الحالي:  {_get_installed_version()}",
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
    messagebox.showinfo("التحديث", f"✅  أنت تستخدم أحدث إصدار ({_get_installed_version()})")


def _show_error_dialog(err):
    from tkinter import messagebox
    messagebox.showwarning("التحديث", "تعذّر التحقق من التحديثات:\n" + err)
