# -*- coding: utf-8 -*-
"""
main.py — نقطة دخول DarbStu
يبدأ FastAPI + Tkinter GUI
"""
import os, sys, threading, time, datetime, sqlite3

# ─── تجاوز الملفات المدمجة في EXE (تفعيل التحديثات الخارجية) ────────
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
# ──────────────────────────────────────────────────────────────────

# ─── نقطة الدخول الرئيسية ────────────────────────────
from constants import (PORT, DB_PATH, DATA_DIR, CLOUDFLARE_DOMAIN,
                       MY_STATIC_DOMAIN, BASE_DIR, APP_VERSION,
                       CURRENT_USER, now_riyadh_date, ensure_dirs)
from config_manager import load_config, invalidate_config_cache
from database import get_db, init_db, load_students
from cloudflare_tunnel import start_cloudflare_tunnel, stop_cloudflare_tunnel
from updater import check_for_updates
from license_manager import (check_license, LicenseClient,
                              check_license_on_startup, ActivationWindow)
from api.app import app, register_routers
from gui.login_window import LoginWindow
from gui.app_gui import AppGUI
from alerts_service import (schedule_daily_alerts, schedule_daily_report,
                             send_daily_report_to_admin)
from database import schedule_auto_backup
from api.mobile_routes import _schedule_tardiness_sender
from report_builder import export_to_noor_excel
from constants import now_riyadh_date

import uvicorn
import tkinter as tk
from ttkthemes import ThemedTk
from tkinter import messagebox
import traceback

# ─── ملف السجلات لالتقاط الأخطاء الصامتة ────────────────────────────────────
_LOG_FILE = os.path.join(
    (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
     else os.path.dirname(os.path.abspath(__file__))),
    'error.log'
)

def _write_log(msg: str):
    try:
        with open(_LOG_FILE, 'a', encoding='utf-8') as _f:
            _f.write(f"[{datetime.datetime.now()}] {msg}\n{'='*60}\n")
    except Exception:
        pass

