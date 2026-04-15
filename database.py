# -*- coding: utf-8 -*-
"""
database.py — طبقة قاعدة البيانات: init + كل عمليات CRUD
"""
import os, sqlite3, datetime, hashlib, json, zipfile, csv, re
import tkinter as tk
from tkinter import messagebox, filedialog
try:
    import pandas as pd
except ImportError:
    pd = None
from typing import List, Dict, Any, Optional
from constants import (DB_PATH, DATA_DIR, BACKUP_DIR, STUDENTS_JSON,
                       TEACHERS_JSON, CONFIG_JSON, ROLE_TABS,
                       STUDENTS_STORE, ensure_dirs)
from config_manager import load_config
import requests

class CloudDBClient:
    """عميل للتواصل مع السيرفر السحابي بدلاً من قاعدة البيانات المحلية."""
    def __init__(self):
        cfg = load_config()
        self.url = cfg.get("cloud_url", "").rstrip("/")
        self.token = cfg.get("cloud_token", "")
        self.enabled = cfg.get("cloud_mode", False)

    def is_active(self):
        return self.enabled and self.url

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, endpoint, params=None):
        try:
            resp = requests.get(f"{self.url}{endpoint}", params=params, headers=self._get_headers(), timeout=10)
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def post(self, endpoint, json_data):
        try:
            resp = requests.post(f"{self.url}{endpoint}", json=json_data, headers=self._get_headers(), timeout=10)
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

_cloud_client = CloudDBClient()

def get_cloud_client():
    global _cloud_client
    return _cloud_client

def refresh_cloud_client():
    global _cloud_client
    _cloud_client = CloudDBClient()

