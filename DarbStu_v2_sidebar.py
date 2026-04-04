# -*- coding: utf-8 -*-
# Absentee Desktop App — Tkinter + FastAPI (MODERN UI + Phones Management + Embedded Browser + Messages Enhancements)
import os, sys, json, sqlite3, socket, datetime, threading, io, csv, base64, webbrowser, subprocess, shutil, re, hashlib, zipfile
import requests
from typing import List, Dict, Any, Optional
import qrcode
from PIL import Image, ImageTk
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uvicorn
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from ttkthemes import ThemedTk
import time


from tkinter import messagebox

# ── Lazy imports: تُحمَّل عند الحاجة فقط لتسريع بدء التشغيل ──
HtmlFrame       = None
DateEntry       = None
Figure          = None
FigureCanvasTkAgg = None
matplotlib      = None
arabic_reshaper = None
get_display     = None

def _ensure_matplotlib():
    global matplotlib, Figure, FigureCanvasTkAgg, arabic_reshaper, get_display
    if matplotlib is not None:
        return
    import matplotlib as _mpl
    from matplotlib.figure import Figure as _Fig
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _FCA
    _mpl.rcParams['font.family'] = ['Tahoma', 'Arial', 'DejaVu Sans']
    _mpl.rcParams['axes.unicode_minus'] = False
    matplotlib = _mpl; Figure = _Fig; FigureCanvasTkAgg = _FCA
    try:
        import arabic_reshaper as _ar
        from bidi.algorithm import get_display as _gd
        arabic_reshaper = _ar; get_display = _gd
    except ImportError:
        pass

def _ensure_tkinterweb():
    global HtmlFrame
    if HtmlFrame is not None:
        return
    from tkinterweb import HtmlFrame as _HF
    HtmlFrame = _HF

def _ensure_tkcalendar():
    global DateEntry
    if DateEntry is not None:
        return
    from tkcalendar import DateEntry as _DE
    DateEntry = _DE


PORT = int(os.environ.get("ABSENTEE_PORT", "8000"))
STATIC_DOMAIN = "https://darbte.uk"  # النطاق الثابت عبر Cloudflare Tunnel


DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "app.db")
TEMPLATE_PATH = os.path.join(DATA_DIR, "message_template.txt")


### CLOUDFLARE TUNNEL - START ###
CLOUDFLARE_DOMAIN = "darbte.uk"  # النطاق الثابت المطلوب
_cf_process = None  # مرجع لعملية cloudflared

def _has_named_tunnel_config() -> bool:
    """يتحقق إذا كان هناك إعداد Named Tunnel (config.yml أو credentials)."""
    cf_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
    config_yml = os.path.join(cf_dir, "config.yml")
    # ابحث عن credentials file للنفق المُسمّى
    if os.path.exists(config_yml):
        try:
            with open(config_yml, "r") as f:
                content = f.read()
            if "tunnel:" in content and "credentials-file:" in content:
                return True
        except Exception:
            pass
    # ابحث عن أي ملف credentials JSON
    if os.path.exists(cf_dir):
        for fname in os.listdir(cf_dir):
            if fname.endswith(".json") and fname != "cert.pem":
                try:
                    with open(os.path.join(cf_dir, fname), "r") as f:
                        data = json.load(f)
                    if "TunnelID" in data or "AccountTag" in data:
                        return True
                except Exception:
                    pass
    return False

def start_cloudflare_tunnel(port: int, domain: str):
    """
    يُشغّل cloudflared tunnel ويعيد الرابط العام.
    - إذا وُجد Named Tunnel مُعدّ (credentials JSON) → يستخدمه مع دومين darbte.uk
    - إذا لم يوجد → يستخدم Quick Tunnel ويلتقط الرابط العشوائي تلقائياً
    """
    global _cf_process
    # ابحث عن cloudflared.exe بالمسارات المعروفة أولاً
    _cf_candidates = [
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
        r"C:\Windows\System32\cloudflared.exe",
    ]
    cloudflared = None
    for _p in _cf_candidates:
        if os.path.isfile(_p):
            cloudflared = _p
            break
    if not cloudflared:
        # fallback: shutil.which مع تفضيل .exe
        cloudflared = shutil.which("cloudflared.exe") or shutil.which("cloudflared")
    if not cloudflared:
        print("[CLOUDFLARE] ⚠️ cloudflared غير مثبّت — يعمل محلياً فقط")
        return None
    # تحقق أن الملف قابل للتنفيذ فعلاً (وليس ملف بدون امتداد)
    if not cloudflared.lower().endswith(".exe") and os.name == "nt":
        alt = shutil.which("cloudflared.exe")
        if alt:
            cloudflared = alt
    print(f"[CLOUDFLARE] مسار cloudflared: {cloudflared}")

    has_named = _has_named_tunnel_config()

    try:
        if has_named:
            print(f"[CLOUDFLARE] 🔑 Named Tunnel مكتشف — سيتصل بـ {domain}")
            cmd = [cloudflared, "tunnel", "--no-autoupdate", "run"]
        else:
            print("[CLOUDFLARE] ⚡ Quick Tunnel (بدون حساب) — سيُنشئ رابطاً مؤقتاً")
            cmd = [
                cloudflared, "tunnel",
                "--url", f"http://localhost:{port}",
                "--hostname", domain,
                "--no-autoupdate"
            ]

        _cf_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        # ─── خيط يقرأ باقي السجلات بعد الالتقاط ─────────────────
        def _drain_logs():
            try:
                for ln in _cf_process.stdout:
                    print(f"[CLOUDFLARE] {ln.rstrip()}")
            except Exception:
                pass

        # ─── قراءة المخرجات والتقاط الرابط ──────────────────────
        detected_url = None
        timeout = 40
        start_t = time.time()

        while time.time() - start_t < timeout:
            if _cf_process.poll() is not None:
                print("[CLOUDFLARE] ❌ انتهت العملية مبكراً")
                break
            line = _cf_process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            print(f"[CLOUDFLARE] {line.rstrip()}")

            # ① التقط رابط trycloudflare العشوائي
            if not detected_url and "trycloudflare.com" in line:
                m = re.search(r'https://[\w\-]+\.trycloudflare\.com', line)
                if m:
                    detected_url = m.group(0)
                    print(f"[CLOUDFLARE] ✅ الرابط المؤقت: {detected_url}")
                    threading.Thread(target=_drain_logs, daemon=True).start()
                    break

            # ② تأكيد اتصال النفق (Named أو مع hostname) — "Registered tunnel connection"
            if not detected_url and "Registered tunnel connection" in line:
                detected_url = f"https://{domain}"
                print(f"[CLOUDFLARE] ✅ متصل بالنطاق: {detected_url}")
                threading.Thread(target=_drain_logs, daemon=True).start()
                break

            # ③ أي سطر يذكر hostname بشكل صريح
            if not detected_url and domain in line and ("http" in line.lower() or "tunnel" in line.lower()):
                detected_url = f"https://{domain}"
                print(f"[CLOUDFLARE] ✅ تم اكتشاف النطاق: {detected_url}")
                threading.Thread(target=_drain_logs, daemon=True).start()
                break

        # ④ إذا انتهت المهلة لكن العملية لا تزال تعمل → افترض النجاح
        if not detected_url and _cf_process and _cf_process.poll() is None:
            detected_url = f"https://{domain}"
            print(f"[CLOUDFLARE] ✅ النفق يعمل (تم افتراض الرابط): {detected_url}")
            threading.Thread(target=_drain_logs, daemon=True).start()

        if not detected_url:
            print("[CLOUDFLARE] ⚠️ لم يُكتشف رابط في المهلة المحددة")

        return detected_url

    except Exception as e:
        print(f"[CLOUDFLARE] ❌ تعذّر تشغيل النفق: {e}")
        return None

def stop_cloudflare_tunnel():
    """يوقف عملية cloudflared."""
    global _cf_process
    if _cf_process:
        try:
            _cf_process.terminate()
            _cf_process = None
            print("[CLOUDFLARE] 🛑 تم إيقاف النفق")
        except Exception as e:
            print(f"[CLOUDFLARE] خطأ عند الإيقاف: {e}")

ngrok = None  # تعطيل ngrok تماماً
### CLOUDFLARE TUNNEL - END ###

APP_TITLE      = "تسجيل غياب الطلاب"
APP_VERSION    = "2.1.0"  # رقم الإصدار الحالي
UPDATE_URL     = "https://raw.githubusercontent.com/moon15mm/DarbStu/main/version.json"
DB_PATH        = "absences.db"
DATA_DIR       = "data"
STUDENTS_JSON  = os.path.join(DATA_DIR, "students.json")
USERS_JSON     = os.path.join(DATA_DIR, "users.json")
TARDINESS_JSON = os.path.join(DATA_DIR, "tardiness.db")  # نفس SQLite
BACKUP_DIR     = os.path.join(DATA_DIR, "backups")

# ─── الأدوار ────────────────────────────────────────────────────
ROLES = {
    "admin":   {"label": "مدير",   "tabs": "all",    "color": "#7c3aed"},
    "deputy":  {"label": "وكيل",   "tabs": "most",   "color": "#1d4ed8"},
    "teacher": {"label": "معلم",   "tabs": "limited","color": "#065f46"},
    "guard":   {"label": "حارس",   "tabs": "view",   "color": "#92400e"},
}

# التبويبات المسموح بها لكل دور
ROLE_TABS = {
    "admin":   None,  # كل شيء
    "deputy":  ["لوحة القيادة","روابط الفصول","السجلات","إدارة الغياب",
                "التأخر","الأعذار","التقارير / الطباعة","إرسال رسائل الغياب",
                "جدولة الروابط","المراقبة الحية","إدارة الطلاب","إضافة طالب"],
    "teacher": ["لوحة القيادة","روابط الفصول","المراقبة الحية"],
    "guard":   ["لوحة القيادة","التأخر","المراقبة الحية"],
}

CURRENT_USER = {"username": "", "role": "admin", "label": "مدير"}
TEACHERS_JSON  = os.path.join(DATA_DIR, "teachers.json")
CONFIG_JSON    = os.path.join(DATA_DIR, "config.json")
HOST           = "127.0.0.1"
PORT           = int(os.environ.get("ABSENTEE_PORT", "8000"))
TZ_OFFSET      = datetime.timedelta(hours=3)
STUDENTS_STORE = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WHATS_PATH = os.path.join(BASE_DIR, "my-whatsapp-server")

def ensure_dirs(): os.makedirs(DATA_DIR, exist_ok=True)

# ─── نظام التحديث التلقائي ────────────────────────────────────
def check_for_updates(root_widget=None, silent=True):
    """
    يتحقق من وجود إصدار جديد على GitHub.
    silent=True: يُخطر فقط إذا وجد تحديث (للتحقق عند بدء التشغيل).
    silent=False: يُظهر نتيجة حتى لو لا يوجد تحديث (للتحقق اليدوي).
    """
    def _check():
        try:
            import urllib.request, json as _j
            with urllib.request.urlopen(UPDATE_URL, timeout=5) as r:
                data = _j.loads(r.read().decode())
            latest   = data.get("version", "0.0.0")
            notes    = data.get("notes", "")
            dl_url   = data.get("download_url", "")

            def _ver(v):
                return tuple(int(x) for x in str(v).split("."))

            if _ver(latest) > _ver(APP_VERSION):
                # يوجد تحديث
                if root_widget:
                    root_widget.after(0, lambda: _show_update_dialog(latest, notes, dl_url))
            else:
                if not silent and root_widget:
                    root_widget.after(0, lambda: _show_no_update_dialog())
        except Exception as e:
            if not silent and root_widget:
                root_widget.after(0, lambda: _show_error_dialog(str(e)))

    threading.Thread(target=_check, daemon=True).start()

def _show_update_dialog(latest, notes, dl_url):
    """يعرض نافذة الإشعار بوجود تحديث."""
    import tkinter as _tk
    from tkinter import ttk as _ttk

    win = _tk.Toplevel()
    win.title("🎉 يوجد تحديث جديد")
    win.geometry("480x300")
    win.resizable(False, False)
    win.grab_set()
    win.lift()

    # رأس
    hdr = _tk.Frame(win, bg="#1565C0", height=60)
    hdr.pack(fill="x"); hdr.pack_propagate(False)
    _tk.Label(hdr, text="🎉 يوجد إصدار جديد من DarbStu",
              bg="#1565C0", fg="white",
              font=("Tahoma", 12, "bold")).pack(expand=True)

    body = _ttk.Frame(win, padding=20); body.pack(fill="both", expand=True)

    _ttk.Label(body,
               text=f"الإصدار الحالي:  {APP_VERSION}",
               font=("Tahoma", 10), foreground="#666").pack(anchor="e")
    _ttk.Label(body,
               text=f"الإصدار الجديد:  {latest}",
               font=("Tahoma", 11, "bold"), foreground="#1565C0").pack(anchor="e", pady=(2,10))

    if notes:
        _ttk.Label(body, text="ما الجديد:", font=("Tahoma", 9, "bold")).pack(anchor="e")
        _ttk.Label(body, text=notes, font=("Tahoma", 9),
                   foreground="#333", wraplength=420, justify="right").pack(anchor="e", pady=(0,12))

    btn_row = _ttk.Frame(body); btn_row.pack(fill="x")

    def _download():
        if dl_url:
            webbrowser.open(dl_url)
        win.destroy()

    _tk.Button(btn_row, text="⬇️  تحميل التحديث",
               command=_download,
               bg="#1565C0", fg="white",
               font=("Tahoma", 10, "bold"),
               relief="flat", cursor="hand2", pady=8).pack(side="right", padx=4)
    _ttk.Button(btn_row, text="لاحقاً",
                command=win.destroy).pack(side="right", padx=4)

def _show_no_update_dialog():
    from tkinter import messagebox
    messagebox.showinfo("التحديث", f"✅ أنت تستخدم أحدث إصدار ({APP_VERSION})")

def _show_error_dialog(err):
    from tkinter import messagebox
    messagebox.showwarning("التحديث", "تعذّر التحقق من التحديثات:\n" + str(err))

def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0)
        s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]
    except Exception: ip = "127.0.0.1"
    finally:
        try: s.close()
        except: pass
    return ip

def now_riyadh_date():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ry_now = utc_now.astimezone(datetime.timezone(TZ_OFFSET))
    return ry_now.date().isoformat()

def navbar_html(base_url: str) -> str:
    """Returns a consistent navigation bar with a 'Home' button."""
    return f"""
    <div style="background-color: #007bff; padding: 12px; text-align: center;">
        <a href="{base_url}/mobile" 
           style="color: white; text-decoration: none; font-weight: bold; font-size: 18px; display: inline-block; padding: 8px 16px; border-radius: 6px; background-color: #0056b3;">
            🏠 الصفحة الرئيسية
        </a>
    </div>
    """

def debug_on() -> bool:
    return os.environ.get("ABSENTEE_DEBUG", "0") == "1"

# ===================== الإعدادات + قالب الرسالة =====================
DEFAULT_CONFIG = {
    "school_name": "مدرسة الدرب الثانوية",
    "assistant_title": "وكيل شؤون الطلاب",
    "assistant_name": "شامي زكري",
    "principal_title": "مدير المدرسة",
    "principal_name": "حسن محمد عبيري",
    "logo_path": "",
    "message_template": (
        "⚠️ تنبيه غياب من {school_name}\n"
        "ولي أمر الطالب/ {student_name}\n"
        "نفيدكم بتغيب ابنكم عن فصله ({class_name}) بتاريخ {date}.\n"
        "نأمل متابعة حضوره لضمان استمرارية تحصيله العلمي.\n"
        "مع التقدير،\nإدارة المدرسة"
    ),
    "period_times": ["07:00", "07:50", "08:40", "09:50", "10:40", "11:30", "12:20"],
    "school_start_time": "07:00",
    "tardiness_recipients": [],
    "tardiness_message_template": (
        "⏱ تنبيه تأخر من {school_name}\n"
        "ولي أمر الطالب/ {student_name}\n"
        "نُحيطكم علماً بأن ابنكم تأخّر عن الحضور اليوم ({date})\n"
        "بمقدار {minutes_late} دقيقة.\n"
        "نأمل الاهتمام بحضوره في الوقت المحدد.\n"
        "مع التقدير،\nإدارة {school_name}"
    ),
    # ─── إعدادات الإشعارات الذكية ─────────────────────────────
    "alert_absence_threshold": 5,        # عدد أيام الغياب قبل التنبيه
    "alert_enabled": True,               # تفعيل/تعطيل الإشعارات
    "alert_notify_admin": True,          # إشعار الإدارة
    "alert_notify_parent": True,         # إشعار ولي الأمر
    "alert_admin_phone": "",             # جوال الإدارة للإشعارات
    "alert_template_parent": (
        "⚠️ تنبيه هام من {school_name}\n"
        "ولي أمر الطالب/ {student_name}\n"
        "نُحيطكم علماً بأن ابنكم تغيّب {absence_count} أيام هذا الشهر.\n"
        "آخر غياب: {last_date}\n"
        "نرجو التواصل مع الإدارة لمتابعة الأمر.\n"
        "مع التقدير،\nإدارة {school_name}"
    ),
    "alert_template_admin": (
        "📊 تقرير غياب متكرر\n"
        "الطالب: {student_name}\n"
        "الفصل: {class_name}\n"
        "عدد أيام الغياب: {absence_count} يوم\n"
        "آخر غياب: {last_date}\n"
        "جوال ولي الأمر: {parent_phone}"
    ),
}

_CONFIG_CACHE: Dict[str, Any] = {}
_CONFIG_MTIME: float = 0.0

def invalidate_config_cache():
    global _CONFIG_CACHE, _CONFIG_MTIME
    _CONFIG_CACHE = {}; _CONFIG_MTIME = 0.0

def load_config() -> Dict[str, Any]:
    """Loads configuration with file-mtime cache — بلا قراءة متكررة."""
    global _CONFIG_CACHE, _CONFIG_MTIME
    try:
        mtime = os.path.getmtime(CONFIG_JSON) if os.path.exists(CONFIG_JSON) else 0.0
    except OSError:
        mtime = 0.0
    if _CONFIG_CACHE and mtime == _CONFIG_MTIME:
        return _CONFIG_CACHE
    cfg = {}
    if os.path.exists(CONFIG_JSON):
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            cfg = {}

    changes_made = False
    for key, default_value in DEFAULT_CONFIG.items():
        if key not in cfg:
            cfg[key] = default_value
            changes_made = True

    if changes_made:
        try:
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except IOError:
            print(f"Warning: Could not update config file at {CONFIG_JSON}")

    # حفظ في الـ cache
    _CONFIG_CACHE = cfg
    try:
        _CONFIG_MTIME = os.path.getmtime(CONFIG_JSON) if os.path.exists(CONFIG_JSON) else 0.0
    except OSError:
        pass
    return cfg


def ar(txt: str) -> str:
    """يضبط عرض النص العربي (shaping + bidi). لو المكتبات غير متوفرة يرجّع النص كما هو."""
    try:
        _ensure_matplotlib()
        if arabic_reshaper and get_display:
            return get_display(arabic_reshaper.reshape(str(txt)))
    except Exception:
        pass
    return str(txt)



def get_message_template() -> str:
    cfg = load_config()
    return (cfg.get("message_template") or DEFAULT_CONFIG["message_template"]).strip()

def render_message(student_name: str, class_name: str, date_str: str) -> str:
    cfg = load_config()
    school = cfg.get("school_name", "المدرسة")
    tpl = get_message_template()
    return tpl.format(school_name=school, student_name=student_name, class_name=class_name, date=date_str)

def logo_img_tag_from_config(cfg: Dict[str, Any]) -> str:
    path = (cfg.get("logo_path") or "").strip()
    if not path: return ""
    try:
        with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        return f'<img src="data:{mime};base64,{b64}" style="height:80px"/>'
    except Exception: return ""

# ===================== قاعدة البيانات =====================
def get_db():
    """يُنشئ اتصال DB مع إعدادات مُحسَّنة."""
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=10000")
    con.execute("PRAGMA temp_store=MEMORY")
    return con

def init_db():
    con = get_db(); cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS absences (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, class_id TEXT NOT NULL,
        class_name TEXT NOT NULL, student_id TEXT NOT NULL, student_name TEXT NOT NULL,
        teacher_id TEXT, teacher_name TEXT, period INTEGER, created_at TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_absences_date ON absences(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_absences_class ON absences(class_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uniq_absence ON absences(date, class_id, student_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_absences_date_period_class ON absences(date, period, class_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_absences_student_name ON absences(student_name)")

    # ─── جدول سجل الرسائل ───────────────────────────────────
    cur.execute("""CREATE TABLE IF NOT EXISTS message_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        date        TEXT NOT NULL,
        student_id  TEXT NOT NULL,
        student_name TEXT NOT NULL,
        class_id    TEXT NOT NULL DEFAULT '',
        class_name  TEXT NOT NULL DEFAULT '',
        phone       TEXT,
        status      TEXT,
        template_used TEXT,
        created_at  TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_message_log_date ON message_log(date)")

    # ─── جدول التأخر ────────────────────────────────────────────
    # الـ UNIQUE الصحيح: تاريخ + طالب فقط (تأخر الدوام مرة واحدة في اليوم)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tardiness'")
    tardiness_exists = cur.fetchone() is not None

    if tardiness_exists:
        # افحص هل الـ UNIQUE القديم يمنع التسجيل
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tardiness'")
        old_sql = (cur.fetchone() or ("",))[0] or ""
        # الجدول القديم لديه UNIQUE يشمل class_id أو period → يمنع التسجيل
        # الحل: أعد بناءه بالبنية الصحيحة
        need_rebuild = ("class_id" in old_sql and "UNIQUE" in old_sql) or                        ("period" in old_sql and "UNIQUE" in old_sql and "student_id" in old_sql)
        if need_rebuild:
            cur.execute("ALTER TABLE tardiness RENAME TO tardiness_old")
            cur.execute("""
            CREATE TABLE tardiness (
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
            try:
                cur.execute("""INSERT OR IGNORE INTO tardiness
                    (id,date,class_id,class_name,student_id,student_name,
                     teacher_name,period,minutes_late,created_at)
                    SELECT id,date,
                           COALESCE(class_id,''),COALESCE(class_name,''),
                           student_id,student_name,
                           teacher_name,period,COALESCE(minutes_late,0),created_at
                    FROM tardiness_old""")
            except Exception: pass
            cur.execute("DROP TABLE IF EXISTS tardiness_old")
            print("[DB] تم ترقية جدول tardiness - الـ UNIQUE الجديد: date+student_id")
        else:
            # أضف أعمدة ناقصة فقط
            existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(tardiness)")}
            for col, dfn in [("teacher_name","TEXT"),("period","INTEGER"),("minutes_late","INTEGER DEFAULT 0")]:
                if col not in existing_cols:
                    try: cur.execute("ALTER TABLE tardiness ADD COLUMN {} {}".format(col, dfn))
                    except Exception: pass
    else:
        cur.execute("""
        CREATE TABLE tardiness (
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tard_date    ON tardiness(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tard_student ON tardiness(student_id)")

    # ─── جدول الأعذار ───────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS excuses (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        date         TEXT NOT NULL,
        student_id   TEXT NOT NULL,
        student_name TEXT NOT NULL,
        class_id     TEXT NOT NULL,
        class_name   TEXT NOT NULL,
        reason       TEXT NOT NULL,
        source       TEXT NOT NULL DEFAULT 'admin',
        approved_by  TEXT,
        created_at   TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_excuse_date    ON excuses(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_excuse_student ON excuses(student_id)")

    # ─── جدول المستخدمين ────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        username     TEXT NOT NULL UNIQUE,
        password     TEXT NOT NULL,
        role         TEXT NOT NULL DEFAULT 'teacher',
        full_name    TEXT,
        active       INTEGER NOT NULL DEFAULT 1,
        allowed_tabs TEXT,
        created_at   TEXT NOT NULL
    )""")
    # ترقية: أضف allowed_tabs إذا لم يكن موجوداً
    _u_cols = {r[1] for r in cur.execute("PRAGMA table_info(users)")}
    if "allowed_tabs" not in _u_cols:
        cur.execute("ALTER TABLE users ADD COLUMN allowed_tabs TEXT")
    # مستخدم مدير افتراضي إذا لم يوجد
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        import hashlib
        default_pw = hashlib.sha256("admin123".encode()).hexdigest()
        cur.execute(
            "INSERT INTO users (username,password,role,full_name,active,created_at) VALUES (?,?,?,?,?,?)",
            ("admin", default_pw, "admin", "المدير", 1, datetime.datetime.utcnow().isoformat())
        )

    # ─── جدول سجل النسخ الاحتياطية ─────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS backup_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        filename   TEXT NOT NULL,
        size_kb    INTEGER,
        created_at TEXT NOT NULL
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        student_id TEXT NOT NULL,
        student_name TEXT NOT NULL,
        class_id TEXT NOT NULL,
        class_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        status TEXT NOT NULL,
        template_used TEXT,
        message_type TEXT NOT NULL DEFAULT 'absence',
        created_at TEXT NOT NULL
    )""")
    # ترقية: أضف message_type إذا لم يكن موجوداً
    _ml_cols = {r[1] for r in cur.execute("PRAGMA table_info(messages_log)")}
    if "message_type" not in _ml_cols:
        cur.execute("ALTER TABLE messages_log ADD COLUMN message_type TEXT NOT NULL DEFAULT 'absence'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_log_date ON messages_log(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_log_student ON messages_log(student_id)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        day_of_week INTEGER NOT NULL, -- 0=Sunday, 1=Monday, ..., 4=Thursday
        class_id TEXT NOT NULL,
        period INTEGER NOT NULL,
        teacher_name TEXT,
        PRIMARY KEY (day_of_week, class_id, period)
    )""")

    con.commit(); con.close()



# ===================== مراسلة الواتساب =====================
def check_whatsapp_server_status() -> bool:
    """يفحص إذا كان خادم الواتساب يعمل ويستجيب"""
    try:
        response = requests.get("http://127.0.0.1:3000/status", timeout=5)
        return response.status_code == 200
    except:
        return False

def send_whatsapp_message(phone: str, message_body: str, student_data: dict = None) -> (bool, str):
    API_URL = "http://127.0.0.1:3000/send-message"
    
    if not phone:
        msg = "رقم الجوال غير موجود أو فارغ."
        print(f"[WHATSAPP-WARN] {msg}")
        return False, msg

    # تنظيف رقم الهاتف
    cleaned_phone = ''.join(filter(str.isdigit, str(phone)))
    if not cleaned_phone:
        msg = f"رقم الجوال '{phone}' غير صالح."
        print(f"[WHATSAPP-WARN] {msg}")
        return False, msg

    # تحويل التنسيق المحلي إلى دولي
    if len(cleaned_phone) == 10 and cleaned_phone.startswith('05'):
        cleaned_phone = '966' + cleaned_phone[1:]
    elif len(cleaned_phone) == 9 and cleaned_phone.startswith('5'):
        cleaned_phone = '966' + cleaned_phone
    elif len(cleaned_phone) == 12 and cleaned_phone.startswith('966'):
        # الرقم بالفعل بالتنسيق الدولي
        pass
    else:
        msg = f"تنسيق رقم الجوال غير مدعوم: {cleaned_phone}"
        print(f"[WHATSAPP-WARN] {msg}")
        return False, msg

    try:
        print(f"[WHATSAPP] محاولة إرسال إلى: {cleaned_phone}")
        print(f"[WHATSAPP] نص الرسالة: {message_body[:100]}...")

        payload = {
            "number":  cleaned_phone,
            "message": message_body
        }
        # إضافة student_data إذا مُررت (لتفعيل بوت الأعذار)
        if student_data:
            payload["student_data"] = student_data

        response = requests.post(API_URL, json=payload, timeout=30)
        print(f"[WHATSAPP] استجابة الخادم: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 'success':
                print(f"[WHATSAPP] ✅ تم الإرسال بنجاح إلى {cleaned_phone}")
                return True, "تم الإرسال بنجاح"
            else:
                error_msg = response_data.get('message', response.text)
                print(f"[WHATSAPP] ❌ فشل الإرسال: {error_msg}")
                return False, f"فشل: {error_msg}"
        elif response.status_code == 503:
            error_msg = "الواتساب غير متصل — امسح QR Code أولاً"
            print(f"[WHATSAPP] ❌ {error_msg}")
            return False, error_msg
        else:
            # أظهر رسالة الخطأ التفصيلية من الخادم
            try:
                err_detail = response.json().get('message', response.text)
            except Exception:
                err_detail = response.text
            error_msg = f"HTTP {response.status_code}: {err_detail}"
            print(f"[WHATSAPP] ❌ {error_msg}")
            return False, error_msg
            
    except requests.exceptions.ConnectionError:
        error_msg = "فشل الاتصال بخادم الواتساب. تأكد من تشغيل الخادم."
        print(f"[WHATSAPP] ❌ {error_msg}")
        return False, error_msg
        
    except requests.exceptions.Timeout:
        error_msg = "انتهت مهلة الاتصال بخادم الواتساب."
        print(f"[WHATSAPP] ❌ {error_msg}")
        return False, error_msg
        
    except Exception as e:
        error_msg = f"حدث خطأ غير متوقع: {e}"
        print(f"[WHATSAPP] ❌ {error_msg}")
        return False, error_msg

def safe_send_absence_alert(student_id: str, student_name: str, class_name: str, date_str: str) -> (bool, str):
    """يرسل تنبيه الغياب مع فحص حالة الخادم أولاً"""
    
    if not check_whatsapp_server_status():
        return False, "خادم الواتساب غير متاح. الرجاء تشغيله أولاً."
    
    store = load_students()
    phone = next((s.get("phone") for c in store.get("list", []) for s in c.get("students", []) if s.get("id") == student_id), None)
    
    if not phone:
        return False, "لا يوجد رقم جوال مسجل للطالب"
        
    message_body = render_message(student_name, class_name, date_str)
    _student_data = {
        "student_id":   student_id,
        "student_name": student_name,
        "class_name":   class_name,
        "class_id":     class_name,   # fallback
        "date":         date_str,
    }
    return send_whatsapp_message(phone, message_body, student_data=_student_data)

def send_absence_alert(student_id: str, student_name: str, class_name: str, date_str: str) -> (bool, str):
    """يرسل تنبيه الغياب باستخدام القالب المخزن."""
    return safe_send_absence_alert(student_id, student_name, class_name, date_str)

def build_absent_groups(date_str: str) -> Dict[str, Dict[str, Any]]:
    """
    يُرجع هيكل مجمّع: {class_id: {"class_name":..., "students": [ {id,name,phone}, ... ]}}
    يعتمد على سجلات الغياب لليوم + أرقام الجوال من students.json
    """
    rows = _apply_class_name_fix(query_absences(date_filter=date_str))
    store = load_students()
    phone_map = {}
    class_name_map = {}
    for c in store["list"]:
        class_name_map[c["id"]] = c["name"]
        for s in c["students"]:
            phone_map[s["id"]] = s.get("phone", "")

    grouped: Dict[str, Dict[str, Any]] = {}
    seen = set()
    for r in rows:
        sid = r["student_id"]
        if sid in seen:
            continue
        seen.add(sid)
        cid = r["class_id"]
        cname = r.get("class_name") or class_name_map.get(cid, cid)
        if cid not in grouped:
            grouped[cid] = {"class_name": cname, "students": []}
        grouped[cid]["students"].append({
            "id": sid,
            "name": r["student_name"],
            "phone": phone_map.get(sid, "")
        })
    for v in grouped.values():
        v["students"].sort(key=lambda s: s["name"])
    return grouped

def log_message_status(date_str: str, student_id: str, student_name: str, class_id: str, class_name: str, phone: str, status: str, template_used: str):
    con = get_db(); cur = con.cursor()
    cur.execute("""
        INSERT INTO messages_log(date, student_id, student_name, class_id, class_name, phone, status, template_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_str, student_id, student_name, class_id, class_name, phone, status,
        template_used, datetime.datetime.utcnow().isoformat()
    ))
    con.commit(); con.close()

def query_today_messages(date_str: str) -> List[Dict[str, Any]]:
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM messages_log WHERE date = ? ORDER BY class_id, student_name", (date_str,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

def save_schedule(day_of_week: int, schedule_data: List[Dict[str, Any]]):
    """Saves the class schedule for a specific day of the week."""
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM schedule WHERE day_of_week = ?", (day_of_week,))
    
    for item in schedule_data:
        if item.get("teacher_name"):
            cur.execute(
                "INSERT INTO schedule (day_of_week, class_id, period, teacher_name) VALUES (?, ?, ?, ?)",
                (day_of_week, item["class_id"], item["period"], item["teacher_name"])
            )
    con.commit()
    con.close()


def load_schedule(day_of_week: int) -> Dict[tuple, str]:
    """Reads the class schedule for a specific day of the week."""
    try:
        con = get_db()
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT class_id, period, teacher_name FROM schedule WHERE day_of_week = ?", (day_of_week,))
        rows = cur.fetchall()
        con.close()
        return {(row['class_id'], row['period']): row['teacher_name'] for row in rows}
    except sqlite3.OperationalError:
        return {}



# ===================== عمليات السجلات =====================
def insert_absences(date_str, class_id, class_name, students, teacher_id, teacher_name, period):
    con = get_db(); cur = con.cursor()
    created, skipped = 0, 0
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for s in students:
        try:
            cur.execute("""INSERT INTO absences
                           (date,class_id,class_name,student_id,student_name,teacher_id,teacher_name,period,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (date_str, class_id, class_name, s["id"], s["name"], teacher_id, teacher_name, period, created_at))
            created += 1
        except sqlite3.IntegrityError:
            skipped += 1
    con.commit(); con.close()
    return {"created": created, "skipped": skipped}

def query_absences(date_filter=None, class_id=None):
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, params = "SELECT * FROM absences WHERE 1=1", []
    if date_filter: q += " AND date = ?"; params.append(date_filter)
    if class_id: q += " AND class_id = ?"; params.append(class_id)
    cur.execute(q + " ORDER BY date DESC, class_id, student_name", params)
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def norm_token(s: str) -> str:
    if s is None: return ""
    return str(s).strip()

def normalize_legacy_class_id(cid: str) -> str:
    if not cid: return cid
    m = re.match(r"^\s*(1314|1416|1516)\s*-\s*(.+)\s*$", str(cid))
    if not m: return cid
    lvl = {"1314": "1", "1416": "2", "1516": "3"}[m.group(1)]
    return f"{lvl}-{str(m.group(2)).strip()}"

def section_label_from_value(v: str, level: str = "") -> str:
    """يحوّل رقم الفصل إلى حرف عربي مع دعم تسمية هندسة للثاني والثالث ثانوي."""
    x = norm_token(v)
    # أرقام → حروف مع مراعاة المرحلة
    num_map = {"1":"أ","2":"ب","3":"ج","4":"د","5":"هـ","6":"و"}
    # للثاني والثالث ثانوي: الفصل 5 = هندسة
    num_map_eng = {"1":"أ","2":"ب","3":"ج","4":"د","5":"هندسة","6":"هندسة 2"}
    lvl = norm_token(level)
    use_eng = lvl in {"ثاني ثانوي","ثالث ثانوي","2","3"}
    chosen_map = num_map_eng if use_eng else num_map
    if x in chosen_map: return chosen_map[x]
    # حروف لاتينية
    latin_map = {"A":"أ","B":"ب","C":"ج","D":"د","E":"هـ","F":"و"}
    return latin_map.get(x.upper(), x or "1")

def display_name_from_legacy(cid: str) -> str:
    if not cid: return ""
    m = re.match(r"^\s*(1314|1416|1516)\s*-\s*(.+)\s*$", str(cid))
    if not m: return ""
    level = {"1314": "أول ثانوي", "1416": "ثاني ثانوي", "1516": "ثالث ثانوي"}[m.group(1)]
    return f"{level} - فصل {section_label_from_value(m.group(2))}"

def level_name_from_value(v: str) -> str:
    x = norm_token(v); digits = "".join(ch for ch in x if ch.isdigit())
    if digits in {"1314", "1416", "1516"}:
        return {"1314": "أول ثانوي", "1416": "ثاني ثانوي", "1516": "ثالث ثانوي"}[digits]
    xl = x.replace("الصف","").replace("ثانوي","").replace("الثانوي","").replace("مرحلة","").strip()
    xl = xl.replace("أولى","أول").replace("اولى","أول").replace("اول","أول").replace("ثانيه","ثاني").replace("ثالثه","ثالث")
    if xl in {"1","١","أول"}: return "أول ثانوي"
    if xl in {"2","٢","ثاني"}: return "ثاني ثانوي"
    if xl in {"3","٣","ثالث"}: return "ثالث ثانوي"
    return "أول ثانوي"

def import_students_from_excel_sheet2_format(xlsx_path: str) -> Dict[str, Any]:
    xls = pd.ExcelFile(xlsx_path)
    # ابحث في كل الأوراق عن صف يحتوي عناوين الطلاب
    sheet_to_use = None
    header_row   = None
    REQUIRED = {"رقم الطالب", "اسم الطالب", "رقم الصف"}
    for sname in xls.sheet_names:
        df0 = pd.read_excel(xlsx_path, sheet_name=sname, header=None, dtype=str, nrows=30)
        for i, row in df0.iterrows():
            vals = set(str(x).strip() for x in row.tolist() if pd.notna(x))
            if REQUIRED <= vals:
                sheet_to_use = sname
                header_row   = i
                break
        if sheet_to_use: break
    # دعم Stu.xlsx: الأعمدة مباشرة في أول صف
    if sheet_to_use is None:
        for sname in xls.sheet_names:
            df_try = pd.read_excel(xlsx_path, sheet_name=sname, dtype=str)
            cols = {str(c).strip() for c in df_try.columns}
            if REQUIRED <= cols:
                sheet_to_use = sname
                header_row   = 0
                break
    if sheet_to_use is None:
        raise ValueError("تعذر اكتشاف صف عناوين الطلاب تلقائيًا. تأكد من وجود أعمدة: رقم الطالب، اسم الطالب، رقم الصف.")
    df = pd.read_excel(xlsx_path, sheet_name=sheet_to_use, header=header_row, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    if "الفصل" not in df.columns and "رقم الفصل" in df.columns: df["الفصل"] = df["رقم الفصل"]
    required = ["رقم الطالب", "اسم الطالب", "رقم الصف", "الفصل", "رقم الجوال"]
    if missing := [c for c in required if c not in df.columns]: raise ValueError(f"أعمدة ناقصة: {', '.join(missing)}")
    for col in required: df[col] = df[col].astype(str).map(norm_token)
    # تخطّ الصفوف الفارغة أو التي فيها nan
    df = df[df["رقم الطالب"].str.lower().isin({"nan","none",""}) == False]
    df = df[df["اسم الطالب"].str.lower().isin({"nan","none",""}) == False]
    df = df[df["رقم الصف"].str.lower().isin({"nan","none",""}) == False]
    df = df[df["الفصل"].str.lower().isin({"nan","none",""}) == False]
    df["level_name"] = df["رقم الصف"].map(level_name_from_value)
    df["section"] = df.apply(lambda r: section_label_from_value(r["الفصل"], r["level_name"]), axis=1)
    def level_digit(row):
        raw = norm_token(row["رقم الصف"]); digits = "".join(ch for ch in raw if ch.isdigit())
        if digits in {"1314", "1416", "1516"}: return {"1314": "1", "1416": "2", "1516": "3"}[digits]
        if raw and raw[0] in "123١٢٣": return {"1":"1","2":"2","3":"3","١":"1","٢":"2","٣":"3"}.get(raw[0], "1")
        if "أول" in row["level_name"]: return "1"
        if "ثاني" in row["level_name"]: return "2"
        if "ثالث" in row["level_name"]: return "3"
        return "1"
    df["level_digit"] = df.apply(level_digit, axis=1)
    df["class_id"] = df["level_digit"] + "-" + df["section"]
    df["class_name"] = df["level_name"] + " / " + df["section"]
    classes: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        cid, cname = row["class_id"], row["class_name"]
        if cid not in classes: classes[cid] = {"id": cid, "name": cname, "students": []}
        classes[cid]["students"].append({"id": row["رقم الطالب"], "name": row["اسم الطالب"], "phone": row["رقم الجوال"]})
    data = {"classes": list(classes.values())}
    with open(STUDENTS_JSON, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ═══════════════════════════════════════════════════════════════
# دوال المصادقة والمستخدمين
# ═══════════════════════════════════════════════════════════════
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def authenticate(username: str, password: str):
    """يتحقق من المستخدم — يُرجع dict المستخدم أو None."""
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND active=1", (username,))
    row = cur.fetchone(); con.close()
    if not row: return None
    if row["password"] != hash_password(password): return None
    return dict(row)

def get_user_allowed_tabs(username: str):
    """يُرجع قائمة التبويبات المسموحة للمستخدم، أو None إذا كان admin."""
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT role, allowed_tabs FROM users WHERE username=?", (username,))
    row = cur.fetchone(); con.close()
    if not row: return None
    if row["role"] == "admin": return None  # admin يرى كل شيء
    if row["allowed_tabs"]:
        import json as _j
        try: return _j.loads(row["allowed_tabs"])
        except: pass
    # fallback: استخدم ROLE_TABS
    return ROLE_TABS.get(row["role"])

def save_user_allowed_tabs(username: str, tabs: list):
    """يحفظ قائمة التبويبات المسموحة للمستخدم."""
    import json as _j
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET allowed_tabs=? WHERE username=?",
                (_j.dumps(tabs, ensure_ascii=False), username))
    con.commit(); con.close()

def get_all_users():
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT id,username,role,full_name,active FROM users ORDER BY role,username")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def create_user(username, password, role, full_name=""):
    try:
        con = get_db(); cur = con.cursor()
        cur.execute(
            "INSERT INTO users (username,password,role,full_name,active,created_at) VALUES (?,?,?,?,?,?)",
            (username, hash_password(password), role, full_name, 1,
             datetime.datetime.utcnow().isoformat()))
        con.commit(); con.close(); return True, "تم إنشاء المستخدم"
    except sqlite3.IntegrityError:
        return False, "اسم المستخدم موجود مسبقاً"

def update_user_password(username, new_password):
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET password=? WHERE username=?",
                (hash_password(new_password), username))
    con.commit(); con.close()

def toggle_user_active(user_id, active):
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET active=? WHERE id=?", (active, user_id))
    con.commit(); con.close()

def delete_user(user_id):
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM users WHERE id=? AND username!='admin'", (user_id,))
    con.commit(); con.close()

# ═══════════════════════════════════════════════════════════════
# دوال التأخر
# ═══════════════════════════════════════════════════════════════
def insert_tardiness(date_str, class_id, class_name, student_id,
                     student_name, teacher_name, period, minutes_late=0):
    created_at = datetime.datetime.utcnow().isoformat()
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("""INSERT INTO tardiness
            (date,class_id,class_name,student_id,student_name,
             teacher_name,period,minutes_late,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (date_str,class_id,class_name,student_id,student_name,
             teacher_name,period,minutes_late,created_at))
        con.commit(); con.close(); return True
    except sqlite3.IntegrityError:
        return False

def query_tardiness(date_filter=None, class_id=None):
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, params = "SELECT * FROM tardiness WHERE 1=1", []
    if date_filter: q += " AND date=?"; params.append(date_filter)
    if class_id:    q += " AND class_id=?"; params.append(class_id)
    cur.execute(q + " ORDER BY date DESC, class_id, student_name", params)
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def delete_tardiness(record_id):
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM tardiness WHERE id=?", (record_id,))
    con.commit(); con.close()

def compute_tardiness_metrics(date_str):
    rows = query_tardiness(date_filter=date_str)
    by_class = {}
    for r in rows:
        cid = r["class_id"]
        if cid not in by_class:
            by_class[cid] = {"class_name": r["class_name"], "count": 0, "total_minutes": 0}
        by_class[cid]["count"] += 1
        by_class[cid]["total_minutes"] += r.get("minutes_late", 0)
    return {"total": len(rows), "by_class": by_class, "rows": rows}

# ═══════════════════════════════════════════════════════════════
# دوال الأعذار
# ═══════════════════════════════════════════════════════════════
EXCUSE_REASONS = [
    "مرض", "وفاة في العائلة", "ظروف طارئة",
    "إجازة رسمية", "عذر طبي", "أخرى"
]

def insert_excuse(date_str, student_id, student_name, class_id,
                  class_name, reason, source="admin", approved_by=""):
    created_at = datetime.datetime.utcnow().isoformat()
    con = get_db(); cur = con.cursor()
    cur.execute("""INSERT INTO excuses
        (date,student_id,student_name,class_id,class_name,
         reason,source,approved_by,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (date_str,student_id,student_name,class_id,class_name,
         reason,source,approved_by,created_at))
    con.commit(); con.close()

def query_excuses(date_filter=None, student_id=None):
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, params = "SELECT * FROM excuses WHERE 1=1", []
    if date_filter: q += " AND date=?"; params.append(date_filter)
    if student_id:  q += " AND student_id=?"; params.append(student_id)
    cur.execute(q + " ORDER BY date DESC, class_name, student_name", params)
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def delete_excuse(excuse_id):
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM excuses WHERE id=?", (excuse_id,))
    con.commit(); con.close()

def student_has_excuse(student_id, date_str):
    """هل للطالب عذر مقبول في هذا اليوم؟"""
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT 1 FROM excuses WHERE student_id=? AND date=? LIMIT 1",
                (student_id, date_str))
    found = cur.fetchone() is not None; con.close(); return found

# ═══════════════════════════════════════════════════════════════
# النسخ الاحتياطية
# ═══════════════════════════════════════════════════════════════
def create_backup(target_dir=None):
    """ينشئ نسخة احتياطية مضغوطة من DB + JSON."""
    if target_dir is None:
        target_dir = BACKUP_DIR
    os.makedirs(target_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(target_dir, f"backup_{ts}.zip")
    try:
        with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as zf:
            # قاعدة البيانات
            if os.path.exists(DB_PATH):
                zf.write(DB_PATH, os.path.basename(DB_PATH))
            # ملفات JSON
            for jf in [STUDENTS_JSON, TEACHERS_JSON, CONFIG_JSON]:
                if os.path.exists(jf):
                    zf.write(jf, os.path.basename(jf))
        size_kb = os.path.getsize(filename) // 1024
        # سجّل في قاعدة البيانات
        con = get_db(); cur = con.cursor()
        cur.execute("INSERT INTO backup_log (filename,size_kb,created_at) VALUES (?,?,?)",
                    (filename, size_kb, datetime.datetime.utcnow().isoformat()))
        con.commit(); con.close()
        # احتفظ بآخر 30 نسخة فقط
        _cleanup_old_backups(target_dir, keep=30)
        return True, filename, size_kb
    except Exception as e:
        return False, str(e), 0

def _cleanup_old_backups(backup_dir, keep=30):
    files = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("backup_") and f.endswith(".zip")],
        reverse=True
    )
    for old in files[keep:]:
        try: os.remove(os.path.join(backup_dir, old))
        except Exception: pass

def get_backup_list():
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM backup_log ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def schedule_auto_backup(root_widget, interval_hours=24):
    """يجدول نسخ احتياطي تلقائي كل X ساعة."""
    def do_backup():
        ok, path, size = create_backup()
        if ok:
            print(f"[BACKUP] ✅ نسخة احتياطية: {os.path.basename(path)} ({size} KB)")
        else:
            print(f"[BACKUP] ❌ فشل: {path}")
        # جدول المرة القادمة
        ms = interval_hours * 3600 * 1000
        root_widget.after(ms, do_backup)
    # أول نسخة بعد ساعة من التشغيل
    root_widget.after(3600 * 1000, do_backup)


def load_students(force_reload: bool = False) -> Dict[str, Any]:
    global STUDENTS_STORE
    if STUDENTS_STORE and not force_reload:
        return STUDENTS_STORE
    ensure_dirs()
    if os.path.exists(STUDENTS_JSON):
        with open(STUDENTS_JSON, "r", encoding="utf-8") as f: data = json.load(f)
        classes = data.get("classes", [])
    else:
        root = tk.Tk(); root.withdraw()
        messagebox.showinfo("استيراد الطلاب", "ملف الطلاب غير موجود. الرجاء اختيار ملف Excel للطلاب.")
        path = filedialog.askopenfilename(title="اختر ملف Excel (طلاب)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: 
            messagebox.showerror("لم يتم الاختيار", "لا يمكن المتابعة بدون ملف الطلاب."); sys.exit(1)
        data = import_students_from_excel_sheet2_format(path)
        classes = data.get("classes", [])
    STUDENTS_STORE = {"list": classes, "by_id": {c["id"]: c for c in classes}}
    return STUDENTS_STORE

def _clean_phone_noor(raw) -> str:
    """يحوّل رقم الجوال من صيغة نور (966XXXXXXXXX) إلى (05XXXXXXXXX)."""
    import re as _re
    if not raw or str(raw).strip() in ("nan","None",""): return ""
    digits = _re.sub(r"\D", "", str(raw).split(".")[0])
    if digits.startswith("966") and len(digits) == 12: return "0" + digits[3:]
    if digits.startswith("9660") and len(digits) == 13: return "0" + digits[4:]
    if digits.startswith("05") and len(digits) == 10: return digits
    if digits.startswith("5") and len(digits) == 9: return "0" + digits
    return digits if len(digits) >= 9 else ""

def import_teachers_from_excel(xlsx_path: str) -> Dict[str, Any]:
    """
    يقرأ ملف Excel للمعلمين — يدعم:
    1. ملف نور (header مدفون، الاسم في عمود 19، الجوال في عمود 3)
    2. ملف عادي بأعمدة: اسم المعلم، رقم الجوال
    """
    NAME_HINTS  = ["اسم المعلم", "المعلم", "الاسم", "اسم الموظف"]
    PHONE_HINTS = ["رقم الجوال", "الجوال", "phone", "telephone"]
    
    xls = pd.ExcelFile(xlsx_path)
    target_df = None

    for sheet_name in xls.sheet_names:
        # اقرأ بدون header للبحث عن صف العناوين
        raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, dtype=str)
        found_row = None
        for i, row in raw.iterrows():
            vals = [str(v).strip() for v in row.values]
            if any(h in v for h in NAME_HINTS for v in vals):
                found_row = i
                break
        if found_row is not None:
            target_df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=found_row, dtype=str)
            target_df.columns = [str(c).strip() for c in target_df.columns]
            break

    if target_df is not None:
        # ملف بأعمدة واضحة
        name_col  = next((c for c in target_df.columns if any(h in c for h in NAME_HINTS)), None)
        phone_col = next((c for c in target_df.columns if any(h in c for h in PHONE_HINTS)), None)
        if not name_col:
            raise ValueError("لم أجد عمود اسم المعلم في الملف.")
        teachers = []
        SKIP = {"nan","none","","اسم المعلم","اسم الموظف"}
        for _, row in target_df.iterrows():
            name = str(row.get(name_col,"")).strip()
            if name.lower() in SKIP or not name: continue
            phone_raw = str(row.get(phone_col,"")) if phone_col else ""
            teachers.append({"اسم المعلم": name, "رقم الجوال": _clean_phone_noor(phone_raw)})
    else:
        # صيغة نور المعروفة: عمود 19 = الاسم، عمود 3 = الجوال
        raw = pd.read_excel(xlsx_path, header=None, dtype=str)
        if raw.shape[1] < 20:
            raise ValueError("لم أتعرف على صيغة الملف. تأكد من أن يحتوي على أعمدة اسم المعلم ورقم الجوال.")
        teachers = []
        SKIP = {"nan","none","","اسم المعلم"}
        for _, row in raw.iterrows():
            name = str(row.iloc[19]).strip()
            if name.lower() in SKIP or not name: continue
            phone_raw = str(row.iloc[3])
            teachers.append({"اسم المعلم": name, "رقم الجوال": _clean_phone_noor(phone_raw)})

    if not teachers:
        raise ValueError("لم يُعثر على أي معلمين في الملف.")

    # أزل المكررات
    seen, unique = set(), []
    for t in teachers:
        n = t["اسم المعلم"]
        if n not in seen:
            seen.add(n); unique.append(t)

    data = {"teachers": unique}
    with open(TEACHERS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def load_teachers() -> Dict[str, Any]:
    if os.path.exists(TEACHERS_JSON):
        with open(TEACHERS_JSON, "r", encoding="utf-8") as f: return json.load(f)
    else:
        root = tk.Tk(); root.withdraw()
        messagebox.showinfo("استيراد المعلمين", "ملف المعلمين غير موجود. الرجاء اختيار ملف Excel للمعلمين.")
        path = filedialog.askopenfilename(title="اختر ملف Excel (معلمون)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: messagebox.showerror("لم يتم الاختيار", "لا يمكن المتابعة بدون ملف المعلمين."); sys.exit(1)
        return import_teachers_from_excel(path)

def _apply_class_name_fix(rows: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    if not rows: return rows
    store = load_students()
    by_id = store.get("by_id", {})
    for r in rows:
        old_cid = r.get("class_id", "")
        cid = normalize_legacy_class_id(old_cid)
        r["class_id"] = cid
        if cid in by_id: r["class_name"] = by_id[cid]["name"]
        elif (legacy_name := display_name_from_legacy(old_cid)): r["class_name"] = legacy_name
        else:
            parts = str(cid).split("-", 1)
            if len(parts) == 2 and parts[0] in {"1","2","3"}:
                level = {"1":"أول ثانوي","2":"ثاني ثانوي","3":"ثالث ثانوي"}[parts[0]]
                r["class_name"] = f"{level} - فصل {section_label_from_value(parts[1])}"
            else: r["class_name"] = r.get("class_name", old_cid)
    return rows
# ===================== بناء التقارير HTML =====================
def build_daily_report_df(date_str):
    rows = _apply_class_name_fix(query_absences(date_filter=date_str))
    if not rows: return pd.DataFrame(columns=["date","class_id","class_name","student_id","student_name","teacher_name","period"])
    return pd.DataFrame(rows).sort_values(["class_id","student_name"])

def build_total_absences_with_dates_by_class() -> dict:
    rows = _apply_class_name_fix(query_absences())
    if not rows: return {}
    df = pd.DataFrame(rows)
    def to_ddmm(s):
        try: y, m, d = str(s).split("-"); return f"{int(d):02d}/{int(m):02d}"
        except Exception: return str(s)
    df["ddmm"] = df["date"].apply(to_ddmm)
    grp = df.groupby(["class_id","class_name","student_id","student_name"])["ddmm"].apply(lambda s: ", ".join(sorted(set(s)))).reset_index()
    counts = df.groupby(["class_id","class_name","student_id","student_name"])["date"].count().reset_index(name="total")
    merged = pd.merge(grp, counts, on=["class_id","class_name","student_id","student_name"], how="left")
    out = {}
    for (cid, cname), g in merged.sort_values(["class_id","student_name","student_id"]).groupby(["class_id","class_name"]):
        out[cid] = {"class_name": cname, "rows": g.to_dict('records')}
    return out

def compute_today_metrics(date_str: Optional[str] = None) -> Dict[str, Any]:
    date_str = date_str or now_riyadh_date()
    store = load_students()
    total_students = len({s["id"] for c in store["list"] for s in c["students"]})
    rows_today = _apply_class_name_fix(query_absences(date_filter=date_str))
    absent_ids_today = {str(r["student_id"]) for r in rows_today}
    total_absent = len(absent_ids_today)
    absent_by_class = {}
    for r in rows_today: absent_by_class.setdefault(r["class_id"], set()).add(str(r["student_id"]))
    by_class = []
    for c in store["list"]:
        cid, cname = c["id"], c["name"]
        class_total = len(c.get("students",
[]))
        class_absent = len(absent_by_class.get(cid, set()))
        by_class.append({"class_id": cid, "class_name": cname, "total": class_total, "absent": class_absent, "present": max(class_total - class_absent, 0)})
    by_class.sort(key=lambda x: x["class_id"])
    return {"date": date_str, "totals": {"students": total_students, "absent": total_absent, "present": max(total_students - total_absent, 0)}, "by_class": by_class}
    

def generate_report_html(title: str, subtitle: str, data_by_class: Dict[str, List[List[str]]], stats: Dict[str, Any], headers: List[str]) -> str:
    """
    ينشئ كود HTML لتقرير غياب قابل للطباعة باستخدام جدول نظيف (RTL).
    """
    cfg = load_config()
    school_name = cfg.get("school_name", "المدرسة")
    logo_html = logo_img_tag_from_config(cfg)

    table_header_html = "".join(f"<th>{h}</th>" for h in headers)
    cols_count = len(headers)

    table_rows_html = ""
    for class_name, students in data_by_class.items():
        table_rows_html += f'<tr class="class-header"><td colspan="{cols_count}">{class_name}</td></tr>'
        for student_row in students:
            table_rows_html += "<tr>"
            for cell in student_row:
                table_rows_html += f"<td>{cell}</td>"
            table_rows_html += "</tr>"

    style_css = """
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap' );
        body { font-family: 'Cairo', sans-serif; margin: 0; background-color: #f4f4f4; }
        .page { width: 297mm; min-height: 210mm; padding: 15mm; margin: 10mm auto; border: 1px #D3D3D3 solid; background: white; box-shadow: 0 0 5px rgba(0,0,0,0.1); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
        .report-title { text-align: center; margin: 20px 0; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 11px;
            table-layout: fixed;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 6px;
            text-align: center;
            word-wrap: break-word;
        }
        thead tr { background-color: #007bff; color: white; }
        th { font-size: 10px; }
        .class-header td { background-color: #f2f2f2; font-weight: bold; color: #333; }
        th:nth-child(1), td:nth-child(1) { width: 3%; }
        th:nth-child(2), td:nth-child(2) { width: 8%; }
        th:nth-child(3), td:nth-child(3) { width: 20%; text-align: right; }
        tr td:nth-child(n+4) { color: red; font-weight: bold; }
        tr td:last-child { background-color: #f8f9fa; font-weight: bold; }
        .stats { margin-top: 20px; padding: 15px; background-color: #e9ecef; border-radius: 5px; }
        @media print {
            body, .page { margin: 0; box-shadow: none; border: none; }
            .page { width: 100%; min-height: auto; }
        }
    """

    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>{title} - {school_name}</title>
        <style>{style_css}</style>
    </head>
    <body>
        <div class="page">
            <div class="header">
                <div>{logo_html}</div>
                <div>
                    <div style="font-weight:bold">{school_name}</div>
                </div>
                <div></div>
            </div>
            <div class="report-title">
                <h2>{title}</h2>
                <p>{subtitle}</p>
            </div>
            <table>
                <thead><tr>{table_header_html}</tr></thead>
                <tbody>{table_rows_html}</tbody>
            </table>
            <div class="stats">
                <div><b>إجمالي السجلات:</b> {stats.get('total_absences', 0)}</div>
                <div><b>عدد الطلاب الفريدين:</b> {stats.get('total_unique_students', 0)}</div>
                <div><b>عدد الفصول:</b> {stats.get('total_classes', 0)}</div>
            </div>
            <div class="footer" style="margin-top:20px; font-size:12px; color:#666;">
                تم إنشاء التقرير بواسطة نظام الغياب.
            </div>
        </div>
    </body>
    </html>
    """


def query_absences_in_range(start_date: str, end_date: str, class_id: Optional[str] = None):
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, params = "SELECT * FROM absences WHERE date BETWEEN ? AND ?", [start_date, end_date]
    if class_id: q += " AND class_id = ?"; params.append(class_id)
    cur.execute(q + " ORDER BY date, class_id, student_name", params)
    rows = [dict(r) for r in cur.fetchall()]; con.close()
    return _apply_class_name_fix(rows)

def generate_daily_report(date_str: str, class_id: Optional[str] = None) -> str:
    absences = query_absences_in_range(date_str, date_str, class_id)
    if not absences: return "<html><body><h2>لا توجد بيانات غياب لهذا اليوم.</h2></body></html>"
    data_by_class = {}
    for i, r in enumerate(sorted(absences, key=lambda x: (x['class_name'], x['student_name']))):
        class_name = r.get('class_name', 'غير محدد')
        if class_name not in data_by_class: data_by_class[class_name] = []
        student_row = [i + 1, r.get('student_id', ''), r.get('student_name', ''), r.get('period', '')]
        data_by_class[class_name].append(student_row)
    stats = {"total_absences": len(absences), "total_unique_students": len(set(r['student_id'] for r in absences)), "total_classes": len(data_by_class)}
    title = f"تقرير الغياب اليومي لفصل: {list(data_by_class.keys())[0]}" if class_id and data_by_class else "تقرير الغياب اليومي للمدرسة"
    headers = ["م", "رقم الطالب", "اسم الطالب", "الحصة"]
    return generate_report_html(title, f"لتاريخ: {date_str}", data_by_class, stats, headers=headers)

def generate_monthly_report(date_str: str, class_id: Optional[str] = None) -> str:
    try:
        report_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "<html><body><h2>صيغة التاريخ غير صالحة.</h2></body></html>"
    
    start_of_month = report_date.replace(day=1)
    next_month_start = (start_of_month + datetime.timedelta(days=32)).replace(day=1)
    end_of_month = next_month_start - datetime.timedelta(days=1)
    
    work_days = []
    current_day = start_of_month
    while current_day <= end_of_month:
        if current_day.weekday() not in [4, 5]:
            work_days.append(current_day)
        current_day += datetime.timedelta(days=1)
        
    if not work_days:
        return "<html><body><h2>لا توجد أيام عمل في هذا الشهر.</h2></body></html>"
    
    absences = query_absences_in_range(start_of_month.isoformat(), end_of_month.isoformat(), class_id)
    
    if not absences:
        return f"<html><body><h2>لا توجد بيانات غياب لشهر {start_of_month.strftime('%Y-%m')}.</h2></body></html>"

    student_summary = {}
    for r in absences:
        sid = r['student_id']
        if sid not in student_summary:
            student_summary[sid] = {
                'student_id': sid,
                'student_name': r['student_name'],
                'class_name': r.get('class_name', 'غير محدد'),
                'dates': set(),
                'total_count': 0
            }
        student_summary[sid]['dates'].add(r['date'])
        student_summary[sid]['total_count'] += 1

    data_by_class = {}
    sorted_students = sorted(student_summary.values(), key=lambda x: (x['class_name'], x['student_name']))
    
    for i, data in enumerate(sorted_students):
        class_name = data['class_name']
        if class_name not in data_by_class:
            data_by_class[class_name] = []
            
        student_row = [i + 1, data['student_id'], data['student_name']]
        
        day_marks = ['X' if d.isoformat() in data['dates'] else '' for d in work_days]
        student_row.extend(day_marks)
        
        student_row.append(data['total_count'])
        
        data_by_class[class_name].append(student_row)
        
    headers = ["م", "رقم الطالب", "اسم الطالب"] + [d.strftime('%d') for d in work_days] + ["المجموع"]
    stats = {
        "total_absences": len(absences),
        "total_unique_students": len(student_summary),
        "total_classes": len(data_by_class)
    }
    
    title = "تقرير الغياب الشهري للمدرسة"
    if class_id and data_by_class:
        title = f"تقرير الغياب الشهري لفصل: {list(data_by_class.keys())[0]}"
        
    month_name = start_of_month.strftime("%B")
    year = start_of_month.year
    subtitle = f"لشهر {month_name} {year}"
    
    return generate_report_html(title, subtitle, data_by_class, stats, headers=headers)


def generate_weekly_report(date_str: str, class_id: Optional[str] = None) -> str:
    try: report_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError: return "<html><body><h2>صيغة التاريخ غير صالحة.</h2></body></html>"
    start_of_week = report_date - datetime.timedelta(days=report_date.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)
    start_str, end_str = start_of_week.isoformat(), end_of_week.isoformat()
    absences = query_absences_in_range(start_str, end_str, class_id)
    if not absences: return f"<html><body><h2>لا توجد بيانات غياب للأسبوع من {start_str} إلى {end_str}.</h2></body></html>"
    data_by_class = {}
    student_summary = {}
    for r in absences:
        sid = r['student_id']
        if sid not in student_summary:
            student_summary[sid] = {'student_id': sid, 'student_name': r['student_name'], 'class_name': r.get('class_name', 'غير محدد'), 'absence_count': 0, 'absence_dates': set()}
        student_summary[sid]['absence_count'] += 1
        student_summary[sid]['absence_dates'].add(r['date'])
    sorted_summary = sorted(student_summary.values(), key=lambda x: (x['class_name'], x['student_name']))
    for i, summary in enumerate(sorted_summary):
        class_name = summary['class_name']
        if class_name not in data_by_class: data_by_class[class_name] = []
        student_row = [i + 1, summary['student_id'], summary['student_name'], summary['absence_count'], ", ".join(sorted(list(summary['absence_dates'])))]
        data_by_class[class_name].append(student_row)
    stats = {"total_absences": len(absences), "total_unique_students": len(student_summary), "total_classes": len(data_by_class)}
    title = "التقرير الأسبوعي لغياب المدرسة"
    if class_id and data_by_class: title = f"التقرير الأسبوعي لغياب فصل: {list(data_by_class.keys())[0]}"
    subtitle = f"للأسبوع من {start_str} إلى {end_str}"
    headers = ["م", "رقم الطالب", "اسم الطالب", "عدد أيام الغياب", "التواريخ"]
    return generate_report_html(title, subtitle, data_by_class, stats, headers=headers)

def generate_student_report(student_id: str) -> str:
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM absences WHERE student_id = ? ORDER BY date DESC", [student_id])
    absences = [dict(r) for r in cur.fetchall()]; con.close()
    absences = _apply_class_name_fix(absences)

    if not absences:
        return "<html><body><h2>لا توجد سجلات غياب لهذا الطالب.</h2></body></html>"

    student_info = absences[0]
    student_name = student_info.get('student_name')
    class_name = student_info.get('class_name')

    report_rows = []
    for i, r in enumerate(absences):
        row = [
            i + 1,
            r.get('date'),
            r.get('class_name'),
            r.get('teacher_name', 'غير مسجل'),
            r.get('period', '-')
        ]
        report_rows.append(row)
    
    data_by_class = { "سجل الغياب": report_rows }

    total_absences = len(absences)
    periods = [r.get('period') for r in absences if r.get('period')]
    most_frequent_period = max(set(periods), key=periods.count) if periods else "N/A"
    
    stats = {
        "total_absences": total_absences,
        "most_frequent_period": most_frequent_period,
        "total_unique_students": 1,
        "total_classes": 1
    }

    title = f"تقرير الغياب المفصّل للطالب: {student_name}"
    subtitle = f"الرقم الأكاديمي: {student_id} | الفصل: {class_name}"
    headers = ["م", "التاريخ", "الفصل الدراسي", "المعلم", "الحصة"]
    
    report_html = generate_report_html(title, subtitle, data_by_class, stats, headers)
    custom_stats_html = f"""
    <div class="stats">
        <h3>ملخص إحصائي للطالب</h3>
        <p><strong>إجمالي أيام الغياب المسجلة:</strong> {stats.get('total_absences', 0)}</p>
        <p><strong>الحصة الأكثر غياباً (إن وجدت):</strong> {stats.get('most_frequent_period', 'لا يوجد')}</p>
    </div>
    """
    report_html = report_html.replace('<div class="stats">', custom_stats_html, 1)

    return report_html

#*****////////////////

def export_to_noor_excel(date_str: str, output_path: str):
    """
    تصدير غياب يوم معين إلى ملف Excel متوافق مع نظام نور المركزي.
    """
    # جلب الغيابات من قاعدة البيانات
    absences = query_absences(date_filter=date_str)
    if not absences:
        messagebox.showinfo("تنبيه", "لا توجد غيابات لهذا اليوم.")
        return

    # تحويل إلى صيغة نور
    rows = []
    for r in absences:
        rows.append({
            "الرقم المدني أو الأكاديمي": r["student_id"],
            "التاريخ الميلادي": r["date"],  # يجب أن يكون YYYY-MM-DD
            "نوع الغياب": "غياب مباشر",
            "السبب": "",
            "اليوم الدراسي": "نعم",
            "الحصة": r.get("period", "كل اليوم")
        })

    # إنشاء DataFrame
    df = pd.DataFrame(rows)

    # التأكد من ترتيب الأعمدة كما في نور
    columns_order = [
        "الرقم المدني أو الأكاديمي",
        "التاريخ الميلادي",
        "نوع الغياب",
        "السبب",
        "اليوم الدراسي",
        "الحصة"
    ]
    df = df[columns_order]

    # حفظ كـ Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="غياب مباشر", index=False)
        
def get_live_monitor_status(date_str: str) -> List[Dict[str, Any]]:
    absences = query_absences(date_filter=date_str)
    
    recorded_slots = {}
    for r in absences:
        period = r.get('period')
        class_id = r.get('class_id')
        teacher_name = r.get('teacher_name')
        if period and class_id and teacher_name:
            recorded_slots[(period, class_id)] = teacher_name
            
    status_data = []
    all_classes = sorted(load_students()['list'], key=lambda x: x['id'])
    
    for period in range(1, 8):
        period_status = {'period': period, 'classes': []}
        for cls in all_classes:
            class_id = cls['id']
            slot_info = recorded_slots.get((period, class_id))
            
            if slot_info:
                status = {
                    'class_id': class_id,
                    'class_name': cls['name'],
                    'status': 'done',
                    'teacher_name': slot_info
                }
            else:
                status = {
                    'class_id': class_id,
                    'class_name': cls['name'],
                    'status': 'pending',
                    'teacher_name': 'بانتظار التسجيل'
                }
            period_status['classes'].append(status)
        status_data.append(period_status)
        
    return status_data

def generate_monitor_table_html(status_data: List[Dict[str, Any]]) -> str:
    if not status_data:
        return "<h3>لا توجد بيانات لعرضها</h3>"
    classes = status_data[0]['classes']
    class_headers_html = "".join(f"<th>{c['class_name']}</th>" for c in classes)
    table_rows_html = ""
    for period_data in status_data:
        row_html = f"<tr><td class='period-header'>الحصة {period_data['period']}</td>"
        for class_status in period_data['classes']:
            status_class = class_status['status']
            icon = '✔' if status_class == 'done' else '✖'
            teacher_name = class_status['teacher_name']
            row_html += f"""
            <td class='cell {status_class}'>
                <span class='status-icon'>{icon}</span>
                <span class='teacher-name'>{teacher_name}</span>
            </td>
            """
        row_html += "</tr>"
        table_rows_html += row_html
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>مراقبة مدمجة</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap' );
            body {{ font-family: 'Cairo', sans-serif; background-color: #f4f7f6; margin: 0; padding: 10px; }}
            #last-update {{ text-align: center; color: #888; margin-bottom: 10px; font-size: 12px;}}
            table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
            th, td {{ border: 1px solid #ddd; text-align: center; vertical-align: middle; }}
            th {{ background-color: #e9ecef; padding: 10px; font-size: 12px; }}
            .period-header {{ font-weight: bold; font-size: 14px; width: 100px; }}
            .cell {{ height: 80px; padding: 8px; }}
            .cell.pending {{ background-color: #fff1f2; }}
            .cell.done {{ background-color: #f0fdf4; }}
            .teacher-name {{ font-weight: bold; font-size: 12px; display: block; }}
            .status-icon {{ font-size: 20px; }}
            .pending .status-icon {{ color: #c53030; }}
            .done .status-icon {{ color: #2f855a; }}
            .pending .teacher-name {{ color: #9f1239; }}
            .done .teacher-name {{ color: #166534; }}
        </style>
    </head>
    <body>
        <p id="last-update"></p>
        <table>
            <thead><tr><th class="period-header">الحصة</th>{class_headers_html}</tr></thead>
            <tbody>{table_rows_html}</tbody>
        </table>
    </body>
    </html>
    """

# ===================== FastAPI =====================
app = FastAPI()

@app.get("/manage-students", response_class=HTMLResponse)
def manage_students_web_page():
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    nav = navbar_html(base_url)
    store = load_students()
    student_options = ""
    for c in store["list"]:
        for s in c["students"]:
            student_options += f'<option value="{s["id"]}">{s["name"]} ({c["name"]})</option>'
    class_options = "".join(f'<option value="{c["id"]}">{c["name"]} ({len(c["students"])} طالب)</option>' for c in store["list"])
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إدارة الطلاب والفصول</title>
        <style>
            body {{ font-family: 'Cairo', sans-serif; background: #f8f9fa; padding: 20px; }}
            .container {{ max-width: 600px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
            h2 {{ text-align: center; margin-bottom: 25px; color: #2c3e50; }}
            .section {{ margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #eee; }}
            label {{ display: block; margin: 12px 0 6px; font-weight: bold; color: #34495e; }}
            select, button {{ width: 100%; padding: 12px; font-size: 16px; border-radius: 8px; }}
            select {{ border: 1px solid #ddd; margin-bottom: 15px; }}
            button {{ background: #e74c3c; color: white; font-weight: bold; cursor: pointer; }}
            button:disabled {{ background: #95a5a6; cursor: not-allowed; }}
            #status {{ margin-top: 20px; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; display: none; }}
            .success {{ background: #d4edda; color: #155724; }}
            .error {{ background: #f8d7da; color: #721c24; }}
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
    </head>
    <body>
        <div class="container">
            <h2>🗑️ إدارة الطلاب والفصول</h2>

            <div class="section">
                <h3>حذف طالب</h3>
                <label>اختر الطالب للحذف:</label>
                <select id="student_id">
                    <option value="">— اختر طالبًا —</option>
                    {student_options}
                </select>
                <button onclick="deleteStudent()">حذف الطالب المحدد</button>
            </div>

            <div class="section">
                <h3>حذف فصل</h3>
                <label>اختر الفصل للحذف (سيتم حذف جميع طلابه):</label>
                <select id="class_id">
                    <option value="">— اختر فصلًا —</option>
                    {class_options}
                </select>
                <button onclick="deleteClass()">حذف الفصل المحدد</button>
            </div>

            <div id="status"></div>
        </div>

        <script>
            async function deleteStudent() {{
                const studentId = document.getElementById('student_id').value;
                if (!studentId) {{ alert('الرجاء اختيار طالب.'); return; }}
                if (!confirm('هل أنت متأكد من حذف هذا الطالب؟ لا يمكن التراجع.')) return;

                const status = document.getElementById('status');
                status.style.display = 'block';
                status.className = '';
                status.textContent = 'جاري الحذف...';

                try {{
                    const res = await fetch('/api/delete-student', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ student_id: studentId }})
                    }});
                    const data = await res.json();
                    if (res.ok) {{
                        status.className = 'success';
                        status.textContent = '✅ تم حذف الطالب بنجاح!';
                        document.getElementById('student_id').value = '';
                    }} else {{
                        throw new Error(data.detail || 'فشل الحذف');
                    }}
                }} catch (err) {{
                    status.className = 'error';
                    status.textContent = '❌ ' + err.message;
                }}
            }}

            async function deleteClass() {{
                const classId = document.getElementById('class_id').value;
                if (!classId) {{ alert('الرجاء اختيار فصل.'); return; }}
                if (!confirm('تحذير: سيتم حذف الفصل وجميع طلابه! هل أنت متأكد؟')) return;

                const status = document.getElementById('status');
                status.style.display = 'block';
                status.className = '';
                status.textContent = 'جاري الحذف...';

                try {{
                    const res = await fetch('/api/delete-class', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ class_id: classId }})
                    }});
                    const data = await res.json();
                    if (res.ok) {{
                        status.className = 'success';
                        status.textContent = '✅ تم حذف الفصل بنجاح!';
                        document.getElementById('class_id').value = '';
                    }} else {{
                        throw new Error(data.detail || 'فشل الحذف');
                    }}
                }} catch (err) {{
                    status.className = 'error';
                    status.textContent = '❌ ' + err.message;
                }}
            }}
        </script>
    </body>
    </html>
    """


@app.post("/api/delete-student", response_class=JSONResponse)
async def api_delete_student(request: Request):
    data = await request.json()
    student_id = data.get("student_id", "").strip()
    if not student_id:
        return JSONResponse({"detail": "الرقم الأكاديمي مطلوب."}, status_code=400)

    store = load_students(force_reload=True)
    classes = store.get("list", [])
    found = False
    for c in classes:
        for i, s in enumerate(c.get("students", [])):
            if s.get("id") == student_id:
                del c["students"][i]
                found = True
                break
        if found:
            break

    if not found:
        return JSONResponse({"detail": "الطالب غير موجود."}, status_code=404)

    try:
        with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
            json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
        global STUDENTS_STORE
        STUDENTS_STORE = None
        load_students(force_reload=True)
        return JSONResponse({"message": "تم حذف الطالب بنجاح"})
    except Exception as e:
        return JSONResponse({"detail": f"فشل الحفظ: {str(e)}"}, status_code=500)


@app.post("/api/delete-class", response_class=JSONResponse)
async def api_delete_class(request: Request):
    data = await request.json()
    class_id = data.get("class_id", "").strip()
    if not class_id:
        return JSONResponse({"detail": "معرف الفصل مطلوب."}, status_code=400)

    store = load_students(force_reload=True)
    classes = store.get("list", [])
    new_classes = [c for c in classes if c.get("id") != class_id]

    if len(new_classes) == len(classes):
        return JSONResponse({"detail": "الفصل غير موجود."}, status_code=404)

    try:
        with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
            json.dump({"classes": new_classes}, f, ensure_ascii=False, indent=2)
        global STUDENTS_STORE
        STUDENTS_STORE = None
        load_students(force_reload=True)
        return JSONResponse({"message": "تم حذف الفصل بنجاح"})
    except Exception as e:
        return JSONResponse({"detail": f"فشل الحفظ: {str(e)}"}, status_code=500)

def live_monitor_html_page() -> str:
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    nav = navbar_html(base_url)
    style_css = """
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f4f7f6; margin: 0; padding: 10px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 15px; color: #333; }
        #last-update { text-align: center; color: #888; margin-bottom: 10px; }
    """
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>لوحة المراقبة الحية</title>
        <style>{style_css}</style>
    </head>
    <body>
        <div class="container">
            <div class="header"><h2>لوحة المراقبة الحية لتسجيل الغياب</h2></div>
            <div id="last-update">جارٍ التحميل...</div>
            <div id="monitor-content">جارٍ التحميل...</div>
        </div>
        <script>
            async function updateMonitor() {{
                try {{
                    const res = await fetch('/api/live_status');
                    const data = await res.json();
                    const now = new Date().toLocaleTimeString('ar-SA');
                    document.getElementById('last-update').innerText = 'آخر تحديث: ' + now;
                    
                    let html = '<table style="width:100%; border-collapse:collapse; table-layout:fixed;">';
                    if (data.length === 0) {{
                        html += '<tr><td>لا توجد بيانات</td></tr>';
                    }} else {{
                        html += '<thead><tr><th style="background:#e9ecef; padding:10px;">الحصة</th>';
                        for (const cls of data[0].classes) {{
                            html += `<th style="background:#e9ecef; padding:10px;">${{cls.class_name}}</th>`;
                        }}
                        html += '</tr></thead><tbody>';
                        for (const period of data) {{
                            html += `<tr><td style="font-weight:bold; width:100px;">الحصة ${{period.period}}</td>`;
                            for (const cls of period.classes) {{
                                const icon = cls.status === 'done' ? '✔' : '✖';
                                const bgColor = cls.status === 'done' ? '#f0fdf4' : '#fff1f2';
                                const color = cls.status === 'done' ? '#166534' : '#9f1239';
                                html += `
                                    <td style="height:80px; padding:8px; text-align:center; background:${{bgColor}}; border:1px solid #ddd;">
                                        <div style="font-size:20px; color:${{color}};">${{icon}}</div>
                                        <div style="font-weight:bold; color:${{color}};">${{cls.teacher_name}}</div>
                                    </td>`;
                            }}
                            html += '</tr>';
                        }}
                        html += '</tbody>';
                    }}
                    html += '</table>';
                    document.getElementById('monitor-content').innerHTML = html;
                }} catch (e) {{
                    document.getElementById('monitor-content').innerHTML = '<p style="color:red;">خطأ في التحديث</p>';
                }}
            }}
            updateMonitor();
            setInterval(updateMonitor, 15000);
        </script>
    </body>
    </html>
    """
    
def class_html(class_id: str, class_name: str,
               students: List[Dict[str,str]],
               teachers: List[Dict[str,str]]) -> str:
    """صفحة تسجيل الغياب للمعلم — تصميم PWA محسّن."""
    import json as _json

    today        = now_riyadh_date()
    cfg          = load_config()
    school       = cfg.get("school_name", "المدرسة")
    period_times = cfg.get("period_times",
        ["07:00","07:50","08:40","09:50","10:40","11:30","12:20"])
    base_url     = (STATIC_DOMAIN if STATIC_DOMAIN and not debug_on()
                    else "http://{}:{}".format(local_ip(), PORT))

    tch_opts = '<option value="">— المعلم —</option>' + "".join(
        '<option value="{n}">{n}</option>'.format(n=t.get("اسم المعلم",""))
        for t in teachers)

    period_opts = '<option value="">— الحصة —</option>' + "".join(
        '<option value="{i}">الحصة {i} — {t}</option>'.format(
            i=i, t=period_times[i-1] if i-1 < len(period_times) else "")
        for i in range(1, 8))

    students_json = _json.dumps(
        [{"id": s.get("id",""), "name": s.get("name","")} for s in students],
        ensure_ascii=False)

    total = len(students)

    # HTML مع .format() بدلاً من f-string لتجنب تضارب {{}}
    html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="theme-color" content="#1565C0">
<link rel="manifest" href="/manifest.json">
<title>__CLASS_NAME__ — __SCHOOL__</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{
  --primary:#1565C0; --primary-d:#0D47A1;
  --danger:#C62828;  --success:#2E7D32;
  --bg:#F5F7FA; --surface:#fff;
  --text:#1a1a2e; --text2:#5A6A7E; --border:#DDE3EA;
}
html,body{height:100%;font-family:'Cairo',sans-serif;background:var(--bg);
          direction:rtl;color:var(--text);overscroll-behavior:none}
.hdr{position:sticky;top:0;z-index:100;background:var(--primary);
     color:#fff;padding:0;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.hdr-top{display:flex;align-items:center;justify-content:space-between;padding:12px 16px 6px}
.hdr-title{font-size:17px;font-weight:900;line-height:1.2}
.hdr-sub{font-size:11px;opacity:.8;margin-top:2px}
.hdr-stats{text-align:left;font-size:11px;opacity:.85}
.hdr-stats b{font-size:18px;font-weight:900;display:block}
.ctrl-bar{background:var(--primary-d);padding:8px 12px;display:flex;gap:8px;align-items:center}
.ctrl-bar select{flex:1;padding:10px;font-family:'Cairo',sans-serif;font-size:14px;
                 border:none;border-radius:8px;background:#fff;color:var(--text);direction:rtl}
.ctrl-bar input[type=date]{padding:10px;font-family:'Cairo',sans-serif;font-size:14px;
    border:none;border-radius:8px;background:#fff;color:var(--text);width:140px}
.quick-row{display:flex;gap:8px;padding:10px 12px;background:#fff;border-bottom:1px solid var(--border)}
.q-btn{flex:1;padding:9px;font-family:'Cairo',sans-serif;font-size:13px;font-weight:700;
       border:1.5px solid var(--border);border-radius:8px;background:#F5F7FA;cursor:pointer}
.q-btn.sel-all{border-color:var(--danger);color:var(--danger)}
.q-btn.clr-all{border-color:var(--success);color:var(--success)}
.search-wrap{padding:8px 12px;background:#fff;border-bottom:1px solid var(--border)}
.search-inp{width:100%;padding:10px 14px;border:1.5px solid var(--border);
            border-radius:10px;font-family:'Cairo',sans-serif;font-size:14px;
            direction:rtl;background:var(--bg)}
.search-inp:focus{outline:none;border-color:var(--primary)}
.stu-list{padding:10px 12px;display:flex;flex-direction:column;gap:7px;padding-bottom:100px}
.stu-btn{width:100%;display:flex;align-items:center;justify-content:space-between;
         padding:14px 16px;font-family:'Cairo',sans-serif;font-size:16px;font-weight:700;
         border:2px solid var(--border);border-radius:12px;background:var(--surface);
         color:var(--text);cursor:pointer;transition:all .15s;text-align:right;line-height:1.3}
.stu-btn .stu-num{font-size:11px;color:var(--text2);margin-top:2px;font-weight:400}
.stu-btn .stu-badge{font-size:22px;min-width:30px;text-align:center}
.stu-btn.absent{background:var(--danger);color:#fff;border-color:#B71C1C}
.stu-btn:active{transform:scale(.98)}
.submit-wrap{position:fixed;bottom:0;right:0;left:0;padding:12px 16px;
             background:#fff;border-top:1px solid var(--border);box-shadow:0 -4px 16px rgba(0,0,0,.08)}
.submit-btn{width:100%;padding:16px;font-family:'Cairo',sans-serif;font-size:17px;font-weight:900;
            border:none;border-radius:12px;background:var(--success);color:#fff;cursor:pointer}
.submit-btn:disabled{background:#B0BEC5;cursor:not-allowed}
.counter-bar{display:flex;gap:10px;padding:6px 12px;background:#fff;
             border-bottom:1px solid var(--border);font-size:12px;font-weight:700}
.cnt-present{color:var(--success)}.cnt-absent{color:var(--danger)}
#toast{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);
       background:#1a1a2e;color:#fff;padding:10px 22px;border-radius:20px;
       font-size:14px;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}
#toast.show{opacity:1}
#toast.ok{background:var(--success)}
#toast.err{background:var(--danger)}
#done-overlay{display:none;position:fixed;inset:0;background:var(--success);
              color:#fff;z-index:9999;flex-direction:column;
              align-items:center;justify-content:center;gap:16px}
.done-icon{font-size:80px}.done-text{font-size:22px;font-weight:900;text-align:center}
.done-sub{font-size:15px;opacity:.85;text-align:center}
.done-btn{margin-top:16px;padding:14px 32px;font-family:'Cairo',sans-serif;
    font-size:16px;font-weight:700;border:2px solid #fff;border-radius:12px;
    background:transparent;color:#fff;cursor:pointer}
</style>
</head>
<body>
<div class="hdr">
  <div class="hdr-top">
    <div>
      <div class="hdr-title">__CLASS_NAME__</div>
      <div class="hdr-sub">__SCHOOL__ — __TODAY__</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px">
      <div class="hdr-stats"><b id="absent-cnt">0</b> غائب</div>
      <button id="notif-btn" onclick="requestNotifPermission()"
        style="background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.4);
               color:#fff;padding:6px 10px;border-radius:8px;font-size:13px;
               font-family:Cairo,sans-serif;cursor:pointer;display:none">
        🔔 تفعيل الإشعارات
      </button>
      <button id="install-btn" onclick="installApp()"
        style="background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.4);
               color:#fff;padding:6px 10px;border-radius:8px;font-size:13px;
               font-family:Cairo,sans-serif;cursor:pointer;display:none">
        📲 تثبيت التطبيق
      </button>
    </div>
  </div>
  <div id="period-alert" style="display:none;background:rgba(255,255,255,.15);
       padding:8px 16px;border-radius:8px;margin-top:8px;font-size:13px;
       text-align:center;font-weight:700">
    🔔 <span id="period-alert-text"></span>
  </div>
</div>
<div class="ctrl-bar">
  __TCH_OPTS_SEL__
  __PERIOD_OPTS_SEL__
  <input type="date" id="date-inp" value="__TODAY__">
</div>
<div class="quick-row">
  <button class="q-btn sel-all" onclick="selectAll()">تحديد الكل غائب</button>
  <button class="q-btn clr-all" onclick="clearAll()">إلغاء التحديد</button>
</div>
<div class="search-wrap">
  <input class="search-inp" id="search" placeholder="بحث باسم الطالب..." oninput="filterStudents(this.value)">
</div>
<div class="counter-bar">
  <span class="cnt-present">حاضر: <span id="cnt-p">__TOTAL__</span></span>
  <span>|</span>
  <span class="cnt-absent">غائب: <span id="cnt-a">0</span></span>
  <span>|</span>
  <span>الإجمالي: __TOTAL__</span>
</div>
<div class="stu-list" id="stu-list"></div>
<div class="submit-wrap">
  <button class="submit-btn" id="submit-btn" onclick="submitAbsences()" disabled>
    اختر المعلم والحصة أولاً
  </button>
</div>
<div id="toast"></div>
<div id="done-overlay">
  <div class="done-icon">&#x2705;</div>
  <div class="done-text" id="done-text">تم التسجيل بنجاح</div>
  <div class="done-sub" id="done-sub"></div>
  <button class="done-btn" onclick="resetPage()">تسجيل حصة جديدة</button>
</div>
<script>
const BASE="__BASE_URL__",CLASS_ID="__CLASS_ID__",TOTAL=__TOTAL__,STUDENTS=__STUDENTS_JSON__;
const absent=new Set();
function buildList(q=""){
  const ul=document.getElementById('stu-list'); ul.innerHTML='';
  const qq=q.trim().toLowerCase();
  STUDENTS.forEach(s=>{
    if(qq&&!s.name.toLowerCase().includes(qq))return;
    const b=document.createElement('button');
    b.className='stu-btn'+(absent.has(s.id)?' absent':'');
    b.onclick=()=>toggleStudent(s.id,b);
    b.innerHTML='<div><div>'+s.name+'</div><div class="stu-num">'+s.id+'</div></div>'
               +'<div class="stu-badge">'+(absent.has(s.id)?'&#x1F534;':'&#x1F7E2;')+'</div>';
    ul.appendChild(b);
  });
}
function toggleStudent(id,btn){
  if(absent.has(id)){absent.delete(id);btn.className='stu-btn';btn.querySelector('.stu-badge').innerHTML='&#x1F7E2;';}
  else{absent.add(id);btn.className='stu-btn absent';btn.querySelector('.stu-badge').innerHTML='&#x1F534;';}
  updateCounter();
}
function updateCounter(){
  const a=absent.size,p=TOTAL-a;
  document.getElementById('cnt-a').textContent=a;
  document.getElementById('cnt-p').textContent=p;
  document.getElementById('absent-cnt').textContent=a;
  const btn=document.getElementById('submit-btn');
  const ready=document.getElementById('teacher-sel').value&&document.getElementById('period-sel').value;
  btn.disabled=!ready;
  btn.textContent=ready?(a>0?'تسجيل '+a+' غائب':'تسجيل (لا غياب)'):'اختر المعلم والحصة أولاً';
}
function checkReady(){updateCounter();}
function selectAll(){STUDENTS.forEach(s=>absent.add(s.id));buildList(document.getElementById('search').value);updateCounter();}
function clearAll(){absent.clear();buildList(document.getElementById('search').value);updateCounter();}
function filterStudents(q){buildList(q);}
function toast(msg,type,ms=2500){
  const t=document.getElementById('toast');
  t.textContent=msg;t.className='show '+(type||'');
  setTimeout(()=>t.className='',ms);
}
async function submitAbsences(){
  const teacher=document.getElementById('teacher-sel').value;
  const period=document.getElementById('period-sel').value;
  const date=document.getElementById('date-inp').value;
  const btn=document.getElementById('submit-btn');
  if(!teacher||!period){toast('اختر المعلم والحصة','err');return;}
  btn.disabled=true;btn.textContent='جارٍ التسجيل...';
  const absentList=STUDENTS.filter(s=>absent.has(s.id));
  try{
    const r=await fetch(BASE+'/api/submit/'+CLASS_ID,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({date,students:absentList,teacher_name:teacher,period:parseInt(period)})
    });
    const d=await r.json();
    if(r.ok){
      document.getElementById('done-text').textContent='تم التسجيل بنجاح';
      document.getElementById('done-sub').textContent=
        absentList.length>0?('غائب: '+absentList.length+' | حاضر: '+(TOTAL-absentList.length)):'لا يوجد غياب';
      document.getElementById('done-overlay').style.display='flex';
    }else{
      toast('فشل: '+JSON.stringify(d),'err',4000);
      btn.disabled=false;btn.textContent='إعادة المحاولة';
    }
  }catch(e){
    toast('خطأ في الاتصال','err',4000);
    btn.disabled=false;btn.textContent='إعادة المحاولة';
  }
}
function resetPage(){
  absent.clear();
  document.getElementById('done-overlay').style.display='none';
  document.getElementById('teacher-sel').value='';
  document.getElementById('period-sel').value='';
  document.getElementById('search').value='';
  buildList();updateCounter();
}
if('serviceWorker' in navigator){
  navigator.serviceWorker.register('/service-worker.js')
    .catch(e=>console.warn('[SW]',e));
}
if(Notification&&Notification.permission==='default'){
  Notification.requestPermission();
}
buildList();updateCounter();
</script>
</body></html>"""

    # استبدل placeholders بالقيم الحقيقية
    html = html.replace("__CLASS_NAME__", class_name)
    html = html.replace("__SCHOOL__",     school)
    html = html.replace("__TODAY__",      today)
    html = html.replace("__BASE_URL__",   base_url)
    html = html.replace("__CLASS_ID__",   class_id)
    html = html.replace("__TOTAL__",      str(total))
    html = html.replace("__STUDENTS_JSON__", students_json)
    html = html.replace("__TCH_OPTS_SEL__",
        '<select id="teacher-sel" onchange="checkReady()">' + tch_opts + '</select>')
    html = html.replace("__PERIOD_OPTS_SEL__",
        '<select id="period-sel" onchange="checkReady()">' + period_opts + '</select>')
    return html


@app.get("/c/{class_id}", response_class=HTMLResponse)
def get_class_page(class_id: str):
    """صفحة تسجيل الغياب لفصل محدد."""
    try:
        store = load_students()
        cls = store["by_id"].get(class_id)
        if not cls:
            return HTMLResponse(content="<h2 style='text-align:center;color:red;font-family:Cairo,Arial'>الفصل غير موجود</h2>", status_code=404)
        try:
            if os.path.exists(TEACHERS_JSON):
                with open(TEACHERS_JSON, "r", encoding="utf-8") as f:
                    teachers_data = json.load(f)
            else:
                teachers_data = {"teachers": []}
        except Exception:
            teachers_data = {"teachers": []}
        teachers_list = teachers_data.get("teachers", []) if isinstance(teachers_data, dict) else []
        return HTMLResponse(content=class_html(class_id, cls["name"], cls["students"], teachers_list))
    except Exception as e:
        import traceback
        print(f"[ERROR /c/{class_id}] {e}\n{traceback.format_exc()}")
        return HTMLResponse(content=f"<h2 style='color:red;font-family:Arial'>خطأ: {e}</h2>", status_code=500)

@app.post("/api/submit/{class_id}")
async def api_submit(class_id: str, req: Request):
    payload = await req.json()
    date_str, students, teacher_name, period = payload.get("date"), payload.get("students", []), payload.get("teacher_name"), payload.get("period")
    if not isinstance(students, list) or not teacher_name: return JSONResponse({"detail": "بيانات غير مكتملة."}, status_code=400)
    store = load_students(); cls = store["by_id"].get(class_id)
    if not cls: return JSONResponse({"detail": "class_id غير صحيح."}, status_code=404)
    valid_ids = set(s["id"] for s in cls["students"])
    filtered = [s for s in students if s.get("id") in valid_ids]
    result = insert_absences(date_str, class_id, cls["name"], filtered, None, teacher_name, period)
    return JSONResponse(result)

# ═══════════════════════════════════════════════════════════════
# صفحات التأخر — /tardiness و /tardiness/{class_id}
# ═══════════════════════════════════════════════════════════════

def _calc_late_minutes(register_time_str: str, cfg: dict) -> int:
    """يحسب دقائق التأخر من وقت التسجيل - وقت بداية الدوام."""
    try:
        start_str = cfg.get("school_start_time", "07:00")
        fmt = "%H:%M"
        t_reg   = datetime.datetime.strptime(register_time_str[:5], fmt)
        t_start = datetime.datetime.strptime(start_str[:5], fmt)
        diff = int((t_reg - t_start).total_seconds() / 60)
        return max(diff, 0)
    except Exception:
        return 0

def get_tardiness_recipients():
    """يُرجع قائمة مستلمي رابط التأخر من الإعدادات."""
    cfg = load_config()
    return cfg.get("tardiness_recipients", [])

def save_tardiness_recipients(recipients):
    """يحفظ قائمة المستلمين في الإعدادات."""
    cfg = load_config()
    cfg["tardiness_recipients"] = recipients
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def send_tardiness_link_to_all():
    """
    يُرسل رابط التأخر (كل المدرسة) لجميع المستلمين المسجّلين.
    يُرجع: (عدد_النجاح, عدد_الفشل, تفاصيل)
    """
    cfg        = load_config()
    base       = (STATIC_DOMAIN if STATIC_DOMAIN and not debug_on()
                  else "http://{}:{}".format(local_ip(), PORT))
    url        = "{}/tardiness".format(base)
    recipients = get_tardiness_recipients()
    today      = now_riyadh_date()
    start_time = cfg.get("school_start_time", "07:00")

    if not recipients:
        return 0, 0, ["لا يوجد مستلمون مسجّلون"]

    msg = (
        f"⏱ رابط تسجيل التأخر\n"
        f"📅 {today}  |  🕐 بداية الدوام: {start_time}\n"
        "يرجى تسجيل المتأخرين من خلال الرابط:\n"
        f"{url}"
    )

    sent, failed, details = 0, 0, []
    for r in recipients:
        phone = r.get("phone", "")
        name  = r.get("name", "")
        if not phone:
            details.append(f"⚠️ {name}: لا يوجد رقم جوال")
            failed += 1
            continue
        ok, status = send_whatsapp_message(phone, msg)
        if ok:
            sent += 1
            details.append(f"✅ {name}")
        else:
            failed += 1
            details.append(f"❌ {name}: {status}")

    return sent, failed, details


def _schedule_tardiness_sender(root_widget):
    """
    يجدول إرسال رابط التأخر تلقائياً عند وقت بداية الدوام كل يوم عمل.
    يُستدعى مرة واحدة عند بدء البرنامج.
    """
    WORK_DAYS = {6, 0, 1, 2, 3}  # الأحد-الخميس (Python: Sun=6,Mon=0...)

    def check_and_send():
        now = datetime.datetime.now()
        # أيام العمل فقط
        if now.weekday() not in WORK_DAYS:
            root_widget.after(60_000, check_and_send)
            return
        cfg        = load_config()
        start_str  = cfg.get("school_start_time", "07:00")
        try:
            h, m   = map(int, start_str.split(":"))
            target  = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff_s  = (target - now).total_seconds()
            # نافذة ±90 ثانية
            if -90 <= diff_s <= 90:
                print(f"[TARDINESS-SCHED] ⏰ حان وقت بداية الدوام ({start_str}) — جارٍ الإرسال...")
                t = threading.Thread(target=send_tardiness_link_to_all, daemon=True)
                t.start()
                # انتظر 5 دقائق قبل الفحص التالي لتجنب الإرسال المتكرر
                root_widget.after(300_000, check_and_send)
                return
        except Exception as e:
            print(f"[TARDINESS-SCHED] خطأ: {e}")
        # فحص كل دقيقة
        root_widget.after(60_000, check_and_send)

    # ابدأ الفحص بعد 30 ثانية من التشغيل
    root_widget.after(30_000, check_and_send)


def _tardiness_page_html(students_list, title, back_url, base_url_str):
    """HTML مشترك لصفحة التأخر (فصل أو كل المدرسة)."""
    cfg        = load_config()
    start_time = cfg.get("school_start_time", "07:00")
    today      = now_riyadh_date()
    now_time   = datetime.datetime.now().strftime("%H:%M")

    # بناء قائمة الطلاب مرتبة أبجدياً
    students_sorted = sorted(students_list, key=lambda s: s.get("name", ""))

    rows_html = ""
    # بناء قاموس بيانات الطلاب كـ JSON لتجنب مشاكل الأحرف الخاصة
    import json as _json
    students_data_js = _json.dumps(
        {s.get("id",""): {"name": s.get("name",""), "cls": s.get("class_name","")}
         for s in students_sorted},
        ensure_ascii=False
    )

    for s in students_sorted:
        sid   = s.get("id","")
        sname = s.get("name","")
        scls  = s.get("class_name","")
        rows_html += """
        <div class="stu-row" id="row-{sid}">
          <div class="stu-info">
            <div class="stu-name">{sname}</div>
            <div class="stu-meta">{scls}</div>
          </div>
          <div class="stu-actions">
            <div class="stu-status" id="status-{sid}"></div>
            <button class="btn-late" onclick="addLate('{sid}')"
                    id="btn-add-{sid}">
              &#x23F1; تسجيل تأخر
            </button>
            <button class="btn-del" onclick="delLate('{sid}')"
                    id="btn-del-{sid}" style="display:none">
              &#x1F5D1; حذف
            </button>
          </div>
        </div>""".format(sid=sid, sname=sname, scls=scls)

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>{title}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
body{{font-family:'Cairo',sans-serif;background:#F5F7FA;direction:rtl;color:#1a1a2e}}
.header{{background:linear-gradient(135deg,#1565C0,#1976D2);color:#fff;padding:16px 20px;
          position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.header h2{{font-size:18px;font-weight:700}}
.header-sub{{font-size:12px;opacity:.85;margin-top:3px;display:flex;gap:16px;flex-wrap:wrap}}
.stats-bar{{display:flex;gap:10px;padding:12px 16px;background:#fff;
             border-bottom:1px solid #E0E7EF;flex-wrap:wrap}}
.stat{{background:#F0F4F8;border-radius:8px;padding:8px 14px;text-align:center;flex:1;min-width:100px}}
.stat-num{{font-size:22px;font-weight:900;color:#1565C0}}
.stat-lbl{{font-size:11px;color:#5A6A7E;margin-top:2px}}
.search-bar{{padding:12px 16px;background:#fff;border-bottom:1px solid #E0E7EF}}
.search-input{{width:100%;padding:10px 14px;border:1.5px solid #DDE3EA;border-radius:10px;
               font-family:'Cairo',sans-serif;font-size:14px;direction:rtl;background:#F5F7FA}}
.search-input:focus{{outline:none;border-color:#1565C0}}
.list{{padding:10px 12px;display:flex;flex-direction:column;gap:10px;padding-bottom:80px}}
.stu-row{{background:#fff;border-radius:14px;padding:18px 20px;
           display:flex;justify-content:space-between;align-items:center;gap:12px;
           box-shadow:0 2px 8px rgba(0,0,0,.08);transition:all .2s;min-height:76px}}
.stu-row.late-done{{border-right:5px solid #E65100;background:#FFF8E1}}
.stu-row.late-deleted{{border-right:4px solid #C62828;opacity:.6}}
.stu-info{{flex:1;min-width:0}}
.stu-name{{font-size:18px;font-weight:700;line-height:1.4;word-break:break-word}}
.stu-meta{{font-size:14px;color:#5A6A7E;margin-top:4px;font-weight:600}}
.stu-actions{{display:flex;flex-direction:column;gap:8px;align-items:flex-end;flex-shrink:0}}
.stu-status{{font-size:13px;font-weight:700;color:#E65100;direction:ltr;text-align:left}}
.btn-late{{background:#E65100;color:#fff;border:none;padding:13px 22px;
            border-radius:10px;font-family:'Cairo',sans-serif;font-size:15px;
            font-weight:700;cursor:pointer;white-space:nowrap;transition:all .18s;
            min-width:140px;text-align:center}}
.btn-late:active{{background:#BF360C;transform:scale(.97)}}
.btn-late:disabled{{background:#B0BEC5;cursor:not-allowed}}
.btn-del{{background:#FFEBEE;color:#C62828;border:1px solid #EF9A9A;
           padding:10px 16px;border-radius:10px;font-family:'Cairo',sans-serif;
           font-size:14px;font-weight:700;cursor:pointer;transition:all .18s}}
.btn-del:active{{background:#FFCDD2}}
.back-btn{{position:fixed;bottom:16px;right:16px;background:#1565C0;color:#fff;
            border:none;padding:12px 20px;border-radius:12px;font-family:'Cairo',sans-serif;
            font-size:14px;font-weight:700;cursor:pointer;box-shadow:0 4px 12px rgba(21,101,192,.4)}}
#toast{{position:fixed;bottom:70px;left:50%;transform:translateX(-50%);
        background:#333;color:#fff;padding:10px 22px;border-radius:20px;
        font-size:13px;opacity:0;transition:opacity .3s;pointer-events:none;
        z-index:999;white-space:nowrap}}
#toast.show{{opacity:1}}
.empty{{text-align:center;padding:40px;color:#9E9E9E;font-size:15px}}
</style>
</head>
<body>
<div class="header">
  <h2>⏱ {title}</h2>
  <div class="header-sub">
    <span>📅 {today}</span>
    <span>🕐 بداية الدوام: {start_time}</span>
    <span id="current-time">⏰ {now_time}</span>
  </div>
</div>

<div class="stats-bar">
  <div class="stat"><div class="stat-num" id="stat-total">{len(students_sorted)}</div><div class="stat-lbl">إجمالي الطلاب</div></div>
  <div class="stat"><div class="stat-num" id="stat-late" style="color:#E65100">0</div><div class="stat-lbl">متأخرون</div></div>
  <div class="stat"><div class="stat-num" id="stat-avg" style="color:#C62828">—</div><div class="stat-lbl">متوسط التأخر</div></div>
</div>

<div class="search-bar">
  <input class="search-input" id="search" placeholder="🔍 بحث باسم الطالب..."
         oninput="filterStudents(this.value)">
</div>

<div class="list" id="list">{rows_html}</div>

<button class="back-btn" onclick="location.href='{back_url}'">← رجوع</button>
<div id="toast"></div>

<script>
const BASE  = "{base_url_str}";
const TODAY = "{today}";
const START = "{start_time}";
const STUDENTS = {students_data_js};
const lateRecords = {{}};  // sid -> {{id, time, minutes}}

function toast(msg, ok=true){{
  const t=document.getElementById('toast');
  t.textContent=msg; t.className='show';
  t.style.background=ok?'#2E7D32':'#C62828';
  setTimeout(()=>t.className='',2500);
}}

function updateStats(){{
  const cnt = Object.keys(lateRecords).length;
  document.getElementById('stat-late').textContent = cnt;
  if(cnt===0){{document.getElementById('stat-avg').textContent='—';return;}}
  const avg = Math.round(Object.values(lateRecords).reduce((s,r)=>s+r.minutes,0)/cnt);
  document.getElementById('stat-avg').textContent = avg+' د';
}}

function setCurrentTime(){{
  const now=new Date();
  const hh=String(now.getHours()).padStart(2,'0');
  const mm=String(now.getMinutes()).padStart(2,'0');
  document.getElementById('current-time').textContent='⏰ '+hh+':'+mm;
}}
setCurrentTime(); setInterval(setCurrentTime, 30000);

async function addLate(sid){{
  const stu  = STUDENTS[sid] || {{}};
  const sname= stu.name || sid;
  const scls = stu.cls  || '';
  const btn  = document.getElementById('btn-add-'+sid);
  btn.disabled=true; btn.textContent='⏳ جارٍ التسجيل...';

  const now=new Date();
  const hh=String(now.getHours()).padStart(2,'0');
  const mm=String(now.getMinutes()).padStart(2,'0');
  const registerTime=hh+':'+mm;

  try{{
    const r=await fetch(BASE+'/api/tardiness/add',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{
        date:TODAY, student_id:sid,
        student_name:sname, class_name:scls,
        register_time:registerTime
      }})
    }});
    const d=await r.json();
    if(d.ok){{
      lateRecords[sid]={{id:d.record_id, time:registerTime, minutes:d.minutes_late}};
      const row=document.getElementById('row-'+sid);
      row.classList.add('late-done');
      document.getElementById('status-'+sid).textContent=
        '⏱ '+registerTime+' ('+d.minutes_late+' دقيقة)';
      document.getElementById('btn-del-'+sid).style.display='inline-block';
      btn.textContent='✅ مسجّل';
      updateStats();
      toast('تم تسجيل تأخر '+sname+' ('+d.minutes_late+' دقيقة)');
    }}else{{
      toast(d.msg||'حدث خطأ',false);
      btn.disabled=false; btn.textContent='⏱ تسجيل تأخر';
    }}
  }}catch(e){{
    toast('خطأ في الاتصال: '+e,false);
    btn.disabled=false; btn.textContent='⏱ تسجيل تأخر';
  }}
}}

async function delLate(sid){{
  const rec=lateRecords[sid];
  if(!rec)return;
  if(!confirm('هل تريد حذف تأخر هذا الطالب؟'))return;
  const r=await fetch(BASE+'/api/tardiness/delete/'+rec.id,{{method:'DELETE'}});
  const d=await r.json();
  if(d.ok){{
    delete lateRecords[sid];
    const row=document.getElementById('row-'+sid);
    row.classList.remove('late-done');
    document.getElementById('status-'+sid).textContent='';
    document.getElementById('btn-del-'+sid).style.display='none';
    const btn=document.getElementById('btn-add-'+sid);
    btn.disabled=false; btn.textContent='⏱ تسجيل تأخر';
    updateStats();
    toast('تم حذف السجل');
  }}
}}

function filterStudents(q){{
  q=q.trim().toLowerCase();
  document.querySelectorAll('.stu-row').forEach(row=>{{
    const name=row.querySelector('.stu-name').textContent.toLowerCase();
    row.style.display=(!q||name.includes(q))?'flex':'none';
  }});
}}

// تحميل سجلات اليوم الحالية
async function loadToday(){{
  try{{
    const r=await fetch(BASE+'/api/tardiness/today');
    const d=await r.json();
    d.records.forEach(rec=>{{
      const sid=rec.student_id;
      lateRecords[sid]={{id:rec.id,time:rec.register_time||'',minutes:rec.minutes_late}};
      const row=document.getElementById('row-'+sid);
      if(!row)return;
      row.classList.add('late-done');
      document.getElementById('status-'+sid).textContent=
        '⏱ '+(rec.register_time||'')+'('+rec.minutes_late+' دقيقة)';
      const btn=document.getElementById('btn-add-'+sid);
      btn.textContent='✅ مسجّل'; btn.disabled=true;
      document.getElementById('btn-del-'+sid).style.display='inline-block';
    }});
    updateStats();
  }}catch(e){{console.warn('loadToday error:',e);}}
}}
loadToday();
</script>
</body></html>"""


@app.get("/tardiness", response_class=HTMLResponse)
def tardiness_all_page():
    """صفحة التأخر — جميع طلاب المدرسة مرتبين أبجدياً."""
    store   = load_students()
    base    = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    all_stu = []
    for cls in store["list"]:
        for s in cls["students"]:
            all_stu.append({**s, "class_name": cls["name"]})
    html = _tardiness_page_html(
        students_list=all_stu,
        title="تسجيل التأخر — جميع الطلاب",
        back_url=f"{base}/mobile",
        base_url_str=base
    )
    return HTMLResponse(html)


@app.get("/tardiness/{class_id}", response_class=HTMLResponse)
def tardiness_class_page(class_id: str):
    """صفحة التأخر — طلاب فصل محدد."""
    store = load_students()
    cls   = store["by_id"].get(class_id)
    if not cls:
        return HTMLResponse("<h3>الفصل غير موجود</h3>", status_code=404)
    base  = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    students = [{**s, "class_name": cls["name"]} for s in cls["students"]]
    html = _tardiness_page_html(
        students_list=students,
        title=f"تسجيل التأخر — {cls['name']}",
        back_url=f"{base}/mobile",
        base_url_str=base
    )
    return HTMLResponse(html)


@app.post("/api/tardiness/add")
async def api_tardiness_add(req: Request):
    """يُسجّل تأخر طالب ويحسب الدقائق تلقائياً."""
    data = await req.json()
    cfg  = load_config()

    student_id   = data.get("student_id","")
    student_name = data.get("student_name","")
    class_name   = data.get("class_name","")
    date_str     = data.get("date", now_riyadh_date())
    register_time= data.get("register_time", datetime.datetime.now().strftime("%H:%M"))

    # احسب الدقائق
    minutes_late = _calc_late_minutes(register_time, cfg)

    # ابحث عن class_id
    store    = load_students()
    class_id = ""
    for cls in store["list"]:
        if cls["name"] == class_name:
            class_id = cls["id"]
            break

    # أدخل في قاعدة البيانات مع حفظ وقت التسجيل
    # نستخدم INSERT OR IGNORE ثم UPDATE لتجنب مشكلة UNIQUE القديمة
    try:
        created_at = datetime.datetime.utcnow().isoformat()
        con = get_db(); cur = con.cursor()

        # تحقق أولاً: هل الطالب مسجّل اليوم بالفعل؟
        cur.execute("SELECT id FROM tardiness WHERE date=? AND student_id=?",
                    (date_str, student_id))
        existing = cur.fetchone()
        if existing:
            con.close()
            return JSONResponse({"ok": False, "msg": "الطالب مسجّل مسبقاً لهذا اليوم"})

        cur.execute("""INSERT INTO tardiness
            (date,class_id,class_name,student_id,student_name,
             teacher_name,period,minutes_late,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (date_str, class_id, class_name, student_id, student_name,
             "", None, minutes_late, created_at))
        record_id = cur.lastrowid
        con.commit(); con.close()
        return JSONResponse({
            "ok": True,
            "record_id": record_id,
            "minutes_late": minutes_late,
            "register_time": register_time
        })
    except sqlite3.IntegrityError as e:
        return JSONResponse({"ok": False, "msg": "الطالب مسجّل مسبقاً"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@app.delete("/api/tardiness/delete/{record_id}")
def api_tardiness_delete(record_id: int):
    """يحذف سجل تأخر."""
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("DELETE FROM tardiness WHERE id=?", (record_id,))
        con.commit(); con.close()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@app.get("/api/tardiness/today")
def api_tardiness_today(date: str = ""):
    """يُرجع سجلات التأخر لليوم مع وقت التسجيل."""
    date_str = date or now_riyadh_date()
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    # نستخدم created_at لاستخراج وقت التسجيل الفعلي
    cur.execute("""SELECT id, student_id, student_name, class_name,
                          minutes_late,
                          substr(created_at,12,5) as register_time
                   FROM tardiness WHERE date=?
                   ORDER BY class_name, student_name""", (date_str,))
    rows = [dict(r) for r in cur.fetchall()]; con.close()
    return {"records": rows, "count": len(rows)}


# ═══════════════════════════════════════════════════════════════
# NEW: PWA Mobile Portal
# ═══════════════════════════════════════════════════════════════

def mobile_portal_html() -> str:
    """Generates the main HTML for the PWA mobile portal with ALL services."""
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
        <title>بوابة الغياب</title>
        <link rel="manifest" href="/manifest.json">
        <meta name="theme-color" content="#007bff">
        <link rel="apple-touch-icon" href="https://i.imgur.com/2h2h4vY.png">
        <style>
            :root {
                --primary-color: #007bff;
                --secondary-color: #6c757d;
                --bg-color: #f8f9fa;
                --card-bg: #ffffff;
                --text-color: #333;
                --success-color: #28a745;
                --warning-color: #ffc107;
                --danger-color: #dc3545;
            }
            body {
                font-family: 'Cairo', sans-serif;
                background-color: var(--bg-color);
                margin: 0;
                color: var(--text-color);
            }
            .header {
                background-color: var(--primary-color);
                color: white;
                padding: 20px;
                text-align: center;
                border-bottom-left-radius: 15px;
                border-bottom-right-radius: 15px;
            }
            .header h1 { margin: 0; font-size: 24px; }
            .header p { margin: 5px 0 0; opacity: 0.9; }
            .main-container { padding: 15px; }
            .card {
                background: var(--card-bg);
                border-radius: 12px;
                padding: 15px;
                margin-bottom: 15px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            }
            .card h2 {
                margin-top: 0;
                margin-bottom: 15px;
                font-size: 18px;
                border-bottom: 2px solid var(--primary-color);
                padding-bottom: 10px;
            }
            .grid-menu {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                gap: 15px;
            }
            .menu-item {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 15px;
                background-color: #f1f3f5;
                border-radius: 10px;
                text-decoration: none;
                color: var(--text-color);
                font-weight: bold;
                text-align: center;
                transition: transform 0.2s;
            }
            .menu-item:hover { transform: translateY(-5px); }
            .menu-item .icon { font-size: 36px; }
            .live-monitor-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 10px;
            }
            .monitor-cell {
                padding: 10px;
                border-radius: 8px;
                text-align: center;
            }
            .monitor-cell.done { background-color: #e9f7ef; color: var(--success-color); }
            .monitor-cell.pending { background-color: #fdf2f2; color: var(--danger-color); }
            .monitor-cell .period { font-weight: bold; }
            .monitor-cell .class-name { font-size: 14px; }
            #last-update { text-align: center; font-size: 12px; color: var(--secondary-color); margin-top: 10px; }
            #install-prompt {
                display: none;
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                background: #333;
                color: white;
                padding: 15px;
                text-align: center;
            }
            #install-prompt button {
                background: var(--primary-color);
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 5px;
                margin-right: 10px;
            }
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
    </head>
    <body>
        <div class="header">
            <h1 id="school-name">بوابة الغياب المدرسية</h1>
            <p>أهلاً بك</p>
        </div>
        <div class="main-container">
            <div class="card">
                <h2>الخدمات الكاملة</h2>
                <div class="grid-menu" id="main-menu">
                    <!-- سيتم ملؤها تلقائيًا -->
                </div>
            </div>
            <div class="card">
                <h2>لوحة المراقبة الحية</h2>
                <div class="live-monitor-grid" id="live-monitor">
                    <p>جاري تحميل البيانات...</p>
                </div>
                <p id="last-update"></p>
            </div>
        </div>
        <div id="install-prompt">
            <button id="install-btn">تثبيت التطبيق</button>
            <button id="dismiss-btn">لاحقًا</button>
        </div>
        <script>
            const schoolNameEl = document.getElementById('school-name');
            const mainMenuEl = document.getElementById('main-menu');
            const liveMonitorEl = document.getElementById('live-monitor');
            const lastUpdateEl = document.getElementById('last-update');

            async function fetchDataAndRender() {
                try {
                    const res = await fetch('/api/mobile-portal-data');
                    const data = await res.json();
                    schoolNameEl.textContent = data.school_name || 'بوابة الغياب';

                    // عرض جميع الخدمات (القديمة + الجديدة)
                    const allServices = [
                        { title: "تسجيل الغياب", url: data.class_links_page_url, icon: "📝" },
                        { title: "إرسال رسائل الغياب", url: data.send_messages_url, icon: "✉️" },
                        { title: "تعديل جدول الحصص", url: data.schedule_edit_url, icon: "🗓️" },
                        { title: "إضافة طالب جديد", url: data.add_student_url, icon: "➕" },
                        { title: "إدارة الطلاب والفصول", url: data.manage_students_url, icon: "🗑️" },
                        { title: "لوحة المراقبة", url: data.monitor_url, icon: "👁️" }
                    ];

                    let menuHtml = '';
                    allServices.forEach(item => {
                        menuHtml += `<a href="${item.url}" class="menu-item"><span class="icon">${item.icon}</span><span>${item.title}</span></a>`;
                    });
                    mainMenuEl.innerHTML = menuHtml;

                    // تحديث لوحة المراقبة
                    let monitorHtml = '';
                    if (data.live_status && data.live_status.length > 0) {
                        const now = new Date();
                        const currentHour = now.getHours();
                        let currentPeriod = 1;
                        if(currentHour >= 8) currentPeriod = 2;
                        if(currentHour >= 9) currentPeriod = 3;
                        if(currentHour >= 10) currentPeriod = 4;
                        if(currentHour >= 11) currentPeriod = 5;
                        if(currentHour >= 12) currentPeriod = 6;
                        if(currentHour >= 13) currentPeriod = 7;
                        const periodData = data.live_status.find(p => p.period === currentPeriod) || data.live_status[0];
                        monitorHtml += `<h3>الحصة ${periodData.period}</h3>`;
                        periodData.classes.forEach(c => {
                            monitorHtml += `
                                <div class="monitor-cell ${c.status}">
                                    <div class="class-name">${c.class_name}</div>
                                    <div class="status-icon">${c.status === 'done' ? '✔️ تم' : '❌ بانتظار'}</div>
                                </div>
                            `;
                        });
                        lastUpdateEl.textContent = 'آخر تحديث: ' + new Date().toLocaleTimeString();
                    } else {
                        monitorHtml = '<p>لا توجد بيانات مراقبة حاليًا.</p>';
                    }
                    liveMonitorEl.innerHTML = monitorHtml;
                } catch (e) {
                    liveMonitorEl.innerHTML = '<p>فشل تحميل البيانات. حاول التحديث.</p>';
                    console.error(e);
                }
            }

            // --- PWA Install Prompt ---
            let deferredPrompt;
            const installPrompt = document.getElementById('install-prompt');
            const installBtn = document.getElementById('install-btn');
            const dismissBtn = document.getElementById('dismiss-btn');
            window.addEventListener('beforeinstallprompt', (e) => {
                e.preventDefault();
                deferredPrompt = e;
                installPrompt.style.display = 'block';
            });
            installBtn.addEventListener('click', async () => {
                if (deferredPrompt) {
                    deferredPrompt.prompt();
                    await deferredPrompt.userChoice;
                    deferredPrompt = null;
                    installPrompt.style.display = 'none';
                }
            });
            dismissBtn.addEventListener('click', () => {
                installPrompt.style.display = 'none';
            });

            // --- Service Worker ---
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/service-worker.js').catch(err => {
                    console.error('Service worker registration failed:', err);
                });
            }

            fetchDataAndRender();
            setInterval(fetchDataAndRender, 30000);
        </script>
    </body>
    </html>
    """

@app.get("/mobile", response_class=HTMLResponse)
def get_mobile_portal_page():
    return HTMLResponse(content=mobile_portal_html())


@app.get("/api/today-schedule")
def api_today_schedule():
    """يُرجع جدول اليوم الحالي مع أوقات الحصص."""
    import datetime as _dt
    now     = _dt.datetime.now()
    # تحويل Python weekday إلى يوم سعودي (0=الأحد)
    dow = (now.weekday() + 1) % 7   # Sun=0..Thu=4
    cfg = load_config()
    period_times = cfg.get("period_times",
        ["07:00","07:50","08:40","09:50","10:40","11:30","12:20"])
    schedule = load_schedule(dow)   # {(class_id, period): teacher}

    periods = []
    for i, pt in enumerate(period_times, 1):
        periods.append({"period": i, "time": pt})

    return JSONResponse({
        "day_of_week": dow,
        "current_time": now.strftime("%H:%M"),
        "period_times": period_times,
        "periods": periods,
    })

@app.get("/manifest.json")
def get_manifest():
    cfg = load_config()
    school_name = cfg.get("school_name", "نظام الغياب")
    return {
        "name": school_name,
        "short_name": "الغياب",
        "description": "نظام إدارة غياب الطلاب",
        "start_url": "/mobile",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#1565C0",
        "theme_color": "#1565C0",
        "lang": "ar",
        "dir": "rtl",
        "categories": ["education"],
        "icons": [
            { "src": "https://i.imgur.com/2h2h4vY.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
            { "src": "https://i.imgur.com/gL6hS8q.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
        ],
        "screenshots": [],
        "shortcuts": [
            { "name": "تسجيل الغياب", "url": "/classes-list", "description": "فتح قائمة الفصول" },
            { "name": "التأخر", "url": "/tardiness", "description": "تسجيل التأخر" },
            { "name": "المراقبة", "url": "/monitor", "description": "مراقبة حية" }
        ]
    }

@app.get("/service-worker.js", response_class=Response)
def get_service_worker():
    js_content = """
// ─── Service Worker — DarbStu PWA v3 ────────────────────────
const CACHE = 'darb-v3';
const OFFLINE_URLS = ['/mobile', '/classes-list', '/tardiness'];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE).then(c => c.addAll(OFFLINE_URLS))
        .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request)
            .then(resp => {
                const clone = resp.clone();
                caches.open(CACHE).then(c => c.put(e.request, clone));
                return resp;
            })
            .catch(() => caches.match(e.request))
    );
});

// ─── إشعارات Push ───────────────────────────────────────────
self.addEventListener('push', e => {
    let data = {};
    try { data = e.data.json(); } catch { data = { title: 'DarbStu', body: e.data.text() }; }
    e.waitUntil(
        self.registration.showNotification(data.title || 'DarbStu', {
            body:    data.body    || '',
            icon:    data.icon    || '/icon-192.png',
            badge:   '/icon-192.png',
            tag:     data.tag     || 'darb-notif',
            data:    data.url     || '/mobile',
            dir:     'rtl',
            lang:    'ar',
            vibrate: [200, 100, 200],
            requireInteraction: true
        })
    );
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    const url = e.notification.data || '/mobile';
    e.waitUntil(
        clients.matchAll({ type: 'window' }).then(ws => {
            for (const w of ws) {
                if (w.url.includes(url) && 'focus' in w) return w.focus();
            }
            if (clients.openWindow) return clients.openWindow(url);
        })
    );
});
"""
    return Response(content=js_content, media_type="application/javascript")

@app.get("/api/mobile-portal-data", response_class=JSONResponse)
def get_mobile_portal_data():
    cfg = load_config()
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    return {
        "school_name": cfg.get("school_name"),
        "live_status": get_live_monitor_status(now_riyadh_date()),
        "class_links_page_url": f"{base_url}/classes-list",
        "tardiness_url": f"{base_url}/tardiness",
        "send_messages_url": f"{base_url}/send-messages",
        "schedule_edit_url": f"{base_url}/schedule/edit",
        "tardiness_all_url": f"{base_url}/tardiness",
        "add_student_url": f"{base_url}/add-student-mobile",
        "manage_students_url": f"{base_url}/manage-students",
        "monitor_url": f"{base_url}/monitor"
    }

@app.get("/classes-list", response_class=HTMLResponse)
def get_classes_list_page():
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    nav = navbar_html(base_url)
    """A simple HTML page that lists all classes with links to their absence forms."""
    store = load_students()
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip( )}:{PORT}"
    
    links_html = ""
    for c in sorted(store["list"], key=lambda x: x['id']):
        links_html += (
            '<div class="class-item">'
            '<a class="class-link" href="{base}/c/{cid}">{name} — غياب</a>'
            '<a class="class-link tard-link" href="{base}/tardiness/{cid}">{name} — تأخر</a>'
            '</div>'
        ).format(base=base_url, cid=c["id"], name=c["name"])

    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>قائمة الفصول</title>
        <style>
            body {{ font-family: 'Cairo', sans-serif; background-color: #f8f9fa; margin: 0; padding: 15px; }}
            h1 {{ text-align: center; color: #333; }}
            .list-container {{ display: flex; flex-direction: column; gap: 10px; }}
            .class-link {{
                display: block;
                padding: 20px;
                background-color: #fff;
                border-radius: 10px;
                text-decoration: none;
                color: #007bff;
                font-weight: bold;
                font-size: 18px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.07);
                transition: transform 0.2s;
            }}
            .class-link:hover {{ transform: scale(1.02); }}
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
    </head>
    <body>
        <h1>اختر الفصل لتسجيل الغياب</h1>
        <div class="list-container">
            {links_html}
        </div>
    </body>
    </html>
    """ )

# ===================== END PWA Mobile Portal =====================

# ===================== NEW: Mobile Send Messages =====================

def send_messages_html() -> str:
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    nav = navbar_html(base_url)
    """Generates the HTML page for sending absence messages from mobile."""
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إرسال رسائل الغياب</title>
        <style>
            body { font-family: 'Cairo', sans-serif; background-color: #f8f9fa; margin: 0; padding: 15px; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { text-align: center; color: #333; }
            .controls { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.07); margin-bottom: 15px; }
            .controls button { background-color: #007bff; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-family: 'Cairo'; }
            #send-btn { background-color: #28a745; }
            .student-list { list-style: none; padding: 0; }
            .student-item { display: flex; align-items: center; background: #fff; padding: 15px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }
            .student-item input[type='checkbox'] { width: 20px; height: 20px; margin-left: 15px; }
            .student-info { flex-grow: 1; }
            .student-info .name { font-weight: bold; }
            .student-info .class { font-size: 14px; color: #6c757d; }
            .status { padding: 5px 10px; border-radius: 15px; font-size: 12px; color: white; }
            .status.ready { background-color: #6c757d; }
            .status.sent { background-color: #28a745; }
            .status.failed { background-color: #dc3545; }
            #status-log { margin-top: 15px; font-size: 14px; text-align: center; }
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
    </head>
    <body>
        <div class="container">
            <h1>إرسال رسائل غياب اليوم</h1>
            <div class="controls">
                <button id="select-all-btn">تحديد الكل</button>
                <button id="send-btn">🚀 إرسال للمحددين</button>
            </div>
            <ul id="student-list-container" class="student-list">
                <!-- Students will be loaded here -->
            </ul>
            <div id="status-log">جاهز</div>
        </div>

        <script>
            const studentListContainer = document.getElementById('student-list-container' );
            const statusLog = document.getElementById('status-log');
            const sendBtn = document.getElementById('send-btn');
            const selectAllBtn = document.getElementById('select-all-btn');
            let isAllSelected = true;

            async function fetchAbsentStudents() {
                try {
                    statusLog.textContent = 'جاري تحميل قائمة الغياب...';
                    const res = await fetch('/api/absent-students-for-messaging');
                    const students = await res.json();
                    
                    if (students.length === 0) {
                        studentListContainer.innerHTML = '<p style="text-align:center;">لا يوجد طلاب غائبون اليوم.</p>';
                        statusLog.textContent = '';
                        return;
                    }

                    let studentsHtml = '';
                    students.forEach(s => {
                        studentsHtml += `
                            <li class="student-item" id="student-${s.student_id}">
                                <input type="checkbox" value="${s.student_id}" checked>
                                <div class="student-info">
                                    <div class="name">${s.student_name}</div>
                                    <div class="class">${s.class_name} | ${s.phone || 'لا يوجد رقم'}</div>
                                </div>
                                <div class="status ready">جاهز</div>
                            </li>
                        `;
                    });
                    studentListContainer.innerHTML = studentsHtml;
                    statusLog.textContent = `تم تحميل ${students.length} طالب.`;
                } catch (e) {
                    statusLog.textContent = 'فشل تحميل البيانات.';
                }
            }

            sendBtn.addEventListener('click', async () => {
                const selectedIds = Array.from(document.querySelectorAll("input[type='checkbox']:checked")).map(cb => cb.value);
                if (selectedIds.length === 0) {
                    alert('الرجاء تحديد طالب واحد على الأقل.');
                    return;
                }

                sendBtn.disabled = true;
                statusLog.textContent = `جاري إرسال ${selectedIds.length} رسالة...`;

                try {
                    const res = await fetch('/api/send-bulk-messages', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ student_ids: selectedIds })
                    });
                    const results = await res.json();
                    
                    results.forEach(result => {
                        const studentLi = document.getElementById(`student-${result.student_id}`);
                        if (studentLi) {
                            const statusDiv = studentLi.querySelector('.status');
                            statusDiv.textContent = result.success ? 'تم الإرسال' : 'فشل';
                            statusDiv.className = `status ${result.success ? 'sent' : 'failed'}`;
                        }
                    });
                    const successCount = results.filter(r => r.success).length;
                    const failedCount = results.length - successCount;
                    statusLog.textContent = `اكتمل: نجح ${successCount}، فشل ${failedCount}.`;

                } catch (e) {
                    statusLog.textContent = 'حدث خطأ فادح أثناء الإرسال.';
                } finally {
                    sendBtn.disabled = false;
                }
            });

            selectAllBtn.addEventListener('click', () => {
                const checkboxes = document.querySelectorAll("input[type='checkbox']");
                checkboxes.forEach(cb => cb.checked = !isAllSelected);
                isAllSelected = !isAllSelected;
                selectAllBtn.textContent = isAllSelected ? 'إلغاء تحديد الكل' : 'تحديد الكل';
            });

            fetchAbsentStudents();
        </script>
    </body>
    </html>
    """

@app.get("/send-messages", response_class=HTMLResponse)
def get_send_messages_page():
    return HTMLResponse(content=send_messages_html())

@app.get("/api/absent-students-for-messaging", response_class=JSONResponse)
def get_absent_students_for_messaging_api():
    """Returns a list of unique absent students for the current day."""
    today = now_riyadh_date()
    absent_groups = build_absent_groups(today)
    
    students_list = []
    for class_id, data in absent_groups.items():
        for student in data["students"]:
            students_list.append({
                "student_id": student["id"],
                "student_name": student["name"],
                "class_name": data["class_name"],
                "phone": student.get("phone")
            })
    return JSONResponse(content=sorted(students_list, key=lambda x: (x['class_name'], x['student_name'])))

@app.get("/monitor", response_class=HTMLResponse)
def get_monitor_page():
    return HTMLResponse(content=live_monitor_html_page())

@app.get("/api/live_status", response_class=JSONResponse)
def get_status_api():
    today = now_riyadh_date()
    status_data = get_live_monitor_status(today)
    return JSONResponse(content=status_data)

def schedule_editor_html() -> str:
    base_url = STATIC_DOMAIN if STATIC_DOMAIN and not debug_on() else f"http://{local_ip()}:{PORT}"
    nav = navbar_html(base_url)
    style_css = """
        body { font-family: 'Cairo', 'Segoe UI', sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #333; }
        .controls { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 10px; background: #f9f9f9; border-radius: 6px; }
        .day-selector button { font-size: 16px; padding: 10px 15px; margin: 0 5px; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; transition: all 0.2s; }
        .day-selector button.active { background-color: #007bff; color: white; border-color: #007bff; }
        #save-btn { font-size: 16px; padding: 10px 20px; border: none; background-color: #28a745; color: white; border-radius: 6px; cursor: pointer; }
        #save-btn:hover { background-color: #218838; }
        #status { font-weight: bold; }
        .table-container { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: center; min-width: 150px; }
        th { background-color: #f2f2f2; font-weight: bold; }
        td select { width: 100%; padding: 5px; border-radius: 4px; border: 1px solid #ccc; }
    """
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>تعديل جدول الحصص</title>
        <style>{style_css}</style>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
    </head>
    <body>
        {nav}
        <div class="container">
            <h1>تعديل جدول الحصص المدرسي</h1>
            <div class="controls">
                <div class="day-selector">
                    <button data-day="0" class="active">الأحد</button>
                    <button data-day="1">الاثنين</button>
                    <button data-day="2">الثلاثاء</button>
                    <button data-day="3">الأربعاء</button>
                    <button data-day="4">الخميس</button>
                </div>
                <div>
                    <span id="status"></span>
                    <button id="save-btn">💾 حفظ الجدول الحالي</button>
                </div>
            </div>
            <div class="table-container">
                <table id="schedule-table">
                    <thead></thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
        <script>
            let currentDay = 0;
            let teacherOptions = '';
            const statusEl = document.getElementById('status');
            const saveBtn = document.getElementById('save-btn');
            const dayButtons = document.querySelectorAll('.day-selector button');

            async function fetchAndRenderSchedule(day) {{
                try {{
                    statusEl.textContent = 'جاري التحميل...';
                    const res = await fetch(`/api/schedule-data/${{day}}`);
                    if (!res.ok) throw new Error('Failed to fetch data');
                    const data = await res.json();

                    if (!teacherOptions) {{
                        teacherOptions = '<option value="">— فارغ —</option>';
                        data.teachers.forEach(t => {{
                            teacherOptions += `<option value="${{t['اسم المعلم']}}">${{t['اسم المعلم']}}</option>`;
                        }});
                    }}

                    const tableHead = document.querySelector('#schedule-table thead');
                    const tableBody = document.querySelector('#schedule-table tbody');

                    let headerHtml = '<tr><th>الحصة</th>';
                    data.classes.forEach(c => {{ headerHtml += `<th>${{c.name}}</th>`; }});
                    headerHtml += '</tr>';
                    tableHead.innerHTML = headerHtml;

                    let bodyHtml = '';
                    for (let period = 1; period <= 7; period++) {{
                        bodyHtml += `<tr><td>الحصة ${{period}}</td>`;
                        data.classes.forEach(c => {{
                            bodyHtml += `<td><select data-class-id="${{c.id}}" data-period="${{period}}">${{teacherOptions}}</select></td>`;
                        }});
                        bodyHtml += '</tr>';
                    }}
                    tableBody.innerHTML = bodyHtml;

                    tableBody.querySelectorAll('select').forEach(select => {{
                        const classId = select.dataset.classId;
                        const period = select.dataset.period;
                        select.value = data.schedule[`${{classId}},${{period}}`] || '';
                    }});
                    statusEl.textContent = 'تم التحميل.';
                }} catch (error) {{
                    statusEl.textContent = 'خطأ في تحميل البيانات.';
                }}
            }}

            saveBtn.addEventListener('click', async () => {{
                const scheduleData = [];
                document.querySelectorAll('#schedule-table tbody select').forEach(select => {{
                    if (select.value) {{
                        scheduleData.push({{
                            class_id: select.dataset.classId,
                            period: parseInt(select.dataset.period),
                            teacher_name: select.value
                        }});
                    }}
                }});
                try {{
                    statusEl.textContent = 'جاري الحفظ...';
                    const res = await fetch('/api/save-schedule', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ day_of_week: currentDay, schedule_data: scheduleData }})
                    }});
                    if (!res.ok) throw new Error('Failed to save');
                    statusEl.textContent = 'تم الحفظ بنجاح!';
                }} catch (error) {{
                    statusEl.textContent = 'خطأ في الحفظ.';
                }}
            }});

            dayButtons.forEach(btn => {{
                btn.addEventListener('click', () => {{
                    currentDay = parseInt(btn.dataset.day);
                    dayButtons.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    fetchAndRenderSchedule(currentDay);
                }});
            }});

            fetchAndRenderSchedule(currentDay);
        </script>
    </body>
    </html>
    """

@app.get("/schedule/edit", response_class=HTMLResponse)
def get_schedule_edit_page():
    return HTMLResponse(content=schedule_editor_html())

@app.get("/api/schedule-data/{day_of_week}", response_class=JSONResponse)
def get_schedule_data_api(day_of_week: int):
    classes = sorted(load_students()["list"], key=lambda c: c['id'])
    teachers = load_teachers().get("teachers", [])
    schedule_raw = load_schedule(day_of_week)
    schedule = {f"{k[0]},{k[1]}": v for k, v in schedule_raw.items()}
    return {"classes": classes, "teachers": teachers, "schedule": schedule}

@app.post("/api/save-schedule", response_class=JSONResponse)
async def save_schedule_api(request: Request):
    data = await request.json()
    day_of_week = data.get("day_of_week")
    schedule_data = data.get("schedule_data")
    if day_of_week is None or schedule_data is None:
        return JSONResponse(content={"error": "Missing data"}, status_code=400)
    try:
        save_schedule(day_of_week, schedule_data)
        return {"message": "تم الحفظ بنجاح"}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/bot/excuse")
async def api_bot_excuse(req: Request):
    """يستقبل العذر من بوت الواتساب ويحفظه في قاعدة البيانات."""
    try:
        data = await req.json()
        student_id   = data.get("student_id", "")
        student_name = data.get("student_name", "")
        class_id     = data.get("class_id", "")
        class_name   = data.get("class_name", "")
        date_str     = data.get("date", now_riyadh_date())
        reason       = data.get("reason", "")
        parent_phone = data.get("parent_phone", "")

        if not student_id or not student_name:
            return JSONResponse({"ok": False, "error": "بيانات ناقصة"}, status_code=400)

        # تحقق من عدم تكرار العذر في نفس اليوم
        if student_has_excuse(student_id, date_str):
            return JSONResponse({"ok": True, "note": "العذر مسجّل مسبقاً"})

        insert_excuse(date_str, student_id, student_name,
                      class_id, class_name, reason,
                      source="whatsapp", approved_by=parent_phone)

        print(f"[BOT] ✅ عذر محفوظ: {student_name} — {date_str} — {reason}")
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"[BOT] ❌ خطأ في حفظ العذر: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/send-bulk-messages", response_class=JSONResponse)
async def send_bulk_messages_api(request: Request):
    """Receives a list of student IDs and sends them absence alerts."""
    data = await request.json()
    student_ids = data.get("student_ids", [])
    today = now_riyadh_date()
    
    absent_groups = build_absent_groups(today)
    all_absent_students = {}
    for class_id, class_data in absent_groups.items():
        for student in class_data["students"]:
            all_absent_students[student["id"]] = {**student, "class_name": class_data["class_name"]}

    results = []
    for sid in student_ids:
        student_details = all_absent_students.get(sid)
        if not student_details:
            results.append({"student_id": sid, "success": False, "message": "Student not found in today's absence list."})
            continue

        success, message = send_absence_alert(
            student_id=sid,
            student_name=student_details["name"],
            class_name=student_details["class_name"],
            date_str=today
        )
        results.append({"student_id": sid, "success": success, "message": message})
        
        try:
            log_message_status(
                date_str=today, student_id=sid, student_name=student_details["name"],
                class_id=student_details.get("class_id", ""), class_name=student_details["class_name"],
                phone=student_details.get("phone", ""), status=message, template_used=get_message_template()
            )
        except Exception as e:
            print(f"Error logging message status for {sid}: {e}")

    return JSONResponse(content=results)

# ===================== END Mobile Send Messages =====================

# ===================== تشغيل واتساب سيرفر =====================
def start_whatsapp_server():
    try:
        if not os.path.isdir(WHATS_PATH):
            messagebox.showerror("خطأ", f"المجلد غير موجود:\n{WHATS_PATH}")
            return
        cmd = rf'cmd.exe /k "cd /d {WHATS_PATH} && npm start"'
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        messagebox.showinfo("تم", "تم فتح نافذة الواتساب سيرفر.\nامسح رمز الـ QR من النافذة الجديدة.")
    except Exception as e:
        messagebox.showerror("خطأ", f"تعذّر تشغيل السيرفر:\n{e}")

# ===================== الواجهة الرسومية =====================


# ═══════════════════════════════════════════════════════════════
# تحليلات لوحة المدير
# ═══════════════════════════════════════════════════════════════

def get_week_comparison() -> Dict:
    """يقارن غياب هذا الأسبوع بالأسبوع الماضي."""
    today   = datetime.date.today()
    monday  = today - datetime.timedelta(days=today.weekday())
    # بداية هذا الأسبوع (الأحد)
    this_sun  = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    last_sun  = this_sun - datetime.timedelta(days=7)
    this_sat  = this_sun + datetime.timedelta(days=6)
    last_sat  = last_sun + datetime.timedelta(days=6)

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()

    def count_week(start, end):
        cur.execute("""SELECT COUNT(DISTINCT date||student_id) as cnt
                       FROM absences WHERE date BETWEEN ? AND ?""",
                    (start.isoformat(), end.isoformat()))
        return (cur.fetchone() or {"cnt": 0})["cnt"]

    def daily_counts(start, end):
        cur.execute("""SELECT date, COUNT(DISTINCT student_id) as cnt
                       FROM absences WHERE date BETWEEN ? AND ?
                       GROUP BY date ORDER BY date""",
                    (start.isoformat(), end.isoformat()))
        return {r["date"]: r["cnt"] for r in cur.fetchall()}

    this_total = count_week(this_sun, this_sat)
    last_total = count_week(last_sun, last_sat)
    this_daily = daily_counts(this_sun, this_sat)
    last_daily = daily_counts(last_sun, last_sat)
    con.close()

    change = this_total - last_total
    pct    = round(change / max(last_total, 1) * 100, 1)
    return {
        "this_total": this_total,
        "last_total": last_total,
        "change":     change,
        "pct":        pct,
        "this_daily": this_daily,
        "last_daily": last_daily,
        "this_week_start": this_sun.isoformat(),
        "last_week_start": last_sun.isoformat(),
    }


def get_top_absent_students(month: str = None, limit: int = 10) -> List[Dict]:
    """أكثر الطلاب غياباً هذا الشهر."""
    if not month:
        month = datetime.datetime.now().strftime("%Y-%m")
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""
        SELECT student_id, MAX(student_name) as name,
               MAX(class_name) as class_name,
               COUNT(DISTINCT date) as days,
               MAX(date) as last_date
        FROM absences WHERE date LIKE ?
        GROUP BY student_id
        ORDER BY days DESC LIMIT ?
    """, (month + "%", limit))
    rows = [dict(r) for r in cur.fetchall()]; con.close()
    return rows


def get_absence_by_day_of_week(months_back: int = 2) -> Dict:
    """يحسب متوسط الغياب لكل يوم من أيام الأسبوع."""
    since = (datetime.date.today() - datetime.timedelta(days=months_back*30)).isoformat()
    con   = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""
        SELECT date, COUNT(DISTINCT student_id) as cnt
        FROM absences WHERE date >= ?
        GROUP BY date
    """, (since,))
    rows = cur.fetchall(); con.close()

    day_names = ["الأحد","الاثنين","الثلاثاء","الأربعاء","الخميس"]
    totals = {d: [] for d in day_names}
    for r in rows:
        try:
            dt  = datetime.date.fromisoformat(r["date"])
            dow = (dt.weekday() + 1) % 7  # 0=Sunday
            if dow < 5:
                totals[day_names[dow]].append(r["cnt"])
        except Exception:
            pass
    return {d: (sum(v)/len(v) if v else 0) for d, v in totals.items()}

# ═══════════════════════════════════════════════════════════════
# نظام الإشعارات الذكية — تنبيه عند تجاوز عتبة الغياب
# ═══════════════════════════════════════════════════════════════

def get_student_absence_count(student_id: str, month: str = None) -> Dict[str, Any]:
    """
    يُرجع عدد أيام غياب الطالب + آخر يوم غياب + الفصل + الاسم.
    month: بصيغة "YYYY-MM" — إذا None يحسب كل السجلات.
    """
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if month:
        cur.execute("""SELECT COUNT(DISTINCT date) as cnt, MAX(date) as last_date,
                              MAX(student_name) as name, MAX(class_name) as class_name
                       FROM absences WHERE student_id=? AND date LIKE ?""",
                    (student_id, month + "%"))
    else:
        cur.execute("""SELECT COUNT(DISTINCT date) as cnt, MAX(date) as last_date,
                              MAX(student_name) as name, MAX(class_name) as class_name
                       FROM absences WHERE student_id=?""",
                    (student_id,))
    row = cur.fetchone(); con.close()
    if not row or not row["cnt"]:
        return {"count": 0, "last_date": "", "name": "", "class_name": ""}
    return {"count": row["cnt"], "last_date": row["last_date"] or "",
            "name": row["name"] or "", "class_name": row["class_name"] or ""}


def get_students_exceeding_threshold(threshold: int = None,
                                      month: str = None) -> List[Dict]:
    """
    يُرجع قائمة الطلاب الذين تجاوزوا عتبة الغياب.
    يُرتَّب تنازلياً حسب عدد الغيابات.
    """
    cfg = load_config()
    if threshold is None:
        threshold = cfg.get("alert_absence_threshold", 5)
    if month is None:
        month = datetime.datetime.now().strftime("%Y-%m")

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""
        SELECT student_id,
               MAX(student_name)  as student_name,
               MAX(class_name)    as class_name,
               COUNT(DISTINCT date) as absence_count,
               MAX(date)          as last_date
        FROM absences
        WHERE date LIKE ?
        GROUP BY student_id
        HAVING absence_count >= ?
        ORDER BY absence_count DESC
    """, (month + "%", threshold))
    rows = [dict(r) for r in cur.fetchall()]; con.close()

    # أضف رقم جوال ولي الأمر من students.json
    store = load_students()
    phone_map = {}
    for cls in store["list"]:
        for s in cls["students"]:
            phone_map[s["id"]] = s.get("phone", "")

    for r in rows:
        r["parent_phone"] = phone_map.get(r["student_id"], "")

    return rows


def send_alert_for_student(student: Dict, cfg: Dict = None) -> Dict:
    """
    يُرسل تنبيه غياب متكرر لولي الأمر و/أو الإدارة.
    يُرجع {"parent": bool, "admin": bool, "errors": []}
    """
    if cfg is None:
        cfg = load_config()

    school     = cfg.get("school_name", "المدرسة")
    sid        = student["student_id"]
    sname      = student["student_name"]
    cls        = student["class_name"]
    count      = student["absence_count"]
    last_date  = student["last_date"]
    phone      = student.get("parent_phone", "")
    result     = {"parent": False, "admin": False, "errors": []}

    # ─ رسالة ولي الأمر
    if cfg.get("alert_notify_parent") and phone:
        tpl = cfg.get("alert_template_parent", "")
        try:
            msg = tpl.format(
                school_name=school, student_name=sname,
                class_name=cls, absence_count=count,
                last_date=last_date, parent_phone=phone)
            ok, status = send_whatsapp_message(phone, msg)
            result["parent"] = ok
            if not ok:
                result["errors"].append("ولي أمر {}: {}".format(sname, status))
        except Exception as e:
            result["errors"].append("خطأ رسالة ولي الأمر: {}".format(e))

    # ─ رسالة الإدارة
    if cfg.get("alert_notify_admin"):
        admin_phone = cfg.get("alert_admin_phone", "").strip()
        if admin_phone:
            tpl = cfg.get("alert_template_admin", "")
            try:
                msg = tpl.format(
                    school_name=school, student_name=sname,
                    class_name=cls, absence_count=count,
                    last_date=last_date, parent_phone=phone or "غير مسجّل")
                ok, status = send_whatsapp_message(admin_phone, msg)
                result["admin"] = ok
                if not ok:
                    result["errors"].append("الإدارة: {}".format(status))
            except Exception as e:
                result["errors"].append("خطأ رسالة الإدارة: {}".format(e))

    return result


def run_smart_alerts(month: str = None, log_cb=None) -> Dict:
    """
    يفحص كل الطلاب ويُرسل تنبيهات لمن تجاوز العتبة.
    يُرجع ملخص العملية.
    """
    cfg = load_config()
    if not cfg.get("alert_enabled", True):
        return {"skipped": True, "reason": "الإشعارات معطّلة"}

    if month is None:
        month = datetime.datetime.now().strftime("%Y-%m")

    threshold = cfg.get("alert_absence_threshold", 5)
    students  = get_students_exceeding_threshold(threshold, month)

    if log_cb:
        log_cb("فحص الإشعارات — {} طالب تجاوز {} أيام غياب".format(
            len(students), threshold))

    sent_p, sent_a, failed = 0, 0, 0
    details = []

    for s in students:
        res = send_alert_for_student(s, cfg)
        if res["parent"]: sent_p += 1
        if res["admin"]:  sent_a += 1
        if res["errors"]: failed += 1
        details.append({
            "student": s["student_name"],
            "class":   s["class_name"],
            "count":   s["absence_count"],
            "parent":  res["parent"],
            "admin":   res["admin"],
            "errors":  res["errors"],
        })
        if log_cb:
            status = "✅" if (res["parent"] or res["admin"]) else "❌"
            log_cb("{} {} — {} يوم غياب".format(
                status, s["student_name"], s["absence_count"]))

    return {
        "month": month, "threshold": threshold,
        "total_students": len(students),
        "sent_parent": sent_p, "sent_admin": sent_a,
        "failed": failed, "details": details,
    }


def schedule_daily_alerts(root_widget, run_hour: int = 14):
    """
    يجدول تشغيل الإشعارات الذكية يومياً في ساعة محددة (افتراضي 14:00).
    """
    def check_and_run():
        now = datetime.datetime.now()
        if now.weekday() in {4, 5}:  # الجمعة والسبت إجازة
            root_widget.after(3_600_000, check_and_run)
            return
        if now.hour == run_hour and now.minute < 5:
            print("[ALERTS] تشغيل الإشعارات الذكية اليومية...")
            threading.Thread(
                target=lambda: run_smart_alerts(
                    log_cb=lambda m: print("[ALERTS]", m)),
                daemon=True).start()
            # انتظر ساعة قبل الفحص التالي لتجنب التكرار
            root_widget.after(3_600_000, check_and_run)
        else:
            root_widget.after(300_000, check_and_run)  # فحص كل 5 دقائق

    root_widget.after(60_000, check_and_run)

# ═══════════════════════════════════════════════════════════════
# نافذة تسجيل الدخول
# ═══════════════════════════════════════════════════════════════
class LoginWindow:
    """نافذة تسجيل الدخول — تظهر عند بدء البرنامج."""

    def __init__(self, root, on_success):
        self.root       = root
        self.on_success = on_success
        self.attempts   = 0
        self._build()

    def _build(self):
        self.root.title("تسجيل الدخول — DarbStu")
        self.root.geometry("420x480")
        self.root.resizable(False, False)
        try: self.root.set_theme("arc")
        except Exception: pass

        # ─ رأس النافذة
        header = tk.Frame(self.root, bg="#1565C0", height=110)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="DarbStu", bg="#1565C0", fg="white",
                 font=("Tahoma", 26, "bold")).pack(pady=(22, 0))
        tk.Label(header, text="نظام إدارة الغياب والتأخر", bg="#1565C0",
                 fg="#BBDEFB", font=("Tahoma", 11)).pack()

        # ─ نموذج الدخول
        body = tk.Frame(self.root, bg="#F5F7FA", padx=40, pady=30)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="اسم المستخدم", bg="#F5F7FA",
                 font=("Tahoma", 11, "bold"), anchor="e").pack(fill="x")
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(body, textvariable=self.username_var,
                                   font=("Tahoma", 13), justify="right")
        username_entry.pack(fill="x", pady=(4, 16))
        username_entry.focus()

        tk.Label(body, text="كلمة المرور", bg="#F5F7FA",
                 font=("Tahoma", 11, "bold"), anchor="e").pack(fill="x")
        self.password_var = tk.StringVar()
        self.pw_entry = ttk.Entry(body, textvariable=self.password_var,
                                   font=("Tahoma", 13), show="●", justify="right")
        self.pw_entry.pack(fill="x", pady=(4, 6))

        # إظهار/إخفاء كلمة المرور
        self.show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="إظهار كلمة المرور",
                        variable=self.show_pw,
                        command=self._toggle_pw).pack(anchor="e")

        self.error_lbl = tk.Label(body, text="", bg="#F5F7FA",
                                   fg="#C62828", font=("Tahoma", 10))
        self.error_lbl.pack(pady=(8, 0))

        login_btn = tk.Button(
            body, text="تسجيل الدخول", bg="#1565C0", fg="white",
            font=("Tahoma", 13, "bold"), relief="flat",
            cursor="hand2", pady=10,
            command=self._do_login
        )
        login_btn.pack(fill="x", pady=(16, 0))

        # ربط Enter
        self.root.bind("<Return>", lambda e: self._do_login())

    def _toggle_pw(self):
        self.pw_entry.config(show="" if self.show_pw.get() else "●")

    def _do_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()

        if not username or not password:
            self.error_lbl.config(text="⚠️ الرجاء إدخال اسم المستخدم وكلمة المرور")
            return

        user = authenticate(username, password)

        if user:
            # تحديث المستخدم الحالي
            CURRENT_USER["username"] = user["username"]
            CURRENT_USER["role"]     = user["role"]
            CURRENT_USER["label"]    = ROLES.get(user["role"], {}).get("label", user["role"])
            CURRENT_USER["name"]     = user.get("full_name", user["username"])
            self.root.unbind("<Return>")
            self.on_success()
        else:
            self.attempts += 1
            if self.attempts >= 5:
                self.error_lbl.config(
                    text="⛔ تم إيقاف الحساب مؤقتاً — أعد تشغيل البرنامج")
                self.pw_entry.config(state="disabled")
            else:
                remaining = 5 - self.attempts
                self.error_lbl.config(
                    text=f"❌ اسم المستخدم أو كلمة المرور غير صحيحة ({remaining} محاولات متبقية)")
            self.password_var.set("")
            self.pw_entry.focus()


class AppGUI:
    def __init__(self, root, public_url=None):
        # 1. تعيين المتغيرات الأساسية أولاً
        self.root = root
        self.root.title(APP_TITLE)
        self.public_url = public_url
        
        self.scheduler_running = False
        self.scheduler_timers = []

        try:
            # مسار الأيقونة (يجب أن يكون ملف .ico)
            # icon_path = 'icon.ico' 
            # self.root.iconbitmap(icon_path)
            pass # تم تعطيله مؤقتاً
        except Exception as e:
            print(f"Could not load icon: {e}")

        self.store = load_students()
        self.ip = local_ip()
        # عرض الدور في عنوان النافذة
        role_label = CURRENT_USER.get("label","")
        user_name  = CURRENT_USER.get("name", CURRENT_USER.get("username",""))
        role_color = ROLES.get(CURRENT_USER.get("role","admin"),{}).get("color","#1565C0")
        root.title(f"DarbStu — {user_name} ({role_label})")
        self.cfg = load_config()

        # ─── كل التبويبات المتاحة في البرنامج ──────────────────────
        all_tabs = {
            "لوحة المراقبة":        "_build_dashboard_tab",
            "روابط الفصول":         "_build_links_tab",
            "التأخر":               "_build_tardiness_tab",
            "الأعذار":              "_build_excuses_tab",
            "المراقبة الحية":       "_build_live_monitor_tab",
            "السجلات / التصدير":    "_build_logs_tab",
            "إدارة الغياب":         "_build_absence_management_tab",
            "التقارير / الطباعة":   "_build_reports_tab",
            "تصدير نور":            "_build_noor_export_tab",
            "الإشعارات الذكية":     "_build_alerts_tab",
            "إرسال رسائل الغياب":   "_build_messages_tab",
            "رسائل التأخر":         "_build_tardiness_messages_tab",
            "مستلمو التأخر":        "_build_tardiness_recipients_tab",
            "جدولة الروابط":        "_build_schedule_tab",
            "إدارة الطلاب":         "_build_student_management_tab",
            "إضافة طالب":           "_build_add_student_tab",
            "إدارة الفصول":         "_build_class_naming_tab",
            "إدارة أرقام الجوالات": "_build_phones_tab",
            "إعدادات المدرسة":      "_build_school_settings_tab",
            "المستخدمون":           "_build_users_tab",
            "النسخ الاحتياطية":     "_build_backup_tab",
        }

        # مجموعات القائمة الجانبية
        sidebar_groups = [
            ("⬤  يومي", [
                "لوحة المراقبة", "روابط الفصول", "التأخر",
                "الأعذار", "المراقبة الحية",
            ]),
            ("⬤  السجلات", [
                "السجلات / التصدير", "إدارة الغياب",
                "التقارير / الطباعة", "تصدير نور", "الإشعارات الذكية",
            ]),
            ("⬤  الرسائل", [
                "إرسال رسائل الغياب", "رسائل التأخر",
                "مستلمو التأخر", "جدولة الروابط",
            ]),
            ("⬤  البيانات", [
                "إدارة الطلاب", "إضافة طالب",
                "إدارة الفصول", "إدارة أرقام الجوالات",
            ]),
            ("⬤  الإعدادات", [
                "إعدادات المدرسة", "المستخدمون", "النسخ الاحتياطية",
            ]),
        ]

        # ─── فلترة التبويبات حسب صلاحيات المستخدم ───────────────
        username = CURRENT_USER.get("username", "admin")
        allowed  = get_user_allowed_tabs(username)

        if allowed is None:
            self.tabs_config = all_tabs
        else:
            self.tabs_config = {k: v for k, v in all_tabs.items() if k in allowed}
            if not self.tabs_config:
                self.tabs_config = {"لوحة المراقبة": "_build_dashboard_tab"}

        # ─── بناء الواجهة الجانبية ────────────────────────────────
        self._tabs_built   = set()
        self._tab_frames   = {}
        self._nav_buttons  = {}
        self._current_tab  = tk.StringVar()

        # الإطار الرئيسي: sidebar + content
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(fill="both", expand=True)

        # ── منطقة المحتوى ──
        self._content_area = tk.Frame(main_frame, bg="white")
        self._content_area.pack(side="left", fill="both", expand=True)

        # فاصل عمودي
        tk.Frame(main_frame, bg="#d0d0d0", width=1).pack(side="left", fill="y")

        # ── القائمة الجانبية ──
        sidebar_outer = tk.Frame(main_frame, bg="#f0f0f0", width=185)
        sidebar_outer.pack(side="left", fill="y")
        sidebar_outer.pack_propagate(False)

        sidebar_canvas = tk.Canvas(sidebar_outer, bg="#f0f0f0",
                                    highlightthickness=0, bd=0)
        sidebar_scroll = ttk.Scrollbar(sidebar_outer, orient="vertical",
                                        command=sidebar_canvas.yview)
        sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar_scroll.pack(side="right", fill="y")
        sidebar_canvas.pack(side="left", fill="both", expand=True)

        sidebar = tk.Frame(sidebar_canvas, bg="#f0f0f0")
        sidebar_win = sidebar_canvas.create_window((0, 0), window=sidebar,
                                                    anchor="nw")

        def _on_sidebar_configure(e):
            sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))
            sidebar_canvas.itemconfig(sidebar_win, width=sidebar_canvas.winfo_width())
        sidebar.bind("<Configure>", _on_sidebar_configure)

        # ── بناء عناصر القائمة ──
        for group_title, group_tabs in sidebar_groups:
            # تصفية حسب الصلاحيات
            visible = [t for t in group_tabs if t in self.tabs_config]
            if not visible:
                continue

            # عنوان المجموعة
            grp_lbl = tk.Label(sidebar, text=group_title,
                               bg="#f0f0f0", fg="#888888",
                               font=("Tahoma", 8, "bold"),
                               anchor="w", padx=10, pady=2)
            grp_lbl.pack(fill="x")

            for tab_name in visible:
                btn = tk.Label(sidebar, text=tab_name,
                               bg="#f0f0f0", fg="#333333",
                               font=("Tahoma", 10),
                               anchor="w", padx=14, pady=6,
                               cursor="hand2")
                btn.pack(fill="x")

                def _make_click(name):
                    def _click(e=None):
                        self._switch_tab(name)
                    return _click

                btn.bind("<Button-1>", _make_click(tab_name))
                btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#e0e8f0") if self._current_tab.get() != b.cget("text") else None)
                btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#f0f0f0") if self._current_tab.get() != b.cget("text") else None)
                self._nav_buttons[tab_name] = btn

            # فاصل بين المجموعات
            tk.Frame(sidebar, bg="#d8d8d8", height=1).pack(fill="x", padx=8, pady=2)

        # ── إنشاء frames للتبويبات (باستخدام place للتحكم الكامل) ──
        for tab_name, builder_name in self.tabs_config.items():
            frame_attr = builder_name.replace("_build_", "").replace("_tab", "") + "_frame"
            f = tk.Frame(self._content_area, bg="white")
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            f.place_forget()
            setattr(self, frame_attr, f)
            self._tab_frames[tab_name] = f

        self.add_student_frame = self._tab_frames.get("إضافة طالب",
                                  tk.Frame(self._content_area, bg="white"))

        # ── دالة التبديل بين التبويبات ──
        def _switch_tab(name):
            if name not in self._tab_frames:
                return

            # ── تجميد الرسم لمنع الوميض (Windows) ──
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 0, 0)  # WM_SETREDRAW OFF
            except Exception:
                hwnd = None

            # أوقف auto-refresh الجدول عند مغادرة تبويبه
            if hasattr(self, '_schedule_auto_refresh_active') and self._current_tab.get() == "جدولة الروابط":
                self._schedule_auto_refresh_active = False

            # أخفِ كل التبويبات
            for f in self._tab_frames.values():
                f.place_forget()

            # تحديث تمييز القائمة
            prev = self._current_tab.get()
            if prev and prev in self._nav_buttons:
                self._nav_buttons[prev].config(bg="#f0f0f0", fg="#333333",
                                                font=("Tahoma", 10))
            self._current_tab.set(name)
            if name in self._nav_buttons:
                self._nav_buttons[name].config(bg="#1565C0", fg="white",
                                                font=("Tahoma", 10, "bold"))

            # بناء التبويب عند أول فتح (Lazy Loading)
            builder_name = self.tabs_config.get(name)
            if builder_name and builder_name not in self._tabs_built:
                self._tabs_built.add(builder_name)
                getattr(self, builder_name)()
                if builder_name == "_build_dashboard_tab" and hasattr(self, "tree_dash"):
                    self.update_dashboard_metrics()
                    self.root.after(10000, self._dashboard_tick)

            # أظهر التبويب المطلوب
            self._tab_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)

            # أعد تشغيل auto-refresh الجدول عند العودة إليه
            if name == "جدولة الروابط" and hasattr(self, '_schedule_auto_refresh_active'):
                self._schedule_auto_refresh_active = True

            # ── استعادة الرسم بعد اكتمال البناء ──
            self.root.update_idletasks()
            try:
                import ctypes
                if hwnd:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 1, 0)  # WM_SETREDRAW ON
                    ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0085)  # RDW_INVALIDATE|RDW_ALLCHILDREN|RDW_UPDATENOW
            except Exception:
                pass

        self._switch_tab = _switch_tab
        self._main_notebook = None  # للتوافق مع الكود القديم

        # افتح أول تبويب
        first_tab = next(iter(self.tabs_config.keys()))
        _switch_tab(first_tab)

        # تحقق من التحديثات بعد 5 ثوان من بدء التشغيل
        main_frame.after(5000, lambda: check_for_updates(root, silent=True))

        self._build_menu(root)
        if hasattr(self, "tree_dash"):
            self.update_dashboard_metrics()
            self.root.after(10000, self._dashboard_tick)

    def _build_menu(self, root):
        m = tk.Menu(root); root.config(menu=m)
        filem = tk.Menu(m, tearoff=0); m.add_cascade(label="ملف", menu=filem)
        filem.add_command(label="إعادة استيراد الطلاب...", command=self.reimport_students)
        filem.add_command(label="إعادة استيراد المعلمين...", command=self.reimport_teachers)
        filem.add_separator()
        filem.add_command(label="إعدادات المدرسة...", command=self._open_school_settings_tab)
        filem.add_command(label="فتح ملف الإعدادات (JSON)...", command=self.open_config_json)
        filem.add_separator()
        filem.add_command(label=f"التحقق من التحديثات... (v{APP_VERSION})",
                          command=lambda: check_for_updates(self.root, silent=False))
        filem.add_separator()
        filem.add_command(label="خروج", command=self.root.destroy)

    def _build_dashboard_tab(self):
        style = ttk.Style(); style.theme_use("arc")
        style.configure("Card.TFrame",      background="#ffffff")
        style.configure("CardTitle.TLabel", background="#ffffff",
                        foreground="#6b7280", font=("Tahoma", 9, "bold"))
        style.configure("CardValue.TLabel", background="#ffffff",
                        font=("Tahoma", 22, "bold"))
        style.configure("Treeview",         rowheight=26, font=("Tahoma", 10))
        style.configure("Treeview.Heading", font=("Tahoma", 10, "bold"))

        # ─ شريط التحكم العلوي
        top_bar = ttk.Frame(self.dashboard_frame)
        top_bar.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top_bar, text="تاريخ اليوم:",
                  font=("Tahoma",10)).pack(side="right", padx=(0,6))
        self.dash_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(top_bar, textvariable=self.dash_date_var,
                  width=12).pack(side="right", padx=4)
        ttk.Button(top_bar, text="🔄 تحديث الآن",
                   command=self.update_dashboard_metrics).pack(side="right", padx=4)
        self.dash_week_lbl = ttk.Label(top_bar, text="",
                                        foreground="#5A6A7E", font=("Tahoma",9))
        self.dash_week_lbl.pack(side="left", padx=8)

        # ─ بطاقات الإحصاء (صف واحد)
        cards_row = ttk.Frame(self.dashboard_frame)
        cards_row.pack(fill="x", padx=10, pady=6)

        def make_card(parent, title, color, sub=""):
            fr = ttk.Frame(parent, style="Card.TFrame")
            fr.pack(side="right", padx=6, fill="x", expand=True,
                    ipadx=10, ipady=10)
            ttk.Label(fr, text=title,
                      style="CardTitle.TLabel").pack(anchor="w", padx=10, pady=(8,0))
            val = ttk.Label(fr, text="—", style="CardValue.TLabel",
                             foreground=color)
            val.pack(anchor="w", padx=10)
            sub_lbl = ttk.Label(fr, text=sub, background="#ffffff",
                                 foreground="#9CA3AF", font=("Tahoma",8))
            sub_lbl.pack(anchor="w", padx=10, pady=(0,8))
            return val, sub_lbl

        self.lbl_total,   self.lbl_total_sub   = make_card(cards_row, "إجمالي الطلاب",  "#3B82F6")
        self.lbl_present, self.lbl_present_sub  = make_card(cards_row, "الحضور اليوم",   "#10B981")
        self.lbl_absent,  self.lbl_absent_sub   = make_card(cards_row, "الغياب اليوم",   "#EF4444")
        self.lbl_tard,    self.lbl_tard_sub      = make_card(cards_row, "التأخر اليوم",   "#F59E0B")
        self.lbl_week,    self.lbl_week_sub      = make_card(cards_row, "غياب الأسبوع",   "#8B5CF6",
                                                              "مقارنة بالأسبوع الماضي")

        # ─ الجسم الرئيسي: جدول + رسوم بيانية
        body = ttk.Frame(self.dashboard_frame)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        # ── العمود الأيسر: جدول الفصول + أكثر الطلاب غياباً
        left = ttk.Frame(body); left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        left.rowconfigure(0, weight=2); left.rowconfigure(1, weight=1)

        # جدول الفصول
        cls_lf = ttk.LabelFrame(left, text=" 📋 الفصول — الحضور والغياب ", padding=4)
        cls_lf.grid(row=0, column=0, sticky="nsew", pady=(0,6))
        cols = ("class_id","class_name","total","present","absent","pct")
        self.tree_dash = ttk.Treeview(cls_lf, columns=cols, show="headings", height=9)
        for c, h, w in zip(cols,
            ["المعرّف","اسم الفصل","الإجمالي","🟢 حاضر","🔴 غائب","نسبة الغياب"],
            [80, 200, 80, 90, 90, 100]):
            self.tree_dash.heading(c, text=h)
            self.tree_dash.column(c, width=w, anchor="center")
        self.tree_dash.tag_configure("high",   background="#FFF0F0")
        self.tree_dash.tag_configure("normal", background="#F0FFF4")
        sb1 = ttk.Scrollbar(cls_lf, orient="vertical",
                             command=self.tree_dash.yview)
        self.tree_dash.configure(yscrollcommand=sb1.set)
        self.tree_dash.pack(side="left", fill="both", expand=True)
        sb1.pack(side="right", fill="y")

        # أكثر الطلاب غياباً
        top_lf = ttk.LabelFrame(left, text=" 🏆 أكثر الطلاب غياباً هذا الشهر ", padding=4)
        top_lf.grid(row=1, column=0, sticky="nsew")
        top_cols = ("name","class_name","days","last_date")
        self.tree_top_absent = ttk.Treeview(
            top_lf, columns=top_cols, show="headings", height=5)
        for c, h, w in zip(top_cols,
            ["اسم الطالب","الفصل","أيام الغياب","آخر غياب"],
            [200, 150, 90, 100]):
            self.tree_top_absent.heading(c, text=h)
            self.tree_top_absent.column(c, width=w, anchor="center")
        self.tree_top_absent.tag_configure("top1", background="#FFEBEE",
                                            foreground="#C62828")
        self.tree_top_absent.tag_configure("top3", background="#FFF8E1",
                                            foreground="#E65100")
        self.tree_top_absent.pack(fill="both", expand=True)

        # ── العمود الأيمن: الرسوم البيانية
        right = ttk.Frame(body); right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1); right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        # دائرة الحضور/الغياب
        pie_lf = ttk.LabelFrame(right, text=" نسبة الحضور/الغياب اليوم ", padding=4)
        pie_lf.grid(row=0, column=0, sticky="nsew", pady=(0,4))
        _ensure_matplotlib()
        self.fig_pie = Figure(figsize=(4, 2.5), dpi=90)
        self.ax_pie  = self.fig_pie.add_subplot(111)
        self.canvas_pie = FigureCanvasTkAgg(self.fig_pie, pie_lf)
        self.canvas_pie.get_tk_widget().pack(fill="both", expand=True)

        # مقارنة الأسبوعين
        week_lf = ttk.LabelFrame(right, text=" مقارنة هذا الأسبوع بالماضي ", padding=4)
        week_lf.grid(row=1, column=0, sticky="nsew", pady=(0,4))
        self.fig_week = Figure(figsize=(4, 2.3), dpi=90)
        self.ax_week  = self.fig_week.add_subplot(111)
        self.canvas_week = FigureCanvasTkAgg(self.fig_week, week_lf)
        self.canvas_week.get_tk_widget().pack(fill="both", expand=True)

        # أكثر الأيام غياباً
        dow_lf = ttk.LabelFrame(right, text=" أكثر أيام الأسبوع غياباً ", padding=4)
        dow_lf.grid(row=2, column=0, sticky="nsew")
        self.fig_dow = Figure(figsize=(4, 2.3), dpi=90)
        self.ax_dow  = self.fig_dow.add_subplot(111)
        self.canvas_dow = FigureCanvasTkAgg(self.fig_dow, dow_lf)
        self.canvas_dow.get_tk_widget().pack(fill="both", expand=True)


    def _dashboard_tick(self):
        self.update_dashboard_metrics(); self.root.after(10000, self._dashboard_tick)

    def update_dashboard_metrics(self):
        date_str = self.dash_date_var.get().strip() or now_riyadh_date()
        try:
            metrics = compute_today_metrics(date_str)
        except Exception as e:
            messagebox.showerror("خطأ", str(e)); return

        t = metrics["totals"]
        pct_absent = round(t["absent"] / max(t["students"],1) * 100, 1)

        # ─ بطاقات الإحصاء
        self.lbl_total.config(text=str(t["students"]))
        self.lbl_present.config(text=str(t["present"]))
        self.lbl_absent.config(text=str(t["absent"]))
        if hasattr(self,"lbl_absent_sub"):
            self.lbl_absent_sub.config(text="{}% من الإجمالي".format(pct_absent))

        # التأخر اليوم
        tard_today = len(query_tardiness(date_filter=date_str))
        if hasattr(self,"lbl_tard"):
            self.lbl_tard.config(text=str(tard_today))

        # مقارنة الأسبوع
        try:
            wk = get_week_comparison()
            if hasattr(self,"lbl_week"):
                self.lbl_week.config(text=str(wk["this_total"]))
            if hasattr(self,"lbl_week_sub"):
                arrow = "▲" if wk["change"]>0 else ("▼" if wk["change"]<0 else "=")
                color  = "#EF4444" if wk["change"]>0 else "#10B981"
                self.lbl_week_sub.config(
                    text="{} {}% عن الأسبوع الماضي".format(
                        arrow, abs(wk["pct"])),
                    foreground=color)
            if hasattr(self,"dash_week_lbl"):
                self.dash_week_lbl.config(
                    text="الأسبوع الماضي: {} غياب".format(wk["last_total"]))
        except Exception as e:
            print("[DASH-WEEK]", e)

        # ─ جدول الفصول
        for i in self.tree_dash.get_children():
            self.tree_dash.delete(i)
        for r in metrics["by_class"]:
            pct = round(r["absent"]/max(r["total"],1)*100, 0)
            tag = "high" if pct >= 20 else "normal"
            self.tree_dash.insert("", "end", tags=(tag,),
                values=(r["class_id"], r["class_name"],
                        r["total"],
                        "🟢 {}".format(r["present"]),
                        "🔴 {}".format(r["absent"]),
                        "{}%".format(int(pct))))

        # ─ أكثر الطلاب غياباً
        if hasattr(self,"tree_top_absent"):
            for i in self.tree_top_absent.get_children():
                self.tree_top_absent.delete(i)
            month = date_str[:7]
            for idx, s in enumerate(get_top_absent_students(month, limit=8)):
                tag = "top1" if idx==0 else ("top3" if idx<3 else "")
                self.tree_top_absent.insert("","end", tags=(tag,),
                    values=(s["name"], s["class_name"],
                            "{} يوم".format(s["days"]), s["last_date"]))

        # ─ رسم الدائرة
        try:
            self.ax_pie.clear()
            sizes  = [t["present"], t["absent"]]
            if sum(sizes) > 0:
                self.ax_pie.pie(
                    sizes,
                    labels=[ar("الحضور"), ar("الغياب")],
                    autopct="%1.1f%%", startangle=90,
                    colors=["#10B981","#EF4444"])
            self.ax_pie.set_title(ar("الحضور/الغياب اليوم"), fontsize=9)
            self.canvas_pie.draw()
        except Exception as e:
            print("[DASH-PIE]", e)

        # ─ رسم مقارنة الأسبوعين
        try:
            self.ax_week.clear()
            wk = get_week_comparison()
            day_names_short = ["أحد","إثنين","ثلاث","أربع","خميس"]
            x = range(5)
            this_vals = [wk["this_daily"].get(
                (datetime.date.fromisoformat(wk["this_week_start"]) +
                 datetime.timedelta(days=i)).isoformat(), 0) for i in range(5)]
            last_vals = [wk["last_daily"].get(
                (datetime.date.fromisoformat(wk["last_week_start"]) +
                 datetime.timedelta(days=i)).isoformat(), 0) for i in range(5)]
            w_bar = 0.35
            self.ax_week.bar([i-w_bar/2 for i in x], last_vals,
                              w_bar, label=ar("الأسبوع الماضي"), color="#93C5FD")
            self.ax_week.bar([i+w_bar/2 for i in x], this_vals,
                              w_bar, label=ar("هذا الأسبوع"), color="#3B82F6")
            self.ax_week.set_xticks(list(x))
            self.ax_week.set_xticklabels([ar(d) for d in day_names_short], fontsize=7)
            self.ax_week.legend(fontsize=7)
            self.ax_week.set_title(ar("مقارنة الأسبوعين"), fontsize=9)
            self.canvas_week.draw()
        except Exception as e:
            print("[DASH-WEEK-CHART]", e)

        # ─ رسم أكثر الأيام غياباً
        try:
            self.ax_dow.clear()
            dow_data = get_absence_by_day_of_week()
            days_ar   = list(dow_data.keys())
            vals      = list(dow_data.values())
            bars = self.ax_dow.bar(
                [ar(d) for d in days_ar], vals,
                color=["#EF4444" if v==max(vals) else "#FCA5A5" for v in vals])
            self.ax_dow.set_title(ar("متوسط الغياب حسب اليوم"), fontsize=9)
            for bar_r, v in zip(bars, vals):
                if v > 0:
                    self.ax_dow.text(bar_r.get_x()+bar_r.get_width()/2,
                                      bar_r.get_height(),
                                      "{:.0f}".format(v),
                                      ha="center", va="bottom", fontsize=7)
            self.canvas_dow.draw()
        except Exception as e:
            print("[DASH-DOW]", e)

    def _build_links_tab(self):
        if self.public_url:
            ttk.Label(self.links_frame, text=f"الرابط العام: {self.public_url}", foreground="blue", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0,4))
            ttk.Label(self.links_frame, text="امسح الـ QR Code للوصول من الإنترنت.").pack(anchor="w", pady=(0,8))
        else:
            ttk.Label(self.links_frame, text=f"الخادم المحلي: http://{self.ip}:{PORT} (يعمل على نفس الشبكة فقط )").pack(anchor="w", pady=(0,8))
        main_container = ttk.Frame(self.links_frame)
        main_container.pack(fill="both", expand=True)
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side="left", fill="both", expand=True, padx=5)
        cols = ("class_id", "class_name", "students", "link")
        tree = ttk.Treeview(left_frame, columns=cols, show="headings", height=8)
        for c, t, w in zip(cols, ["المعرّف","اسم الفصل","عدد الطلاب","الرابط"], [80, 180, 80, 300]):
            tree.heading(c, text=t); tree.column(c, width=w, anchor="center")
        tree.pack(fill="x", expand=True); self.tree_links = tree
        self.qr_canvas = tk.Label(left_frame); self.qr_canvas.pack(pady=8, anchor="center")
        send_controls_frame = ttk.LabelFrame(main_container, text=" إرسال الرابط إلى معلم ", padding=10)
        send_controls_frame.pack(side="right", fill="y", padx=5, anchor="n")
        ttk.Label(send_controls_frame, text="اختر المعلم:").pack(anchor="e")
        self.teacher_var = tk.StringVar()
        self.teacher_combo = ttk.Combobox(send_controls_frame, textvariable=self.teacher_var, state="readonly", width=30)
        self.teacher_combo.pack(anchor="e", pady=5, fill="x")
        self.send_link_button = ttk.Button(send_controls_frame, text="إرسال الرابط المحدد عبر واتساب", command=self.on_send_link_to_teacher, state="disabled")
        self.send_link_button.pack(anchor="e", pady=10)
        self.tree_links.bind("<<TreeviewSelect>>", self.on_class_select)
        self.teacher_combo.bind("<<ComboboxSelected>>", self.on_teacher_select)
        self._refresh_links_and_teachers()

    def _refresh_links_and_teachers(self):
        if not hasattr(self, "tree_links") or not self.tree_links.winfo_exists():
            return
        for i in self.tree_links.get_children(): self.tree_links.delete(i)
        base_url = self.public_url or f"http://{self.ip}:{PORT}"
        for c in self.store["list"]:
            link = f"{base_url}/c/{c['id']}"
            self.tree_links.insert("", "end", values=(c["id"], c["name"], len(c["students"] ), link))
        self.teachers_data = load_teachers()
        teacher_names = [t["اسم المعلم"] for t in self.teachers_data.get("teachers", [])]
        self.teacher_combo['values'] = teacher_names
        self.teacher_var.set("")
        self.send_link_button.config(state="disabled")
        self.qr_img = None
        self.qr_canvas.config(image=None)

    def on_class_select(self, event=None):
        if not (sel := self.tree_links.selection()): return
        link = self.tree_links.item(sel[0])["values"][3]
        img = qrcode.make(link).resize((220,220)); self.qr_img = ImageTk.PhotoImage(img)
        self.qr_canvas.config(image=self.qr_img)
        if self.teacher_var.get():
            self.send_link_button.config(state="normal")

    def on_teacher_select(self, event=None):
        if self.tree_links.selection():
            self.send_link_button.config(state="normal")

    def on_send_link_to_teacher(self):
        if not (sel := self.tree_links.selection()):
            messagebox.showwarning("تنبيه", "الرجاء تحديد فصل من القائمة أولاً.")
            return
        if not (teacher_name := self.teacher_var.get()):
            messagebox.showwarning("تنبيه", "الرجاء اختيار معلم من القائمة.")
            return
        class_name, link = self.tree_links.item(sel[0])["values"][1], self.tree_links.item(sel[0])["values"][3]
        teacher = next((t for t in self.teachers_data.get("teachers", []) if t["اسم المعلم"] == teacher_name), None)
        if not teacher:
            messagebox.showerror("خطأ", "لم يتم العثور على بيانات المعلم المحدد.")
            return
        teacher_phone = teacher.get("رقم الجوال")
        if not teacher_phone:
            messagebox.showwarning("تنبيه", f"لا يوجد رقم جوال مسجل للمعلم '{teacher_name}'.")
            return
        if not messagebox.askyesno("تأكيد الإرسال", f"هل أنت متأكد من إرسال رابط فصل '{class_name}' إلى المعلم '{teacher_name}'؟"):
            return
        self.send_link_button.config(state="disabled"); self.root.update_idletasks()
        # Note: send_link_to_teacher is not defined in the provided code, assuming it's a wrapper for send_whatsapp_message
        message_body = f"السلام عليكم أ. {teacher_name},\nإليك رابط تسجيل غياب فصل: {class_name}\n{link}"
        success, message = send_whatsapp_message(teacher_phone, message_body)
        messagebox.showinfo("نتيجة الإرسال", message)
        self.send_link_button.config(state="normal")

    def _build_logs_tab(self):
        top = ttk.Frame(self.logs_frame); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="تاريخ:").pack(side="right")
        self.date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(top, textvariable=self.date_var, width=12).pack(side="right", padx=5)
        ttk.Label(top, text="فصل:").pack(side="right")
        self.class_var = tk.StringVar()
        class_ids = ["(الكل)"] + [c["id"] for c in self.store["list"]]
        cb = ttk.Combobox(top, textvariable=self.class_var, values=class_ids, width=12, state="readonly"); cb.current(0); cb.pack(side="right", padx=5)
        ttk.Button(top, text="تحديث", command=self.refresh_logs).pack(side="right", padx=5)
        ttk.Button(top, text="تقرير رسائل اليوم", command=self._open_today_messages_report).pack(side="left", padx=5)

        cols = ("date","class_id","class_name","student_id","student_name","teacher_name","period","created_at")
        tree = ttk.Treeview(self.logs_frame, columns=cols, show="headings", height=12)
        for c,h,w in zip(cols, ["التاريخ","المعرّف","الفصل","رقم الطالب","اسم الطالب","المعلم","الحصة","وقت التسجيل"], [90,90,200,120,240,140,60,170]):
            tree.heading(c, text=h); tree.column(c, width=w, anchor="center")
        tree.pack(fill="both", expand=True); self.tree_logs = tree; self.refresh_logs()
    
    def refresh_logs(self):
        try:
            date_f = self.date_var.get().strip() if hasattr(self, "date_var") else now_riyadh_date()
            class_id = self.class_var.get() if hasattr(self, "class_var") else None
            if class_id == "(الكل)":
                class_id = None

            rows = _apply_class_name_fix(query_absences(date_f or None, class_id))

            if not hasattr(self, "tree_logs"):
                return

            for i in self.tree_logs.get_children():
                self.tree_logs.delete(i)

            for r in rows:
                self.tree_logs.insert(
                    "", "end",
                    values=(
                        r.get("date", ""),
                        r.get("class_id", ""),
                        r.get("class_name", ""),
                        r.get("student_id", ""),
                        r.get("student_name", ""),
                        r.get("teacher_name", ""),
                        r.get("period", ""),
                        r.get("created_at", "")
                    )
                )
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر تحديث السجلات:\n{e}")

    def _build_absence_management_tab(self):
        frame = self.absence_management_frame
        controls_frame = ttk.LabelFrame(frame, text=" بحث وتعديل ", padding=10)
        controls_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(controls_frame, text="اسم الطالب أو رقمه:").pack(side="right", padx=(0, 5))
        self.absence_search_var = tk.StringVar()
        ttk.Entry(controls_frame, textvariable=self.absence_search_var, width=25).pack(side="right", padx=5)
        ttk.Label(controls_frame, text="في تاريخ:").pack(side="right", padx=(10, 5))
        _ensure_tkcalendar()
        self.absence_date_entry = DateEntry(controls_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd', locale='ar_SA')
        self.absence_date_entry.pack(side="right", padx=5)
        search_button = ttk.Button(controls_frame, text="🔍 بحث", command=self.search_absences_for_student)
        search_button.pack(side="right", padx=10)
        self.delete_absence_button = ttk.Button(controls_frame, text="🗑️ حذف الغياب المحدد", state="disabled", command=self.delete_selected_absence)
        self.delete_absence_button.pack(side="left", padx=10)

        results_frame = ttk.Frame(frame); results_frame.pack(fill="both", expand=True, padx=10, pady=5)
        cols = ("record_id", "student_id", "student_name", "class_name", "period", "teacher_name")
        self.tree_absences = ttk.Treeview(results_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["ID", "رقم الطالب", "اسم الطالب", "الفصل", "الحصة", "مسجل بواسطة"], [60, 100, 250, 180, 60, 150]):
            self.tree_absences.heading(col, text=header); self.tree_absences.column(col, width=w, anchor="center")
        self.tree_absences.pack(fill="both", expand=True)
        self.tree_absences.bind("<<TreeviewSelect>>", self.on_absence_record_select)

    def on_absence_record_select(self, event=None):
        if self.tree_absences.selection():
            self.delete_absence_button.config(state="normal")
        else:
            self.delete_absence_button.config(state="disabled")

    def search_absences_for_student(self):
        for item in self.tree_absences.get_children():
            self.tree_absences.delete(item)
        query = self.absence_search_var.get().strip()
        date_filter = self.absence_date_entry.get()
        if not query:
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم أو رقم الطالب للبحث.")
            return
        if not date_filter:
            messagebox.showwarning("تنبيه", "الرجاء تحديد التاريخ للبحث.")
            return
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        sql_query = "SELECT id, student_id, student_name, class_name, period, teacher_name FROM absences WHERE date = ? AND (student_name LIKE ? OR student_id = ?)"
        params = (date_filter, f'%{query}%', query)
        cur.execute(sql_query, params); rows = cur.fetchall(); con.close()
        if not rows:
            messagebox.showinfo("لا توجد نتائج", f"لم يتم العثور على أي سجلات غياب للطالب '{query}' في تاريخ {date_filter}.")
        else:
            for row in rows:
                self.tree_absences.insert("", "end", values=(row['id'], row['student_id'], row['student_name'], row['class_name'], row['period'], row['teacher_name']))
        self.delete_absence_button.config(state="disabled")

    def delete_selected_absence(self):
        if not (selected_items := self.tree_absences.selection()):
            messagebox.showwarning("تنبيه", "الرجاء تحديد سجل الغياب الذي تريد حذفه أولاً.")
            return
        item_id = selected_items[0]
        record_values = self.tree_absences.item(item_id, "values")
        db_id = record_values[0]; student_name = record_values[2]; class_name = record_values[3]; period = record_values[4]
        confirmation_message = (f"هل أنت متأكد من حذف سجل الغياب التالي؟\n\nالطالب: {student_name}\nالفصل: {class_name}\nالحصة: {period}\n\nهذا الإجراء سيحول الطالب إلى 'حاضر' في هذه الحصة ولا يمكن التراجع عنه.")
        if not messagebox.askyesno("تأكيد الحذف", confirmation_message): return
        try:
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM absences WHERE id = ?", (db_id,)); con.commit(); con.close()
            self.tree_absences.delete(item_id)
            messagebox.showinfo("تم الحذف", "تم حذف سجل الغياب بنجاح.")
            self.update_dashboard_metrics()
            self.delete_absence_button.config(state="disabled")
        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ أثناء محاولة الحذف من قاعدة البيانات:\n{e}")

    def _build_reports_tab(self):
        controls_frame = ttk.LabelFrame(self.reports_frame, text="خيارات التقرير", padding=10)
        controls_frame.pack(fill="x", padx=5, pady=5)
        self.report_type_var = tk.StringVar(value="daily")
        types_frame = ttk.Frame(controls_frame); types_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(types_frame, text="نوع التقرير:").pack(side="right", padx=(0, 10))
        report_types = [("يومي", "daily"), ("أسبوعي", "weekly"), ("شهري", "monthly"), ("طالب محدد", "student")]
        for text, value in report_types:
            ttk.Radiobutton(types_frame, text=text, variable=self.report_type_var, value=value, command=self._update_report_controls).pack(side="right", padx=5)
        self.inputs_frame = ttk.Frame(controls_frame); self.inputs_frame.pack(fill="x", pady=5)
        self.report_date_label = ttk.Label(self.inputs_frame, text="تاريخ:")
        self.report_date_var = tk.StringVar(value=now_riyadh_date())
        self.report_date_entry = ttk.Entry(self.inputs_frame, textvariable=self.report_date_var, width=15)
        self.report_class_label = ttk.Label(self.inputs_frame, text="الفصل:")
        self.report_class_var = tk.StringVar()
        class_ids = ["(كل الفصول)"] + [c["id"] for c in self.store["list"]]
        self.report_class_combo = ttk.Combobox(self.inputs_frame, textvariable=self.report_class_var, values=class_ids, width=15, state="readonly")
        self.report_class_combo.current(0)
        self.report_student_label = ttk.Label(self.inputs_frame, text="ابحث عن الطالب (بالاسم أو الرقم):")
        self.report_student_var = tk.StringVar()
        self.report_student_entry = ttk.Entry(self.inputs_frame, textvariable=self.report_student_var, width=30)
        
        buttons_frame = ttk.Frame(controls_frame)
        buttons_frame.pack(pady=5)
        ttk.Button(buttons_frame, text="إنشاء التقرير", command=self.on_generate_report).pack(side="right", padx=5)
        self.print_button = ttk.Button(buttons_frame, text="طباعة التقرير الحالي", command=self.on_print_report, state="disabled")
        self.print_button.pack(side="right", padx=5)
        
        ttk.Button(buttons_frame, text="📤 تصدير لـ نور", command=self.export_to_noor_from_ui).pack(side="right", padx=5)

        view_frame = ttk.LabelFrame(self.reports_frame, text="عرض التقرير", padding=10)
        view_frame.pack(fill="both", expand=True, padx=5, pady=5)
        _ensure_tkinterweb()
        self.report_browser = HtmlFrame(view_frame, horizontal_scrollbar="auto")
        self.report_browser.pack(fill="both", expand=True)
        self.report_browser.load_html("<html><body style='font-family:sans-serif; text-align:center; color:#888;'><h1>جاهز لإنشاء التقارير</h1><p>اختر نوع التقرير من الأعلى ثم اضغط على 'إنشاء التقرير'</p></body></html>")
        self._update_report_controls()

    def _update_report_controls(self):
        for widget in [self.report_date_label, self.report_date_entry, self.report_class_label, self.report_class_combo, self.report_student_label, self.report_student_entry]:
            widget.pack_forget()
        report_type = self.report_type_var.get()
        if report_type in ["daily", "weekly", "monthly"]:
            self.report_date_label.pack(side="right", padx=(0, 5))
            self.report_date_entry.pack(side="right", padx=5)
            self.report_class_label.pack(side="right", padx=(15, 5))
            self.report_class_combo.pack(side="right", padx=5)
            if report_type == "daily": self.report_date_label.config(text="تاريخ اليوم:")
            elif report_type == "weekly": self.report_date_label.config(text="أي يوم في الأسبوع:")
            elif report_type == "monthly": self.report_date_label.config(text="أي يوم في الشهر:")
        elif report_type == "student":
            self.report_student_label.pack(side="right", padx=(0, 5))
            self.report_student_entry.pack(side="right", padx=5)

    def on_generate_report(self):
        report_type = self.report_type_var.get()
        html_content = ""
        self.current_report_html = "" 
        try:
            self.root.config(cursor="wait"); self.root.update_idletasks()
            class_id_filter = self.report_class_var.get()
            if class_id_filter == "(كل الفصول)": class_id_filter = None
            if report_type == "student":
                search_query = self.report_student_var.get().strip()
                if not search_query:
                    messagebox.showwarning("بيانات ناقصة", "الرجاء إدخال اسم أو رقم الطالب للبحث عنه.")
                    return
                found_student = None
                for c in self.store['list']:
                    for s in c['students']:
                        if search_query.lower() in s['name'].lower() or search_query == s['id']:
                            found_student = s
                            break
                    if found_student: break
                
                # --- START: هذا هو السطر الذي تم إصلاحه ---
                if not found_student:
                    messagebox.showerror("غير موجود", f"لم يتم العثور على طالب يطابق البحث: '{search_query}'")
                    return
                # --- END: هذا هو السطر الذي تم إصلاحه ---

                if not messagebox.askyesno("تأكيد", f"هل تريد إنشاء تقرير للطالب:\n\nالاسم: {found_student['name']}\nالرقم: {found_student['id']}"):
                    return
                html_content = generate_student_report(found_student['id'])
            else:
                date_str = self.report_date_var.get()
                if not date_str:
                    messagebox.showerror("خطأ", "الرجاء إدخال تاريخ صالح.")
                    return
                if report_type == "daily":
                    html_content = generate_daily_report(date_str, class_id_filter)
                elif report_type == "weekly":
                    html_content = generate_weekly_report(date_str, class_id_filter)
                elif report_type == "monthly":
                    html_content = generate_monthly_report(date_str, class_id_filter)
            
            if html_content and "لا توجد بيانات" not in html_content:
                self.current_report_html = html_content
                self.report_browser.load_html(html_content)
                self.print_button.config(state="normal")
            else:
                self.current_report_html = ""
                self.report_browser.load_html(html_content or "<html><body><h2>لم يتم إنشاء التقرير أو لا توجد بيانات.</h2></body></html>")
                self.print_button.config(state="disabled")
        except Exception as e:
            messagebox.showerror("خطأ فادح", f"حدث خطأ أثناء إنشاء التقرير:\n{e}")
            self.print_button.config(state="disabled")
        finally:
            self.root.config(cursor="")


    def on_print_report(self):
        if not hasattr(self, 'current_report_html') or not self.current_report_html:
            messagebox.showwarning("لا يوجد تقرير", "الرجاء إنشاء تقرير أولاً قبل محاولة الطباعة.")
            return
        
        try:
            temp_report_path = os.path.join(DATA_DIR, "temp_report_to_print.html")
            with open(temp_report_path, "w", encoding="utf-8") as f:
                f.write(self.current_report_html)
            webbrowser.open(f"file://{os.path.abspath(temp_report_path)}")
            messagebox.showinfo("جاهز للطباعة", "تم فتح التقرير في متصفحك. الرجاء استخدام أمر الطباعة من هناك (Ctrl+P).")
        except Exception as e:
            messagebox.showerror("خطأ في تجهيز الطباعة", f"لم يتمكن من إنشاء ملف الطباعة المؤقت:\n{e}")

    def export_to_noor_from_ui(self):
        date_str = self.report_date_var.get().strip()
        if not date_str:
            messagebox.showerror("خطأ", "الرجاء تحديد تاريخ صالح.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="حفظ ملف نور"
        )
        if file_path:
            export_to_noor_excel(date_str, file_path)

    def _build_phones_tab(self):
        top_frame = ttk.Frame(self.phones_frame); top_frame.pack(fill="x", pady=(8, 8))
        ttk.Label(top_frame, text="بحث:").pack(side="left", padx=(0, 5)); self.search_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.search_var, width=30).pack(side="left", padx=5)
        ttk.Button(top_frame, text="بحث", command=self.search_students).pack(side="left", padx=5)
        ttk.Button(top_frame, text="مسح", command=self.clear_search).pack(side="left", padx=5)
        ttk.Button(top_frame, text="حفظ التعديلات", command=self.save_phone_edits).pack(side="right", padx=5)
        cols = ("student_id", "student_name", "phone", "class_name")
        self.tree_phones = ttk.Treeview(self.phones_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["رقم الطالب", "اسم الطالب", "رقم الجوال", "الفصل"], [120, 250, 180, 200]):
            self.tree_phones.heading(col, text=header); self.tree_phones.column(col, width=w, anchor="center")
        self.tree_phones.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_phones.bind("<Double-1>", self.on_double_click_phone)
        self.load_students_to_treeview()

    def load_students_to_treeview(self):
        for item in self.tree_phones.get_children(): self.tree_phones.delete(item)
        self.all_students_data = [{"student_id": s.get("id", ""), "student_name": s.get("name", ""), "phone": s.get("phone", ""), "class_name": c["name"]} for c in self.store["list"] for s in c["students"]]
        self.display_students(self.all_students_data)

    def display_students(self, students_list):
        for student in students_list: self.tree_phones.insert("", "end", values=(student["student_id"], student["student_name"], student["phone"], student["class_name"]))
        self.highlight_phone_numbers()

    def highlight_phone_numbers(self):
        all_phones = [self.tree_phones.item(i, "values")[2].strip() for i in self.tree_phones.get_children() if self.tree_phones.item(i, "values")[2].strip()]
        phone_counts = {p: all_phones.count(p) for p in all_phones}
        for item in self.tree_phones.get_children():
            phone = self.tree_phones.item(item, "values")[2].strip()
            tags = ()
            if not phone: pass
            elif not (phone.startswith(('+', '00', '966')) and phone.replace('+', '').isdigit()): tags = ("invalid",)
            elif phone_counts.get(phone, 0) > 1: tags = ("duplicate",)
            self.tree_phones.item(item, tags=tags)
        self.tree_phones.tag_configure("invalid", background="#ffebee", foreground="#c62828")
        self.tree_phones.tag_configure("duplicate", background="#e8f5e9", foreground="#2e7d32")

    def on_double_click_phone(self, event):
        if self.tree_phones.identify("region", event.x, event.y) != "cell" or self.tree_phones.identify_column(event.x) != "#3": return
        if not (item_id := self.tree_phones.focus()): return
        current_values = list(self.tree_phones.item(item_id, "values"))
        entry = ttk.Entry(self.tree_phones); entry.insert(0, current_values[2]); entry.select_range(0, tk.END); entry.focus()
        if not (bbox := self.tree_phones.bbox(item_id, column="#3")): return
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        def save_edit(e=None):
            current_values[2] = entry.get().strip(); self.tree_phones.item(item_id, values=current_values); entry.destroy(); self.highlight_phone_numbers()
        entry.bind("<Return>", save_edit); entry.bind("<FocusOut>", save_edit); entry.bind("<Escape>", lambda e: entry.destroy())

    def save_phone_edits(self):
        updated_phones = {self.tree_phones.item(i, "values")[0]: self.tree_phones.item(i, "values")[2] for i in self.tree_phones.get_children()}
        for c in self.store["list"]:
            for s in c["students"]:
                if (sid := s.get("id")) in updated_phones: s["phone"] = updated_phones[sid]
        with open(STUDENTS_JSON, "w", encoding="utf-8") as f: json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("تم الحفظ", "تم حفظ أرقام الجوالات بنجاح."); self.load_students_to_treeview()

    def search_students(self):
        query = self.search_var.get().strip().lower()
        filtered = [s for s in self.all_students_data if not query or query in str(s["student_id"]).lower() or query in str(s["student_name"]).lower()]
        for item in self.tree_phones.get_children(): self.tree_phones.delete(item)
        self.display_students(filtered)

    def clear_search(self): self.search_var.set(""); self.search_students()

    def _build_messages_tab(self):
        self.msg_template_var = tk.StringVar(value=get_message_template())
        self.msg_date_var = tk.StringVar(value=now_riyadh_date())
        self.msg_groups = {}
        self.msg_vars = {}
        self.class_select_vars = {}
        self.global_select_var = tk.BooleanVar(value=False)

        top = ttk.Frame(self.messages_frame); top.pack(fill="x", pady=(6,6))
        ttk.Label(top, text="تاريخ الغياب:").pack(side="right", padx=(0,5))
        ttk.Entry(top, textvariable=self.msg_date_var, width=12).pack(side="right", padx=5)
        ttk.Button(top, text="تحميل الغياب", command=self._msg_load_groups).pack(side="right", padx=5)

        chk_all = ttk.Checkbutton(top, text="اختيار الجميع", variable=self.global_select_var, command=self._msg_toggle_all)
        chk_all.pack(side="right", padx=10)

        ttk.Button(top, text="تعديل نص الرسالة", command=self._msg_open_template_editor).pack(side="right", padx=5)
        ttk.Button(top, text="تشغيل WhatsApp Server", command=start_whatsapp_server).pack(side="right", padx=5)
        self.send_button = ttk.Button(top, text="إرسال للمحددين", command=self._msg_send_selected)
        self.send_button.pack(side="right", padx=5)

        status_bar = ttk.Frame(self.messages_frame); status_bar.pack(fill="x", padx=5)
        ttk.Label(status_bar, text="الحالة:").pack(side="right")
        self.status_label = ttk.Label(status_bar, text="جاهز", foreground="green")
        self.status_label.pack(side="right")

        wrapper = ttk.Frame(self.messages_frame); wrapper.pack(fill="both", expand=True, padx=5, pady=5)

        self.msg_scroll = ttk.Scrollbar(wrapper, orient="vertical")
        self.msg_scroll.pack(side="right", fill="y")

        self.msg_canvas = tk.Canvas(wrapper, yscrollcommand=self.msg_scroll.set, highlightthickness=0)
        self.msg_canvas.pack(side="left", fill="both", expand=True)

        self.msg_scroll.config(command=self.msg_canvas.yview)

        self.msg_inner = ttk.Frame(self.msg_canvas)
        self._msg_canvas_window = self.msg_canvas.create_window((0, 0), window=self.msg_inner, anchor="nw")

        self.msg_inner.bind(
            "<Configure>",
            lambda e: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all"))
        )

        self.msg_canvas.bind(
            "<Configure>",
            lambda e: self.msg_canvas.itemconfigure(self._msg_canvas_window, width=e.width)
        )

        self._msg_load_groups()

    def _msg_load_groups(self):
        date_str = self.msg_date_var.get().strip()
        if not date_str:
            if hasattr(self, 'msg_inner') and self.msg_inner.winfo_children():
                 messagebox.showerror("خطأ", "الرجاء إدخال تاريخ.")
            return

        for child in self.msg_inner.winfo_children():
            child.destroy()
        self.msg_vars.clear()
        self.class_select_vars.clear()

        self.msg_groups = build_absent_groups(date_str)
        total_students = sum(len(v["students"]) for v in self.msg_groups.values())
        if not self.msg_groups or total_students == 0:
            self.status_label.config(text=f"لا توجد غيابات بتاريخ {date_str}", foreground="orange")
            ttk.Label(self.msg_inner, text="لا توجد بيانات لعرضها.", foreground="#888").pack(pady=20)
            self.msg_inner.update_idletasks()
            self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all"))
            return

        for cid, obj in sorted(self.msg_groups.items(), key=lambda kv: kv[0]):
            self._msg_build_class_section(cid, obj["class_name"], obj["students"])

        self.status_label.config(text=f"تم تحميل {total_students} طالبًا غائبًا.", foreground="green")

        self.msg_inner.update_idletasks()
        self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all"))


    def _msg_build_class_section(self, class_id: str, class_name: str, students: List[Dict[str, str]]):
        frame = ttk.LabelFrame(self.msg_inner, text=class_name, padding=10)
        frame.pack(fill="x", expand=True, pady=6)

        top_row = ttk.Frame(frame)
        top_row.pack(fill="x", pady=(0, 6))
        var_all = tk.BooleanVar(value=False)
        self.class_select_vars[class_id] = var_all

        chk = ttk.Checkbutton(top_row, text="اختيار جميع طلاب هذا الفصل", variable=var_all,
                              command=lambda cid=class_id: self._msg_toggle_class(cid))
        chk.pack(side="right")

        ttk.Label(top_row, text=f"عدد الطلاب: {len(students)}").pack(side="left")

        grid = ttk.Frame(frame)
        grid.pack(fill="x", expand=True)

        cols = 2
        for i, s in enumerate(students):
            r = i // cols
            c = i % cols
            cell = ttk.Frame(grid)
            cell.grid(row=r, column=c, sticky="ew", padx=4, pady=3)

            var = tk.BooleanVar(value=False)
            self.msg_vars[s["id"]] = var

            phone_txt = s.get("phone", "")
            label = f"{s['name']} — {phone_txt if phone_txt else 'لا يوجد رقم'}"
            ttk.Checkbutton(cell, text=label, variable=var).pack(anchor="w")

        for c in range(cols):
            grid.columnconfigure(c, weight=1)


    def _msg_toggle_class(self, class_id: str):
        checked = self.class_select_vars.get(class_id, tk.BooleanVar(value=False)).get()
        for s in self.msg_groups.get(class_id, {}).get("students", []):
            sid = s["id"]
            if sid in self.msg_vars:
                self.msg_vars[sid].set(checked)

    def _msg_toggle_all(self):
        checked = self.global_select_var.get()
        for var in self.class_select_vars.values():
            var.set(checked)
        for v in self.msg_vars.values():
            v.set(checked)

    def _msg_open_template_editor(self):
        win = tk.Toplevel(self.root)
        win.title("تعديل نص رسالة الغياب")
        win.geometry("650x350")
        win.transient(self.root)
        win.grab_set()

        info_frame = ttk.Frame(win)
        info_frame.pack(fill="x", padx=15, pady=(10, 5))
        ttk.Label(info_frame, text="المتغيّرات المدعومة:", anchor="e").pack(side="right")
        ttk.Label(info_frame, text="{school_name}, {student_name}, {class_name}, {date}", foreground="#007bff", anchor="w").pack(side="left")
        ttk.Separator(win, orient='horizontal').pack(fill='x', padx=10, pady=5)

        fields_frame = ttk.Frame(win, padding="10")
        fields_frame.pack(fill="both", expand=True)

        current_template = (load_config().get("message_template") or DEFAULT_CONFIG["message_template"]).strip()
        lines = current_template.split('\n')

        entries = []
        labels = [
            "السطر الأول (تنبيه):",
            "السطر الثاني (ولي الأمر):",
            "السطر الثالث (نص الإفادة):",
            "السطر الرابع (الحث على المتابعة):",
            "السطر الخامس (التحية):",
            "السطر السادس (التوقيع):"
        ]
        
        for i in range(6):
            row_frame = ttk.Frame(fields_frame)
            row_frame.pack(fill="x", pady=4)
            
            label_text = labels[i] if i < len(labels) else f"السطر الإضافي {i+1}:"
            lbl = ttk.Label(row_frame, text=label_text, width=25, anchor="e")
            lbl.pack(side="right", padx=5)
            
            entry = ttk.Entry(row_frame, font=("Tahoma", 10), justify='right')
            entry.pack(side="left", fill="x", expand=True)
            
            if i < len(lines):
                entry.insert(0, lines[i])
            
            entries.append(entry)

        def save_and_close():
            new_lines = [e.get().strip() for e in entries if e.get().strip()]
            new_template = "\n".join(new_lines)

            if not new_template:
                messagebox.showwarning("تنبيه", "لا يمكن حفظ قالب فارغ.", parent=win)
                return
            
            try:
                cfg = load_config()
                cfg["message_template"] = new_template
                with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                
                if hasattr(self, 'msg_template_var'):
                    self.msg_template_var.set(new_template)

                messagebox.showinfo("تم الحفظ", "تم تحديث نص الرسالة بنجاح.", parent=win)
                win.destroy()

            except Exception as e:
                messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ القالب:\n{e}", parent=win)

        buttons_frame = ttk.Frame(win)
        buttons_frame.pack(fill="x", padx=10, pady=(10, 10))

        ttk.Button(buttons_frame, text="حفظ وإغلاق", command=save_and_close).pack(side="left", padx=5)
        ttk.Button(buttons_frame, text="إلغاء", command=win.destroy).pack(side="right", padx=5)

    def _msg_send_selected(self):
        date_str = self.msg_date_var.get().strip()
        if not date_str:
            messagebox.showerror("خطأ", "الرجاء إدخال تاريخ.")
            return

        selected = []
        for cid, obj in self.msg_groups.items():
            cname = obj["class_name"]
            for s in obj["students"]:
                if self.msg_vars.get(s["id"], tk.BooleanVar()).get():
                    selected.append((cid, cname, s))

        if not selected:
            messagebox.showinfo("تنبيه", "الرجاء تحديد طالب واحد على الأقل.")
            return

        tpl = self.msg_template_var.get() or get_message_template()
        self.status_label.config(text="جارٍ الإرسال...", foreground="blue")
        self.send_button.config(state="disabled")
        self.root.update_idletasks()

        s_ok, s_fail = 0, 0
        for cid, cname, s in selected:
            student_name = s["name"]
            phone = s.get("phone", "")
            body = render_message(student_name, class_name=cname, date_str=date_str)
            success, msg = safe_send_absence_alert(s["id"], student_name, cname, date_str)
            status_text = "تم الإرسال" if success else f"فشل: {msg}"
            if success:
                s_ok += 1
            else:
                s_fail += 1

            try:
                log_message_status(date_str, s["id"], student_name, cid, cname, phone, status_text, body)
            except Exception as e:
                print("log_message_status error:", e)

            self.status_label.config(text=f"جاري الإرسال... ✅{s_ok} / ❌{s_fail}", foreground="blue")
            self.root.update_idletasks()

        self.send_button.config(state="normal")
        summary = f"اكتمل: نجح {s_ok}، فشل {s_fail}."
        self.status_label.config(text=summary, foreground="green" if s_fail == 0 else "red")
        messagebox.showinfo("نتيجة الإرسال", summary)
    
    def _open_today_messages_report(self):
        date_str = now_riyadh_date()
        rows = query_today_messages(date_str)
        win = tk.Toplevel(self.root)
        win.title(f"تقرير رسائل اليوم ({date_str})")
        win.geometry("800x500")

        cols = ("student_name", "class_name", "phone", "status")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, h, w in zip(cols, ["اسم الطالب", "الفصل", "رقم الجوال", "حالة الرسالة"], [220, 220, 140, 200]):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="center")
        tree.pack(fill="both", expand=True)

        for r in rows:
            tree.insert("", "end", values=(r["student_name"], r["class_name"], r["phone"], r["status"]))

    def _build_student_management_tab(self):
        top_frame = ttk.Frame(self.student_management_frame); top_frame.pack(fill="x", pady=(8, 8))
        ttk.Label(top_frame, text="بحث:").pack(side="left", padx=(0, 5))
        self.student_search_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.student_search_var, width=30).pack(side="left", padx=5)
        ttk.Button(top_frame, text="بحث", command=self.search_students_for_management).pack(side="left", padx=5)
        ttk.Button(top_frame, text="مسح", command=self.clear_student_search).pack(side="left", padx=5)
        ttk.Button(top_frame, text="حفظ التعديلات", command=self.save_student_class_edits).pack(side="right", padx=5)
        cols = ("student_id", "student_name", "current_class", "new_class")
        self.tree_student_management = ttk.Treeview(self.student_management_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["رقم الطالب", "اسم الطالب", "الفصل الحالي", "الفصل الجديد"], [120, 250, 200, 200]):
            self.tree_student_management.heading(col, text=header); self.tree_student_management.column(col, width=w, anchor="center")
        self.tree_student_management.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_student_management.bind("<Double-1>", self.on_double_click_student_class)
                # أزرار الحذف
        delete_frame = ttk.Frame(top_frame)
        delete_frame.pack(side="right", padx=10)
        ttk.Button(delete_frame, text="🗑️ حذف الطالب المحدد", command=self.delete_selected_student).pack(pady=2)
        ttk.Button(delete_frame, text="🗑️ حذف فصل محدد", command=self.delete_selected_class).pack(pady=2)
        
        self.load_students_to_management_treeview()

    def load_students_to_management_treeview(self):
        for item in self.tree_student_management.get_children():
            self.tree_student_management.delete(item)
        self.all_students_class_data = []
        for c in self.store["list"]:
            for s in c["students"]:
                self.all_students_class_data.append({"student_id": s.get("id", ""), "student_name": s.get("name", ""), "current_class_id": c["id"], "current_class_name": c["name"]})
        self.display_students_for_management(self.all_students_class_data)

    def display_students_for_management(self, students_list):
        all_class_names = [c["name"] for c in self.store["list"]]
        for student in students_list:
            self.tree_student_management.insert("", "end", values=(student["student_id"], student["student_name"], student["current_class_name"], student["current_class_name"]))
        self.all_class_names_for_student_mng = all_class_names

    def on_double_click_student_class(self, event):
        if self.tree_student_management.identify("region", event.x, event.y) != "cell" or self.tree_student_management.identify_column(event.x) != "#4":
            return
        if not (item_id := self.tree_student_management.focus()): return
        current_values = list(self.tree_student_management.item(item_id, "values"))
        combo = ttk.Combobox(self.tree_student_management, values=self.all_class_names_for_student_mng, state="readonly"); combo.set(current_values[3]); combo.focus()
        if not (bbox := self.tree_student_management.bbox(item_id, column="#4")): return
        combo.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        def save_edit(e=None):
            selected_class = combo.get(); current_values[3] = selected_class
            self.tree_student_management.item(item_id, values=current_values); combo.destroy()
        combo.bind("<<ComboboxSelected>>", save_edit); combo.bind("<FocusOut>", save_edit); combo.bind("<Escape>", lambda e: combo.destroy())

    def search_students_for_management(self):
        query = self.student_search_var.get().strip().lower()
        filtered = [s for s in self.all_students_class_data if not query or query in str(s["student_id"]).lower() or query in str(s["student_name"]).lower()]
        for item in self.tree_student_management.get_children():
            self.tree_student_management.delete(item)
        self.display_students_for_management(filtered)

    def clear_student_search(self):
        self.student_search_var.set("")
        self.search_students_for_management()

    def save_student_class_edits(self):
        changes_made = False
        for item in self.tree_student_management.get_children():
            values = self.tree_student_management.item(item, "values")
            student_id, current_class_name, new_class_name = values[0], values[2], values[3]
            if current_class_name != new_class_name:
                changes_made = True
                student_data = None; old_class_index = -1
                for i, c in enumerate(self.store["list"]):
                    for j, s in enumerate(c["students"]):
                        if s.get("id") == student_id:
                            student_data = c["students"].pop(j)
                            old_class_index = i
                            break
                    if student_data: break
                
                if not student_data: continue

                new_class_found = False
                for c in self.store["list"]:
                    if c["name"] == new_class_name:
                        c["students"].append(student_data)
                        new_class_found = True
                        break
                
                if not new_class_found:
                    self.store["list"][old_class_index]["students"].append(student_data)

        if changes_made:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم الحفظ", "تم نقل الطلاب وحفظ التعديلات بنجاح.")
            self.update_all_tabs_after_data_change()
        else:
            messagebox.showinfo("لا توجد تغييرات", "لم يتم إجراء أي تغييرات على فصول الطلاب.")

    def _build_class_naming_tab(self):
        top_frame = ttk.Frame(self.class_naming_frame)
        top_frame.pack(fill="x", pady=(8, 8), padx=5)
        ttk.Label(top_frame, text="انقر نقرًا مزدوجًا على الاسم الجديد لتعديله.").pack(side="right")
        ttk.Button(top_frame, text="حفظ التعديلات", command=self.save_class_name_edits).pack(side="left")

        cols = ("class_id", "current_name", "new_name")
        self.tree_class_naming = ttk.Treeview(self.class_naming_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["المعرّف", "الاسم الحالي", "الاسم الجديد"], [150, 300, 300]):
            self.tree_class_naming.heading(col, text=header)
            self.tree_class_naming.column(col, width=w, anchor="center")
        self.tree_class_naming.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_class_naming.bind("<Double-1>", self.on_double_click_class_name)
        self.load_class_names_to_treeview()

    def load_class_names_to_treeview(self):
        for item in self.tree_class_naming.get_children():
            self.tree_class_naming.delete(item)
        sorted_classes = sorted(self.store["list"], key=lambda c: c.get("id", ""))
        for c in sorted_classes:
            class_id = c.get("id", "")
            class_name = c.get("name", "")
            self.tree_class_naming.insert("", "end", values=(class_id, class_name, class_name))

    def on_double_click_class_name(self, event):
        if self.tree_class_naming.identify("region", event.x, event.y) != "cell" or self.tree_class_naming.identify_column(event.x) != "#3":
            return
        if not (item_id := self.tree_class_naming.focus()): return
        
        current_values = list(self.tree_class_naming.item(item_id, "values"))
        entry = ttk.Entry(self.tree_class_naming)
        entry.insert(0, current_values[2])
        entry.select_range(0, tk.END)
        entry.focus()
        
        if not (bbox := self.tree_class_naming.bbox(item_id, column="#3")): return
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        
        def save_edit(e=None):
            current_values[2] = entry.get().strip()
            self.tree_class_naming.item(item_id, values=current_values)
            entry.destroy()
        
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def save_class_name_edits(self):
        changes_made = False
        new_names_map = {self.tree_class_naming.item(i, "values")[0]: self.tree_class_naming.item(i, "values")[2] for i in self.tree_class_naming.get_children()}

        for c in self.store["list"]:
            class_id = c.get("id")
            if class_id in new_names_map:
                new_name = new_names_map[class_id]
                if c["name"] != new_name:
                    c["name"] = new_name
                    changes_made = True
        
        if changes_made:
            try:
                with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                    json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
                
                messagebox.showinfo("تم الحفظ", "تم تحديث أسماء الفصول بنجاح.")
                self.update_all_tabs_after_data_change()

            except Exception as e:
                messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ أسماء الفصول:\n{e}")
        else:
            messagebox.showinfo("لا توجد تغييرات", "لم يتم إجراء أي تغييرات على أسماء الفصول.")


    # ══════════════════════════════════════════════════════════
    # تبويب التأخر
    # ══════════════════════════════════════════════════════════
    def _build_tardiness_tab(self):
        frame = self.tardiness_frame

        # شريط التحكم
        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", pady=(8,4), padx=5)
        ttk.Label(ctrl, text="التاريخ:").pack(side="right", padx=(0,5))
        self.tard_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(ctrl, textvariable=self.tard_date_var, width=12).pack(side="right", padx=5)
        ttk.Label(ctrl, text="الفصل:").pack(side="right", padx=(10,5))
        self.tard_class_var = tk.StringVar()
        class_ids = ["(الكل)"] + [c["id"] for c in self.store["list"]]
        ttk.Combobox(ctrl, textvariable=self.tard_class_var,
                     values=class_ids, width=12, state="readonly").pack(side="right", padx=5)
        ttk.Button(ctrl, text="🔍 عرض", command=self._tard_load).pack(side="right", padx=5)
        ttk.Button(ctrl, text="➕ إضافة تأخر", command=self._tard_add_dialog).pack(side="right", padx=5)
        ttk.Button(ctrl, text="🗑️ حذف المحدد", command=self._tard_delete).pack(side="left", padx=5)

        # إحصائيات سريعة
        stats_row = ttk.Frame(frame); stats_row.pack(fill="x", padx=5, pady=4)
        self.tard_stat_lbl = ttk.Label(stats_row, text="", foreground="#1565C0",
                                        font=("Tahoma",10,"bold"))
        self.tard_stat_lbl.pack(side="right")

        # الجدول
        cols = ("id","date","class_name","student_name","student_id",
                "teacher_name","period","minutes_late")
        self.tree_tard = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for col, hdr, w in zip(cols,
            ["ID","التاريخ","الفصل","اسم الطالب","رقم الطالب","المعلم","الحصة","دقائق التأخر"],
            [40,90,160,220,110,140,60,100]):
            self.tree_tard.heading(col, text=hdr)
            self.tree_tard.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_tard.yview)
        self.tree_tard.configure(yscrollcommand=sb.set)
        self.tree_tard.pack(side="left", fill="both", expand=True, padx=(5,0))
        sb.pack(side="right", fill="y", padx=(0,5))

        # ألوان التأخر
        self.tree_tard.tag_configure("late_heavy", background="#FFEBEE", foreground="#C62828")
        self.tree_tard.tag_configure("late_mild",  background="#FFF8E1", foreground="#E65100")
        self._tard_load()

    def _tard_load(self):
        date_f  = self.tard_date_var.get().strip() if hasattr(self,"tard_date_var") else now_riyadh_date()
        cls_id  = self.tard_class_var.get() if hasattr(self,"tard_class_var") else None
        if cls_id == "(الكل)": cls_id = None
        rows = query_tardiness(date_filter=date_f or None, class_id=cls_id)
        if not hasattr(self,"tree_tard"): return
        for i in self.tree_tard.get_children(): self.tree_tard.delete(i)
        total_min = 0
        for r in rows:
            mins = r.get("minutes_late", 0)
            total_min += mins
            tag = "late_heavy" if mins >= 15 else "late_mild" if mins >= 5 else ""
            self.tree_tard.insert("", "end", tags=(tag,),
                values=(r["id"], r["date"], r["class_name"], r["student_name"],
                        r["student_id"], r.get("teacher_name",""), r.get("period",""),
                        f"{mins} دقيقة"))
        if hasattr(self,"tard_stat_lbl"):
            self.tard_stat_lbl.config(
                text=f"الإجمالي: {len(rows)} طالب متأخر | متوسط التأخر: {total_min//max(len(rows),1)} دقيقة")

    def _tard_add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("إضافة تأخر")
        win.geometry("460x420")
        win.transient(self.root); win.grab_set()

        ttk.Label(win, text="إضافة سجل تأخر", font=("Tahoma",13,"bold")).pack(pady=(16,8))

        form = ttk.Frame(win, padding=20); form.pack(fill="both", expand=True)

        def row(lbl, widget_fn):
            f = ttk.Frame(form); f.pack(fill="x", pady=4)
            ttk.Label(f, text=lbl, width=14, anchor="e").pack(side="right")
            w = widget_fn(f); w.pack(side="right", fill="x", expand=True, padx=(0,6))
            return w

        date_var = tk.StringVar(value=self.tard_date_var.get())
        row("التاريخ:", lambda p: ttk.Entry(p, textvariable=date_var))

        cls_var = tk.StringVar()
        cls_combo = row("الفصل:", lambda p: ttk.Combobox(
            p, textvariable=cls_var,
            values=[c["name"] for c in self.store["list"]],
            state="readonly"))

        stu_var = tk.StringVar()
        stu_combo = row("الطالب:", lambda p: ttk.Combobox(
            p, textvariable=stu_var, state="readonly"))

        def on_cls_change(*_):
            cls = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if cls:
                stu_combo["values"] = [f'{s["name"]} ({s["id"]})' for s in cls["students"]]
        cls_combo.bind("<<ComboboxSelected>>", on_cls_change)

        tch_var = tk.StringVar()
        teachers = load_teachers()
        tch_names = [t["اسم المعلم"] for t in teachers.get("teachers",[])]
        row("المعلم:", lambda p: ttk.Combobox(p, textvariable=tch_var,
                                               values=tch_names, state="readonly"))

        period_var = tk.StringVar(value="1")
        row("الحصة:", lambda p: ttk.Combobox(p, textvariable=period_var,
                                              values=[str(i) for i in range(1,8)],
                                              state="readonly", width=6))

        mins_var = tk.StringVar(value="10")
        mins_entry = row("دقائق التأخر:", lambda p: ttk.Entry(p, textvariable=mins_var, width=8))

        status_lbl = ttk.Label(win, text="", foreground="green")
        status_lbl.pack()

        def save():
            cls_obj = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if not cls_obj: messagebox.showwarning("تنبيه","اختر فصلاً",parent=win); return
            stu_txt = stu_var.get()
            if not stu_txt: messagebox.showwarning("تنبيه","اختر طالباً",parent=win); return
            sid   = stu_txt.split("(")[-1].rstrip(")")
            sname = stu_txt.split("(")[0].strip()
            try: mins = int(mins_var.get())
            except ValueError: mins = 0
            ok = insert_tardiness(
                date_var.get(), cls_obj["id"], cls_obj["name"],
                sid, sname, tch_var.get(),
                int(period_var.get() or 1), mins)
            if ok:
                status_lbl.config(text="✅ تم التسجيل")
                self._tard_load()
            else:
                status_lbl.config(text="⚠️ السجل موجود مسبقاً", foreground="orange")

        ttk.Button(win, text="💾 حفظ", command=save).pack(pady=10)

    def _tard_delete(self):
        sel = self.tree_tard.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد سجلاً أولاً"); return
        rid = self.tree_tard.item(sel[0])["values"][0]
        if not messagebox.askyesno("تأكيد","هل تريد حذف هذا السجل؟"): return
        delete_tardiness(rid)
        self._tard_load()

    # ══════════════════════════════════════════════════════════
    # تبويب الأعذار
    # ══════════════════════════════════════════════════════════
    def _build_whatsapp_bot_section(self, parent_frame):
        """قسم إدارة بوت الواتساب — يُضمَّن داخل تبويب الأعذار."""
        wa_lf = ttk.LabelFrame(parent_frame, text=" 🤖 بوت واتساب الأعذار ", padding=8)
        wa_lf.pack(fill="x", padx=5, pady=(10, 4))

        wa_top = ttk.Frame(wa_lf); wa_top.pack(fill="x")
        self._wa_status_dot = tk.Label(wa_top, text="⬤", font=("Tahoma", 14), fg="#aaaaaa")
        self._wa_status_dot.pack(side="right", padx=(0, 4))
        self._wa_status_text = ttk.Label(wa_top, text="جارٍ التحقق...", font=("Tahoma", 10))
        self._wa_status_text.pack(side="right", padx=(0, 8))

        btn_row = ttk.Frame(wa_lf); btn_row.pack(fill="x", pady=(6, 0))

        def _start_wa():
            if not os.path.isdir(WHATS_PATH):
                messagebox.showerror("خطأ", "مجلد الواتساب غير موجود:\n" + WHATS_PATH)
                return
            try:
                cmd = rf'cmd.exe /k "cd /d {WHATS_PATH} && node server.js"'
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self._wa_status_text.config(text="جارٍ التشغيل... انتظر 10 ثوانٍ")
                parent_frame.after(10000, _check_wa_status)
            except Exception as e:
                messagebox.showerror("خطأ", "تعذّر التشغيل:\n" + str(e))

        def _check_wa_status():
            try:
                import urllib.request
                r = urllib.request.urlopen("http://localhost:3000/status", timeout=1)
                import json as _j
                data = _j.loads(r.read())
                if data.get("ready"):
                    self._wa_status_dot.config(fg="#22c55e")
                    pending = data.get("pending", 0)
                    self._wa_status_text.config(
                        text=f"✅ متصل ويعمل  |  انتظار ردود: {pending}",
                        foreground="#166534")
                else:
                    self._wa_status_dot.config(fg="#f59e0b")
                    self._wa_status_text.config(
                        text="⏳ الخادم يعمل لكن لم يتصل بعد — امسح QR",
                        foreground="#92400e")
            except Exception:
                self._wa_status_dot.config(fg="#ef4444")
                self._wa_status_text.config(text="🔴 الخادم غير متصل", foreground="#991b1b")
            parent_frame.after(15000, _check_wa_status)

        ttk.Button(btn_row, text="▶ تشغيل خادم الواتساب",
                   command=_start_wa).pack(side="right", padx=4)
        ttk.Button(btn_row, text="🔄 فحص الحالة",
                   command=_check_wa_status).pack(side="right", padx=4)

        # زر إيقاف/تشغيل البوت
        bot_row = ttk.Frame(wa_lf); bot_row.pack(fill="x", pady=(6, 0))
        ttk.Label(bot_row, text="حالة البوت:", font=("Tahoma", 9, "bold")).pack(side="right", padx=(0, 6))
        self._bot_toggle_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bot_row,
            text="البوت مفعّل (يرد على الأعذار تلقائياً)",
            variable=self._bot_toggle_var,
            command=lambda: _toggle_bot(self._bot_toggle_var.get())
        ).pack(side="right")

        def _toggle_bot(enabled: bool):
            try:
                import urllib.request as _ur
                data = json.dumps({"enabled": enabled}).encode()
                req = _ur.Request("http://localhost:3000/bot-toggle",
                                  data=data, headers={"Content-Type": "application/json"},
                                  method="POST")
                _ur.urlopen(req, timeout=3)
                status = "مفعّل ✅" if enabled else "موقوف ⏸"
                self._wa_status_text.config(
                    text=f"البوت {status}",
                    foreground="#166634" if enabled else "#92400e")
            except Exception:
                pass

        # قسم الكلمات المفتاحية
        ttk.Separator(wa_lf, orient="horizontal").pack(fill="x", pady=(8, 4))
        kw_hdr = ttk.Frame(wa_lf); kw_hdr.pack(fill="x")
        ttk.Label(kw_hdr, text="🔑 الكلمات المفتاحية للأعذار:",
                  font=("Tahoma", 9, "bold")).pack(side="right")
        ttk.Button(kw_hdr, text="💾 حفظ الكلمات",
                   command=lambda: _save_keywords()).pack(side="left", padx=4)
        ttk.Button(kw_hdr, text="🔄 تحميل من الخادم",
                   command=lambda: _load_keywords()).pack(side="left", padx=2)

        ttk.Label(wa_lf,
            text="أدخل الكلمات مفصولة بفاصلة — مثال: عذر، مريض، سفر، ok",
            font=("Tahoma", 8), foreground="#666").pack(anchor="e", pady=(2, 0))

        self._kw_text = tk.Text(wa_lf, height=3, font=("Tahoma", 10),
                                 wrap="word", relief="solid", bd=1)
        self._kw_text.pack(fill="x", pady=(4, 0))
        self._kw_text.insert("1.0",
            "عذر، معذور، مريض، مرض، علاج، مستشفى، وفاة، سفر، ظروف، إجازة، اجازة، excuse، ok، اوك، نعم، موافق، 1")

        def _load_keywords():
            try:
                import urllib.request as _ur, json as _j
                r = _ur.urlopen("http://localhost:3000/bot-config", timeout=1)
                cfg = _j.loads(r.read())
                kws = cfg.get("keywords", [])
                enabled = cfg.get("bot_enabled", True)
                self._kw_text.delete("1.0", "end")
                self._kw_text.insert("1.0", "، ".join(kws))
                self._bot_toggle_var.set(enabled)
            except Exception:
                pass  # الخادم غير متصل

        def _save_keywords():
            raw = self._kw_text.get("1.0", "end").strip()
            import re as _re
            kws = [k.strip() for k in _re.split(r'[،,،\n]+', raw) if k.strip()]
            if not kws:
                messagebox.showerror("خطأ", "لا توجد كلمات للحفظ!")
                return
            try:
                import urllib.request as _ur, json as _j
                data = json.dumps({"keywords": kws}, ensure_ascii=False).encode("utf-8")
                req = _ur.Request("http://localhost:3000/bot-keywords",
                                  data=data, headers={"Content-Type": "application/json"},
                                  method="POST")
                resp = _ur.urlopen(req, timeout=3)
                result = _j.loads(resp.read())
                if result.get("ok"):
                    messagebox.showinfo("تم", f"تم حفظ {len(kws)} كلمة مفتاحية بنجاح.")
                    _load_keywords()
            except Exception as e:
                messagebox.showerror("خطأ", "تعذّر حفظ الكلمات.\nتأكد من تشغيل الخادم أولاً.\n" + str(e))

        # تأجيل network calls لما بعد ظهور التبويب
        parent_frame.after(300, _check_wa_status)
        parent_frame.after(600, _load_keywords)

    def _build_excuses_tab(self):
        frame = self.excuses_frame

        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", pady=(8,4), padx=5)
        ttk.Label(ctrl, text="التاريخ:").pack(side="right", padx=(0,5))
        self.exc_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(ctrl, textvariable=self.exc_date_var, width=12).pack(side="right", padx=5)
        ttk.Button(ctrl, text="🔍 عرض", command=self._exc_load).pack(side="right", padx=5)
        ttk.Button(ctrl, text="➕ إضافة عذر", command=self._exc_add_dialog).pack(side="right", padx=5)
        ttk.Button(ctrl, text="🗑️ حذف", command=self._exc_delete).pack(side="left", padx=5)

        # شرح
        ttk.Label(frame,
            text="ملاحظة: الطلاب الذين لديهم عذر مقبول سيظهر غيابهم بلون مختلف في التقارير.",
            foreground="#5A6A7E", font=("Tahoma",9)).pack(anchor="e", padx=5)

        cols = ("id","date","student_name","student_id","class_name","reason","source","approved_by")
        self.tree_excuses = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for col, hdr, w in zip(cols,
            ["ID","التاريخ","اسم الطالب","رقم الطالب","الفصل","سبب العذر","المصدر","الموافق"],
            [40,90,220,110,160,160,80,120]):
            self.tree_excuses.heading(col, text=hdr)
            self.tree_excuses.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_excuses.yview)
        self.tree_excuses.configure(yscrollcommand=sb.set)
        self.tree_excuses.pack(side="left", fill="both", expand=True, padx=(5,0))
        sb.pack(side="right", fill="y", padx=(0,5))

        self.tree_excuses.tag_configure("wa_excuse", background="#E8F5E9", foreground="#2E7D32")
        self.tree_excuses.tag_configure("admin_excuse", background="#E3F2FD", foreground="#1565C0")
        frame.after(100, self._exc_load)

        # ─── قسم بوت الواتساب ────────────────────────────────
        self._build_whatsapp_bot_section(frame)

    def _exc_load(self):
        date_f = self.exc_date_var.get().strip() if hasattr(self,"exc_date_var") else now_riyadh_date()
        rows   = query_excuses(date_filter=date_f or None)
        if not hasattr(self,"tree_excuses"): return
        for i in self.tree_excuses.get_children(): self.tree_excuses.delete(i)
        for r in rows:
            tag = "wa_excuse" if r.get("source")=="whatsapp" else "admin_excuse"
            self.tree_excuses.insert("", "end", tags=(tag,),
                values=(r["id"], r["date"], r["student_name"], r["student_id"],
                        r["class_name"], r["reason"],
                        "واتساب" if r.get("source")=="whatsapp" else "إداري",
                        r.get("approved_by","")))

    def _exc_add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("إضافة عذر غياب")
        win.geometry("500x420")
        win.transient(self.root); win.grab_set()

        ttk.Label(win, text="إضافة عذر لطالب", font=("Tahoma",13,"bold")).pack(pady=(16,8))
        form = ttk.Frame(win, padding=20); form.pack(fill="both", expand=True)

        def row(lbl, widget_fn):
            f = ttk.Frame(form); f.pack(fill="x", pady=5)
            ttk.Label(f, text=lbl, width=14, anchor="e").pack(side="right")
            w = widget_fn(f); w.pack(side="right", fill="x", expand=True, padx=(0,6))
            return w

        date_var = tk.StringVar(value=self.exc_date_var.get())
        row("التاريخ:", lambda p: ttk.Entry(p, textvariable=date_var))

        cls_var = tk.StringVar()
        cls_combo = row("الفصل:", lambda p: ttk.Combobox(
            p, textvariable=cls_var,
            values=[c["name"] for c in self.store["list"]],
            state="readonly"))

        stu_var = tk.StringVar()
        stu_combo = row("الطالب:", lambda p: ttk.Combobox(
            p, textvariable=stu_var, state="readonly"))

        def on_cls(*_):
            cls = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if cls:
                stu_combo["values"] = [f'{s["name"]} ({s["id"]})' for s in cls["students"]]
        cls_combo.bind("<<ComboboxSelected>>", on_cls)

        reason_var = tk.StringVar(value=EXCUSE_REASONS[0])
        row("سبب العذر:", lambda p: ttk.Combobox(
            p, textvariable=reason_var, values=EXCUSE_REASONS, state="readonly"))

        approved_var = tk.StringVar(value=CURRENT_USER.get("name","المدير"))
        row("الموافق:", lambda p: ttk.Entry(p, textvariable=approved_var))

        status_lbl = ttk.Label(win, text=""); status_lbl.pack()

        def save():
            cls_obj = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if not cls_obj: messagebox.showwarning("تنبيه","اختر فصلاً",parent=win); return
            stu_txt = stu_var.get()
            if not stu_txt: messagebox.showwarning("تنبيه","اختر طالباً",parent=win); return
            sid   = stu_txt.split("(")[-1].rstrip(")")
            sname = stu_txt.split("(")[0].strip()
            insert_excuse(date_var.get(), sid, sname,
                          cls_obj["id"], cls_obj["name"],
                          reason_var.get(), "admin", approved_var.get())
            status_lbl.config(text="✅ تم حفظ العذر", foreground="green")
            self._exc_load()

        ttk.Button(win, text="💾 حفظ العذر", command=save).pack(pady=10)

    def _exc_delete(self):
        sel = self.tree_excuses.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد سجلاً"); return
        rid = self.tree_excuses.item(sel[0])["values"][0]
        if not messagebox.askyesno("تأكيد","حذف هذا العذر؟"): return
        delete_excuse(rid); self._exc_load()

    # ══════════════════════════════════════════════════════════
    # تبويب المستخدمين (للمدير فقط)
    # ══════════════════════════════════════════════════════════
    def _build_users_tab(self):
        frame = self.users_frame

        # ─ العنوان
        hdr = tk.Frame(frame, bg="#7C3AED", height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="👥 إدارة المستخدمين وصلاحيات التبويبات",
                 bg="#7C3AED", fg="white",
                 font=("Tahoma",12,"bold")).pack(side="right", padx=14, pady=10)

        # ─ تقسيم رأسي: قائمة المستخدمين + لوحة الصلاحيات
        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # ══ الجانب الأيمن: قائمة المستخدمين ═════════════════════
        left_lf = ttk.LabelFrame(paned, text=" قائمة المستخدمين ", padding=6)
        paned.add(left_lf, weight=2)

        ctrl = ttk.Frame(left_lf); ctrl.pack(fill="x", pady=(0,6))
        ttk.Button(ctrl, text="➕ جديد",
                   command=self._user_add_dialog).pack(side="right", padx=3)
        ttk.Button(ctrl, text="🔑 كلمة المرور",
                   command=self._user_change_pw).pack(side="right", padx=3)
        ttk.Button(ctrl, text="🔄 تفعيل/تعطيل",
                   command=self._user_toggle).pack(side="right", padx=3)
        ttk.Button(ctrl, text="🗑️ حذف",
                   command=self._user_delete).pack(side="right", padx=3)

        cols = ("id","username","full_name","role","active","tabs_info")
        self.tree_users = ttk.Treeview(left_lf, columns=cols,
                                        show="headings", height=16)
        for col, hdr_t, w in zip(cols,
            ["ID","اسم المستخدم","الاسم الكامل","الدور","الحالة","التبويبات"],
            [35, 130, 180, 100, 70, 110]):
            self.tree_users.heading(col, text=hdr_t)
            self.tree_users.column(col, width=w, anchor="center")
        self.tree_users.tag_configure("inactive",  foreground="#9E9E9E")
        self.tree_users.tag_configure("admin_row", foreground="#7C3AED",
                                       font=("Tahoma",10,"bold"))
        self.tree_users.tag_configure("custom",    foreground="#1565C0")
        sb = ttk.Scrollbar(left_lf, orient="vertical",
                            command=self.tree_users.yview)
        self.tree_users.configure(yscrollcommand=sb.set)
        self.tree_users.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree_users.bind("<<TreeviewSelect>>", self._on_user_select)

        # ══ الجانب الأيسر: صلاحيات التبويبات ════════════════════
        right_lf = ttk.LabelFrame(paned, text=" صلاحيات التبويبات ", padding=8)
        paned.add(right_lf, weight=3)

        self._tabs_perm_user_lbl = ttk.Label(
            right_lf,
            text="← اختر مستخدماً من القائمة",
            font=("Tahoma",11,"bold"), foreground="#5A6A7E")
        self._tabs_perm_user_lbl.pack(pady=(4,8))

        hint = ttk.Label(right_lf,
            text="✅ مُفعَّل  |  ☐ مُعطَّل  —  المدير يرى كل التبويبات دائماً",
            foreground="#5A6A7E", font=("Tahoma",9))
        hint.pack(anchor="e", pady=(0,6))

        # أزرار تحديد سريع
        quick = ttk.Frame(right_lf); quick.pack(fill="x", pady=(0,8))
        ttk.Button(quick, text="تحديد الكل",
                   command=self._tabs_select_all).pack(side="right", padx=3)
        ttk.Button(quick, text="إلغاء الكل",
                   command=self._tabs_deselect_all).pack(side="right", padx=3)
        ttk.Button(quick, text="افتراضي للدور",
                   command=self._tabs_reset_to_role).pack(side="right", padx=3)
        self._tabs_save_btn = ttk.Button(
            quick, text="💾 حفظ الصلاحيات",
            command=self._tabs_save, state="disabled")
        self._tabs_save_btn.pack(side="left", padx=3)

        ttk.Separator(right_lf, orient="horizontal").pack(fill="x", pady=(0,8))

        # شبكة checkboxes للتبويبات
        all_tabs_list = [
            "لوحة المراقبة",   "روابط الفصول",     "السجلات / التصدير",
            "إدارة الغياب",     "التأخر",             "الأعذار",
            "مستلمو التأخر",   "رسائل التأخر",      "إدارة الطلاب",
            "إضافة طالب",       "إدارة الفصول",      "التقارير / الطباعة",
            "إدارة أرقام الجوالات", "إرسال رسائل الغياب", "جدولة الروابط",
            "المراقبة الحية",   "الإشعارات الذكية",  "تصدير نور",
            "مستلمو التأخر",   "المستخدمون",         "النسخ الاحتياطية",
        ]
        # أزل المكررات مع الحفاظ على الترتيب
        seen_tabs = set()
        self._all_tabs = []
        for t in all_tabs_list:
            if t not in seen_tabs:
                seen_tabs.add(t); self._all_tabs.append(t)

        self._tab_vars = {}
        scroll_frame_outer = ttk.Frame(right_lf)
        scroll_frame_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_frame_outer, highlightthickness=0)
        sb2    = ttk.Scrollbar(scroll_frame_outer, orient="vertical",
                                command=canvas.yview)
        self._tabs_inner = ttk.Frame(canvas)

        self._tabs_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=self._tabs_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb2.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")

        # بناء checkboxes في شبكة عمودين
        COLS = 2
        for idx, tab_name in enumerate(self._all_tabs):
            var = tk.BooleanVar(value=False)
            self._tab_vars[tab_name] = var
            r, c = divmod(idx, COLS)
            cb = ttk.Checkbutton(
                self._tabs_inner,
                text=tab_name,
                variable=var,
                command=self._on_tab_perm_change)
            cb.grid(row=r, column=c, sticky="w",
                    padx=12, pady=4, ipadx=4)

        for c in range(COLS):
            self._tabs_inner.columnconfigure(c, weight=1)

        self._current_perm_user = None
        frame.after(100, self._users_load)

    def _users_load(self):
        if not hasattr(self,"tree_users"): return
        for i in self.tree_users.get_children(): self.tree_users.delete(i)
        import json as _j
        for u in get_all_users():
            tag = "admin_row" if u["role"]=="admin" else (
                  "inactive"  if not u["active"] else "")
            role_label  = ROLES.get(u["role"],{}).get("label", u["role"])
            active_lbl  = "✅" if u["active"] else "❌"
            # معلومة التبويبات
            if u["role"] == "admin":
                tabs_info = "كل التبويبات"
                tag = "admin_row"
            elif u.get("allowed_tabs"):
                try:
                    tlist = _j.loads(u["allowed_tabs"])
                    tabs_info = "{} تبويب".format(len(tlist))
                    tag = "custom"
                except:
                    tabs_info = "افتراضي"
            else:
                tabs_info = "افتراضي"
            self.tree_users.insert("","end", tags=(tag,),
                values=(u["id"], u["username"],
                        u.get("full_name",""),
                        role_label, active_lbl, tabs_info))

    def _on_user_select(self, event=None):
        """عند اختيار مستخدم — حمّل صلاحياته في checkboxes."""
        sel = self.tree_users.selection()
        if not sel: return
        vals     = self.tree_users.item(sel[0], "values")
        username = vals[1]
        role_lbl = vals[3]

        self._current_perm_user = username

        # تحديث العنوان
        label = "{} — {}".format(vals[2] or username, role_lbl)
        self._tabs_perm_user_lbl.configure(
            text="تبويبات المستخدم: " + label,
            foreground="#1565C0" if role_lbl != "مدير" else "#7C3AED")

        # تعطيل التعديل للمدير
        is_admin = (role_lbl == "مدير")
        state = "disabled" if is_admin else "normal"
        self._tabs_save_btn.configure(state="disabled")

        # حمّل التبويبات الحالية
        import json as _j, sqlite3 as _sq
        con = _sq.connect(DB_PATH); con.row_factory = _sq.Row; cur = con.cursor()
        cur.execute("SELECT role, allowed_tabs FROM users WHERE username=?", (username,))
        row = cur.fetchone(); con.close()

        if not row:
            return

        if row["role"] == "admin":
            # المدير: كل التبويبات مُفعَّلة ومقفلة
            for var in self._tab_vars.values(): var.set(True)
            for child in self._tabs_inner.winfo_children():
                if isinstance(child, ttk.Checkbutton):
                    child.configure(state="disabled")
            return

        # أفعّل checkboxes
        for child in self._tabs_inner.winfo_children():
            if isinstance(child, ttk.Checkbutton):
                child.configure(state="normal")

        # حدد التبويبات المسموحة
        if row["allowed_tabs"]:
            try:
                allowed = _j.loads(row["allowed_tabs"])
            except:
                allowed = ROLE_TABS.get(row["role"]) or []
        else:
            allowed = ROLE_TABS.get(row["role"]) or []

        allowed_set = set(allowed) if allowed else set()
        for tab_name, var in self._tab_vars.items():
            var.set(tab_name in allowed_set)

        if not is_admin:
            self._tabs_save_btn.configure(state="normal")

    def _on_tab_perm_change(self):
        """عند تغيير أي checkbox."""
        if self._current_perm_user:
            self._tabs_save_btn.configure(state="normal")

    def _tabs_select_all(self):
        if not self._current_perm_user: return
        for var in self._tab_vars.values(): var.set(True)
        self._tabs_save_btn.configure(state="normal")

    def _tabs_deselect_all(self):
        if not self._current_perm_user: return
        for var in self._tab_vars.values(): var.set(False)
        self._tabs_save_btn.configure(state="normal")

    def _tabs_reset_to_role(self):
        """إعادة التبويبات لافتراضيات الدور."""
        if not self._current_perm_user: return
        import sqlite3 as _sq
        con = _sq.connect(DB_PATH); con.row_factory = _sq.Row; cur = con.cursor()
        cur.execute("SELECT role FROM users WHERE username=?",
                    (self._current_perm_user,))
        row = cur.fetchone(); con.close()
        if not row: return
        role_tabs = ROLE_TABS.get(row["role"])
        allowed   = set(role_tabs) if role_tabs else set(self._all_tabs)
        for tab_name, var in self._tab_vars.items():
            var.set(tab_name in allowed)
        self._tabs_save_btn.configure(state="normal")

    def _tabs_save(self):
        """حفظ صلاحيات التبويبات للمستخدم المحدد."""
        if not self._current_perm_user:
            messagebox.showwarning("تنبيه","اختر مستخدماً أولاً"); return
        selected = [t for t, v in self._tab_vars.items() if v.get()]
        if not selected:
            if not messagebox.askyesno("تأكيد",
                "لم تختر أي تبويب — هل تريد حفظ (لن يرى المستخدم أي تبويب)؟"):
                return
        save_user_allowed_tabs(self._current_perm_user, selected)
        self._tabs_save_btn.configure(state="disabled")
        frame.after(100, self._users_load)
        messagebox.showinfo("تم",
            "تم حفظ {} تبويب للمستخدم '{}'".format(
                len(selected), self._current_perm_user))



    def _user_add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("مستخدم جديد")
        win.geometry("400x360")
        win.transient(self.root); win.grab_set()

        ttk.Label(win, text="إنشاء مستخدم جديد",
                  font=("Tahoma",12,"bold")).pack(pady=(14,8))
        form = ttk.Frame(win, padding=16); form.pack(fill="both")

        fields = {}
        for lbl, key, show in [
            ("اسم المستخدم *","username",""),
            ("الاسم الكامل","full_name",""),
            ("كلمة المرور *","password","●"),
            ("تأكيد كلمة المرور","confirm","●"),
        ]:
            f = ttk.Frame(form); f.pack(fill="x", pady=4)
            ttk.Label(f, text=lbl, width=18, anchor="e").pack(side="right")
            var = tk.StringVar()
            e = ttk.Entry(f, textvariable=var, show=show, justify="right")
            e.pack(side="right", fill="x", expand=True)
            fields[key] = var

        f = ttk.Frame(form); f.pack(fill="x", pady=4)
        ttk.Label(f, text="الدور *", width=18, anchor="e").pack(side="right")
        role_var = tk.StringVar(value="teacher")
        ttk.Combobox(f, textvariable=role_var,
                     values=["admin","deputy","teacher","guard"],
                     state="readonly").pack(side="right", fill="x", expand=True)

        status_lbl = ttk.Label(win, text=""); status_lbl.pack()

        def save():
            un = fields["username"].get().strip()
            fn = fields["full_name"].get().strip()
            pw = fields["password"].get()
            cp = fields["confirm"].get()
            if not un or not pw:
                status_lbl.config(text="⚠️ اسم المستخدم وكلمة المرور مطلوبان",
                                   foreground="orange"); return
            if pw != cp:
                status_lbl.config(text="❌ كلمتا المرور غير متطابقتين",
                                   foreground="red"); return
            if len(pw) < 6:
                status_lbl.config(text="⚠️ كلمة المرور يجب أن تكون 6 أحرف على الأقل",
                                   foreground="orange"); return
            ok, msg = create_user(un, pw, role_var.get(), fn)
            if ok:
                status_lbl.config(text="✅ "+msg, foreground="green")
                frame.after(100, self._users_load)
                win.after(1200, win.destroy)
            else:
                status_lbl.config(text="❌ "+msg, foreground="red")

        ttk.Button(win, text="إنشاء المستخدم", command=save).pack(pady=10)

    def _user_change_pw(self):
        sel = self.tree_users.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد مستخدماً"); return
        username = self.tree_users.item(sel[0])["values"][1]
        new_pw = simpledialog.askstring("كلمة المرور الجديدة",
                                         f"أدخل كلمة مرور جديدة للمستخدم: {username}",
                                         show="●", parent=self.root)
        if not new_pw: return
        if len(new_pw) < 6:
            messagebox.showwarning("تنبيه","كلمة المرور يجب أن تكون 6 أحرف على الأقل"); return
        update_user_password(username, new_pw)
        messagebox.showinfo("تم","تم تغيير كلمة المرور بنجاح")

    def _user_toggle(self):
        sel = self.tree_users.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد مستخدماً"); return
        vals    = self.tree_users.item(sel[0])["values"]
        user_id = vals[0]
        is_active = "فعّال" in str(vals[4])
        if vals[1] == "admin":
            messagebox.showwarning("تنبيه","لا يمكن تعطيل حساب المدير الرئيسي"); return
        toggle_user_active(user_id, 0 if is_active else 1)
        frame.after(100, self._users_load)

    def _user_delete(self):
        sel = self.tree_users.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد مستخدماً"); return
        vals    = self.tree_users.item(sel[0])["values"]
        user_id, username = vals[0], vals[1]
        if username == "admin":
            messagebox.showwarning("تنبيه","لا يمكن حذف حساب المدير الرئيسي"); return
        if not messagebox.askyesno("تأكيد",f"حذف المستخدم '{username}'؟"): return
        delete_user(user_id); self._users_load()

    # ══════════════════════════════════════════════════════════
    # تبويب النسخ الاحتياطية
    # ══════════════════════════════════════════════════════════
    def _build_school_settings_tab(self):
        """تبويب إعدادات المدرسة — تعديل بيانات المدرسة والإدارة."""
        frame = self.school_settings_frame

        # عنوان
        hdr = tk.Frame(frame, bg="#1565C0", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🏫 إعدادات المدرسة",
                 bg="#1565C0", fg="white",
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=16, pady=12)

        lf = ttk.LabelFrame(frame, text=" بيانات المدرسة والإدارة ", padding=16)
        lf.pack(fill="x", padx=20, pady=16)

        cfg = load_config()

        fields = [
            ("school_name",      "اسم المدرسة:"),
            ("assistant_title",  "لقب الوكيل:"),
            ("assistant_name",   "اسم الوكيل:"),
            ("principal_title",  "لقب المدير:"),
            ("principal_name",   "اسم المدير:"),
        ]

        self._school_vars = {}
        for key, label in fields:
            row = ttk.Frame(lf); row.pack(fill="x", pady=6)
            ttk.Label(row, text=label, width=16, anchor="e",
                      font=("Tahoma", 10, "bold")).pack(side="right", padx=(0, 8))
            var = tk.StringVar(value=cfg.get(key, ""))
            ttk.Entry(row, textvariable=var, width=40,
                      font=("Tahoma", 10), justify="right").pack(side="right", fill="x", expand=True)
            self._school_vars[key] = var

        ttk.Separator(lf, orient="horizontal").pack(fill="x", pady=(12, 8))

        btn_row = ttk.Frame(lf); btn_row.pack(fill="x")
        self._school_status = ttk.Label(btn_row, text="", foreground="green",
                                         font=("Tahoma", 10))
        self._school_status.pack(side="right", padx=12)

        def _save():
            cfg = load_config()
            for key, var in self._school_vars.items():
                cfg[key] = var.get().strip()
            try:
                with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                self._school_status.config(text="✅ تم الحفظ بنجاح", foreground="green")
                frame.after(3000, lambda: self._school_status.config(text=""))
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل الحفظ:\n{e}")

        def _reset():
            cfg = load_config()
            for key, var in self._school_vars.items():
                var.set(cfg.get(key, ""))
            self._school_status.config(text="تم إعادة التحميل", foreground="#555")
            frame.after(2000, lambda: self._school_status.config(text=""))

        ttk.Button(btn_row, text="💾 حفظ التغييرات", command=_save).pack(side="right", padx=4)
        ttk.Button(btn_row, text="🔄 إعادة تحميل", command=_reset).pack(side="right", padx=4)

        # ─── قسم إدارة الفصل الدراسي (للمدير فقط) ───────────────
        if CURRENT_USER.get("role") == "admin":
            self._build_term_management_section(frame)

    def _build_term_management_section(self, parent_frame):
        """قسم إنهاء الفصل الدراسي ونهاية السنة — للمدير فقط."""

        sep = ttk.Separator(parent_frame, orient="horizontal")
        sep.pack(fill="x", padx=20, pady=(0, 8))

        lf = ttk.LabelFrame(parent_frame,
                             text=" 🔐 إدارة الفصل الدراسي — للمدير فقط ",
                             padding=16)
        lf.pack(fill="x", padx=20, pady=(0, 16))

        # تحذير
        warn = tk.Label(lf,
            text="⚠️  هذه الإجراءات لا يمكن التراجع عنها. ستُنشأ نسخة احتياطية تلقائياً قبل كل إجراء.",
            bg="#fff8e1", fg="#7c4a00", font=("Tahoma", 9),
            wraplength=700, justify="right", pady=6, padx=10, relief="flat")
        warn.pack(fill="x", pady=(0, 12))

        # ── الزر 1: نهاية الفصل الدراسي ──
        term_lf = ttk.LabelFrame(lf, text=" نهاية الفصل الدراسي ", padding=10)
        term_lf.pack(fill="x", pady=(0, 10))

        tk.Label(term_lf,
            text="يحذف جميع سجلات الغياب والتأخر ويبقي الطلاب والإعدادات والجداول كما هي.",
            font=("Tahoma", 9), fg="#555", wraplength=650, justify="right"
        ).pack(anchor="e", pady=(0, 8))

        ttk.Button(term_lf, text="📋 إنهاء الفصل الدراسي",
                   command=self._end_semester).pack(side="right")

        # ── الزر 2: نهاية السنة الدراسية ──
        year_lf = ttk.LabelFrame(lf, text=" نهاية السنة الدراسية ", padding=10)
        year_lf.pack(fill="x", pady=(0, 10))

        tk.Label(year_lf,
            text="يُرقّي الطلاب: أول→ثاني، ثاني→ثالث، ثالث يُحذفون. ثم يحذف الغياب والتأخر.",
            font=("Tahoma", 9), fg="#555", wraplength=650, justify="right"
        ).pack(anchor="e", pady=(0, 8))

        ttk.Button(year_lf, text="🎓 إنهاء السنة الدراسية وترقية الطلاب",
                   command=self._end_academic_year).pack(side="right")

        # ── النسخ الاحتياطية الخاصة بالفصول ──
        backup_lf = ttk.LabelFrame(lf, text=" 💾 نسخ احتياطية الفصول الدراسية ", padding=10)
        backup_lf.pack(fill="x", pady=(0,4))

        # أزرار في صف واحد: تحديث + فتح المجلد + استعادة
        btn_row2 = ttk.Frame(backup_lf); btn_row2.pack(fill="x", pady=(0, 4))
        ttk.Button(btn_row2, text="🔄 تحديث",
                   command=self._load_term_backups).pack(side="right", padx=4)
        ttk.Button(btn_row2, text="📂 فتح المجلد",
                   command=lambda: (
                       os.makedirs(os.path.join(BACKUP_DIR, "terms"), exist_ok=True),
                       os.startfile(os.path.join(BACKUP_DIR, "terms"))
                   )).pack(side="right", padx=4)
        tk.Button(btn_row2,
                   text="↩️ استعادة المحددة",
                   command=self._restore_term_backup,
                   bg="#c62828", fg="white",
                   font=("Tahoma", 9, "bold"),
                   relief="flat", cursor="hand2").pack(side="right", padx=4)

        # القائمة
        list_frame = ttk.Frame(backup_lf)
        list_frame.pack(fill="x")
        sb = ttk.Scrollbar(list_frame, orient="vertical")
        self._term_backup_list = tk.Listbox(list_frame, height=6,
                                             font=("Courier", 9), selectmode="single",
                                             bg="#f9f9f9",
                                             yscrollcommand=sb.set)
        sb.config(command=self._term_backup_list.yview)
        sb.pack(side="right", fill="y")
        self._term_backup_list.pack(side="left", fill="x", expand=True)

        parent_frame.after(200, self._load_term_backups)

    def _load_term_backups(self):
        """يحمّل قائمة نسخ الفصول الاحتياطية."""
        if not hasattr(self, "_term_backup_list"):
            return
        self._term_backup_list.delete(0, "end")
        terms_dir = os.path.join(BACKUP_DIR, "terms")
        if not os.path.exists(terms_dir):
            self._term_backup_list.insert("end", "(لا توجد نسخ احتياطية بعد)")
            return
        files = sorted(
            [f for f in os.listdir(terms_dir) if f.endswith(".zip")],
            reverse=True
        )
        if not files:
            self._term_backup_list.insert("end", "(لا توجد نسخ احتياطية بعد)")
            return
        for f in files:
            size = os.path.getsize(os.path.join(terms_dir, f)) // 1024
            self._term_backup_list.insert("end", f"  {f}   ({size} KB)")

    def _create_term_backup(self, label: str) -> tuple:
        """ينشئ نسخة احتياطية خاصة بالفصل/السنة."""
        terms_dir = os.path.join(BACKUP_DIR, "terms")
        os.makedirs(terms_dir, exist_ok=True)
        ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = os.path.join(terms_dir, f"{label}_{ts}.zip")
        try:
            with zipfile.ZipFile(fname, "w", zipfile.ZIP_DEFLATED) as zf:
                if os.path.exists(DB_PATH):
                    zf.write(DB_PATH, os.path.basename(DB_PATH))
                for jf in [STUDENTS_JSON, TEACHERS_JSON, CONFIG_JSON]:
                    if os.path.exists(jf):
                        zf.write(jf, os.path.basename(jf))
            return True, fname
        except Exception as e:
            return False, str(e)

    def _end_semester(self):
        """إنهاء الفصل الدراسي — حذف الغياب والتأخر فقط."""
        if CURRENT_USER.get("role") != "admin":
            messagebox.showerror("غير مسموح", "هذا الإجراء للمدير فقط.")
            return

        # تأكيد مزدوج
        if not messagebox.askyesno("تأكيد إنهاء الفصل",
            "سيتم حذف جميع سجلات الغياب والتأخر.\nستُنشأ نسخة احتياطية تلقائياً قبل الحذف.\n\nهل أنت متأكد؟", icon="warning"):
            return

        pw = simpledialog.askstring("تأكيد الهوية",
            "أدخل كلمة مرور المدير للمتابعة:", show="*")
        if not pw:
            return
        from hashlib import sha256
        if authenticate(CURRENT_USER.get("username", "admin"), pw) is None:
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return

        # نسخة احتياطية
        ok, path = self._create_term_backup("نهاية_فصل")
        if not ok:
            messagebox.showerror("خطأ", "فشل إنشاء النسخة الاحتياطية:\n" + str(path))
            return

        # حذف الغياب والتأخر
        try:
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM absences")
            cur.execute("DELETE FROM tardiness")
            try:
                cur.execute("DELETE FROM message_log")
            except Exception:
                pass
            con.commit(); con.close()

            global STUDENTS_STORE
            STUDENTS_STORE = None

            messagebox.showinfo("تم", "✅ تم إنهاء الفصل الدراسي بنجاح.\nالنسخة الاحتياطية: " + os.path.basename(path))
            self._load_term_backups()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

    def _end_academic_year(self):
        """إنهاء السنة الدراسية — ترقية الطلاب + حذف الغياب والتأخر."""
        if CURRENT_USER.get("role") != "admin":
            messagebox.showerror("غير مسموح", "هذا الإجراء للمدير فقط.")
            return

        if not messagebox.askyesno("تأكيد إنهاء السنة",
            "سيتم:\n• ترقية طلاب أول ثانوي → ثاني ثانوي\n• ترقية طلاب ثاني ثانوي → ثالث ثانوي\n• حذف طلاب ثالث ثانوي من البرنامج\n• حذف جميع سجلات الغياب والتأخر\n\nستُنشأ نسخة احتياطية تلقائياً قبل الإجراء.\n\nهل أنت متأكد؟", icon="warning"):
            return

        pw = simpledialog.askstring("تأكيد الهوية",
            "أدخل كلمة مرور المدير للمتابعة:", show="*")
        if not pw:
            return
        if authenticate(CURRENT_USER.get("username", "admin"), pw) is None:
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return

        # نسخة احتياطية
        ok, path = self._create_term_backup("نهاية_سنة")
        if not ok:
            messagebox.showerror("خطأ", "فشل إنشاء النسخة الاحتياطية:\n" + str(path))
            return

        # ── ترقية الطلاب ──
        try:
            store = load_students(force_reload=True)
            classes = store["list"]

            # خريطة الترقية: ID الفصل → المستوى والقسم
            # نفترض أن ID الفصل بصيغة "1-أ", "2-ب", "3-ج" إلخ
            upgraded = 0
            deleted  = 0
            errors   = []

            # جمّع الطلاب حسب المستوى
            level1_classes = [c for c in classes if str(c["id"]).startswith("1-")]
            level2_classes = [c for c in classes if str(c["id"]).startswith("2-")]
            level3_classes = [c for c in classes if str(c["id"]).startswith("3-")]

            # 1. احذف طلاب المستوى 3
            for cls in level3_classes:
                deleted += len(cls["students"])
                cls["students"] = []

            # 2. انقل طلاب المستوى 2 → المستوى 3
            for cls2 in level2_classes:
                suffix = str(cls2["id"])[2:]  # مثلاً "أ" من "2-أ"
                target_id = f"3-{suffix}"
                target = next((c for c in level3_classes if c["id"] == target_id), None)
                if target:
                    target["students"] = cls2["students"]
                    upgraded += len(cls2["students"])
                    cls2["students"] = []
                else:
                    errors.append(f"لم يُوجد فصل {target_id}")

            # 3. انقل طلاب المستوى 1 → المستوى 2
            for cls1 in level1_classes:
                suffix = str(cls1["id"])[2:]
                target_id = f"2-{suffix}"
                target = next((c for c in level2_classes if c["id"] == target_id), None)
                if target:
                    target["students"] = cls1["students"]
                    upgraded += len(cls1["students"])
                    cls1["students"] = []
                else:
                    errors.append(f"لم يُوجد فصل {target_id}")

            # احفظ الطلاب المُحدَّثين
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)

            global STUDENTS_STORE
            STUDENTS_STORE = None

            # احذف الغياب والتأخر
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM absences")
            cur.execute("DELETE FROM tardiness")
            try:
                cur.execute("DELETE FROM message_log")
            except Exception:
                pass
            con.commit(); con.close()

            msg = ("✅ تمت إنهاء السنة الدراسية بنجاح.\n\n"
                   f"• طلاب مُرقَّون: {upgraded}\n"
                   f"• طلاب محذوفون (ثالث): {deleted}\n"
                   f"• النسخة الاحتياطية: {os.path.basename(path)}")
            if errors:
                msg += "\n\n⚠️ تحذيرات:\n" + "\n".join(errors)
            messagebox.showinfo("تم", msg)
            self._load_term_backups()
            self.update_all_tabs_after_data_change()

        except Exception as e:
            messagebox.showerror("خطأ", f"فشل ترقية الطلاب:\n{e}")

    def _restore_term_backup(self):
        """استعادة نسخة احتياطية من نسخ الفصول."""
        if CURRENT_USER.get("role") != "admin":
            messagebox.showerror("غير مسموح", "هذا الإجراء للمدير فقط.")
            return

        sel = self._term_backup_list.curselection()
        if not sel:
            messagebox.showwarning("تنبيه", "اختر نسخة احتياطية من القائمة أولاً.")
            return

        item = self._term_backup_list.get(sel[0]).strip()
        if item.startswith("("):
            return

        fname = item.split("(")[0].strip()
        terms_dir = os.path.join(BACKUP_DIR, "terms")
        fpath = os.path.join(terms_dir, fname)

        if not os.path.exists(fpath):
            messagebox.showerror("خطأ", "الملف غير موجود.")
            return

        if not messagebox.askyesno("تأكيد الاستعادة",
            f"سيتم استبدال جميع البيانات الحالية بالنسخة:\n{fname}\n\nهل أنت متأكد؟", icon="warning"):
            return

        pw = simpledialog.askstring("تأكيد الهوية",
            "أدخل كلمة مرور المدير للمتابعة:", show="*")
        if not pw:
            return
        if authenticate(CURRENT_USER.get("username", "admin"), pw) is None:
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return

        try:
            # نسخة احتياطية من الوضع الحالي قبل الاستعادة
            self._create_term_backup("قبل_استعادة")

            with zipfile.ZipFile(fpath, "r") as zf:
                # استعد DB
                if "absences.db" in zf.namelist():
                    zf.extract("absences.db", os.path.dirname(DB_PATH))
                # استعد JSON
                for jname in ["students.json", "teachers.json", "config.json"]:
                    if jname in zf.namelist():
                        zf.extract(jname, DATA_DIR)

            global STUDENTS_STORE
            STUDENTS_STORE = None
            invalidate_config_cache()

            messagebox.showinfo("تم", f"✅ تمت الاستعادة بنجاح من:\n{fname}\n\nأعد تشغيل البرنامج لتطبيق التغييرات.")
            try:
                self.update_all_tabs_after_data_change()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الاستعادة:\n{e}")

    def _build_backup_tab(self):
        frame = self.backup_frame

        ttk.Label(frame, text="النسخ الاحتياطية",
                  font=("Tahoma",13,"bold")).pack(pady=(12,4))

        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", padx=10, pady=8)
        ttk.Button(ctrl, text="💾 نسخ احتياطي الآن",
                   command=self._do_backup).pack(side="right", padx=4)
        ttk.Button(ctrl, text="📂 فتح مجلد النسخ",
                   command=self._open_backup_dir).pack(side="right", padx=4)
        ttk.Button(ctrl, text="🗑️ حذف المحدد",
                   command=self._delete_backup).pack(side="right", padx=4)

        # معلومات المجلد
        info = ttk.LabelFrame(frame, text=" إعدادات النسخ الاحتياطية ", padding=10)
        info.pack(fill="x", padx=10, pady=4)

        r1 = ttk.Frame(info); r1.pack(fill="x", pady=3)
        ttk.Label(r1, text="مجلد الحفظ:", width=16, anchor="e").pack(side="right")
        self.backup_dir_var = tk.StringVar(value=os.path.abspath(BACKUP_DIR))
        ttk.Entry(r1, textvariable=self.backup_dir_var, state="readonly",
                  font=("Courier",9)).pack(side="right", fill="x", expand=True, padx=4)
        ttk.Button(r1, text="تغيير", width=8,
                   command=self._change_backup_dir).pack(side="left")

        r2 = ttk.Frame(info); r2.pack(fill="x", pady=3)
        ttk.Label(r2, text="النسخ كل:", width=16, anchor="e").pack(side="right")
        self.backup_interval_var = tk.StringVar(value="24")
        ttk.Spinbox(r2, from_=1, to=168, textvariable=self.backup_interval_var,
                    width=6).pack(side="right", padx=4)
        ttk.Label(r2, text="ساعة").pack(side="right")

        self.backup_status = ttk.Label(frame, text="", foreground="green",
                                        font=("Tahoma",10))
        self.backup_status.pack(pady=4)

        # سجل النسخ
        ttk.Label(frame, text="سجل النسخ السابقة:",
                  font=("Tahoma",10,"bold")).pack(anchor="e", padx=10)
        cols = ("filename","size_kb","created_at")
        self.tree_backup = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        for col, hdr, w in zip(cols,
            ["اسم الملف","الحجم (KB)","تاريخ الإنشاء"],
            [280,100,200]):
            self.tree_backup.heading(col, text=hdr)
            self.tree_backup.column(col, width=w, anchor="center")
        self.tree_backup.pack(fill="both", expand=True, padx=10, pady=5)
        frame.after(100, self._backup_load)

    def _backup_load(self):
        if not hasattr(self,"tree_backup"): return
        for i in self.tree_backup.get_children(): self.tree_backup.delete(i)
        for b in get_backup_list():
            self.tree_backup.insert("","end",
                values=(os.path.basename(b["filename"]),
                        b.get("size_kb",0),
                        b["created_at"][:19]))

    def _do_backup(self):
        backup_dir = self.backup_dir_var.get() if hasattr(self,"backup_dir_var") else BACKUP_DIR
        ok, path, size = create_backup(backup_dir)
        if ok:
            self.backup_status.config(
                text=f"✅ تم إنشاء النسخة: {os.path.basename(path)} ({size} KB)",
                foreground="green")
            frame.after(100, self._backup_load)
        else:
            self.backup_status.config(text=f"❌ فشل: {path}", foreground="red")

    def _open_backup_dir(self):
        d = self.backup_dir_var.get() if hasattr(self,"backup_dir_var") else BACKUP_DIR
        os.makedirs(d, exist_ok=True)
        try: os.startfile(os.path.abspath(d))
        except Exception: webbrowser.open(f"file://{os.path.abspath(d)}")

    def _change_backup_dir(self):
        d = filedialog.askdirectory(title="اختر مجلد النسخ الاحتياطية")
        if d and hasattr(self,"backup_dir_var"):
            self.backup_dir_var.set(d)

    def _delete_backup(self):
        sel = self.tree_backup.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد نسخة"); return
        fname = self.tree_backup.item(sel[0])["values"][0]
        d = self.backup_dir_var.get() if hasattr(self,"backup_dir_var") else BACKUP_DIR
        full_path = os.path.join(d, fname)
        if not messagebox.askyesno("تأكيد",f"حذف النسخة: {fname}؟"): return
        try:
            if os.path.exists(full_path): os.remove(full_path)
            messagebox.showinfo("تم","تم حذف النسخة الاحتياطية")
            frame.after(100, self._backup_load)
        except Exception as e:
            messagebox.showerror("خطأ",str(e))




    # ══════════════════════════════════════════════════════════
    # تبويب رسائل التأخر
    # ══════════════════════════════════════════════════════════
    def _build_tardiness_messages_tab(self):
        frame = self.tardiness_messages_frame

        # ─ رأس
        hdr = tk.Frame(frame, bg="#E65100", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📲 إرسال رسائل ولي الأمر — المتأخرون",
                 bg="#E65100", fg="white",
                 font=("Tahoma",13,"bold")).pack(side="right", padx=16, pady=12)

        # ─ شريط الأدوات العلوي
        top = ttk.Frame(frame); top.pack(fill="x", padx=10, pady=(8,4))

        ttk.Label(top, text="التاريخ:").pack(side="right", padx=(0,4))
        self.tard_msg_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(top, textvariable=self.tard_msg_date_var,
                  width=12).pack(side="right", padx=4)
        ttk.Button(top, text="تحميل المتأخرين",
                   command=self._tard_msg_load).pack(side="right", padx=4)
        ttk.Button(top, text="تشغيل WhatsApp Server",
                   command=start_whatsapp_server).pack(side="right", padx=4)

        self.tard_global_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="اختيار الجميع",
                        variable=self.tard_global_var,
                        command=self._tard_msg_toggle_all).pack(side="right", padx=8)

        self.tard_send_msg_btn = ttk.Button(
            top, text="📤 إرسال للمحددين",
            command=self._tard_msg_send_selected)
        self.tard_send_msg_btn.pack(side="right", padx=4)

        # حالة الإرسال
        self.tard_msg_status = ttk.Label(
            frame, text="", foreground="green", font=("Tahoma",10))
        self.tard_msg_status.pack(anchor="e", padx=10)

        # ─ قالب الرسالة (قابل للتعديل)
        tpl_lf = ttk.LabelFrame(frame, text=" ✏️ نص الرسالة ", padding=8)
        tpl_lf.pack(fill="x", padx=10, pady=(0,6))

        tpl_top = ttk.Frame(tpl_lf); tpl_top.pack(fill="x", pady=(0,4))
        ttk.Label(tpl_top,
                  text="المتغيرات: {student_name} {class_name} {date} {minutes_late} {school_name}",
                  foreground="#5A6A7E", font=("Tahoma",9)).pack(side="right")
        ttk.Button(tpl_top, text="حفظ القالب",
                   command=self._tard_msg_save_template).pack(side="left")

        cfg = load_config()
        self.tard_msg_tpl_text = tk.Text(
            tpl_lf, height=5, font=("Tahoma",10), wrap="word")
        self.tard_msg_tpl_text.insert("1.0",
            cfg.get("tardiness_message_template", ""))
        self.tard_msg_tpl_text.pack(fill="x")

        # ─ قائمة المتأخرين
        list_lf = ttk.LabelFrame(
            frame, text=" 📋 المتأخرون ", padding=6)
        list_lf.pack(fill="both", expand=True, padx=10, pady=(0,6))

        cols = ("chk","student_name","class_name","minutes_late",
                "register_time","parent_phone","msg_status")
        self.tree_tard_msg = ttk.Treeview(
            list_lf, columns=cols, show="headings", height=12)
        headers = ["☐","اسم الطالب","الفصل","دقائق التأخر",
                   "وقت التسجيل","جوال ولي الأمر","حالة الرسالة"]
        widths   = [30, 220, 150, 100, 90, 130, 110]
        for col, hdr_t, w in zip(cols, headers, widths):
            self.tree_tard_msg.heading(col, text=hdr_t)
            self.tree_tard_msg.column(col, width=w, anchor="center")

        self.tree_tard_msg.tag_configure("no_phone",  background="#FFEBEE", foreground="#9E9E9E")
        self.tree_tard_msg.tag_configure("has_phone", background="#F5F5F5")
        self.tree_tard_msg.tag_configure("sent_ok",   background="#E8F5E9", foreground="#2E7D32")
        self.tree_tard_msg.tag_configure("sent_fail", background="#FFEBEE", foreground="#C62828")

        sb = ttk.Scrollbar(list_lf, orient="vertical",
                            command=self.tree_tard_msg.yview)
        self.tree_tard_msg.configure(yscrollcommand=sb.set)
        self.tree_tard_msg.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree_tard_msg.bind("<Button-1>", self._tard_msg_toggle_row)

        # ─ سجل الإرسال
        log_lf = ttk.LabelFrame(frame, text=" 📝 سجل الإرسال ", padding=4)
        log_lf.pack(fill="x", padx=10, pady=(0,8))
        self.tard_msg_log = tk.Text(
            log_lf, height=4, state="disabled",
            font=("Tahoma",9), wrap="word")
        self.tard_msg_log.pack(fill="x")

        self._tard_msg_checked = set()
        self._tard_msg_vars    = {}   # student_id -> BooleanVar
        frame.after(100, self._tard_msg_load)

    def _tard_msg_load(self):
        """يُحمّل المتأخرين لليوم المحدد."""
        if not hasattr(self, "tree_tard_msg"): return
        for i in self.tree_tard_msg.get_children():
            self.tree_tard_msg.delete(i)
        self._tard_msg_checked.clear()
        self._tard_msg_vars.clear()

        date_str = self.tard_msg_date_var.get().strip()                    if hasattr(self,"tard_msg_date_var") else now_riyadh_date()
        rows = query_tardiness(date_filter=date_str)

        if not rows:
            self.tard_msg_status.configure(
                text="لا يوجد متأخرون بتاريخ {}".format(date_str),
                foreground="orange")
            return

        # ابحث عن أرقام جوالات الطلاب
        store = load_students()
        phone_map = {s["id"]: s.get("phone","")
                     for cls in store["list"] for s in cls["students"]}

        # فحص الرسائل المُرسَلة مسبقاً
        sent_map = self._tard_msg_get_sent_map(date_str)

        count = 0
        for r in rows:
            sid       = r["student_id"]
            phone     = phone_map.get(sid, "")
            mins      = r.get("minutes_late", 0)
            reg_time  = r.get("created_at","")[:5] if r.get("created_at") else ""
            sent_stat = sent_map.get(sid, "")

            tag = ("sent_ok"   if sent_stat == "تم الإرسال" else
                   "sent_fail" if "فشل" in sent_stat        else
                   "no_phone"  if not phone                  else
                   "has_phone")

            self.tree_tard_msg.insert(
                "", "end", iid=sid, tags=(tag,),
                values=("☐", r["student_name"], r.get("class_name",""),
                        "{} دقيقة".format(mins), reg_time,
                        phone or "— لا يوجد رقم",
                        sent_stat or ""))
            count += 1

        self.tard_msg_status.configure(
            text="{} متأخر — {} لديهم رقم جوال".format(
                count, sum(1 for r in rows if phone_map.get(r["student_id"]))),
            foreground="#1565C0")

    def _tard_msg_get_sent_map(self, date_str: str) -> dict:
        """يستعلم عن الرسائل المُرسَلة للمتأخرين من جدول message_log."""
        try:
            con = get_db()
            con.row_factory = sqlite3.Row; cur = con.cursor()
            cur.execute("""SELECT student_id, status FROM messages_log
                           WHERE date=? AND message_type='tardiness'""",
                        (date_str,))
            result = {r["student_id"]: r["status"] for r in cur.fetchall()}
            con.close(); return result
        except Exception:
            return {}

    def _tard_msg_toggle_row(self, event):
        region = self.tree_tard_msg.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree_tard_msg.identify_column(event.x)
        if col != "#1": return
        iid = self.tree_tard_msg.identify_row(event.y)
        if not iid: return
        if iid in self._tard_msg_checked:
            self._tard_msg_checked.discard(iid)
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[0] = "☐"
            self.tree_tard_msg.item(iid, values=vals)
        else:
            self._tard_msg_checked.add(iid)
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[0] = "☑"
            self.tree_tard_msg.item(iid, values=vals)

    def _tard_msg_toggle_all(self):
        checked = self.tard_global_var.get()
        for iid in self.tree_tard_msg.get_children():
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[0] = "☑" if checked else "☐"
            self.tree_tard_msg.item(iid, values=vals)
            if checked: self._tard_msg_checked.add(iid)
            else:        self._tard_msg_checked.discard(iid)

    def _tard_msg_save_template(self):
        tpl = self.tard_msg_tpl_text.get("1.0","end").strip()               if hasattr(self,"tard_msg_tpl_text") else ""
        if not tpl: return
        cfg = load_config()
        cfg["tardiness_message_template"] = tpl
        with open(CONFIG_JSON,"w",encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("تم","تم حفظ قالب رسالة التأخر")

    def _tard_msg_send_selected(self):
        if not self._tard_msg_checked:
            messagebox.showwarning("تنبيه","حدد طلاباً أولاً"); return

        date_str = self.tard_msg_date_var.get().strip()                    if hasattr(self,"tard_msg_date_var") else now_riyadh_date()
        cfg      = load_config()
        school   = cfg.get("school_name","المدرسة")
        tpl      = cfg.get("tardiness_message_template","")
        store    = load_students()
        phone_map = {s["id"]: s.get("phone","")
                     for cls in store["list"] for s in cls["students"]}
        tard_rows = {r["student_id"]: r
                     for r in query_tardiness(date_filter=date_str)}

        if not messagebox.askyesno("تأكيد",
            "إرسال رسائل التأخر لـ {} طالب؟".format(
                len(self._tard_msg_checked))):
            return

        self.tard_send_msg_btn.configure(state="disabled")
        self.root.update_idletasks()

        def do_send():
            ok_cnt = fail_cnt = skip_cnt = 0
            for sid in list(self._tard_msg_checked):
                row   = tard_rows.get(sid)
                phone = phone_map.get(sid,"")
                if not row:
                    skip_cnt += 1; continue
                if not phone:
                    skip_cnt += 1
                    self._tard_msg_log_append("⚠️ {} — لا يوجد رقم جوال".format(
                        row.get("student_name",sid)))
                    self._tard_msg_update_row(sid, "لا يوجد رقم")
                    continue
                try:
                    mins = row.get("minutes_late",0)
                    msg  = tpl.format(
                        school_name=school,
                        student_name=row.get("student_name",""),
                        class_name=row.get("class_name",""),
                        date=date_str,
                        minutes_late=mins)
                except Exception:
                    msg = "تنبيه: تأخّر ابنكم {} دقيقة بتاريخ {}".format(
                        row.get("minutes_late",0), date_str)

                ok, status = send_whatsapp_message(phone, msg)
                log_status = "تم الإرسال" if ok else "فشل: {}".format(status)

                # سجّل في message_log
                try:
                    created = datetime.datetime.utcnow().isoformat()
                    con = get_db(); cur = con.cursor()
                    cur.execute("""INSERT INTO messages_log
                        (date,student_id,student_name,class_id,class_name,
                         phone,status,template_used,message_type,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (date_str, sid,
                         row.get("student_name",""),
                         row.get("class_id",""),
                         row.get("class_name",""),
                         phone, log_status, msg, "tardiness", created))
                    con.commit(); con.close()
                except Exception: pass

                if ok:
                    ok_cnt += 1
                    self._tard_msg_log_append(
                        "✅ {} ({} دقيقة)".format(
                            row.get("student_name",""), mins))
                    self._tard_msg_update_row(sid, "تم الإرسال", "sent_ok")
                else:
                    fail_cnt += 1
                    short_err = status[:40] if len(status) > 40 else status
                    self._tard_msg_log_append(
                        "❌ {} — {}".format(
                            row.get("student_name",""), status))
                    self._tard_msg_update_row(sid, short_err, "sent_fail")

            summary = "اكتمل — نجح: {} | فشل: {} | تخطّى: {}".format(
                ok_cnt, fail_cnt, skip_cnt)
            self.root.after(0, lambda: (
                self.tard_msg_status.configure(
                    text=summary,
                    foreground="green" if fail_cnt==0 else "orange"),
                self.tard_send_msg_btn.configure(state="normal"),
                messagebox.showinfo("نتيجة الإرسال", summary)
            ))

        threading.Thread(target=do_send, daemon=True).start()

    def _tard_msg_log_append(self, msg: str):
        def _do():
            if not hasattr(self,"tard_msg_log"): return
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.tard_msg_log.configure(state="normal")
            self.tard_msg_log.insert("end","[{}] {}\n".format(ts, msg))
            self.tard_msg_log.see("end")
            self.tard_msg_log.configure(state="disabled")
        self.root.after(0, _do)

    def _tard_msg_update_row(self, iid: str, status: str, tag: str = ""):
        def _do():
            if not self.tree_tard_msg.exists(iid): return
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[-1] = status
            self.tree_tard_msg.item(iid, values=vals,
                                     tags=(tag,) if tag else ())
        self.root.after(0, _do)

    # ══════════════════════════════════════════════════════════
    # تبويب الإشعارات الذكية
    # ══════════════════════════════════════════════════════════
    def _build_alerts_tab(self):
        frame = self.alerts_frame

        # ─ رأس
        hdr = tk.Frame(frame, bg="#7C3AED", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔔 الإشعارات الذكية — تنبيه الغياب المتكرر",
                 bg="#7C3AED", fg="white",
                 font=("Tahoma",13,"bold")).pack(side="right", padx=16, pady=12)

        scroll = ttk.Frame(frame)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ─ إعدادات العتبة
        cfg_lf = ttk.LabelFrame(scroll, text=" ⚙️ إعدادات التنبيه ", padding=12)
        cfg_lf.pack(fill="x", pady=(0,10))

        cfg = load_config()

        # صف 1: العتبة والتفعيل
        r1 = ttk.Frame(cfg_lf); r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="تنبيه عند تجاوز:", width=16, anchor="e").pack(side="right")
        self.alert_thresh_var = tk.IntVar(value=cfg.get("alert_absence_threshold",5))
        ttk.Spinbox(r1, from_=1, to=30,
                    textvariable=self.alert_thresh_var, width=6).pack(side="right", padx=4)
        ttk.Label(r1, text="يوم غياب في الشهر").pack(side="right")

        self.alert_enabled_var = tk.BooleanVar(value=cfg.get("alert_enabled", True))
        ttk.Checkbutton(r1, text="تفعيل الإشعارات التلقائية",
                        variable=self.alert_enabled_var).pack(side="left", padx=20)

        # صف 2: المستلمون
        r2 = ttk.Frame(cfg_lf); r2.pack(fill="x", pady=4)
        self.alert_parent_var = tk.BooleanVar(value=cfg.get("alert_notify_parent", True))
        ttk.Checkbutton(r2, text="إشعار ولي الأمر",
                        variable=self.alert_parent_var).pack(side="right", padx=4)
        self.alert_admin_var = tk.BooleanVar(value=cfg.get("alert_notify_admin", True))
        ttk.Checkbutton(r2, text="إشعار الإدارة",
                        variable=self.alert_admin_var).pack(side="right", padx=4)

        # صف 3: جوال الإدارة
        r3 = ttk.Frame(cfg_lf); r3.pack(fill="x", pady=4)
        ttk.Label(r3, text="جوال الإدارة:", width=16, anchor="e").pack(side="right")
        self.alert_admin_phone_var = tk.StringVar(value=cfg.get("alert_admin_phone",""))
        ttk.Entry(r3, textvariable=self.alert_admin_phone_var,
                  width=20, justify="right").pack(side="right", padx=4)
        ttk.Label(r3, text="(يستلم تنبيهات جميع الطلاب)",
                  foreground="#5A6A7E").pack(side="right")

        # صف 4: وقت التشغيل التلقائي
        r4 = ttk.Frame(cfg_lf); r4.pack(fill="x", pady=4)
        ttk.Label(r4, text="وقت التشغيل اليومي:", width=16, anchor="e").pack(side="right")
        self.alert_hour_var = tk.IntVar(value=14)
        ttk.Spinbox(r4, from_=8, to=20,
                    textvariable=self.alert_hour_var, width=6).pack(side="right", padx=4)
        ttk.Label(r4, text=":00 (يومياً أيام الأحد–الخميس)").pack(side="right")

        btn_row = ttk.Frame(cfg_lf); btn_row.pack(fill="x", pady=(8,0))
        ttk.Button(btn_row, text="💾 حفظ الإعدادات",
                   command=self._save_alert_settings).pack(side="right", padx=4)
        ttk.Button(btn_row, text="▶ تشغيل الإشعارات الآن",
                   command=self._run_alerts_now).pack(side="right", padx=4)

        # ─ جدول الطلاب المتجاوزين للعتبة
        tbl_lf = ttk.LabelFrame(scroll, text=" 📋 الطلاب المتجاوزون للعتبة (هذا الشهر) ", padding=8)
        tbl_lf.pack(fill="both", expand=True, pady=(0,10))

        tbl_hdr = ttk.Frame(tbl_lf); tbl_hdr.pack(fill="x", pady=(0,6))
        self.alert_month_var = tk.StringVar(
            value=datetime.datetime.now().strftime("%Y-%m"))
        ttk.Label(tbl_hdr, text="الشهر (YYYY-MM):").pack(side="right", padx=(0,6))
        ttk.Entry(tbl_hdr, textvariable=self.alert_month_var,
                  width=10).pack(side="right")
        ttk.Button(tbl_hdr, text="🔍 تحديث",
                   command=self._load_alert_students).pack(side="right", padx=4)
        ttk.Button(tbl_hdr, text="📤 إرسال للمحددين",
                   command=self._send_alerts_selected).pack(side="left", padx=4)
        self.alert_sel_lbl = ttk.Label(tbl_hdr, text="", foreground="#7C3AED")
        self.alert_sel_lbl.pack(side="left", padx=8)

        cols = ("chk","student_name","class_name","absence_count",
                "last_date","parent_phone","status")
        self.tree_alerts = ttk.Treeview(tbl_lf, columns=cols,
                                         show="headings", height=12)
        for col, hdr, w in zip(cols,
            ["☐","اسم الطالب","الفصل","أيام الغياب","آخر غياب","جوال ولي الأمر","الحالة"],
            [30,220,150,100,100,130,120]):
            self.tree_alerts.heading(col, text=hdr)
            self.tree_alerts.column(col, width=w, anchor="center")
        self.tree_alerts.tag_configure("high",   background="#FFEBEE", foreground="#C62828")
        self.tree_alerts.tag_configure("medium", background="#FFF8E1", foreground="#E65100")
        self.tree_alerts.tag_configure("sent",   background="#E8F5E9", foreground="#2E7D32")
        sb = ttk.Scrollbar(tbl_lf, orient="vertical", command=self.tree_alerts.yview)
        self.tree_alerts.configure(yscrollcommand=sb.set)
        self.tree_alerts.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree_alerts.bind("<Button-1>", self._alert_toggle_check)

        # ─ سجل الإرسال
        log_lf = ttk.LabelFrame(scroll, text=" 📝 سجل الإرسال ", padding=6)
        log_lf.pack(fill="x")
        self.alert_log = tk.Text(log_lf, height=5, state="disabled",
                                  font=("Tahoma",9), wrap="word")
        self.alert_log.pack(fill="x")

        self._alert_checked = set()
        self._load_alert_students()

    def _save_alert_settings(self):
        cfg = load_config()
        cfg["alert_absence_threshold"] = self.alert_thresh_var.get()
        cfg["alert_enabled"]           = self.alert_enabled_var.get()
        cfg["alert_notify_parent"]     = self.alert_parent_var.get()
        cfg["alert_notify_admin"]      = self.alert_admin_var.get()
        cfg["alert_admin_phone"]       = self.alert_admin_phone_var.get().strip()
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("تم", "تم حفظ إعدادات الإشعارات بنجاح")

    def _load_alert_students(self):
        if not hasattr(self, "tree_alerts"): return
        for i in self.tree_alerts.get_children(): self.tree_alerts.delete(i)
        self._alert_checked.clear()
        month     = self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else datetime.datetime.now().strftime("%Y-%m")
        threshold = self.alert_thresh_var.get() if hasattr(self,"alert_thresh_var") else 5
        students  = get_students_exceeding_threshold(threshold, month)
        for s in students:
            cnt   = s["absence_count"]
            tag   = "high" if cnt >= threshold * 2 else "medium"
            phone = s.get("parent_phone","") or "—"
            self.tree_alerts.insert("", "end", tags=(tag,),
                iid=s["student_id"],
                values=("☐", s["student_name"], s["class_name"],
                        "{} يوم".format(cnt), s["last_date"],
                        phone, ""))
        self.alert_sel_lbl.configure(
            text="إجمالي: {} طالب".format(len(students)))

    def _alert_toggle_check(self, event):
        region = self.tree_alerts.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree_alerts.identify_column(event.x)
        if col != "#1": return  # عمود الـ checkbox فقط
        iid = self.tree_alerts.identify_row(event.y)
        if not iid: return
        if iid in self._alert_checked:
            self._alert_checked.discard(iid)
            vals = list(self.tree_alerts.item(iid, "values"))
            vals[0] = "☐"
            self.tree_alerts.item(iid, values=vals)
        else:
            self._alert_checked.add(iid)
            vals = list(self.tree_alerts.item(iid, "values"))
            vals[0] = "☑"
            self.tree_alerts.item(iid, values=vals)
        self.alert_sel_lbl.configure(
            text="محدد: {} | إجمالي: {}".format(
                len(self._alert_checked),
                len(self.tree_alerts.get_children())))

    def _run_alerts_now(self):
        if not messagebox.askyesno("تأكيد",
            "سيتم إرسال تنبيهات لجميع الطلاب المتجاوزين للعتبة.\nهل تريد المتابعة؟"):
            return
        self._append_alert_log("▶ بدء الإشعارات التلقائية...")
        def do():
            result = run_smart_alerts(
                month=self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else None,
                log_cb=lambda m: self.root.after(0, lambda msg=m: self._append_alert_log(msg)))
            summary = "✅ اكتمل — ولي أمر: {} | إدارة: {} | فشل: {}".format(
                result.get("sent_parent",0),
                result.get("sent_admin",0),
                result.get("failed",0))
            self.root.after(0, lambda: self._append_alert_log(summary))
            self.root.after(0, self._load_alert_students)
        threading.Thread(target=do, daemon=True).start()

    def _send_alerts_selected(self):
        if not self._alert_checked:
            messagebox.showwarning("تنبيه","انقر على ☐ لتحديد الطلاب أولاً"); return
        if not messagebox.askyesno("تأكيد",
            "إرسال تنبيهات لـ {} طالب؟".format(len(self._alert_checked))):
            return
        month  = self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else datetime.datetime.now().strftime("%Y-%m")
        thresh = self.alert_thresh_var.get() if hasattr(self,"alert_thresh_var") else 5
        all_s  = {s["student_id"]: s for s in get_students_exceeding_threshold(thresh, month)}
        selected = [all_s[sid] for sid in self._alert_checked if sid in all_s]
        self._append_alert_log("▶ إرسال لـ {} طالب محدد...".format(len(selected)))
        def do():
            cfg = load_config(); ok_p = ok_a = fail = 0
            for s in selected:
                res = send_alert_for_student(s, cfg)
                if res["parent"]: ok_p += 1
                if res["admin"]:  ok_a += 1
                if res["errors"]: fail += 1
                status = "✅" if (res["parent"] or res["admin"]) else "❌"
                msg = "{} {} — ولي أمر: {} | إدارة: {}".format(
                    status, s["student_name"],
                    "تم" if res["parent"] else "فشل/لا رقم",
                    "تم" if res["admin"]  else "فشل/لا رقم")
                sid = s["student_id"]
                self.root.after(0, lambda m=msg, i=sid: (
                    self._append_alert_log(m),
                    self._update_alert_row(i, "✅ أُرسل" if "✅" in m else "❌ فشل")))
            summary = "اكتمل — ولي أمر: {} | إدارة: {} | فشل: {}".format(ok_p, ok_a, fail)
            self.root.after(0, lambda: self._append_alert_log(summary))
        threading.Thread(target=do, daemon=True).start()

    def _update_alert_row(self, iid, status):
        if not self.tree_alerts.exists(iid): return
        vals = list(self.tree_alerts.item(iid, "values"))
        vals[-1] = status
        self.tree_alerts.item(iid, values=vals,
                               tags=("sent" if "✅" in status else "high",))

    def _append_alert_log(self, msg: str):
        if not hasattr(self, "alert_log"): return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.alert_log.configure(state="normal")
        self.alert_log.insert("end", "[{}] {}\n".format(ts, msg))
        self.alert_log.see("end")
        self.alert_log.configure(state="disabled")

    # ══════════════════════════════════════════════════════════
    # تبويب تصدير نور التلقائي
    # ══════════════════════════════════════════════════════════
    def _build_noor_export_tab(self):
        frame = self.noor_export_frame

        hdr = tk.Frame(frame, bg="#1565C0", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📤 تصدير ملف نور — يدوي وتلقائي",
                 bg="#1565C0", fg="white",
                 font=("Tahoma",13,"bold")).pack(side="right", padx=16, pady=12)

        body = ttk.Frame(frame); body.pack(fill="both", expand=True, padx=15, pady=15)

        # ─ تصدير يدوي
        manual = ttk.LabelFrame(body, text=" 📋 تصدير يدوي ", padding=12)
        manual.pack(fill="x", pady=(0,12))

        mr1 = ttk.Frame(manual); mr1.pack(fill="x", pady=4)
        ttk.Label(mr1, text="التاريخ:", width=14, anchor="e").pack(side="right")
        self.noor_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(mr1, textvariable=self.noor_date_var, width=14).pack(side="right", padx=4)

        mr2 = ttk.Frame(manual); mr2.pack(fill="x", pady=4)
        ttk.Label(mr2, text="مجلد الحفظ:", width=14, anchor="e").pack(side="right")
        self.noor_dir_var = tk.StringVar(value=os.path.abspath(DATA_DIR))
        ttk.Entry(mr2, textvariable=self.noor_dir_var, state="readonly",
                  font=("Courier",9), width=40).pack(side="right", padx=4)
        ttk.Button(mr2, text="تغيير", width=8,
                   command=self._noor_choose_dir).pack(side="left")

        ttk.Button(manual, text="💾 تصدير الآن",
                   command=self._noor_export_now).pack(anchor="e", pady=6)
        self.noor_status = ttk.Label(manual, text="", foreground="green")
        self.noor_status.pack(anchor="e")

        # ─ تصدير تلقائي
        auto = ttk.LabelFrame(body, text=" ⏰ تصدير تلقائي في نهاية اليوم ", padding=12)
        auto.pack(fill="x", pady=(0,12))

        ar1 = ttk.Frame(auto); ar1.pack(fill="x", pady=4)
        self.noor_auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ar1, text="تفعيل التصدير التلقائي اليومي",
                        variable=self.noor_auto_var).pack(side="right")

        ar2 = ttk.Frame(auto); ar2.pack(fill="x", pady=4)
        ttk.Label(ar2, text="وقت التصدير:", width=14, anchor="e").pack(side="right")
        self.noor_hour_var = tk.IntVar(value=13)
        ttk.Spinbox(ar2, from_=10, to=17,
                    textvariable=self.noor_hour_var, width=5).pack(side="right", padx=4)
        ttk.Label(ar2, text=":30 (يومياً أيام الأحد–الخميس)").pack(side="right")

        ttk.Button(auto, text="💾 حفظ إعدادات التصدير التلقائي",
                   command=self._noor_save_auto).pack(anchor="e", pady=6)

        # ─ سجل الملفات المُصدَّرة
        hist = ttk.LabelFrame(body, text=" 📁 ملفات نور المُصدَّرة ", padding=8)
        hist.pack(fill="both", expand=True)

        cols = ("filename","date","size","path")
        self.tree_noor = ttk.Treeview(hist, columns=cols, show="headings", height=8)
        for col, hdr_t, w in zip(cols,
            ["اسم الملف","التاريخ","الحجم","المسار"],
            [200,100,80,300]):
            self.tree_noor.heading(col, text=hdr_t)
            self.tree_noor.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(hist, orient="vertical", command=self.tree_noor.yview)
        self.tree_noor.configure(yscrollcommand=sb.set)
        self.tree_noor.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        ttk.Button(hist, text="📂 فتح المجلد",
                   command=self._noor_open_dir).pack(pady=4)
        frame.after(100, self._noor_load_history)

    def _noor_choose_dir(self):
        d = filedialog.askdirectory(title="اختر مجلد حفظ ملفات نور")
        if d and hasattr(self, "noor_dir_var"):
            self.noor_dir_var.set(d)

    def _noor_export_now(self):
        date_str = self.noor_date_var.get().strip() if hasattr(self,"noor_date_var") else now_riyadh_date()
        save_dir = self.noor_dir_var.get().strip() if hasattr(self,"noor_dir_var") else DATA_DIR
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, "noor_{}.xlsx".format(date_str))
        try:
            export_to_noor_excel(date_str, filename)
            size_kb = os.path.getsize(filename) // 1024
            if hasattr(self,"noor_status"):
                self.noor_status.configure(
                    text="✅ تم التصدير: {} ({} KB)".format(
                        os.path.basename(filename), size_kb),
                    foreground="green")
            frame.after(100, self._noor_load_history)
            messagebox.showinfo("تم التصدير", "تم حفظ ملف نور:\n{}".format(filename))
        except Exception as e:
            if hasattr(self,"noor_status"):
                self.noor_status.configure(
                    text="❌ فشل: {}".format(e), foreground="red")

    def _noor_save_auto(self):
        messagebox.showinfo("تم","إعدادات التصدير التلقائي محفوظة. سيعمل كل يوم عمل في الوقت المحدد.")

    def _noor_open_dir(self):
        d = self.noor_dir_var.get() if hasattr(self,"noor_dir_var") else DATA_DIR
        try: os.startfile(os.path.abspath(d))
        except Exception: webbrowser.open("file://{}".format(os.path.abspath(d)))

    def _noor_load_history(self):
        if not hasattr(self,"tree_noor"): return
        for i in self.tree_noor.get_children(): self.tree_noor.delete(i)
        save_dir = self.noor_dir_var.get().strip() if hasattr(self,"noor_dir_var") else DATA_DIR
        if not os.path.isdir(save_dir): return
        files = sorted(
            [f for f in os.listdir(save_dir) if f.startswith("noor_") and f.endswith(".xlsx")],
            reverse=True)
        for f in files[:30]:
            full = os.path.join(save_dir, f)
            size = "{} KB".format(os.path.getsize(full)//1024) if os.path.exists(full) else "—"
            date = f.replace("noor_","").replace(".xlsx","")
            self.tree_noor.insert("","end", values=(f, date, size, full))

    def update_all_tabs_after_data_change(self):
        """
        A central function to refresh all relevant UI components after underlying data (students.json) has changed.
        """
        self.store = load_students(force_reload=True)

        # حدّث فقط التبويبات المبنية فعلاً (Lazy Loading)
        if hasattr(self, "tree_dash"):         self.update_dashboard_metrics()
        if hasattr(self, "tree_links"):        self._refresh_links_and_teachers()
        if hasattr(self, "tree_logs"):         self.refresh_logs()
        if hasattr(self, "report_class_combo"):self._refresh_report_options()
        if hasattr(self, "tree_phones"):       self.load_students_to_treeview()
        if hasattr(self, "tree_student_management"): self.load_students_to_management_treeview()
        if hasattr(self, "tree_class_naming"): self.load_class_names_to_treeview()
        if hasattr(self, "msg_canvas"):        self._msg_load_groups()
        if hasattr(self, "schedule_widgets"):  self.populate_schedule_table()
        if hasattr(self, "tree_tard"):         self._tard_load()
        if hasattr(self, "tree_excuses"):      self._exc_load()
        if hasattr(self, "tree_users"):        self._users_load()
        if hasattr(self, "tree_backup"):       self.root.after(100, self._backup_load)
        if hasattr(self, "_term_backup_list"): self._load_term_backups()
        
    def _refresh_report_options(self):
        class_ids = ["(كل الفصول)"] + [c["id"] for c in self.store["list"]]
        self.report_class_combo['values'] = class_ids
        self.report_class_combo.current(0)

    def _build_live_monitor_tab(self):
        frame = self.live_monitor_frame
        links_frame = ttk.LabelFrame(frame, text=" روابط الوصول الخارجي (للمتصفحات الأخرى) ", padding=10)
        links_frame.pack(fill="x", pady=5, padx=5)
        def copy_to_clipboard(text_to_copy):
            self.root.clipboard_clear(); self.root.clipboard_append(text_to_copy); messagebox.showinfo("تم النسخ", "تم نسخ الرابط إلى الحافظة بنجاح!")
        local_frame = ttk.Frame(links_frame); local_frame.pack(fill="x", pady=2)
        monitor_url_local = f"http://{self.ip}:{PORT}/monitor"
        ttk.Label(local_frame, text="الرابط المحلي:", width=12 ).pack(side="right", padx=5)
        local_link_entry = ttk.Entry(local_frame, font=("Segoe UI", 9)); local_link_entry.insert(0, monitor_url_local)
        local_link_entry.config(state="readonly"); local_link_entry.pack(side="right", fill="x", expand=True)
        ttk.Button(local_frame, text="📋 نسخ", width=8, command=lambda: copy_to_clipboard(monitor_url_local)).pack(side="left", padx=5)
        if self.public_url:
            public_frame = ttk.Frame(links_frame); public_frame.pack(fill="x", pady=2)
            monitor_url_public = self.public_url + "/monitor"
            ttk.Label(public_frame, text="الرابط العام:", width=12).pack(side="right", padx=5)
            public_link_entry = ttk.Entry(public_frame, font=("Segoe UI", 9)); public_link_entry.insert(0, monitor_url_public)
            public_link_entry.config(state="readonly"); public_link_entry.pack(side="right", fill="x", expand=True)
            ttk.Button(public_frame, text="📋 نسخ", width=8, command=lambda: copy_to_clipboard(monitor_url_public)).pack(side="left", padx=5)
        browser_frame = ttk.Frame(frame, padding=(0, 10, 0, 0)); browser_frame.pack(fill="both", expand=True)
        _ensure_tkinterweb()
        live_monitor_browser = HtmlFrame(browser_frame, horizontal_scrollbar="auto"); live_monitor_browser.pack(fill="both", expand=True)
        def update_browser_content():
            try:
                today = now_riyadh_date()
                status_data = get_live_monitor_status(today)
                html_content = generate_monitor_table_html(status_data)
                now_str = datetime.datetime.now().strftime('%H:%M:%S')
                final_html = html_content.replace('<p id="last-update"></p>', f'<p id="last-update">آخر تحديث: {now_str}</p>')
                live_monitor_browser.load_html(final_html)
                self.root.after(15000, update_browser_content)
            except Exception as e:
                print(f"Error updating live monitor: {e}")
                live_monitor_browser.load_html(f"<h3>حدث خطأ أثناء التحديث: {e}</h3>")
                self.root.after(30000, update_browser_content)
        self.root.after(500, update_browser_content)

    def reimport_students(self):
        path = filedialog.askopenfilename(title="اختر ملف Excel (طلاب)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: return

        try:
            with open(STUDENTS_JSON, "r", encoding="utf-8") as f:
                current_data = json.load(f)
            custom_names_map = {c['id']: c['name'] for c in current_data.get('classes', [])}
        except (FileNotFoundError, json.JSONDecodeError):
            custom_names_map = {}

        try:
            import_students_from_excel_sheet2_format(path)
            
            if custom_names_map:
                with open(STUDENTS_JSON, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                
                for c in new_data.get('classes', []):
                    if c['id'] in custom_names_map:
                        c['name'] = custom_names_map[c['id']]
                
                with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("تم", "تم تحديث الطلاب بنجاح مع الحفاظ على أسماء الفصول المخصصة.")
            self.update_all_tabs_after_data_change()

        except Exception as e:
            messagebox.showerror("خطأ في استيراد الطلاب", str(e))


    def reimport_teachers(self):
        path = filedialog.askopenfilename(title="اختر ملف Excel (معلمون)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: return
        try:
            import_teachers_from_excel(path)
            self.teachers_data = load_teachers()
            messagebox.showinfo("تم", "تم تحديث المعلمين بنجاح.")
            self._refresh_links_and_teachers()
        except Exception as e:
            messagebox.showerror("خطأ في استيراد المعلمين", str(e))

    def _open_school_settings_tab(self):
        """ينتقل مباشرة إلى تبويب إعدادات المدرسة."""
        if hasattr(self, "_switch_tab") and "إعدادات المدرسة" in self._tab_frames:
            self._switch_tab("إعدادات المدرسة")
        else:
            messagebox.showinfo("تنبيه", "التبويب غير متاح لهذا المستخدم.")

    def open_config_json(self):
        """يفتح نافذة تعديل config.json داخل البرنامج."""
        ensure_dirs()
        if not os.path.exists(CONFIG_JSON):
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)

        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                content_str = f.read()
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر قراءة الملف:\n{e}")
            return

        win = tk.Toplevel(self.root)
        win.title("تعديل ملف الإعدادات — config.json")
        win.geometry("800x600")
        win.transient(self.root)

        # شريط العنوان
        hdr = tk.Frame(win, bg="#1565C0", height=40)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙ تعديل config.json",
                 bg="#1565C0", fg="white",
                 font=("Tahoma", 11, "bold")).pack(side="right", padx=12, pady=8)
        tk.Label(hdr, text=os.path.abspath(CONFIG_JSON),
                 bg="#1565C0", fg="#90CAF9",
                 font=("Courier", 8)).pack(side="left", padx=12, pady=8)

        # منطقة النص
        txt_frame = ttk.Frame(win); txt_frame.pack(fill="both", expand=True, padx=8, pady=6)
        txt = tk.Text(txt_frame, font=("Courier New", 10), wrap="none",
                      undo=True, relief="solid", bd=1)
        vsb = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(txt_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", content_str)

        # أزرار
        btn_frame = ttk.Frame(win); btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        status_lbl = ttk.Label(btn_frame, text="", foreground="green", font=("Tahoma", 9))
        status_lbl.pack(side="right", padx=8)

        def _save():
            raw = txt.get("1.0", "end").strip()
            try:
                parsed = json.loads(raw)  # تحقق من صحة JSON
                with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, ensure_ascii=False, indent=2)
                status_lbl.config(text="✅ تم الحفظ بنجاح", foreground="green")
                win.after(3000, lambda: status_lbl.config(text=""))
            except json.JSONDecodeError as e:
                messagebox.showerror("خطأ JSON", f"الملف يحتوي على خطأ:\n{e}", parent=win)

        def _open_external():
            try:
                os.startfile(os.path.abspath(CONFIG_JSON))
            except Exception:
                webbrowser.open(f"file://{os.path.abspath(CONFIG_JSON)}")

        def _format():
            raw = txt.get("1.0", "end").strip()
            try:
                parsed = json.loads(raw)
                formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
                txt.delete("1.0", "end")
                txt.insert("1.0", formatted)
                status_lbl.config(text="✅ تم التنسيق", foreground="green")
            except json.JSONDecodeError as e:
                messagebox.showerror("خطأ", f"لا يمكن التنسيق:\n{e}", parent=win)

        ttk.Button(btn_frame, text="💾 حفظ", command=_save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="✨ تنسيق JSON", command=_format).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="📂 فتح بالمفكرة", command=_open_external).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="✖ إغلاق", command=win.destroy).pack(side="left", padx=4)

    def _build_schedule_tab(self):
        self.cfg = load_config()
        frame = self.schedule_frame
        self.schedule_widgets = {}
        self.schedule_time_vars = {}

        today_weekday = (datetime.datetime.now().weekday() + 1) % 7
        default_day = today_weekday if today_weekday <= 4 else 0
        self.selected_day_var = tk.IntVar(value=default_day)

        days_frame = ttk.Frame(frame, padding=(10, 5))
        days_frame.pack(fill="x", side="top")
        ttk.Label(days_frame, text="اختر اليوم لعرض/تعديل جدوله:", font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 10))
        
        days_map = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}
        for day_index, day_name in days_map.items():
            rb = ttk.Radiobutton(days_frame, text=day_name, variable=self.selected_day_var, value=day_index, command=self.populate_schedule_table)
            rb.pack(side="right", padx=5)

        main_controls_frame = ttk.Frame(frame, padding=10)
        main_controls_frame.pack(fill="x", side="top")

        buttons_frame = ttk.Frame(main_controls_frame)
        buttons_frame.pack(side="right", fill="y", padx=(10, 0))
        self.start_scheduler_button = ttk.Button(buttons_frame, text="🚀 بدء الإرسال الآلي (لليوم)", command=self.start_scheduler)
        self.start_scheduler_button.pack(fill="x", pady=2)
        self.stop_scheduler_button = ttk.Button(buttons_frame, text="🛑 إيقاف الإرسال", command=self.stop_scheduler, state="disabled")
        self.stop_scheduler_button.pack(fill="x", pady=2)
        ttk.Button(buttons_frame, text="💾 حفظ الجدول والتواقيت", command=self.on_save_schedule_and_times).pack(fill="x", pady=(10, 2))
        ttk.Button(buttons_frame, text="🔄 تحديث الجدول", command=self.populate_schedule_table).pack(fill="x", pady=2)
        self._schedule_last_sync = ttk.Label(buttons_frame, text="", foreground="#888", font=("Tahoma", 8))
        self._schedule_last_sync.pack(fill="x", pady=(0,2))
        
        # --- NEW: Web Editor and Clear Buttons ---
        web_buttons_frame = ttk.Frame(buttons_frame)
        web_buttons_frame.pack(fill="x", pady=(10, 0))
        
        web_menu = tk.Menu(web_buttons_frame, tearoff=0)
        web_menu.add_command(label="فتح الرابط المحلي", command=lambda: self.open_schedule_editor('local'))
        if self.public_url:
            web_menu.add_command(label="فتح الرابط العالمي", command=lambda: self.open_schedule_editor('public'))
        else:
            web_menu.add_command(label="فتح الرابط العالمي (معطل)", state="disabled")

        menubutton = ttk.Menubutton(web_buttons_frame, text="✏️ تعديل الجدول من الويب", menu=web_menu, direction="below")
        menubutton.pack(fill="x", pady=2)

        ttk.Button(web_buttons_frame, text="🗑️ مسح الجدول الحالي", command=self.clear_current_schedule).pack(fill="x", pady=2)
        # --- END NEW ---

        # ─── وقت بداية الدوام (لحساب التأخر) ──────────────────
        start_frame = ttk.LabelFrame(main_controls_frame, text=" 🏫 بداية الدوام ")
        start_frame.pack(side="right", fill="y", padx=(0,6))
        ttk.Label(start_frame, text="وقت بداية الدوام:", font=("Tahoma",10)).pack(pady=(8,2))
        self.school_start_var = tk.StringVar(
            value=self.cfg.get("school_start_time","07:00"))
        start_entry = ttk.Entry(start_frame, textvariable=self.school_start_var,
                                 width=8, justify="center", font=("Courier",12,"bold"))
        start_entry.pack(padx=10, pady=4)
        ttk.Label(start_frame, text="(HH:MM)", foreground="#5A6A7E",
                  font=("Tahoma",8)).pack()
        ttk.Label(start_frame,
                  text="يُستخدم لحساب\ndقائق التأخر",
                  foreground="#5A6A7E", font=("Tahoma",8),
                  justify="center").pack(pady=(4,8))
        # ──────────────────────────────────────────────────────

        times_frame = ttk.LabelFrame(main_controls_frame, text="⏰ توقيت الحصص (HH:MM)")
        times_frame.pack(side="right", fill="y", padx=10)
        
        default_times = self.cfg.get("period_times", ["07:00", "07:50", "08:40", "09:50", "10:40", "11:30", "12:20"])
        for i in range(7):
            period = i + 1
            row = ttk.Frame(times_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"الحصة {period}:").pack(side="right")
            
            time_var = tk.StringVar(value=default_times[i] if i < len(default_times) else "")
            time_entry = ttk.Entry(row, textvariable=time_var, width=7, justify='center')
            time_entry.pack(side="left", padx=5)
            self.schedule_time_vars[period] = time_var

        status_frame = ttk.LabelFrame(main_controls_frame, text="📝 سجل الحالة")
        status_frame.pack(side="left", fill="both", expand=True)
        self.scheduler_log = tk.Text(status_frame, height=8, width=50, state="disabled", wrap="word", font=("Segoe UI", 9))
        log_scroll = ttk.Scrollbar(status_frame, orient="vertical", command=self.scheduler_log.yview)
        self.scheduler_log.config(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.scheduler_log.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        table_container = ttk.Frame(frame)
        table_container.pack(fill="both", expand=True, padx=5, pady=5)

        canvas = tk.Canvas(table_container)
        scrollbar_y = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x = ttk.Scrollbar(table_container, orient="horizontal", command=canvas.xview)
        scrollbar_x.pack(side="bottom", fill="x")
        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        canvas.pack(side="left", fill="both", expand=True)
        self.schedule_table_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=self.schedule_table_frame, anchor="nw")
        self.schedule_table_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        self.populate_schedule_table()

        # ── تحديث تلقائي كل 30 ثانية لمزامنة التغييرات من الويب ──
        self._schedule_auto_refresh_active = True
        def _auto_refresh_schedule():
            if not self._schedule_auto_refresh_active:
                return
            if self._current_tab.get() == "جدولة الروابط":
                self.populate_schedule_table()
                if hasattr(self, "_schedule_last_sync"):
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    self._schedule_last_sync.config(text=f"آخر تحديث: {now}")
            frame.after(30000, _auto_refresh_schedule)
        frame.after(30000, _auto_refresh_schedule)

    def open_schedule_editor(self, link_type: str):
        if link_type == 'local':
            url = f"http://{self.ip}:{PORT}/schedule/edit"
        elif link_type == 'public':
            if not self.public_url:
                messagebox.showerror("خطأ", "الرابط العالمي غير متاح حاليًا." )
                return
            url = f"{self.public_url}/schedule/edit"
        else:
            return
        webbrowser.open(url)

    def clear_current_schedule(self):
        password = simpledialog.askstring("تأكيد", "للمتابعة، الرجاء إدخال كلمة المرور:", show='*')
        if password != "123":
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return
        
        selected_day = self.selected_day_var.get()
        day_name = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}.get(selected_day, "المحدد")
        
        if not messagebox.askyesno("تأكيد المسح", f"هل أنت متأكد من أنك تريد مسح جميع مدخلات جدول يوم {day_name}؟\nلا يمكن التراجع عن هذا الإجراء."):
            return
            
        try:
            save_schedule(selected_day, []) # Save an empty schedule
            self.populate_schedule_table() # Refresh the UI
            messagebox.showinfo("تم المسح", f"تم مسح جدول يوم {day_name} بنجاح.")
        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ أثناء مسح الجدول: {e}")

    # ══════════════════════════════════════════════════════════
    # إعداد مستلمي رابط التأخر (داخل تبويب جدولة الروابط)
    # ══════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════
    # تبويب مستقل: مستلمو رابط التأخر
    # ══════════════════════════════════════════════════════════
    def _build_tardiness_recipients_tab(self):
        """يبني تبويب إدارة مستلمي رابط التأخر."""
        frame = self.tardiness_recipients_frame

        # عنوان التبويب
        hdr = tk.Frame(frame, bg="#E65100", height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⏱ إعداد إرسال رابط التأخر التلقائي",
                 bg="#E65100", fg="white",
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=16, pady=12)

        tk.Label(frame,
            text="يُرسَل رابط تسجيل التأخر (كل طلاب المدرسة) لجميع المستلمين "
                 "تلقائياً في وقت بداية الدوام يومياً — أو يدوياً بضغطة زر.",
            font=("Tahoma", 10), fg="#444", justify="right",
            wraplength=900
        ).pack(anchor="e", padx=16, pady=(10, 0))

        # ─── مؤشر خادم الواتساب المختصر ─────────────────────────
        wa_mini = ttk.LabelFrame(frame, text=" 🟢 خادم واتساب ", padding=6)
        wa_mini.pack(fill="x", padx=10, pady=(6, 0))
        wa_mini_row = ttk.Frame(wa_mini); wa_mini_row.pack(fill="x")

        self._wa_mini_dot = tk.Label(wa_mini_row, text="⬤", font=("Tahoma", 13), fg="#aaaaaa")
        self._wa_mini_dot.pack(side="right", padx=(0, 4))
        self._wa_mini_text = ttk.Label(wa_mini_row, text="جارٍ التحقق...", font=("Tahoma", 9))
        self._wa_mini_text.pack(side="right", padx=(0, 6))

        def _mini_start_wa():
            if not os.path.isdir(WHATS_PATH):
                messagebox.showerror("خطأ", "مجلد الواتساب غير موجود:\n" + WHATS_PATH)
                return
            try:
                # يشغّل الخادم مع تعطيل البوت تلقائياً
                cmd = rf'cmd.exe /k "cd /d {WHATS_PATH} && node server.js"'
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self._wa_mini_text.config(text="جارٍ التشغيل... انتظر 10 ثوانٍ")
                # بعد تشغيل الخادم أوقف البوت تلقائياً
                def _disable_bot_after_start():
                    try:
                        import urllib.request as _ur
                        data = json.dumps({"enabled": False}).encode()
                        req = _ur.Request("http://localhost:3000/bot-toggle",
                                          data=data,
                                          headers={"Content-Type": "application/json"},
                                          method="POST")
                        _ur.urlopen(req, timeout=3)
                        print("[WA] البوت مُوقَف تلقائياً عند التشغيل من تبويب التأخر")
                    except Exception:
                        pass
                frame.after(10000, _mini_check)
                frame.after(11000, _disable_bot_after_start)
            except Exception as e:
                messagebox.showerror("خطأ", "تعذّر التشغيل:\n" + str(e))

        def _mini_check():
            try:
                import urllib.request, json as _j
                r = urllib.request.urlopen("http://localhost:3000/status", timeout=1)
                data = _j.loads(r.read())
                if data.get("ready"):
                    self._wa_mini_dot.config(fg="#22c55e")
                    self._wa_mini_text.config(text="✅ متصل ويعمل", foreground="#166534")
                else:
                    self._wa_mini_dot.config(fg="#f59e0b")
                    self._wa_mini_text.config(text="⏳ يعمل — امسح QR", foreground="#92400e")
            except Exception:
                self._wa_mini_dot.config(fg="#ef4444")
                self._wa_mini_text.config(text="🔴 غير متصل", foreground="#991b1b")
            frame.after(15000, _mini_check)

        ttk.Button(wa_mini_row, text="▶ تشغيل",
                   command=_mini_start_wa).pack(side="left", padx=4)
        ttk.Button(wa_mini_row, text="🔄",
                   command=_mini_check).pack(side="left", padx=2)

        frame.after(200, _mini_check)

        # بناء الواجهة الرئيسية
        self._build_tardiness_recipients_ui(frame)

    def _build_tardiness_recipients_ui(self, parent_frame):
        """يبني واجهة إدارة مستلمي رابط التأخر."""

        lf = ttk.LabelFrame(
            parent_frame,
            text=" 📤 مستلمو رابط التأخر التلقائي ",
            padding=10
        )
        lf.pack(fill="both", expand=True, padx=10, pady=(8,4))

        # رابط التأخر للنسخ — يُحسب دائماً من local_ip الحي
        def get_tard_url():
            base = (STATIC_DOMAIN if STATIC_DOMAIN and not debug_on()
                    else "http://{}:{}".format(local_ip(), PORT))
            return "{}/tardiness".format(base)

        url_row = ttk.Frame(lf); url_row.pack(fill="x", pady=(0,8))
        ttk.Label(url_row, text="رابط التأخر:", font=("Tahoma",9,"bold")).pack(side="right", padx=(0,6))
        self.tard_url_var = tk.StringVar(value=get_tard_url())
        url_entry = ttk.Entry(url_row, textvariable=self.tard_url_var,
                               state="readonly", font=("Courier",9))
        url_entry.pack(side="right", fill="x", expand=True)

        def copy_url():
            url = get_tard_url()
            self.tard_url_var.set(url)   # تحديث فوري
            self.root.clipboard_clear()
            self.root.clipboard_append(url)

        def refresh_url():
            self.tard_url_var.set(get_tard_url())

        btn_frame = ttk.Frame(url_row); btn_frame.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="نسخ",    width=5, command=copy_url).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="تحديث",  width=5, command=refresh_url).pack(side="right", padx=2)

        # تحديث الرابط تلقائياً بعد ثانية (بعد أن يكون الخادم جاهزاً)
        lf.after(1500, refresh_url)

        # أزرار الإرسال اليدوي
        send_row = ttk.Frame(lf); send_row.pack(fill="x", pady=(0,8))
        self.tard_send_btn = ttk.Button(
            send_row, text="📲 إرسال الرابط الآن للجميع",
            command=self._send_tardiness_now)
        self.tard_send_btn.pack(side="right", padx=4)
        self.tard_status_lbl = ttk.Label(
            send_row, text="", foreground="green", font=("Tahoma",9))
        self.tard_status_lbl.pack(side="right", padx=8)

        # حالة الجدول التلقائي
        auto_row = ttk.Frame(lf); auto_row.pack(fill="x", pady=(0,8))
        self.tard_auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            auto_row,
            text="إرسال تلقائي عند بداية الدوام",
            variable=self.tard_auto_var
        ).pack(side="right")
        ttk.Label(auto_row, text="(يتم يومياً أيام الأحد—الخميس)",
                  foreground="#5A6A7E", font=("Tahoma",9)).pack(side="right", padx=6)

        ttk.Separator(lf, orient="horizontal").pack(fill="x", pady=6)

        # ─ إضافة مستلم
        add_row = ttk.Frame(lf); add_row.pack(fill="x", pady=(0,6))
        ttk.Label(add_row, text="اسم المستلم:", width=12, anchor="e").pack(side="right")
        self.tard_name_var  = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.tard_name_var,
                  width=20, justify="right").pack(side="right", padx=4)
        ttk.Label(add_row, text="الجوال:", width=7, anchor="e").pack(side="right", padx=(8,0))
        self.tard_phone_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.tard_phone_var,
                  width=14, justify="right").pack(side="right", padx=4)
        ttk.Button(add_row, text="➕ إضافة",
                   command=self._tard_recipient_add).pack(side="right", padx=4)

        # ─ جدول المستلمين
        cols = ("name","phone","role")
        self.tree_tard_recv = ttk.Treeview(
            lf, columns=cols, show="headings", height=6)
        for col, hdr, w in zip(cols,
            ["الاسم", "رقم الجوال", "الدور/الوظيفة"],
            [200, 140, 160]):
            self.tree_tard_recv.heading(col, text=hdr)
            self.tree_tard_recv.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(lf, orient="vertical",
                            command=self.tree_tard_recv.yview)
        self.tree_tard_recv.configure(yscrollcommand=sb.set)
        self.tree_tard_recv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        del_row = ttk.Frame(lf); del_row.pack(fill="x", pady=(6,0))
        ttk.Button(del_row, text="🗑️ حذف المحدد",
                   command=self._tard_recipient_del).pack(side="right", padx=4)
        ttk.Button(del_row, text="استيراد من قائمة المعلمين",
                   command=self._tard_import_teachers).pack(side="right", padx=4)

        self._tard_recipients_load()

    def _tard_recipients_load(self):
        if not hasattr(self, "tree_tard_recv"): return
        for i in self.tree_tard_recv.get_children():
            self.tree_tard_recv.delete(i)
        for r in get_tardiness_recipients():
            self.tree_tard_recv.insert("", "end",
                values=(r.get("name",""), r.get("phone",""), r.get("role","")))

    def _tard_recipient_add(self):
        name  = self.tard_name_var.get().strip() if hasattr(self,"tard_name_var") else ""
        phone = self.tard_phone_var.get().strip() if hasattr(self,"tard_phone_var") else ""
        if not name or not phone:
            messagebox.showwarning("تنبيه", "أدخل الاسم ورقم الجوال")
            return
        role = simpledialog.askstring(
            "الدور", "ما دور/وظيفة '"+name+"'؟ (اختياري)",
            parent=self.root) or ""
        recps = get_tardiness_recipients()
        # تجنب التكرار
        if any(r["phone"]==phone for r in recps):
            messagebox.showwarning("تنبيه","رقم الجوال موجود مسبقاً")
            return
        recps.append({"name":name,"phone":phone,"role":role})
        save_tardiness_recipients(recps)
        self.tard_name_var.set("")
        self.tard_phone_var.set("")
        self._tard_recipients_load()

    def _tard_recipient_del(self):
        if not hasattr(self,"tree_tard_recv"): return
        sel = self.tree_tard_recv.selection()
        if not sel:
            messagebox.showwarning("تنبيه","حدد مستلماً أولاً")
            return
        vals  = self.tree_tard_recv.item(sel[0])["values"]
        phone = vals[1]
        if not messagebox.askyesno("تأكيد",f"حذف '{vals[0]}'؟"): return
        recps = [r for r in get_tardiness_recipients() if r.get("phone")!=phone]
        save_tardiness_recipients(recps)
        self._tard_recipients_load()

    def _tard_import_teachers(self):
        """يستورد أرقام المعلمين من قائمة المعلمين الموجودة."""
        teachers_data = load_teachers()
        teachers      = teachers_data.get("teachers", [])
        recps         = get_tardiness_recipients()
        existing_phones = {r["phone"] for r in recps}
        added = 0
        for t in teachers:
            name  = t.get("اسم المعلم","")
            phone = t.get("رقم الجوال","")
            if phone and phone not in existing_phones:
                recps.append({"name":name,"phone":phone,"role":"معلم"})
                existing_phones.add(phone)
                added += 1
        save_tardiness_recipients(recps)
        self._tard_recipients_load()
        messagebox.showinfo("تم",f"تم استيراد {added} معلم من قائمة المعلمين.")

    def _send_tardiness_now(self):
        """يرسل رابط التأخر الآن لجميع المستلمين."""
        if not hasattr(self,"tard_send_btn"): return
        recps = get_tardiness_recipients()
        if not recps:
            messagebox.showwarning("تنبيه","لا يوجد مستلمون. أضف مستلمين أولاً.")
            return
        if not check_whatsapp_server_status():
            messagebox.showerror("خطأ","خادم واتساب غير متاح. شغّله أولاً.")
            return
        self.tard_send_btn.config(state="disabled")
        if hasattr(self,"tard_status_lbl"):
            self.tard_status_lbl.config(
                text=f"⏳ جارٍ الإرسال لـ {len(recps)} مستلم...",
                foreground="blue")
        self.root.update_idletasks()

        def do_send():
            sent, failed, details = send_tardiness_link_to_all()
            detail_txt = "\n".join(details)
            self.root.after(0, lambda: self._after_tardiness_send(
                sent, failed, detail_txt))

        threading.Thread(target=do_send, daemon=True).start()

    def _after_tardiness_send(self, sent, failed, detail_txt):
        if hasattr(self,"tard_send_btn"):
            self.tard_send_btn.config(state="normal")
        if hasattr(self,"tard_status_lbl"):
            color = "green" if failed==0 else ("orange" if sent>0 else "red")
            self.tard_status_lbl.config(
                text=f"✅ {sent} | ❌ {failed}",
                foreground=color)
        messagebox.showinfo(
            "نتيجة الإرسال",
            "تم الإرسال بنجاح: {}\nفشل: {}\n\nالتفاصيل:\n{}".format(
                sent, failed, detail_txt))

    def populate_schedule_table(self):
        for widget in self.schedule_table_frame.winfo_children():
            widget.destroy()
        self.schedule_widgets.clear()

        selected_day = self.selected_day_var.get()
        classes = sorted(self.store["list"], key=lambda c: c['id'])
        teachers_data = load_teachers()
        teacher_names = [""] + [t["اسم المعلم"] for t in teachers_data.get("teachers", [])]
        saved_schedule = load_schedule(selected_day)

        header_font = ("Segoe UI", 10, "bold")
        ttk.Label(self.schedule_table_frame, text="الحصة", font=header_font, borderwidth=1, relief="solid", padding=5).grid(row=0, column=0, sticky="nsew")
        for col_idx, cls in enumerate(classes, 1):
            ttk.Label(self.schedule_table_frame, text=cls['name'], font=header_font, borderwidth=1, relief="solid", padding=5, anchor="center").grid(row=0, column=col_idx, sticky="nsew")

        for period in range(1, 8):
            ttk.Label(self.schedule_table_frame, text=f"الحصة {period}", font=header_font, borderwidth=1, relief="solid", padding=5).grid(row=period, column=0, sticky="nsew")
            for col_idx, cls in enumerate(classes, 1):
                class_id = cls['id']
                combo = ttk.Combobox(self.schedule_table_frame, values=teacher_names, state="readonly", justify='center', width=15)
                
                # Dynamic width adjustment
                max_len = max(len(name) for name in teacher_names) if teacher_names else 15
                combo.bind('<Button-1>', lambda e, c=combo, w=max_len: c.config(width=w))

                combo.grid(row=period, column=col_idx, sticky="nsew", padx=1, pady=1)
                teacher = saved_schedule.get((class_id, period))
                if teacher in teacher_names:
                    combo.set(teacher)
                self.schedule_widgets[(class_id, period)] = combo

    def log_scheduler_message(self, message):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        full_message = f"[{now}] {message}\n"
        self.scheduler_log.config(state="normal")
        self.scheduler_log.insert("1.0", full_message)
        self.scheduler_log.config(state="disabled")

    def on_save_schedule_and_times(self):
        selected_day = self.selected_day_var.get()
        day_name = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}.get(selected_day, "المحدد")

        schedule_data = []
        for period in range(1, 8):
            for cls in self.store["list"]:
                widget = self.schedule_widgets.get((cls['id'], period))
                if widget:
                    schedule_data.append({"class_id": cls['id'], "period": period, "teacher_name": widget.get()})
        try:
            save_schedule(selected_day, schedule_data)
        except Exception as e:
            messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ جدول يوم {day_name}:\n{e}")
            return

        period_times = [self.schedule_time_vars[p].get() for p in range(1, 8)]
        self.cfg["period_times"] = period_times
        # حفظ وقت بداية الدوام
        if hasattr(self, "school_start_var"):
            self.cfg["school_start_time"] = self.school_start_var.get().strip()
        try:
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ التواقيت:\n{e}")
            return
            
        messagebox.showinfo("تم الحفظ", f"تم حفظ جدول يوم {day_name} والتواقيت بنجاح.")
        self.log_scheduler_message(f"تم حفظ جدول يوم {day_name}.")


    def start_scheduler(self):
        today = datetime.datetime.now()
        day_of_week = (today.weekday() + 1) % 7 
        
        if day_of_week > 4:
            messagebox.showwarning("يوم عطلة", "لا يمكن بدء المرسل الآلي في يوم عطلة نهاية الأسبوع.")
            self.log_scheduler_message("⚠️ محاولة بدء الإرسال في يوم عطلة. تم الرفض.")
            return

        if self.scheduler_running:
            messagebox.showwarning("قيد التشغيل", "المرسل الآلي يعمل بالفعل.")
            return

        if not messagebox.askyesno("تأكيد البدء", "هل أنت متأكد من أنك تريد بدء الإرسال الآلي لروابط الحصص؟"):
            return

        self.scheduler_running = True
        self.start_scheduler_button.config(state="disabled")
        self.stop_scheduler_button.config(state="normal")
        day_name = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}.get(day_of_week)
        self.log_scheduler_message(f"🚀 تم بدء المرسل الآلي لجدول يوم {day_name}.")

        schedule = load_schedule(day_of_week)
        if not schedule:
            self.log_scheduler_message(f"⚠️ تحذير: جدول يوم {day_name} فارغ. لن يتم إرسال أي شيء.")
            self.stop_scheduler()
            return

        now = datetime.datetime.now()
        base_url = self.public_url or f"http://{self.ip}:{PORT}"
        
        for period in range(1, 8  ):
            time_str = self.schedule_time_vars[period].get()
            try:
                hour, minute = map(int, time_str.split(':'))
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                delay = (target_time - now).total_seconds()
                if delay < 0:
                    self.log_scheduler_message(f"الحصة {period} ({time_str}): الوقت قد فات. تم تخطيها.")
                    continue

                timer = threading.Timer(delay, self.send_links_for_period, args=[period, schedule, base_url])
                self.scheduler_timers.append(timer)
                timer.start()
                self.log_scheduler_message(f"الحصة {period}: تمت جدولتها للإرسال الساعة {time_str}.")

            except (ValueError, AttributeError):
                self.log_scheduler_message(f"الحصة {period}: صيغة الوقت ({time_str}) غير صالحة. تم تخطيها.")
        
        if not self.scheduler_timers:
            self.log_scheduler_message("لم تتم جدولة أي حصص. تأكد من التواقيت.")
            self.stop_scheduler()


    def stop_scheduler(self):
        for timer in self.scheduler_timers:
            timer.cancel()
        
        self.scheduler_timers = []
        self.scheduler_running = False
        self.start_scheduler_button.config(state="normal")
        self.stop_scheduler_button.config(state="disabled")
        self.log_scheduler_message("🛑 تم إيقاف المرسل الآلي.")

    def send_links_for_period(self, period, schedule, base_url):
        self.log_scheduler_message(f"🔔 حان وقت الحصة {period}! جارٍ إرسال الروابط...")
        
        teachers_to_notify = {}
        
        for (class_id, p), teacher_name in schedule.items():
            if p == period and teacher_name:
                class_info = self.store["by_id"].get(class_id)
                if class_info:
                    if teacher_name not in teachers_to_notify:
                        teachers_to_notify[teacher_name] = []
                    teachers_to_notify[teacher_name].append(class_info)

        if not teachers_to_notify:
            self.log_scheduler_message(f"الحصة {period}: لا يوجد معلمون مجدولون لهذه الحصة.")
            return

        all_teachers = {t["اسم المعلم"]: t for t in load_teachers().get("teachers", [])}

        for teacher_name, assigned_classes in teachers_to_notify.items():
            teacher_data = all_teachers.get(teacher_name)
            if not teacher_data or not teacher_data.get("رقم الجوال"):
                self.log_scheduler_message(f"الحصة {period}: فشل إرسال لـ '{teacher_name}' (لا يوجد رقم جوال).")
                continue

            links_text = "\n".join([f"- فصل: {c['name']}\n  الرابط: {base_url}/c/{c['id']}" for c in assigned_classes])
            message_body = (
                f"السلام عليكم أ. {teacher_name},\n"
                f"إليك روابط تسجيل الغياب للحصة {period}:\n\n"
                f"{links_text}\n\n"
                "مع تحيات إدارة المدرسة."
            )
            
            success, msg = send_whatsapp_message(teacher_data["رقم الجوال"], message_body)
            
            if success:
                self.log_scheduler_message(f"✅ تم إرسال روابط الحصة {period} إلى '{teacher_name}'.")
            else:
                self.log_scheduler_message(f"❌ فشل إرسال لـ '{teacher_name}': {msg}")


    def _build_add_student_tab(self):
        frame = self.add_student_frame

    # الحقول
        ttk.Label(frame, text="الاسم الكامل:").grid(row=0, column=1, padx=10, pady=10, sticky="e")
        self.add_name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.add_name_var, width=40).grid(row=0, column=0, padx=10, pady=10, sticky="w")
    
        ttk.Label(frame, text="الرقم الأكاديمي:").grid(row=1, column=1, padx=10, pady=10, sticky="e")
        self.add_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.add_id_var, width=40).grid(row=1, column=0, padx=10, pady=10, sticky="w")
    
        ttk.Label(frame, text="رقم الجوال (اختياري):").grid(row=2, column=1, padx=10, pady=10, sticky="e")
        self.add_phone_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.add_phone_var, width=40).grid(row=2, column=0, padx=10, pady=10, sticky="w")
    
        ttk.Label(frame, text="الفصل:").grid(row=3, column=1, padx=10, pady=10, sticky="e")
        self.add_class_var = tk.StringVar()
        class_names = [c["name"] for c in self.store["list"]]
        self.add_class_combo = ttk.Combobox(frame, textvariable=self.add_class_var, values=class_names, state="readonly", width=37)
        self.add_class_combo.grid(row=3, column=0, padx=10, pady=10, sticky="w")

    # زر الإضافة
        ttk.Button(frame, text="➕ إضافة الطالب", command=self.add_new_student).grid(row=4, column=0, columnspan=2, pady=20)

    # رسالة الحالة
        self.add_status_label = ttk.Label(frame, text="")
        self.add_status_label.grid(row=5, column=0, columnspan=2, pady=10)       

    def add_new_student(self):
        name = self.add_name_var.get().strip()
        student_id = self.add_id_var.get().strip()
        phone = self.add_phone_var.get().strip()
        class_name = self.add_class_var.get().strip()
    
        if not name or not student_id or not class_name:
            messagebox.showwarning("بيانات ناقصة", "الرجاء تعبئة الاسم، الرقم الأكاديمي، والفصل.")
            return
    
        # البحث عن class_id من الاسم
        target_class = None
        for c in self.store["list"]:
            if c["name"] == class_name:
                target_class = c
                break
        if not target_class:
            messagebox.showerror("خطأ", "الفصل المحدد غير موجود.")
            return

    # التحقق من التكرار
        for c in self.store["list"]:
            for s in c["students"]:
                if s.get("id") == student_id:
                    messagebox.showerror("تكرار", f"الرقم الأكاديمي '{student_id}' مستخدم مسبقًا.")
                    return

    # إضافة الطالب
        new_student = {"id": student_id, "name": name, "phone": phone}
        target_class["students"].append(new_student)

    # حفظ
        try:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم", "تمت إضافة الطالب بنجاح!")
            self.add_status_label.config(text="✅ تم الحفظ", foreground="green")
            # مسح الحقول
            self.add_name_var.set("")
            self.add_id_var.set("")
            self.add_phone_var.set("")
            self.add_class_var.set("")
            # تحديث المتجر عالميًا
            global STUDENTS_STORE
            STUDENTS_STORE = None
            self.store = load_students(force_reload=True)
            # تحديث باقي التبويبات
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحفظ:\n{e}")
            
    def delete_selected_student(self):
        if not (selection := self.tree_student_management.selection()):
            messagebox.showwarning("تنبيه", "الرجاء تحديد طالب من القائمة أولاً.")
            return
        values = self.tree_student_management.item(selection[0], "values")
        student_id = values[0]
        student_name = values[1]
        if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف الطالب:\nالاسم: {student_name}\nالرقم: {student_id}\n\nلا يمكن التراجع عن هذا الإجراء!"):
            return

    # ← ابدأ المسافة البادئة هنا (4 مسافات)
        store = load_students(force_reload=True)
        classes = store.get("list", [])
        found = False
        for c in classes:
            for i, s in enumerate(c.get("students", [])):
                if s.get("id") == student_id:
                    del c["students"][i]
                    found = True
                    break
            if found:
                break

        if not found:
            messagebox.showerror("خطأ", "الطالب غير موجود في البيانات!")
            return

        try:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم", "تم حذف الطالب بنجاح.")
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

    def delete_selected_class(self):
        class_names = [c["name"] for c in self.store["list"]]
        class_name = simpledialog.askstring("حذف فصل", "اكتب اسم الفصل الذي تريد حذفه بالضبط:", parent=self.root)
        if not class_name:
            return
        if class_name not in class_names:
            messagebox.showerror("خطأ", "اسم الفصل غير موجود!")
            return
    
        class_id = next(c["id"] for c in self.store["list"] if c["name"] == class_name)
        student_count = len(next(c["students"] for c in self.store["list"] if c["id"] == class_id))
    
        if not messagebox.askyesno("تأكيد الحذف", f"تحذير: سيتم حذف الفصل '{class_name}' وجميع طلابه ({student_count} طالب)!\nهل أنت متأكد؟"):
            return

        new_classes = [c for c in self.store["list"] if c["id"] != class_id]
        try:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": new_classes}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم", f"تم حذف الفصل '{class_name}' بنجاح.")
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

# ===================== main =====================
# ===================== main =====================
# ===================== main =====================
def main():
    # --- START: CLOUDFLARE TUNNEL CONFIGURATION ---
    MY_STATIC_DOMAIN = CLOUDFLARE_DOMAIN  # النطاق الثابت: darbte.uk
    # --- END: CLOUDFLARE TUNNEL CONFIGURATION ---

    ensure_dirs(); init_db()

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
    else:
        print(f"\n[CLOUDFLARE] يعمل محلياً فقط — http://localhost:{PORT}\n")
    root = ThemedTk(theme="arc"); root.set_theme("arc")

    def on_closing():
        try:
            stop_cloudflare_tunnel()
        except Exception: pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    def launch_main_app():
        """يُشغَّل بعد تسجيل الدخول الناجح."""
        # امسح نافذة تسجيل الدخول وابن التطبيق الرئيسي
        for w in root.winfo_children():
            w.destroy()
        # ← إصلاح: أعد تفعيل تغيير الحجم الذي أوقفه LoginWindow
        root.resizable(True, True)
        root.geometry("1280x800")
        root.state("zoomed")   # تكبير كامل عند البدء
        gui = AppGUI(root, public_url)
        # جدول النسخ الاحتياطية التلقائية
        schedule_auto_backup(root, interval_hours=24)
        # جدول إرسال رابط التأخر تلقائياً عند بداية الدوام
        _schedule_tardiness_sender(root)
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

    # اعرض نافذة تسجيل الدخول أولاً
    login = LoginWindow(root, on_success=launch_main_app)
    root.mainloop()

if __name__ == "__main__":
    try: main()
    except SystemExit: pass
    except Exception as e:
        print(f"Fatal: {e}")
        try: stop_cloudflare_tunnel()
        except: pass
        sys.exit(1)