def main():
    # --- START: CLOUDFLARE TUNNEL CONFIGURATION ---
    MY_STATIC_DOMAIN = CLOUDFLARE_DOMAIN  # النطاق الثابت: darbte.uk
    # --- END: CLOUDFLARE TUNNEL CONFIGURATION ---
    
    # ─── تأمين السيرفر من الدوران اللانهائي ───────────────
    os.environ["DARB_SERVER_MODE"] = "1"
    # ──────────────────────────────────────────────────

    ensure_dirs(); init_db()

    # ═══ ترقية: إنشاء جدول behavioral_contracts إن لم يكن موجوداً ══
    try:
        _con2 = get_db(); _cur2 = _con2.cursor()
        _cur2.execute("""
            CREATE TABLE IF NOT EXISTS behavioral_contracts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT NOT NULL,
                student_id   TEXT NOT NULL,
                student_name TEXT NOT NULL,
                class_name   TEXT NOT NULL,
                subject      TEXT,
                period_from  TEXT,
                period_to    TEXT,
                notes        TEXT,
                created_at   TEXT NOT NULL
            )""")
        _con2.commit(); _con2.close()
        print("[MIGRATE] ✅ جدول العقود السلوكية جاهز")
    except Exception as _e2:
        print("[MIGRATE] خطأ في جدول العقود السلوكية:", _e2)
    # ═══════════════════════════════════════════════════════════════

    # ═══ ترقية إجبارية لجدول tardiness ═══════════════════════════
    # تُنفَّذ دائماً بغض النظر عن حالة init_db
    try:
        _con = get_db()
        _cur = _con.cursor()
        # اقرأ تعريف الجدول الحالي
        _cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tardiness'")
        _row = _cur.fetchone()
        if _row:
            _sql = _row[0] or ""
            # إذا الـ UNIQUE يشمل class_id → يمنع التسجيل → أعد البناء
            if "class_id" in _sql and "UNIQUE" in _sql:
                print("[MIGRATE] جارٍ إصلاح جدول tardiness...")
                _cur.execute("DROP TABLE IF EXISTS _tard_bak") # تنظيف في حال وجود محاولة سابقة فاشلة
                _cur.execute("ALTER TABLE tardiness RENAME TO _tard_bak")
                _cur.execute("""CREATE TABLE tardiness (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    date         TEXT NOT NULL,
                    class_id     TEXT NOT NULL DEFAULT '',
                    class_name   TEXT NOT NULL DEFAULT '',
                    student_id   TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    teacher_name TEXT,
                    period       INTEGER,
                    minutes_late INTEGER DEFAULT 0,
                    created_at   TEXT NOT NULL,
                    UNIQUE(date, student_id)
                )""")
                # انقل البيانات القديمة
                _cols = [r[1] for r in _cur.execute("PRAGMA table_info(_tard_bak)")]
                _sel  = ", ".join(
                    "COALESCE({}, {})".format(c, "''" if c in ("class_id","class_name") else
                                              "0"  if c == "minutes_late" else "NULL")
                    if c in ("class_id","class_name","minutes_late") else c
                    for c in _cols
                )
                _cur.execute(
                    "INSERT OR IGNORE INTO tardiness ({}) SELECT {} FROM _tard_bak".format(
                        ", ".join(_cols), _sel))
                _cur.execute("DROP TABLE _tard_bak")
                _con.commit()
                print("[MIGRATE] ✅ تم إصلاح جدول tardiness — يمكنك الآن تسجيل التأخر")
            else:
                # أضف الأعمدة الناقصة فقط
                _existing = {r[1] for r in _cur.execute("PRAGMA table_info(tardiness)")}
                for _col, _dfn in [("teacher_name","TEXT"),("period","INTEGER"),
                                    ("minutes_late","INTEGER DEFAULT 0")]:
                    if _col not in _existing:
                        _cur.execute("ALTER TABLE tardiness ADD COLUMN {} {}".format(_col, _dfn))
                _con.commit()
        _con.close()
    except Exception as _e:
        print("[MIGRATE] خطأ في الترقية:", _e)
    # ═══════════════════════════════════════════════════════════════
    server_thread = threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning"), daemon=True)
    server_thread.start()
    time.sleep(1)
    public_url = None
    
    # ─── Cloudflare Tunnel ───────────────────────────────────────
    public_url = start_cloudflare_tunnel(PORT, MY_STATIC_DOMAIN)
    if public_url:
        print(f"\n{'='*60}")
        print(f"  ✅ الرابط العام: {public_url}")
        print(f"{'='*60}\n")
        # حفظ الرابط في الإعدادات لعرضه في واجهة المشرف
        from config_manager import load_config, save_config
        _c = load_config()
        _c["cloud_url_internal"] = public_url # استخدم مسمى داخلي لا يتعارض مع cloud_url الخاص بالعميل
        save_config(_c)
    else:
        print(f"\n[CLOUDFLARE] يعمل محلياً فقط — http://localhost:{PORT}\n")
    root = ThemedTk(theme="arc"); root.set_theme("arc")

    # ─── التقط كل استثناء Tkinter صامت وأظهره ─────────────────────────────
    def _tk_exc_hook(exc_type, exc_val, exc_tb):
        tb_str = ''.join(traceback.format_exception(exc_type, exc_val, exc_tb))
        _write_log(tb_str)
        messagebox.showerror(
            "خطأ غير متوقع",
            f"{exc_val}\n\nالتفاصيل محفوظة في:\n{_LOG_FILE}"
        )
    root.report_callback_exception = _tk_exc_hook

    def on_closing():
        try:
            stop_cloudflare_tunnel()
        except Exception: pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    def launch_main_app():
        """يُشغَّل بعد تسجيل الدخول الناجح."""
        try:
            # امسح نافذة تسجيل الدخول وابن التطبيق الرئيسي
            for w in root.winfo_children():
                w.destroy()
            # ← إصلاح: أعد تفعيل تغيير الحجم الذي أوقفه LoginWindow
            root.resizable(True, True)
            root.geometry("1280x800")
            root.update()
            root.state("zoomed")   # تكبير كامل عند البدء
            gui = AppGUI(root, public_url)
            root.update()
        except Exception as _e:
            tb_str = traceback.format_exc()
            _write_log(tb_str)
            # أظهر آخر 4 أسطر من الـ traceback (الأكثر فائدة)
            tb_lines = tb_str.strip().splitlines()
            tb_short = '\n'.join(tb_lines[-6:]) if len(tb_lines) > 6 else tb_str
            messagebox.showerror(
                "خطأ في تشغيل البرنامج",
                f"{tb_short}\n\n(الملف الكامل: {_LOG_FILE})"
            )
            return
        # جدول النسخ الاحتياطية التلقائية
        schedule_auto_backup(root, interval_hours=24)
        # جدول إرسال رابط التأخر تلقائياً عند بداية الدوام
        _schedule_tardiness_sender(root)
        # جدول التقرير اليومي للإدارة
        schedule_daily_report(root)
        # جدول الإشعارات الذكية اليومية
        schedule_daily_alerts(root, run_hour=14)
        # جدول تصدير نور التلقائي
        def _noor_auto_check():
            now = datetime.datetime.now()
            if now.weekday() not in {6,0,1,2,3}: # الأحد-الخميس
                root.after(3_600_000, _noor_auto_check); return
            cfg = load_config()
            if cfg.get("noor_auto_export") and now.hour == cfg.get("noor_export_hour",13) and now.minute < 5:
                date_str = now_riyadh_date()
                save_dir = cfg.get("noor_save_dir", DATA_DIR)
                fname = os.path.join(save_dir, "noor_{}.xlsx".format(date_str))
                try:
                    export_to_noor_excel(date_str, fname)
                    print("[NOOR] ✅ تم التصدير التلقائي:", fname)
                except Exception as e:
                    print("[NOOR] ❌ فشل التصدير:", e)
                root.after(3_600_000, _noor_auto_check)
            else:
                root.after(300_000, _noor_auto_check)
        root.after(60_000, _noor_auto_check)

    # ─── فحص الترخيص ────────────────────────────────────────────
    lic_ok, lic_msg, lic_info, lic_client = check_license_on_startup(root)

    if not lic_ok:
        def _after_activation():
            _ok, _msg, _info, _ = check_license_on_startup(root)
            if _ok:
                LoginWindow(root, on_success=launch_main_app)
            else:
                messagebox.showerror("خطأ في الترخيص", _msg)
                root.destroy()
                sys.exit(1)
        ActivationWindow(root, msg=lic_msg, on_success=_after_activation)
    else:
        # اعرض نافذة تسجيل الدخول أولاً
        LoginWindow(root, on_success=launch_main_app)

    root.mainloop()

if __name__ == "__main__":
    try: main()
    except SystemExit: pass
    except Exception as e:
        tb_str = traceback.format_exc()
        _write_log(tb_str)
        try:
            import tkinter as _tk
            _r = _tk.Tk(); _r.withdraw()
            from tkinter import messagebox as _mb
            _mb.showerror("خطأ فادح", f"{e}\n\nالتفاصيل في:\n{_LOG_FILE}")
            _r.destroy()
        except Exception:
            pass
        try: stop_cloudflare_tunnel()
        except: pass