def get_db():
    """يُنشئ اتصال DB مع إعدادات مُحسَّنة."""
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=10000")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA busy_timeout=3000")   # 3 ثوانٍ قبل رفع الخطأ
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
        # إذا وُجدت tardiness_old → ترقية سابقة توقفت في المنتصف، أكملها أولاً
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tardiness_old'")
        if cur.fetchone():
            try:
                cur.execute("""INSERT OR IGNORE INTO tardiness
                    (id,date,class_id,class_name,student_id,student_name,
                     teacher_name,period,minutes_late,created_at)
                    SELECT id,date,
                           COALESCE(class_id,''),COALESCE(class_name,''),
                           student_id,student_name,
                           teacher_name,period,COALESCE(minutes_late,0),created_at
                    FROM tardiness_old""")
            except Exception:
                pass
            cur.execute("DROP TABLE tardiness_old")
            print("[DB] تم تنظيف tardiness_old من ترقية سابقة غير مكتملة")

        # افحص هل الـ UNIQUE الحالي هو (date, student_id) الصحيح
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tardiness'")
        current_sql = (cur.fetchone() or ("",))[0] or ""
        import re as _re
        m = _re.search(r'UNIQUE\s*\(([^)]+)\)', current_sql, _re.IGNORECASE)
        current_unique = m.group(1).replace(' ', '').lower() if m else ""
        need_rebuild = current_unique not in ("date,student_id", "")

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
            except Exception:
                pass
            cur.execute("DROP TABLE tardiness_old")
            print("[DB] تم ترقية جدول tardiness — الـ UNIQUE الجديد: date+student_id")
        else:
            # أضف أعمدة ناقصة فقط
            existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(tardiness)")}
            for col, dfn in [("teacher_name","TEXT"), ("period","INTEGER"),
                             ("minutes_late","INTEGER DEFAULT 0")]:
                if col not in existing_cols:
                    try:
                        cur.execute("ALTER TABLE tardiness ADD COLUMN {} {}".format(col, dfn))
                    except Exception:
                        pass
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
    # ترقية: أضف الأعمدة الناقصة في جدول users
    _u_cols = {r[1] for r in cur.execute("PRAGMA table_info(users)")}
    if "allowed_tabs" not in _u_cols:
        cur.execute("ALTER TABLE users ADD COLUMN allowed_tabs TEXT")
    if "phone" not in _u_cols:
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
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
    # ─── جدول نتائج الطلاب ──────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_results (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_no  TEXT NOT NULL,
        student_name TEXT NOT NULL,
        section      TEXT,
        school_year  TEXT,
        page_no      INTEGER NOT NULL DEFAULT 0,
        pdf_path     TEXT NOT NULL DEFAULT '',
        gpa          TEXT,
        class_rank   TEXT,
        section_rank TEXT,
        excused_abs  TEXT,
        unexcused_abs TEXT,
        subjects_json TEXT,
        uploaded_at  TEXT NOT NULL
    )""")
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS
        idx_results_identity ON student_results(identity_no, school_year)""")

    # ─── جدول رموز تفعيل النتائج ─────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS result_tokens (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        token      TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        note       TEXT
    )""")

    # ─── جدول الاستئذان ─────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS permissions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        date         TEXT NOT NULL,
        student_id   TEXT NOT NULL,
        student_name TEXT NOT NULL,
        class_id     TEXT NOT NULL DEFAULT '',
        class_name   TEXT NOT NULL DEFAULT '',
        parent_phone TEXT NOT NULL DEFAULT '',
        reason       TEXT,
        approved_by  TEXT,
        status       TEXT NOT NULL DEFAULT 'انتظار',
        msg_sent_at  TEXT,
        approved_at  TEXT,
        created_at   TEXT NOT NULL
    )""")
    _pcols = {r[1] for r in cur.execute("PRAGMA table_info(permissions)")}
    for _col,_dfn in [("parent_phone","TEXT NOT NULL DEFAULT ''"),
                       ("msg_sent_at","TEXT"),("approved_at","TEXT")]:
        if _col not in _pcols:
            try: cur.execute("ALTER TABLE permissions ADD COLUMN {} {}".format(_col,_dfn))
            except: pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_perm_date ON permissions(date)")

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

    # ─── جداول الموجّه الطلابي ───────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS counselor_sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        date         TEXT NOT NULL,
        student_id   TEXT NOT NULL,
        student_name TEXT NOT NULL,
        class_name   TEXT NOT NULL,
        reason       TEXT,
        notes        TEXT,
        action_taken TEXT,
        created_at   TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS counselor_alerts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        date         TEXT NOT NULL,
        student_id   TEXT NOT NULL,
        student_name TEXT NOT NULL,
        type         TEXT NOT NULL,
        method       TEXT NOT NULL,
        status       TEXT,
        created_at   TEXT NOT NULL
    )""")

    # ─── جدول العقود السلوكية ───────────────────────────────────
    cur.execute("""
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

    # ─── جدول تحويلات الموجّه (المحوّلون من وكيل شؤون الطلاب) ────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS counselor_referrals (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        date         TEXT NOT NULL,
        student_id   TEXT NOT NULL,
        student_name TEXT NOT NULL,
        class_name   TEXT NOT NULL,
        referral_type TEXT NOT NULL DEFAULT 'غياب',
        absence_count INTEGER DEFAULT 0,
        tardiness_count INTEGER DEFAULT 0,
        notes        TEXT,
        referred_by  TEXT DEFAULT 'وكيل شؤون الطلاب',
        status       TEXT DEFAULT 'جديد',
        created_at   TEXT NOT NULL
    )""")

    # ─── جدول خطابات الاستفسار الأكاديمي ────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS academic_inquiries (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        date             TEXT NOT NULL,
        counselor_name   TEXT NOT NULL,
        teacher_username TEXT NOT NULL,
        teacher_name     TEXT NOT NULL,
        class_name       TEXT NOT NULL,
        subject          TEXT NOT NULL,
        student_name     TEXT NOT NULL,
        teacher_reply_date TEXT,
        teacher_reply_reasons TEXT,
        teacher_reply_evidence TEXT,
        status           TEXT DEFAULT 'جديد',
        inquiry_type     TEXT DEFAULT 'تدني ملحوظ',
        created_at       TEXT NOT NULL
    )""")
    try:
        cur.execute("ALTER TABLE academic_inquiries ADD COLUMN inquiry_type TEXT DEFAULT 'تدني ملحوظ'")
    except: pass

    # ─── جدول تحويلات الطلاب من المعلم ───────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_referrals (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        ref_date             TEXT NOT NULL,
        student_id           TEXT DEFAULT '',
        student_name         TEXT NOT NULL,
        class_id             TEXT DEFAULT '',
        class_name           TEXT NOT NULL,
        subject              TEXT DEFAULT '',
        period               TEXT DEFAULT '',
        session_time         TEXT DEFAULT '',
        session_ampm         TEXT DEFAULT 'ص',
        violation_type       TEXT DEFAULT 'سلوكية',
        violation            TEXT DEFAULT '',
        problem_causes       TEXT DEFAULT '',
        repeat_count         TEXT DEFAULT 'الأول',
        teacher_action1      TEXT DEFAULT '',
        teacher_action2      TEXT DEFAULT '',
        teacher_action3      TEXT DEFAULT '',
        teacher_action4      TEXT DEFAULT '',
        teacher_action5      TEXT DEFAULT '',
        teacher_name         TEXT NOT NULL,
        teacher_username     TEXT DEFAULT '',
        teacher_date         TEXT DEFAULT '',
        status               TEXT DEFAULT 'pending',
        deputy_meeting_date  TEXT DEFAULT '',
        deputy_meeting_period TEXT DEFAULT '',
        deputy_action1       TEXT DEFAULT '',
        deputy_action2       TEXT DEFAULT '',
        deputy_action3       TEXT DEFAULT '',
        deputy_action4       TEXT DEFAULT '',
        deputy_name          TEXT DEFAULT '',
        deputy_date          TEXT DEFAULT '',
        deputy_referred_date TEXT DEFAULT '',
        counselor_meeting_date TEXT DEFAULT '',
        counselor_meeting_period TEXT DEFAULT '',
        counselor_action1    TEXT DEFAULT '',
        counselor_action2    TEXT DEFAULT '',
        counselor_action3    TEXT DEFAULT '',
        counselor_action4    TEXT DEFAULT '',
        counselor_name       TEXT DEFAULT '',
        counselor_date       TEXT DEFAULT '',
        counselor_referred_back_date TEXT DEFAULT '',
        created_at           TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_teacher ON student_referrals(teacher_username)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_status  ON student_referrals(status)")

    con.commit(); con.close()




