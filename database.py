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
                       ensure_dirs)
import constants
from config_manager import load_config
import requests

# ─── حالة التشغيل (سيرفر أم عميل) ───────────────────────────
# نستخدم متغير بيئة لضمان ثبات القيمة عبر جميع العمليات (Processes)
def is_server_side():
    return os.environ.get("DARB_SERVER_MODE") == "1"
# ────────────────────────────────────────────────────────────

class CloudDBClient:
    """عميل للتواصل مع السيرفر السحابي بدلاً من قاعدة البيانات المحلية."""
    def __init__(self):
        cfg = load_config()
        self.url = cfg.get("cloud_url", "").rstrip("/")
        self.token = cfg.get("cloud_token", "")
        self.enabled = cfg.get("cloud_mode", False)

    def is_active(self):
        # تم إلغاء قيد os.environ["DARB_SERVER_MODE"] للسماح للأجهزة العميلة بسحب البيانات
        # حتى لو كانت تشغل سيرفر محلياً للأجهزة المتنقلة الخاصة بها.
        return self.enabled and self.url

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, endpoint, params=None):
        try:
            resp = requests.get(f"{self.url}{endpoint}", params=params, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200:
                print(f"[CLOUD-GET-ERROR] {endpoint} -> Status {resp.status_code}: {resp.text[:200]}")
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            print(f"[CLOUD-GET-EXCEPTION] {endpoint} -> {e}")
            return {"ok": False, "msg": str(e)}

    def post(self, endpoint, json_data):
        try:
            resp = requests.post(f"{self.url}{endpoint}", json=json_data, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200:
                print(f"[CLOUD-POST-ERROR] {endpoint} -> Status {resp.status_code}: {resp.text[:200]}")
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            print(f"[CLOUD-POST-EXCEPTION] {endpoint} -> {e}")
            return {"ok": False, "msg": str(e)}

    def delete(self, endpoint, params=None):
        try:
            resp = requests.delete(f"{self.url}{endpoint}", params=params, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200:
                print(f"[CLOUD-DELETE-ERROR] {endpoint} -> Status {resp.status_code}: {resp.text[:200]}")
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            print(f"[CLOUD-DELETE-EXCEPTION] {endpoint} -> {e}")
            return {"ok": False, "msg": str(e)}

    def put(self, endpoint, json_data):
        try:
            resp = requests.put(f"{self.url}{endpoint}", json=json_data, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200:
                print(f"[CLOUD-PUT-ERROR] {endpoint} -> Status {resp.status_code}: {resp.text[:200]}")
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            print(f"[CLOUD-PUT-EXCEPTION] {endpoint} -> {e}")
            return {"ok": False, "msg": str(e)}

    def patch(self, endpoint, json_data):
        try:
            resp = requests.patch(f"{self.url}{endpoint}", json=json_data, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200:
                print(f"[CLOUD-PATCH-ERROR] {endpoint} -> Status {resp.status_code}: {resp.text[:200]}")
            return resp.json() if resp.status_code == 200 else {"ok": False, "msg": f"Error {resp.status_code}"}
        except Exception as e:
            print(f"[CLOUD-PATCH-EXCEPTION] {endpoint} -> {e}")
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

    # ─── جدول التعاميم الرسمية ────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS circulars (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        date             TEXT NOT NULL,
        title            TEXT NOT NULL,
        content          TEXT,
        attachment_path  TEXT,
        created_by       TEXT NOT NULL,
        target_role      TEXT DEFAULT 'all',
        created_at       TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_circulars_date ON circulars(date)")

    # ─── جدول قراءة التعاميم ─────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS circular_reads (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        circular_id      INTEGER NOT NULL,
        username         TEXT NOT NULL,
        read_at          TEXT NOT NULL,
        UNIQUE(circular_id, username)
    )""")

    # ─── جدول ملاحظات الطالب الإدارية ───────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_notes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id  TEXT NOT NULL,
        note        TEXT NOT NULL,
        author      TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_snotes_student ON student_notes(student_id)")

    migrate_circulars_permission(cur)
    con.commit(); con.close()

def migrate_circulars_permission(cur):
    """تتأكد من تفعيل تبويب التعاميم لجميع المعلمين والوكلاء الذين لديهم صلاحيات مخصصة."""
    cur.execute("SELECT id, role, allowed_tabs FROM users WHERE allowed_tabs IS NOT NULL AND allowed_tabs != ''")
    rows = cur.fetchall()
    for rid, role, allowed_tabs_json in rows:
        try:
            tabs = json.loads(allowed_tabs_json)
            if isinstance(tabs, list) and "التعاميم والنشرات" not in tabs:
                tabs.append("التعاميم والنشرات")
                cur.execute("UPDATE users SET allowed_tabs=? WHERE id=?", (json.dumps(tabs, ensure_ascii=False), rid))
        except:
            pass

def clear_yearly_data(reset_type='term'):
    """
    يحذف البيانات المتراكمة لتصفير البرنامج لبداية جديدة.
    reset_type: 'term' (نهاية فصل) أو 'year' (نهاية سنة)
    """
    con = get_db(); cur = con.cursor()
    
    # الجداول التي تُحذف في نهاية كل فصل (semester/term)
    term_tables = [
        "absences", "tardiness", "messages_log", "message_log",
        "excuses", "permissions", "student_referrals",
        "counselor_referrals", "academic_inquiries"
    ]
    
    # الجداول الإضافية التي تُحذف فقط في نهاية السنة
    year_only_tables = [
        "student_results", "result_tokens", "counselor_sessions",
        "behavioral_contracts", "circulars", "circular_reads",
        "counselor_alerts"
    ]
    
    tables_to_clear = term_tables
    if reset_type == 'year':
        tables_to_clear += year_only_tables
        
    for table in tables_to_clear:
        try:
            cur.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            # الجدول قد لا يكون موجوداً في نسخ قديمة
            pass
            
    con.commit(); con.close()
    return True




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

def delete_absence(rec_id):
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/absences/{rec_id}")
        return

    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM absences WHERE id=?", (rec_id,))
    con.commit(); con.close()

def query_absences(date_filter=None, class_id_filter=None, student_id=None, **kwargs):
    client = get_cloud_client()
    if client.is_active():
        params = {}
        if date_filter: params["date"] = date_filter
        elif "date_filter" in kwargs: params["date"] = kwargs["date_filter"]
        
        if student_id: params["student_id"] = student_id
        elif "student_id" in kwargs: params["student_id"] = kwargs["student_id"]
        
        if class_id_filter: params["class_id"] = class_id_filter
        elif "class_id_filter" in kwargs: params["class_id"] = kwargs["class_id_filter"]
        
        res = client.get("/web/api/absences", params=params)
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, p = "SELECT * FROM absences WHERE 1=1", []
    
    # Handle Positional or Keyword args
    d_f = date_filter or kwargs.get("date_filter")
    if d_f: q += " AND date=?"; p.append(d_f)
    
    s_id = student_id or kwargs.get("student_id")
    if s_id: q += " AND student_id=?"; p.append(s_id)
    
    c_id = class_id_filter or kwargs.get("class_id_filter")
    if c_id: q += " AND class_id=?"; p.append(c_id)
    cur.execute(q + " ORDER BY date DESC, class_id, student_name", p)
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
            role      = res.get("role", "teacher")
            full_name = res.get("name", username)
            # احفظ المستخدم محلياً حتى تعمل get_user_allowed_tabs بشكل صحيح
            try:
                _con = get_db(); _cur = _con.cursor()
                _cur.execute("""
                    INSERT INTO users (username,password,role,full_name,active,created_at,allowed_tabs)
                    VALUES (?,?,?,?,1,?,?)
                    ON CONFLICT(username) DO UPDATE
                    SET role=excluded.role, full_name=excluded.full_name,
                        allowed_tabs=COALESCE(excluded.allowed_tabs, allowed_tabs)
                """, (username, "", role, full_name,
                      datetime.datetime.utcnow().isoformat(),
                      json.dumps(res.get("allowed_tabs")) if res.get("allowed_tabs") else None))
                _con.commit(); _con.close()
            except Exception as _e:
                print(f"[AUTH-CACHE] {_e}")
            return {"username": username, "role": role, "full_name": full_name}
        return None

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND active=1", (username,))
    row = cur.fetchone(); con.close()
    if not row: return None
    if row["password"] != hash_password(password): return None
    return dict(row)

def get_user_info(username: str):
    """يُرجع معلومات المستخدم من لقاعدة البيانات."""
    client = get_cloud_client()
    if client.is_active():
        # في وضع السحاب، قد نحتاج لإضافة نقطة نهاية لهذا أو استخدام authenticate
        return {"username": username, "role": "teacher", "full_name": username}

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT username, role, full_name, active FROM users WHERE username=?", (username,))
    row = cur.fetchone(); con.close()
    return dict(row) if row else None

def get_user_allowed_tabs(username: str):
    """يُرجع قائمة التبويبات المسموحة للمستخدم، أو None إذا كان admin."""
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT role, allowed_tabs FROM users WHERE username=?", (username,))
    row = cur.fetchone(); con.close()
    if not row:
        # المستخدم غير موجود محلياً (وضع السحاب) — استخدم الدور من CURRENT_USER
        from constants import CURRENT_USER, ROLE_TABS as _RT
        role = CURRENT_USER.get("role", "teacher")
        if role == "admin": return None
        return _RT.get(role)
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
    client = get_cloud_client()
    if client.is_active():
         client.post("/web/api/users/allowed-tabs", {"username": username, "tabs": tabs})
         return

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
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/sync/users")
        if res.get("ok"):
            return res.get("users", [])

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT id,username,role,full_name,active,COALESCE(phone,'') as phone FROM users ORDER BY role,username")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows


def save_user_phone(username: str, phone: str):
    """يحفظ رقم جوال المستخدم."""
    client = get_cloud_client()
    if client.is_active():
        client.post("/web/api/users/phone", {"username": username, "phone": phone})
        return

    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET phone=? WHERE username=?", (phone.strip(), username))
    con.commit(); con.close()

def create_user(username, password, role, full_name=""):
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/users/create", {
            "username": username, "password": password, "role": role, "full_name": full_name
        })
        return res.get("ok", False), res.get("msg", "Error")

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
    client = get_cloud_client()
    if client.is_active():
        client.post("/web/api/users/update-password", {"username": username, "password": new_password})
        return

    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET password=? WHERE username=?",
                (hash_password(new_password), username))
    con.commit(); con.close()

def toggle_user_active(user_id, active):
    client = get_cloud_client()
    if client.is_active():
        client.post("/web/api/users/toggle-active", {"user_id": user_id, "active": active})
        return

    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE users SET active=? WHERE id=?", (active, user_id))
    con.commit(); con.close()

def delete_user(user_id):
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/users/{user_id}")
        return

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
            "class_id": class_id, "class_name": class_name,
            "period": period, "minutes_late": minutes_late
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

def delete_tardiness(rec_id):
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/tardiness/{rec_id}")
        return

    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM tardiness WHERE id=?", (rec_id,))
    con.commit(); con.close()

def query_tardiness(date_filter=None, student_id=None, class_id=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/tardiness", params={"date": date_filter, "student_id": student_id, "class_id": class_id})
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, p = "SELECT * FROM tardiness WHERE 1=1", []
    if date_filter: q += " AND date=?";   p.append(date_filter)
    if student_id:  q += " AND student_id=?"; p.append(student_id)
    if class_id:    q += " AND class_id=?";   p.append(class_id)
    cur.execute(q + " ORDER BY date DESC, created_at DESC", p)
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

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

def delete_excuse(rec_id):
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/excuses/{rec_id}")
        return

    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM excuses WHERE id=?", (rec_id,))
    con.commit(); con.close()

def query_excuses(date_filter=None, student_id=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/excuses", params={"date": date_filter, "student_id": student_id})
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q, p = "SELECT * FROM excuses WHERE 1=1", []
    if date_filter: q += " AND date=?";   p.append(date_filter)
    if student_id:  q += " AND student_id=?"; p.append(student_id)
    cur.execute(q + " ORDER BY date DESC", p)
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

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
    if constants.STUDENTS_STORE and not force_reload:
        return constants.STUDENTS_STORE
    
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/students")
        if res.get("ok"):
            classes = res.get("classes", [])
            constants.STUDENTS_STORE = {"list": classes, "by_id": {c["id"]: c for c in classes}}
            # حفظ في الملف المحلي للمزامنة
            try:
                ensure_dirs()
                with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                    json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[SYNC-STUDENTS-ERROR] {e}")
            return constants.STUDENTS_STORE

    ensure_dirs()
    if os.path.exists(STUDENTS_JSON):
        with open(STUDENTS_JSON, "r", encoding="utf-8") as f: data = json.load(f)
        classes = data.get("classes", [])
    else:
        # إذا لم يكن الملف موجوداً، لا تجبر المستخدم على الاستيراد إذا كان في وضع السحاب
        if client.is_active():
            return {"list": [], "by_id": {}}
            
        root = tk.Tk(); root.withdraw()
        confirm = messagebox.askyesno("بيانات الطلاب مفقودة", 
                                     "ملف الطلاب غير موجود. هل تريد استيراد ملف Excel الآن؟\n(اختر 'لا' إذا كنت تنوي المزامنة مع السحاب لاحقاً)")
        if not confirm:
            return {"list": [], "by_id": {}}
            
        path = filedialog.askopenfilename(title="اختر ملف Excel (طلاب)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: 
            return {"list": [], "by_id": {}}
        data = import_students_from_excel_sheet2_format(path)
        classes = data.get("classes", [])
    constants.STUDENTS_STORE = {"list": classes, "by_id": {c["id"]: c for c in classes}}
    return constants.STUDENTS_STORE

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
        n = t.get("اسم المعلم", "")
        if n and n not in seen:
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
            teachers = res.get("teachers", [])
            data = {"teachers": teachers}
            # حفظ في الملف المحلي للمزامنة
            try:
                ensure_dirs()
                with open(TEACHERS_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[SYNC-TEACHERS-ERROR] {e}")
            return data

    if os.path.exists(TEACHERS_JSON):
        with open(TEACHERS_JSON, "r", encoding="utf-8-sig") as f: return json.load(f)
    else:
        if client.is_active():
            return {"teachers": []}
            
        root = tk.Tk(); root.withdraw()
        confirm = messagebox.askyesno("بيانات المعلمين مفقودة", 
                                     "ملف المعلمين غير موجود. هل تريد استيراد الملف الآن؟")
        if not confirm:
            return {"teachers": []}
            
        path = filedialog.askopenfilename(title="اختر ملف Excel (معلمون)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: 
            return {"teachers": []}
        return import_teachers_from_excel(path)

def force_sync_cloud_data():
    """يجبر النظام على سحب البيانات من السحاب وحفظها محلياً."""
    try:
        load_students(force_reload=True)
        load_teachers()
        _sync_config_from_server()
        return True
    except Exception as e:
        print(f"[FORCE-SYNC-ERROR] {e}")
        return False

def _sync_config_from_server():
    """يسحب config.json من السيرفر ويدمج الإعدادات المهمة محلياً."""
    try:
        client = get_cloud_client()
        if not client or not client.is_active():
            return
        resp = client.get("/web/api/config")
        # الـ endpoint يُرجع الإعدادات مباشرة بدون مغلف ok/config
        remote = resp if isinstance(resp, dict) and "school_name" in resp else resp.get("config", {})
        if not remote:
            return
        from config_manager import load_config, save_config, invalidate_config_cache
        local = load_config()
        # المفاتيح التي يجب مزامنتها من السيرفر
        SYNC_KEYS = [
            "school_name", "school_gender",
            "tardiness_message_template", "message_template",
            "alert_absence_threshold", "alert_tardiness_threshold",
            "period_times", "school_start_time",
        ]
        changed = False
        for key in SYNC_KEYS:
            if key in remote and remote[key] != local.get(key):
                local[key] = remote[key]
                changed = True
        if changed:
            save_config(local)
            invalidate_config_cache()
            print("[CLOUD-SYNC] تم تحديث الإعدادات من السيرفر")
    except Exception as e:
        print(f"[CLOUD-SYNC-CONFIG-ERROR] {e}")

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
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/referrals/all", params={"status": status_filter})
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if status_filter:
        cur.execute("SELECT * FROM student_referrals WHERE status=? ORDER BY created_at DESC",
                    (status_filter,))
    else:
        cur.execute("SELECT * FROM student_referrals ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def get_referral_by_id(ref_id: int) -> dict:
    """يُعيد تفاصيل تحويل واحد."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get(f"/web/api/referrals/detail/{ref_id}")
        return res.get("row", {}) if res.get("ok") else {}

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM student_referrals WHERE id=?", (ref_id,))
    row = cur.fetchone(); con.close()
    return dict(row) if row else {}

def update_referral_deputy(ref_id: int, data: dict):
    """يحفظ إجراءات الوكيل على التحويل."""
    client = get_cloud_client()
    if client.is_active():
        data["id"] = ref_id
        client.post("/web/api/referrals/update-deputy", data)
        return

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
    client = get_cloud_client()
    if client.is_active():
        data["id"] = ref_id
        client.post("/web/api/referrals/update-counselor", data)
        return

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
    client = get_cloud_client()
    if client.is_active():
        client.post("/web/api/referrals/close", {"id": ref_id})
        return

    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE student_referrals SET status='resolved' WHERE id=?", (ref_id,))
    con.commit(); con.close()

def get_deputy_phones() -> list:
    """يُعيد أرقام جوالات المستخدمين ذوي دور وكيل."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/users/deputy-phones")
        return res.get("phones", []) if res.get("ok") else []

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
    client = get_cloud_client()
    if client.is_active():
        res = client.get(f"/web/api/academic-inquiry/{inq_id}")
        return res.get("row", {}) if res.get("ok") else {}

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM academic_inquiries WHERE id=?", (inq_id,))
    row = cur.fetchone(); con.close(); return dict(row) if row else {}

def reply_academic_inquiry(inq_id: int, data: dict):
    client = get_cloud_client()
    if client.is_active():
        # نرسل الـ id مع البيانات
        data["id"] = inq_id
        client.post("/web/api/reply-academic-inquiry", data)
        return

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


# ─── وظائف الموجه الطلابي المضافة للمزامنة ──────────────────────────

def insert_counselor_session(data: dict) -> int:
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/counselor/session/create", data)
        return res.get("id", 0) if res.get("ok") else 0

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO counselor_sessions (date, student_id, student_name, class_name, reason, notes, action_taken, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("date", now.split("T")[0]),
        data.get("student_id"), data.get("student_name"),
        data.get("class_name"), data.get("reason"),
        data.get("notes"), data.get("action_taken"), now
    ))
    new_id = cur.lastrowid
    con.commit(); con.close()
    return new_id

def get_counselor_sessions(student_id: str = None) -> list:
    client = get_cloud_client()
    if client.is_active():
        params = {"student_id": student_id} if student_id else {}
        res = client.get("/web/api/counselor/sessions", params=params)
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if student_id:
        cur.execute("SELECT * FROM counselor_sessions WHERE student_id=? ORDER BY date DESC, created_at DESC", (student_id,))
    else:
        cur.execute("SELECT * FROM counselor_sessions ORDER BY date DESC, created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def delete_counselor_session(sess_id: int):
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/counselor/session/{sess_id}")
        return

    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM counselor_sessions WHERE id=?", (sess_id,))
    con.commit(); con.close()

def insert_counselor_alert(data: dict) -> int:
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/counselor/alert/create", data)
        return res.get("id", 0) if res.get("ok") else 0

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO counselor_alerts (date, student_id, student_name, type, method, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("date", now.split("T")[0]),
        data.get("student_id"), data.get("student_name"),
        data.get("type"), data.get("method"),
        data.get("status"), now
    ))
    new_id = cur.lastrowid
    con.commit(); con.close()
    return new_id

def get_counselor_alerts(student_id: str = None) -> list:
    client = get_cloud_client()
    if client.is_active():
        params = {"student_id": student_id} if student_id else {}
        res = client.get("/web/api/counselor/alerts", params=params)
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if student_id:
        cur.execute("SELECT * FROM counselor_alerts WHERE student_id=? ORDER BY date DESC", (student_id,))
    else:
        cur.execute("SELECT * FROM counselor_alerts ORDER BY date DESC")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def insert_behavioral_contract(data: dict) -> int:
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/counselor/contract/create", data)
        return res.get("id", 0) if res.get("ok") else 0

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO behavioral_contracts
        (date, student_id, student_name, class_name, subject, period_from, period_to, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("date"), data.get("student_id"), data.get("student_name"),
        data.get("class_name"), data.get("subject"), data.get("period_from"),
        data.get("period_to"), data.get("notes"), now
    ))
    new_id = cur.lastrowid
    con.commit(); con.close()
    return new_id

def get_behavioral_contracts(student_id: str = None) -> list:
    client = get_cloud_client()
    if client.is_active():
        params = {"student_id": student_id} if student_id else {}
        res = client.get("/web/api/counselor/contracts", params=params)
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if student_id:
        cur.execute("SELECT * FROM behavioral_contracts WHERE student_id=? ORDER BY date DESC", (student_id,))
    else:
        cur.execute("SELECT * FROM behavioral_contracts ORDER BY date DESC, created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]; con.close(); return rows

def delete_behavioral_contract(contract_id: int):
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/counselor/contract/{contract_id}")
        return

    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM behavioral_contracts WHERE id=?", (contract_id,))
    con.commit(); con.close()

# ===================== بناء التقارير HTML =====================

# ─── وظائف التعاميم الرسمية ──────────────────────────────────────────

def create_circular(data: Dict[str, Any]) -> int:
    """يُنشئ تعميماً جديداً بحرفية عالية."""
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/circulars/create", data)
        return res.get("id", 0)

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO circulars (date, title, content, attachment_path, created_by, target_role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data.get("date", now[:10]), data["title"], data.get("content", ""),
          data.get("attachment_path", ""), data["created_by"],
          data.get("target_role", "all"), now))
    new_id = cur.lastrowid
    con.commit(); con.close()
    return new_id

def get_circulars(username: str = None, role: str = None) -> List[Dict[str, Any]]:
    """يجلب التعاميم الموجهة للمستخدم، مع حالة القراءة بشكل صحيح وموحد."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/circulars/list")
        if res and isinstance(res, dict) and res.get("ok"):
            return res.get("rows", [])
        return []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    # ضمان أن الدور في حالة صغيرة للمقارنة
    role = str(role).lower() if role else ""
    
    if role == "admin":
        # المدير يرى كل شيء مع عدد القراءات
        cur.execute("""
            SELECT c.*, 
                   (SELECT COUNT(*) FROM circular_reads r WHERE r.circular_id = c.id) as read_count,
                   1 as is_read
            FROM circulars c
            ORDER BY c.date DESC, c.id DESC
        """)
    else:
        # المستخدم العادي يرى الموجه له فقط (all أو دوره المحدد) + هل قرأه هو
        cur.execute("""
            SELECT c.*, 
                   (SELECT COUNT(*) FROM circular_reads r WHERE r.circular_id = c.id AND r.username = ?) as is_read
            FROM circulars c
            WHERE LOWER(c.target_role) = 'all' OR LOWER(c.target_role) = ?
            ORDER BY c.date DESC, c.id DESC
        """, (username, role))
    
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

def delete_circular(circular_id: int):
    """يحذف التعميم وسجلاته وملفه المرفق."""
    client = get_cloud_client()
    if client.is_active():
        client.delete(f"/web/api/circulars/{circular_id}")
        return

    con = get_db(); cur = con.cursor()
    # جلب مسار الملف قبل الحذف
    cur.execute("SELECT attachment_path FROM circulars WHERE id=?", (circular_id,))
    row = cur.fetchone()
    att_path = row[0] if row else ""
    
    # حذف سجلات القراءة والتعميم
    cur.execute("DELETE FROM circular_reads WHERE circular_id=?", (circular_id,))
    cur.execute("DELETE FROM circulars WHERE id=?", (circular_id,))
    con.commit(); con.close()
    
    # حذف الملف الفعلي إن وجد
    if att_path:
        full_path = os.path.join(DATA_DIR, att_path)
        if os.path.exists(full_path):
            try: os.remove(full_path)
            except: pass

def mark_circular_as_read(circular_id: int, username: str):
    """يسجل أن المستخدم قد قرأ التعميم."""
    client = get_cloud_client()
    if client.is_active():
        client.post("/web/api/circulars/mark-read", {"id": circular_id, "username": username})
        return

    con = get_db(); cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("INSERT OR IGNORE INTO circular_reads (circular_id, username, read_at) VALUES (?, ?, ?)",
                (circular_id, username, now))
    con.commit(); con.close()

def get_unread_circulars_count(username: str, role: str) -> int:
    """يحسب عدد التعاميم غير المقروءة الموجهة للمستخدم."""
    if role == "admin": return 0 # المدير لا يحتاج تنبيه لتعاميمه
    
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/circulars/unread-count")
        return res.get("count", 0)

    con = get_db(); cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM circulars c
        WHERE (c.target_role = 'all' OR c.target_role = ?)
        AND NOT EXISTS (SELECT 1 FROM circular_reads r WHERE r.circular_id = c.id AND r.username = ?)
    """, (role, username))
    count = cur.fetchone()[0]
    con.close()
    return count

def get_student_analytics_data(student_id: str) -> Dict[str, Any]:
    """
    يجمع كافة البيانات التحليلية لطالب واحد من جميع الجداول.
    """
    con = get_db(); cur = con.cursor()
    data = {"absences": [], "tardiness": [], "referrals": [], "sessions": [], "results": None}

    # 1. جلب سجلات الغياب مرتبة حسب التاريخ
    cur.execute("SELECT date, period FROM absences WHERE student_id=? ORDER BY date ASC", (student_id,))
    data["absences"] = [{"date": r[0], "period": r[1]} for r in cur.fetchall()]

    # 2. جلب سجلات التأخر
    cur.execute("SELECT date, minutes_late, period FROM tardiness WHERE student_id=? ORDER BY date ASC", (student_id,))
    data["tardiness"] = [{"date": r[0], "minutes": r[1], "period": r[2]} for r in cur.fetchall()]

    # 3. جلب التحويلات السلوكية
    status_map = {
        "pending": "قيد الانتظار",
        "with_deputy": "لدى الوكيل",
        "with_counselor": "لدى الموجه الطلابي",
        "completed": "مكتمل",
        "accepted": "مقبول",
        "rejected": "مرفوض"
    }
    cur.execute("SELECT ref_date, violation_type, violation, status FROM student_referrals WHERE student_id=? ORDER BY ref_date DESC", (student_id,))
    data["referrals"] = []
    for r in cur.fetchall():
        st_ar = status_map.get(r[3], r[3])
        data["referrals"].append({"date": r[0], "type": r[1], "violation": r[2], "status": st_ar})

    # 4. جلسات التوجيه الطلابي
    cur.execute("SELECT date, reason, action_taken FROM counselor_sessions WHERE student_id=? ORDER BY date DESC", (student_id,))
    data["sessions"] = [{"date": r[0], "reason": r[1], "action": r[2]} for r in cur.fetchall()]

    # 5. آخر نتيجة دراسية
    cur.execute("SELECT gpa, class_rank, subjects_json, school_year, section_rank FROM student_results WHERE identity_no=? ORDER BY uploaded_at DESC LIMIT 1", (student_id,))
    row = cur.fetchone()
    if row:
        data["results"] = {
            "gpa":          row[0],
            "rank":         row[1],
            "subjects":     json.loads(row[2]) if row[2] else [],
            "year":         row[3],
            "section_rank": row[4],
        }

    # 6. تجميع البيانات المحسوبة للويب والرسوم البيانية
    data["total_absences"] = len(data["absences"])
    data["total_tardiness"] = sum(r["minutes"] for r in data["tardiness"])
    data["behavior_referrals"] = len(data["referrals"])
    data["counselor_sessions"] = len(data["sessions"])
    
    gpa = "—"
    if data["results"] and data["results"].get("gpa"):
        gpa = f"{data['results']['gpa']}"
        if data["results"].get("rank"):
            gpa += f" (#{data['results']['rank']})"
    data["academic_results"] = gpa

    # اتجاه الغياب (شهرياً)
    trend = {}
    for a in data["absences"]:
        m = a["date"][:7] # YYYY-MM
        trend[m] = trend.get(m, 0) + 1
    data["absence_trend"] = trend

    # الاحداث الأخيرة (دمج الكل وترتيبهم)
    status_map = {
        "pending": "قيد الانتظار",
        "with_deputy": "لدى الوكيل",
        "with_counselor": "لدى الموجه الطلابي",
        "completed": "مكتمل",
        "accepted": "مقبول",
        "rejected": "مرفوض"
    }

    events = []
    for r in data["absences"]:
        events.append({"date": r["date"], "type": "غياب", "details": f"الحصة: {r['period']}", "status": "مسجل"})
    for r in data["tardiness"]:
        events.append({"date": r["date"], "type": "تأخر", "details": f"تأخر {r['minutes']} دقيقة", "status": "مسجل"})
    for r in data["referrals"]:
        st = r["status"]
        st_ar = status_map.get(st, st) # الترجمة أو النص الأصلي إن لم يوجد
        events.append({"date": r["date"], "type": f"تحويل {r['type']}", "details": r["violation"], "status": st_ar})
    for r in data["sessions"]:
        events.append({"date": r["date"], "type": "جلسة إرشادية", "details": r["reason"], "status": "منتهية"})
    
    events.sort(key=lambda x: x["date"], reverse=True)
    data["recent_events"] = events[:20]

    # إجمالي أيام الدراسة الفعلية (أيام تم تسجيل غياب فيها لأي طالب)
    cur.execute("SELECT COUNT(DISTINCT date) FROM absences")
    row = cur.fetchone()
    data["total_school_days"] = max(row[0], 1) if row else 1

    # الأعذار المقبولة
    cur.execute("SELECT date FROM excuses WHERE student_id=?", (student_id,))
    excused_dates = {r[0] for r in cur.fetchall()}
    data["excused_count"]   = len(excused_dates)
    data["unexcused_count"] = max(0, len(data["absences"]) - len(excused_dates))

    # توزيع الغياب حسب يوم الأسبوع
    day_names = ["الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
    dow = {d: 0 for d in day_names}
    import datetime as _dt
    for a in data["absences"]:
        try:
            d = _dt.date.fromisoformat(a["date"])
            dow[day_names[d.weekday()]] += 1
        except: pass
    data["absence_by_dow"] = dow

    # الملاحظات الإدارية
    cur.execute("SELECT id, note, author, created_at FROM student_notes WHERE student_id=? ORDER BY created_at DESC", (student_id,))
    data["notes"] = [{"id": r[0], "note": r[1], "author": r[2], "created_at": r[3]} for r in cur.fetchall()]

    con.close()
    return data


def get_student_notes(student_id: str) -> list:
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT id, note, author, created_at FROM student_notes WHERE student_id=? ORDER BY created_at DESC", (student_id,))
    rows = [{"id": r[0], "note": r[1], "author": r[2], "created_at": r[3]} for r in cur.fetchall()]
    con.close()
    return rows

def add_student_note(student_id: str, note: str, author: str) -> int:
    import datetime as _dt
    con = get_db(); cur = con.cursor()
    cur.execute("INSERT INTO student_notes (student_id, note, author, created_at) VALUES (?,?,?,?)",
                (student_id, note, author, _dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    new_id = cur.lastrowid
    con.commit(); con.close()
    return new_id

def delete_student_note(note_id: int):
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM student_notes WHERE id=?", (note_id,))
    con.commit(); con.close()


def clear_student_results():
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM student_results")
    con.commit(); con.close()