# ===================== عمليات السجلات =====================
def insert_absences(date_str, class_id, class_name, students, teacher_id, teacher_name, period):
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/add-absence", {
            "date": date_str, "class_id": class_id, "class_name": class_name,
            "students": students, "period": period
        })
        return res if res.get("ok") else {"created": 0, "skipped": 0}

    con = get_db(); cur = con.cursor()
    created, skipped = 0, 0
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for s in students:
        try:
            cur.execute("""INSERT OR IGNORE INTO absences
                           (date,class_id,class_name,student_id,student_name,teacher_id,teacher_name,period,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (date_str, class_id, class_name, s["id"], s["name"], teacher_id, teacher_name, period, created_at))
            created += 1
        except sqlite3.IntegrityError:
            skipped += 1
    con.commit(); con.close()
    return {"created": created, "skipped": skipped}

def query_absences(date_filter=None, class_id=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/absences", params={"date": date_filter, "class_id": class_id})
        return res.get("rows", []) if res.get("ok") else []

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
    # تنظيف قيم العشرية مثل "1.0" → "1"
    if x.endswith(".0") and x[:-2].isdigit():
        x = x[:-2]
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

def _read_excel_safe(xlsx_path: str):
    """
    يقرأ ملف Excel بطريقة آمنة تتجاوز مشاكل الـ styles.
    يجرب عدة محركات ويعود إلى القراءة المباشرة كـ ZIP إذا فشلت كلها.
    يُرجع: dict {sheet_name: [[row_values], ...]}
    """
    import zipfile, xml.etree.ElementTree as ET
    ext = os.path.splitext(xlsx_path)[1].lower()

    # ─── محاولة 1: xlrd للملفات القديمة .xls ─────────────────
    if ext == ".xls":
        try:
            xl = pd.ExcelFile(xlsx_path, engine="xlrd")
            result = {}
            for sname in xl.sheet_names:
                df = pd.read_excel(xlsx_path, sheet_name=sname, header=None, dtype=str, engine="xlrd")
                result[sname] = df.values.tolist()
            return result
        except Exception:
            pass

    # ─── محاولة 2: openpyxl العادي ────────────────────────────
    try:
        xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
        result = {}
        for sname in xl.sheet_names:
            df = pd.read_excel(xlsx_path, sheet_name=sname, header=None, dtype=str, engine="openpyxl")
            result[sname] = df.values.tolist()
        return result
    except Exception:
        pass

    # ─── محاولة 3: قراءة مباشرة كـ ZIP (تتجاوز مشكلة styles) ─
    try:
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        with zipfile.ZipFile(xlsx_path) as z:
            # اقرأ Shared Strings
            strings = []
            if "xl/sharedStrings.xml" in z.namelist():
                ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in ss_root.findall(f"{{{ns}}}si"):
                    t = si.find(f"{{{ns}}}t")
                    if t is not None:
                        strings.append(t.text or "")
                    else:
                        parts = si.findall(f".//{{{ns}}}t")
                        strings.append("".join(p.text or "" for p in parts))

            # اقرأ أسماء الأوراق
            wb_root = ET.fromstring(z.read("xl/workbook.xml"))
            sheet_els = wb_root.findall(f".//{{{ns}}}sheet")
            # رسم العلاقات: rId → ملف الورقة
            rels_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            rid_map = {r.get("Id"): r.get("Target")
                       for r in rels_root.findall(f"{{{rel_ns}}}Relationship")}

            result = {}
            for sel in sheet_els:
                sname = sel.get("name", "")
                rid   = sel.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
                target = rid_map.get(rid, "")
                if not target.startswith("xl/"):
                    target = "xl/" + target
                if target not in z.namelist():
                    continue

                ws_root = ET.fromstring(z.read(target))
                rows_els = ws_root.findall(f".//{{{ns}}}row")
                sheet_rows = []
                for row_el in rows_els:
                    cells = row_el.findall(f"{{{ns}}}c")
                    row_data = []
                    for c in cells:
                        t_attr = c.get("t", "")
                        v = c.find(f"{{{ns}}}v")
                        val = ""
                        if v is not None and v.text is not None:
                            val = v.text
                            if t_attr == "s":
                                try:
                                    val = strings[int(val)]
                                except Exception:
                                    val = ""
                        row_data.append(val)
                    sheet_rows.append(row_data)
                result[sname] = sheet_rows
        return result
    except Exception as e:
        raise ValueError(f"تعذّر قراءة الملف بأي طريقة: {e}")


def _noor_level_name(raw: str) -> str:
    """
    يحوّل قيمة 'رقم الصف' من صيغة نور الجديدة 'الأول الثانوي_السنة المشتركة'
    إلى اسم مستوى موحّد مثل 'أول ثانوي'.
    """
    raw = str(raw).strip()
    if "الأول" in raw or "أول" in raw:
        return "أول ثانوي"
    if "الثاني" in raw or "ثاني" in raw:
        return "ثاني ثانوي"
    if "الثالث" in raw or "ثالث" in raw:
        return "ثالث ثانوي"
    return level_name_from_value(raw)


def _noor_level_digit(raw: str) -> str:
    """يُرجع الرقم (1, 2, 3) للمستوى من قيمة نور."""
    raw = str(raw).strip()
    if "الأول" in raw or "أول" in raw:
        return "1"
    if "الثاني" in raw or "ثاني" in raw:
        return "2"
    if "الثالث" in raw or "ثالث" in raw:
        return "3"
    # fallback: الدالة القديمة
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits in {"1314", "1416", "1516"}:
        return {"1314": "1", "1416": "2", "1516": "3"}[digits]
    if raw and raw[0] in "123١٢٣":
        return {"1":"1","2":"2","3":"3","١":"1","٢":"2","٣":"3"}.get(raw[0], "1")
    return "1"


def _noor_build_class_name(level_name: str, section_label: str) -> str:
    """يبني اسم الفصل مع المسار إذا كان موجوداً."""
    return f"{level_name} / {section_label}"


def import_students_from_excel_sheet2_format(xlsx_path: str) -> Dict[str, Any]:
    """
    يستورد بيانات الطلاب من Excel — يدعم جميع الصيغ:

    الصيغة 1 (الكلاسيكية): أعمدة رقم الطالب، اسم الطالب، رقم الصف (رقم)، الفصل، رقم الجوال
    الصيغة 2 (نور الجديدة): الجوال، الفصل، رقم الصف (نص كامل)، اسم الطالب، رقم الطالب
    الصيغة 3 (ملفات bkp/قديمة): legacy IDs مثل 1314-1 لتمييز المستويات

    ⬅ مرن تلقائياً — لا يحتاج تدخل المستخدم.
    """
    # ─── قراءة الملف بطريقة آمنة ────────────────────────────────
    all_sheets = _read_excel_safe(xlsx_path)

    # ─── أسماء الأعمدة المعروفة ──────────────────────────────────
    # الأعمدة الإلزامية للبحث
    STUDENT_ID_COLS  = {"رقم الطالب", "رقم الهوية", "الرقم الأكاديمي", "رقم_الطالب"}
    STUDENT_NM_COLS  = {"اسم الطالب", "الاسم", "اسم_الطالب"}
    LEVEL_COLS       = {"رقم الصف", "المرحلة", "الصف", "رقم_الصف"}
    SECTION_COLS     = {"الفصل", "رقم الفصل", "رقم_الفصل"}
    PHONE_COLS       = {"رقم الجوال", "الجوال", "جوال", "رقم_الجوال", "phone"}

    BLANK = {"nan", "none", ""}

    def clean(v):
        s = str(v).strip() if v is not None else ""
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        return s

    def find_col(cols_set, header_row):
        """يبحث عن أول عمود يطابق أيًا من الأسماء المعروفة."""
        for i, h in enumerate(header_row):
            if clean(h) in cols_set:
                return i
        return None

    def is_blank(v):
        return clean(v).lower() in BLANK

    # ─── ابحث عن الورقة والصف المناسبَين ────────────────────────
    found_sheet   = None
    found_hdr_idx = None
    found_rows    = None

    for sname, rows in all_sheets.items():
        for i, row in enumerate(rows[:30]):
            row_vals = {clean(v) for v in row if v is not None and clean(v)}
            # تحقق من وجود عمودَي الطالب على الأقل
            has_id   = bool(row_vals & STUDENT_ID_COLS)
            has_name = bool(row_vals & STUDENT_NM_COLS)
            if has_id and has_name:
                found_sheet   = sname
                found_hdr_idx = i
                found_rows    = rows
                break
        if found_sheet:
            break

    if not found_sheet:
        raise ValueError(
            "تعذّر اكتشاف بيانات الطلاب تلقائيًا.\n"
            "تأكد من وجود أعمدة مثل: رقم الطالب، اسم الطالب، رقم الصف\n"
            f"الملف يحتوي على الأوراق: {list(all_sheets.keys())}"
        )

    hdr = [clean(v) for v in found_rows[found_hdr_idx]]
    data_rows = found_rows[found_hdr_idx + 1:]

    # ─── تحديد فهارس الأعمدة ────────────────────────────────────
    idx_id      = find_col(STUDENT_ID_COLS, hdr)
    idx_name    = find_col(STUDENT_NM_COLS, hdr)
    idx_level   = find_col(LEVEL_COLS,      hdr)
    idx_section = find_col(SECTION_COLS,    hdr)
    idx_phone   = find_col(PHONE_COLS,      hdr)

    if idx_id is None or idx_name is None:
        raise ValueError(f"لم يُعثر على عمود رقم الطالب أو اسم الطالب. الأعمدة الموجودة: {hdr}")

    # ─── دوال مساعدة داخلية ─────────────────────────────────────
    def get_cell(row, idx):
        if idx is None or idx >= len(row):
            return ""
        return clean(row[idx])

    LETTERS = ["أ", "ب", "ج", "د", "هـ", "و", "ز", "ح", "ط", "ي"]
    # تحويل الحروف العربية إلى إنجليزية لاستخدامها في روابط URL
    AR_TO_EN_SECTION = {
        "أ": "A", "ب": "B", "ج": "C", "د": "D", "هـ": "E",
        "و": "F", "ز": "G", "ح": "H", "ط": "I", "ي": "J",
        "ه": "E",
        # أقسام خاصة
        "هندسة": "ENG", "هندسة 2": "ENG2",
        "علوم": "SCI", "علوم حاسب": "CS", "إدارة": "MGT",
        "أدبي": "LIT", "علمي": "SCI2", "شريعة": "ISL",
    }

    def make_safe_class_id(level_digit, section_label, track=""):
        """يبني class_id آمناً لروابط URL (إنجليزي فقط، بدون حروف عربية)."""
        import re as _re
        sec_en = AR_TO_EN_SECTION.get(section_label, None)
        if sec_en is None:
            # حاول تحويل حرف بحرف
            sec_en = "".join(AR_TO_EN_SECTION.get(ch, ch) for ch in section_label)
        # احذف أي حرف غير آمن (حروف عربية أو رموز)
        sec_en = _re.sub(r'[^A-Za-z0-9]', '', sec_en)
        if not sec_en:
            # آخر ملاذ: hash قصير
            import hashlib as _hs
            sec_en = _hs.md5(section_label.encode()).hexdigest()[:4].upper()
        if track:
            track_safe = _re.sub(r'[^A-Za-z0-9]', '', track)
            if not track_safe:
                import hashlib as _hs
                track_safe = _hs.md5(track.encode()).hexdigest()[:4].upper()
            return f"{level_digit}-{sec_en}-{track_safe}"
        return f"{level_digit}-{sec_en}"

    def sort_key(v):
        try:
            return (0, int(v))
        except ValueError:
            return (1, v)

    # ─── المرور الأول: جمع أرقام الفصول الفريدة لكل مجموعة ──────
    # المجموعة = (raw_level) — لنبني خريطة رقم→حرف بناءً على الرتبة الفعلية
    # مثال: ثاني ثانوي لديه [1,3,4,5,6] → أ,ب,ج,د,هـ (رقم 2 غائب فلا يُفقد حرف)
    from collections import defaultdict
    group_sections: Dict[str, list] = defaultdict(list)

    for row in data_rows:
        if not row:
            continue
        s_id   = get_cell(row, idx_id)
        s_name = get_cell(row, idx_name)
        if is_blank(s_id) or is_blank(s_name):
            continue
        raw_lv  = get_cell(row, idx_level)   if idx_level   is not None else ""
        raw_sec = get_cell(row, idx_section) if idx_section is not None else ""
        if raw_sec and raw_sec not in group_sections[raw_lv]:
            group_sections[raw_lv].append(raw_sec)

    # رتّب الأرقام تصاعدياً وعيّن حرفاً لكل رتبة
    # {level_raw: {section_raw: letter}}
    group_section_map: Dict[str, Dict[str, str]] = {}
    for lv_raw, secs in group_sections.items():
        sorted_secs = sorted(secs, key=sort_key)
        group_section_map[lv_raw] = {
            sec: (LETTERS[i] if i < len(LETTERS) else str(i + 1))
            for i, sec in enumerate(sorted_secs)
        }

    # ─── المرور الثاني: بناء الفصول ─────────────────────────────
    classes: Dict[str, Dict[str, Any]] = {}

    for row in data_rows:
        if not row:
            continue
        student_id   = get_cell(row, idx_id)
        student_name = get_cell(row, idx_name)
        if is_blank(student_id) or is_blank(student_name):
            continue

        raw_level   = get_cell(row, idx_level)   if idx_level   is not None else ""
        raw_section = get_cell(row, idx_section) if idx_section is not None else ""
        raw_phone   = get_cell(row, idx_phone)   if idx_phone   is not None else ""

        phone = _clean_phone_noor(raw_phone)

        if raw_level:
            level_name  = _noor_level_name(raw_level)
            level_digit = _noor_level_digit(raw_level)
        else:
            level_name  = "أول ثانوي"
            level_digit = "1"

        # ─── الحرف بناءً على الرتبة الفعلية داخل المجموعة ────────
        sec_map = group_section_map.get(raw_level, {})
        if raw_section and sec_map:
            section_label = sec_map.get(raw_section, raw_section)
        elif raw_section:
            section_label = section_label_from_value(raw_section, level_name)
        else:
            section_label = "أ"

        # ─── class_id و class_name ───────────────────────────────
        if raw_level and "_" in raw_level:
            parts = raw_level.split("_", 1)
            track = parts[1].strip() if len(parts) > 1 else ""
            if track:
                class_id   = make_safe_class_id(level_digit, section_label, track)
                class_name = f"{level_name} ({track}) / {section_label}"
            else:
                class_id   = make_safe_class_id(level_digit, section_label)
                class_name = f"{level_name} / {section_label}"
        else:
            class_id   = make_safe_class_id(level_digit, section_label)
            class_name = f"{level_name} / {section_label}"

        if class_id not in classes:
            classes[class_id] = {"id": class_id, "name": class_name, "students": []}
        classes[class_id]["students"].append({
            "id":    student_id,
            "name":  student_name,
            "phone": phone,
        })

    if not classes:
        raise ValueError("لم يُعثر على أي طلاب في الملف — تحقق من صحة البيانات.")

    data = {"classes": list(classes.values())}
    with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ═══════════════════════════════════════════════════════════════
# دوال المصادقة والمستخدمين
# ═══════════════════════════════════════════════════════════════
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def authenticate(username: str, password: str):
    """يتحقق من المستخدم — يُرجع dict المستخدم أو None."""
    client = get_cloud_client()
    if client.is_active():
        # في وضع السحاب، نستخدم الـ API للتحقق
        res = client.post("/web/api/login", {"username": username, "password": password})
        if res.get("ok"):
            return {"username": username, "role": res.get("role", "teacher"), "full_name": res.get("name", username)}
        return None

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

def query_permissions(date_filter=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/permissions", params={"date": date_filter})
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, params = "SELECT * FROM permissions WHERE 1=1", []
    if date_filter: q += " AND date=?"; params.append(date_filter)
    cur.execute(q + " ORDER BY created_at DESC", params)
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def get_all_users():
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT id,username,role,full_name,active,COALESCE(phone,'') as phone FROM users ORDER BY role,username")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def save_user_phone(username: str, phone: str):
    """يحفظ رقم جوال المستخدم."""
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET phone=? WHERE username=?", (phone.strip(), username))
    con.commit(); con.close()

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
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/add-tardiness", {
            "date": date_str, "student_id": student_id, "student_name": student_name,
            "class_id": class_id, "class_name": class_name, "minutes_late": minutes_late
        })
        return res.get("ok", False)

    created_at = datetime.datetime.utcnow().isoformat()
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("""INSERT OR IGNORE INTO tardiness
            (date,class_id,class_name,student_id,student_name,
             teacher_name,period,minutes_late,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (date_str,class_id,class_name,student_id,student_name,
             teacher_name,period,minutes_late,created_at))
        con.commit(); con.close(); return True
    except sqlite3.IntegrityError:
        return False

def query_tardiness(date_filter=None, class_id=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/tardiness", params={"date": date_filter})
        return res.get("rows", []) if res.get("ok") else []

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
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/add-excuse", {
            "date": date_str, "student_id": student_id, "student_name": student_name,
            "class_id": class_id, "class_name": class_name, "reason": reason
        })
        return res.get("ok", False)

    created_at = datetime.datetime.utcnow().isoformat()
    con = get_db(); cur = con.cursor()
    cur.execute("""INSERT OR IGNORE INTO excuses
        (date,student_id,student_name,class_id,class_name,
         reason,source,approved_by,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (date_str,student_id,student_name,class_id,class_name,
         reason,source,approved_by,created_at))
    con.commit(); con.close()

def query_excuses(date_filter=None, student_id=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/excuses", params={"date": date_filter})
        return res.get("rows", []) if res.get("ok") else []

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
    
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/students")
        if res.get("ok"):
            classes = res.get("classes", [])
            STUDENTS_STORE = {"list": classes, "by_id": {c["id"]: c for c in classes}}
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
    
    ID_HINTS    = ["رقم الهوية", "رقم السجل", "السجل المدني", "الهوية"]
    
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
        id_col    = next((c for c in target_df.columns if any(h in c for h in ID_HINTS)), None)
        if not name_col:
            raise ValueError("لم أجد عمود اسم المعلم في الملف.")
        teachers = []
        SKIP = {"nan","none","","اسم المعلم","اسم الموظف"}
        for _, row in target_df.iterrows():
            name = str(row.get(name_col,"")).strip()
            if name.lower() in SKIP or not name: continue
            phone_raw = str(row.get(phone_col,"")) if phone_col else ""
            id_raw = str(row.get(id_col,"")).strip() if id_col else ""
            if id_raw.endswith(".0"): id_raw = id_raw[:-2]
            teachers.append({"اسم المعلم": name, "رقم الجوال": _clean_phone_noor(phone_raw), "رقم الهوية": id_raw})
    else:
        # صيغة نور المعروفة: عمود 19 = الاسم، عمود 3 = الجوال، عمود 18 قد يكون السجل
        raw = pd.read_excel(xlsx_path, header=None, dtype=str)
        if raw.shape[1] < 20:
            raise ValueError("لم أتعرف على صيغة الملف. تأكد من أن يحتوي على أعمدة اسم المعلم ورقم الجوال.")
        teachers = []
        SKIP = {"nan","none","","اسم المعلم"}
        for _, row in raw.iterrows():
            name = str(row.iloc[19]).strip()
            if name.lower() in SKIP or not name: continue
            phone_raw = str(row.iloc[3])
            id_raw = str(row.iloc[18]).strip() if raw.shape[1] >= 19 else ""
            if id_raw.endswith(".0"): id_raw = id_raw[:-2]
            if not id_raw.isdigit() or len(id_raw) < 8: id_raw = ""
            teachers.append({"اسم المعلم": name, "رقم الجوال": _clean_phone_noor(phone_raw), "رقم الهوية": id_raw})

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
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/teachers")
        if res.get("ok"):
            return {"teachers": res.get("teachers", [])}

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


# ═══════════════════════════════════════════════════════════════
# تحويلات الطلاب — student_referrals CRUD
# ═══════════════════════════════════════════════════════════════
def create_student_referral(data: dict) -> int:
    """يُنشئ تحويل طالب جديد ويُعيد الـ id."""
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/referrals/create", data)
        return res.get("id", 0) if res.get("ok") else 0

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO student_referrals
        (ref_date,student_id,student_name,class_id,class_name,
         subject,period,session_time,session_ampm,
         violation_type,violation,problem_causes,repeat_count,
         teacher_action1,teacher_action2,teacher_action3,teacher_action4,teacher_action5,
         teacher_name,teacher_username,teacher_date,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get("ref_date",""), data.get("student_id",""), data.get("student_name",""),
        data.get("class_id",""), data.get("class_name",""),
        data.get("subject",""), data.get("period",""),
        data.get("session_time",""), data.get("session_ampm","ص"),
        data.get("violation_type","سلوكية"), data.get("violation",""),
        data.get("problem_causes",""), data.get("repeat_count","الأول"),
        data.get("teacher_action1",""), data.get("teacher_action2",""),
        data.get("teacher_action3",""), data.get("teacher_action4",""),
        data.get("teacher_action5",""), data.get("teacher_name",""),
        data.get("teacher_username",""), data.get("teacher_date",""),
        "pending", now
    ))
    ref_id = cur.lastrowid
    con.commit(); con.close()
    return ref_id

def get_referrals_for_teacher(teacher_username: str) -> list:
    """يُعيد كل تحويلات المعلم."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/referrals/teacher", params={"username": teacher_username})
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""SELECT * FROM student_referrals
                   WHERE teacher_username=? ORDER BY created_at DESC""",
                (teacher_username,))
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def get_all_referrals(status_filter: str = None) -> list:
    """يُعيد كل التحويلات (للوكيل/المدير)."""
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if status_filter:
        cur.execute("SELECT * FROM student_referrals WHERE status=? ORDER BY created_at DESC",
                    (status_filter,))
    else:
        cur.execute("SELECT * FROM student_referrals ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def get_referral_by_id(ref_id: int) -> dict:
    """يُعيد تفاصيل تحويل واحد."""
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM student_referrals WHERE id=?", (ref_id,))
    row = cur.fetchone(); con.close()
    return dict(row) if row else {}

def update_referral_deputy(ref_id: int, data: dict):
    """يحفظ إجراءات الوكيل على التحويل."""
    con = get_db(); cur = con.cursor()
    new_status = data.get("status", "with_deputy")
    cur.execute("""UPDATE student_referrals SET
        status=?, deputy_meeting_date=?, deputy_meeting_period=?,
        deputy_action1=?, deputy_action2=?, deputy_action3=?, deputy_action4=?,
        deputy_name=?, deputy_date=?, deputy_referred_date=?
        WHERE id=?
    """, (
        new_status,
        data.get("deputy_meeting_date",""), data.get("deputy_meeting_period",""),
        data.get("deputy_action1",""), data.get("deputy_action2",""),
        data.get("deputy_action3",""), data.get("deputy_action4",""),
        data.get("deputy_name",""), data.get("deputy_date",""),
        data.get("deputy_referred_date",""), ref_id
    ))
    con.commit(); con.close()

def update_referral_counselor(ref_id: int, data: dict):
    """يحفظ إجراءات الموجه على التحويل."""
    con = get_db(); cur = con.cursor()
    new_status = data.get("status", "with_counselor")
    cur.execute("""UPDATE student_referrals SET
        status=?, counselor_meeting_date=?, counselor_meeting_period=?,
        counselor_action1=?, counselor_action2=?, counselor_action3=?, counselor_action4=?,
        counselor_name=?, counselor_date=?, counselor_referred_back_date=?
        WHERE id=?
    """, (
        new_status,
        data.get("counselor_meeting_date",""), data.get("counselor_meeting_period",""),
        data.get("counselor_action1",""), data.get("counselor_action2",""),
        data.get("counselor_action3",""), data.get("counselor_action4",""),
        data.get("counselor_name",""), data.get("counselor_date",""),
        data.get("counselor_referred_back_date",""), ref_id
    ))
    con.commit(); con.close()

def close_referral(ref_id: int):
    """يُغلق التحويل (تم الحل)."""
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE student_referrals SET status='resolved' WHERE id=?", (ref_id,))
    con.commit(); con.close()

def get_deputy_phones() -> list:
    """يُعيد أرقام جوالات المستخدمين ذوي دور وكيل."""
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT phone FROM users WHERE role='deputy' AND active=1 AND phone!='' AND phone IS NOT NULL")
    phones = [r[0] for r in cur.fetchall()]; con.close(); return phones

def get_counselor_phones() -> list:
    """يُعيد أرقام جوالات الموجّهين من config.json."""
    try:
        from config_manager import load_config
        cfg = load_config()
        phones = []
        for key in ("counselor1_phone", "counselor2_phone"):
            p = cfg.get(key, "").strip()
            if p:
                phones.append(p)
        return phones
    except Exception:
        return []

# ═══════════════════════════════════════════════════════════════
# خطابات الاستفسار الأكاديمي (الموجه ← المعلم)
# ═══════════════════════════════════════════════════════════════
def create_academic_inquiry(data: dict) -> int:
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/create-academic-inquiry", data)
        return res.get("id", 0) if res.get("ok") else 0

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO academic_inquiries
        (date, counselor_name, teacher_username, teacher_name,
         class_name, subject, student_name,
         teacher_reply_date, teacher_reply_reasons, teacher_reply_evidence,
         status, inquiry_type, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get("date", ""), data.get("counselor_name", ""),
        data.get("teacher_username", ""), data.get("teacher_name", ""),
        data.get("class_name", ""), data.get("subject", ""),
        data.get("student_name", ""),
        "", "", "", "جديد", data.get("inquiry_type", "تدني ملحوظ"), now
    ))
    inq_id = cur.lastrowid
    con.commit(); con.close()
    return inq_id

def get_academic_inquiries(teacher_username: str = None) -> list:
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/academic-inquiries")
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if teacher_username:
        cur.execute("SELECT * FROM academic_inquiries WHERE teacher_username=? ORDER BY created_at DESC", (teacher_username,))
    else:
        cur.execute("SELECT * FROM academic_inquiries ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def get_academic_inquiry(inq_id: int) -> dict:
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM academic_inquiries WHERE id=?", (inq_id,))
    row = cur.fetchone(); con.close(); return dict(row) if row else {}

def reply_academic_inquiry(inq_id: int, data: dict):
    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        UPDATE academic_inquiries
        SET teacher_reply_date=?, teacher_reply_reasons=?, teacher_reply_evidence=?, status=?, inquiry_type=?
        WHERE id=?
    """, (
        data.get("date", now.split("T")[0]),
        data.get("reasons", ""),
        data.get("evidence", ""),
        "تم الرد",
        data.get("inquiry_type", ""),
        inq_id
    ))
    con.commit(); con.close()

# ===================== بناء التقارير HTML =====================
