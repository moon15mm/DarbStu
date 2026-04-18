# -*- coding: utf-8 -*-
"""
license_manager.py — نظام الترخيص والاشتراك
"""
import os, json, base64, datetime, hashlib, threading, requests, sys
from typing import List, Dict, Any, Optional
import hashlib as _hl, hmac as _hm, uuid as _uuid, platform as _plat
import tkinter as tk
from tkinter import ttk, messagebox
from constants import BASE_DIR, APP_VERSION, ROLES, CURRENT_USER
from database import get_db

# ═══════════════════════════════════════════════════════════════
# نظام الترخيص والاشتراك
# ═══════════════════════════════════════════════════════════════
import hashlib as _hl, hmac as _hm, uuid as _uuid, platform as _plat

LICENSE_FILE    = os.path.join(BASE_DIR, "license.dat")
LICENSE_SERVER  = "https://darbstu-license.up.railway.app"  # غيّر هذا
LICENSE_SECRET  = "DARB_SECRET_2025_XK9"  # سر مشترك بين البرنامج والخادم

def _get_machine_id() -> str:
    """معرف فريد للجهاز: MAC + اسم الجهاز."""
    try:
        mac  = hex(_uuid.getnode())
        host = _plat.node()
        raw  = "{}:{}".format(mac, host)
        return _hl.sha256(raw.encode()).hexdigest()[:32]
    except Exception:
        return "UNKNOWN"

def _sign(data: dict) -> str:
    """يوقّع البيانات بالسر المشترك."""
    import json as _j
    payload = _j.dumps(data, sort_keys=True, ensure_ascii=False)
    return _hm.new(
        LICENSE_SECRET.encode(), payload.encode(), _hl.sha256
    ).hexdigest()

def _verify_signature(data: dict, signature: str) -> bool:
    return _hm.compare_digest(_sign(data), signature)

def save_license(lic: dict):
    """يحفظ ملف الترخيص مشفراً."""
    import json as _j, base64 as _b64
    raw = _j.dumps(lic, ensure_ascii=False)
    enc = _b64.b64encode(raw.encode()).decode()
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        f.write(enc)

def load_license() -> dict:
    """يقرأ ملف الترخيص."""
    import json as _j, base64 as _b64
    if not os.path.exists(LICENSE_FILE):
        return {}
    try:
        with open(LICENSE_FILE, encoding="utf-8") as f:
            enc = f.read().strip()
        raw = _b64.b64decode(enc).decode()
        return _j.loads(raw)
    except Exception:
        return {}

def check_license() -> dict:
    """
    يتحقق من حالة الترخيص.
    يُرجع: {"valid": bool, "days_left": int, "school": str, "msg": str}
    """
    lic = load_license()
    if not lic:
        return {"valid": False, "days_left": 0, "school": "",
                "msg": "لم يتم تفعيل البرنامج — أدخل مفتاح الترخيص"}

    # تحقق من التوقيع
    sig  = lic.pop("signature", "")
    valid_sig = _verify_signature(lic, sig)
    lic["signature"] = sig
    if not valid_sig:
        return {"valid": False, "days_left": 0, "school": lic.get("school_name",""),
                "msg": "ملف الترخيص تالف — تواصل مع الدعم"}

    # تحقق من الجهاز
    machine_id = _get_machine_id()
    if lic.get("machine_id") and lic["machine_id"] != machine_id:
        return {"valid": False, "days_left": 0, "school": lic.get("school_name",""),
                "msg": "الترخيص مرتبط بجهاز مختلف — تواصل مع الدعم"}

    # تحقق من تاريخ الانتهاء
    try:
        expiry    = datetime.date.fromisoformat(lic["expiry_date"])
        today     = datetime.date.today()
        days_left = (expiry - today).days
    except Exception:
        days_left = -1

    if days_left < 0:
        return {"valid": False, "days_left": 0,
                "school": lic.get("school_name",""),
                "msg": "انتهى الاشتراك بتاريخ {} — جدّد اشتراكك".format(
                    lic.get("expiry_date",""))}

    return {"valid": True, "days_left": days_left,
            "school": lic.get("school_name",""),
            "expiry": lic.get("expiry_date",""),
            "msg": ""}

def activate_license(license_key: str) -> tuple:
    """
    يتصل بالخادم ويفعّل الترخيص.
    يُرجع: (True, "رسالة") أو (False, "خطأ")
    """
    import urllib.request, json as _j
    machine_id = _get_machine_id()
    payload    = _j.dumps({
        "license_key": license_key.strip().upper(),
        "machine_id":  machine_id,
    }).encode()

    try:
        req  = urllib.request.Request(
            LICENSE_SERVER + "/activate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")
        resp = urllib.request.urlopen(req, timeout=8)
        data = _j.loads(resp.read())

        if data.get("ok"):
            lic = data["license"]
            lic["machine_id"] = machine_id
            # احسب التوقيع
            sig = _sign({k:v for k,v in lic.items() if k != "signature"})
            lic["signature"] = sig
            save_license(lic)
            return True, "تم تفعيل البرنامج بنجاح! صالح حتى " + lic.get("expiry_date","")
        else:
            return False, data.get("msg", "مفتاح غير صالح")
    except urllib.error.URLError:
        return False, "تعذّر الاتصال بخادم التفعيل — تحقق من الإنترنت"
    except Exception as e:
        return False, str(e)

def try_renew_license():
    """يحاول تجديد الترخيص تلقائياً لو اقترب الانتهاء (<7 أيام)."""
    import urllib.request, json as _j
    lic = load_license()
    if not lic: return

    status = check_license()
    if not status["valid"]: return
    if status["days_left"] > 7: return

    # حاول التجديد
    try:
        payload = _j.dumps({
            "license_key": lic.get("license_key",""),
            "machine_id":  _get_machine_id(),
        }).encode()
        req  = urllib.request.Request(
            LICENSE_SERVER + "/renew",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")
        resp = urllib.request.urlopen(req, timeout=5)
        data = _j.loads(resp.read())
        if data.get("ok"):
            new_lic = data["license"]
            new_lic["machine_id"] = _get_machine_id()
            sig = _sign({k:v for k,v in new_lic.items() if k != "signature"})
            new_lic["signature"] = sig
            save_license(new_lic)
            print("[LICENSE] ✅ تم تجديد الترخيص حتى", new_lic.get("expiry_date",""))
    except Exception as e:
        print("[LICENSE] تحذير — تعذّر التجديد التلقائي:", e)


class LicenseWindow:
    """شاشة التفعيل وانتهاء الاشتراك."""

    def __init__(self, root: tk.Tk, status: dict, on_success=None):
        self.root       = root
        self.status     = status
        self.on_success = on_success
        self._build(root)

    def _build(self, root):
        win = tk.Toplevel(root)
        win.title("ترخيص DarbStu")
        win.geometry("480x380")
        win.resizable(False, False)
        win.transient(root)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", root.destroy)  # إغلاق = خروج من البرنامج

        # خلفية
        bg = tk.Frame(win, bg="#1565C0")
        bg.pack(fill="both", expand=True)

        tk.Label(bg, text="🔐 DarbStu",
                 bg="#1565C0", fg="white",
                 font=("Tahoma",18,"bold")).pack(pady=(28,4))
        tk.Label(bg, text="نظام إدارة الغياب والتأخر",
                 bg="#1565C0", fg="#90CAF9",
                 font=("Tahoma",11)).pack(pady=(0,20))

        # بطاقة بيضاء
        card = tk.Frame(bg, bg="white", padx=28, pady=24)
        card.pack(fill="x", padx=24)

        # رسالة الحالة
        msg = self.status.get("msg","")
        days_left = self.status.get("days_left",0)

        if not self.status.get("valid"):
            tk.Label(card, text="⛔ " + msg,
                     bg="white", fg="#C62828",
                     font=("Tahoma",11,"bold"),
                     wraplength=380).pack(pady=(0,16))
        else:
            tk.Label(card, text="⚠️ متبقي {} يوم فقط على انتهاء الاشتراك".format(days_left),
                     bg="white", fg="#E65100",
                     font=("Tahoma",11,"bold")).pack(pady=(0,16))

        tk.Label(card, text="أدخل مفتاح الترخيص:",
                 bg="white", fg="#374151",
                 font=("Tahoma",10)).pack(anchor="e")

        self.key_var = tk.StringVar()
        key_entry = ttk.Entry(card, textvariable=self.key_var,
                              width=32, justify="center",
                              font=("Tahoma",11))
        key_entry.pack(pady=6, ipady=4)
        key_entry.focus()

        self.status_lbl = tk.Label(card, text="",
                                    bg="white", font=("Tahoma",9))
        self.status_lbl.pack(pady=(0,8))

        btn = tk.Button(card,
            text="✅ تفعيل البرنامج",
            bg="#1565C0", fg="white",
            font=("Tahoma",11,"bold"),
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=self._activate)
        btn.pack()

        # رابط تواصل
        tk.Label(bg,
            text="للاشتراك والتجديد: تواصل مع مزوّد البرنامج",
            bg="#1565C0", fg="#90CAF9",
            font=("Tahoma",9)).pack(pady=14)

        self.win = win
        key_entry.bind("<Return>", lambda e: self._activate())

    def _activate(self):
        key = self.key_var.get().strip()
        if not key:
            self.status_lbl.config(text="أدخل المفتاح أولاً", fg="#C62828")
            return
        self.status_lbl.config(text="⏳ جارٍ التفعيل...", fg="#1565C0")
        self.win.update_idletasks()

        import threading as _th
        def _run():
            ok, msg = activate_license(key)
            def _done():
                if ok:
                    self.status_lbl.config(text="✅ " + msg, fg="#2E7D32")
                    self.win.after(1200, self._on_activated)
                else:
                    self.status_lbl.config(text="❌ " + msg, fg="#C62828")
            self.win.after(0, _done)
        _th.Thread(target=_run, daemon=True).start()

    def _on_activated(self):
        self.win.destroy()
        if self.on_success:
            self.on_success()


# ═══════════════════════════════════════════════════════════════
# رموز تفعيل بوابة النتائج — أحادية الاستخدام
# ═══════════════════════════════════════════════════════════════

import secrets as _secrets
import string  as _string

def generate_tokens(count: int = 1, note: str = "") -> List[str]:
    """يولّد رموز تفعيل عشوائية ويحفظها في DB."""
    CHARS = _string.ascii_uppercase + _string.digits
    # استبعد الأحرف المتشابهة بصرياً
    CHARS = CHARS.replace("0","").replace("O","").replace("I","").replace("1","")
    tokens = []
    con = get_db(); cur = con.cursor()
    for _ in range(count):
        while True:
            # صيغة XXXX-XXXX
            raw   = "".join(_secrets.choice(CHARS) for _ in range(8))
            token = raw[:4] + "-" + raw[4:]
            # تأكد من عدم التكرار
            cur.execute("SELECT id FROM result_tokens WHERE token=?", (token,))
            if not cur.fetchone():
                break
        cur.execute("""INSERT INTO result_tokens (token, created_at, note)
                       VALUES (?,?,?)""",
                    (token, datetime.datetime.utcnow().isoformat(), note))
        tokens.append(token)
    con.commit(); con.close()
    return tokens

def consume_token(token: str) -> bool:
    """
    يتحقق من صحة الرمز ويحذفه فوراً.
    يُرجع True إذا كان صحيحاً، False إذا لم يُوجد أو استُخدم.
    """
    token = token.strip().upper()
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM result_tokens WHERE token=?", (token,))
    deleted = cur.rowcount
    con.commit(); con.close()
    return deleted > 0

def get_tokens_count() -> int:
    """عدد الرموز المتبقية."""
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM result_tokens")
    count = cur.fetchone()[0]
    con.close()
    return count

def get_all_tokens() -> List[Dict]:
    """يُرجع كل الرموز المتبقية."""
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM result_tokens ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

def delete_all_tokens():
    """يحذف كل الرموز (إعادة ضبط)."""
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM result_tokens")
    con.commit(); con.close()


# ═══════════════════════════════════════════════════════════════
# نظام الترخيص — شاشة التفعيل
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# نظام الترخيص — مضمّن مباشرة
# ═══════════════════════════════════════════════════════════════

import os, json, hashlib, platform, uuid, datetime
import urllib.request, urllib.error

# ─── إعدادات (غيّرها قبل التوزيع) ───────────────────────────
SHEET_ID         = os.environ.get("GSHEET_ID",       "1tdX9spw1sGEDeeExKouGghN_y37fUPJG3LDXi5v7Tao")
APPS_SCRIPT_URL  = os.environ.get("APPS_SCRIPT_URL", "https://script.google.com/macros/s/AKfycbyzg2NkvN779YIsFq-w3xQTZI5AZ3bRlar7KcKfCkhUFqFeItzhWVLadBmKLFwOVWs/exec")
LICENSE_FILE     = os.path.join(BASE_DIR, ".darb_license")
TRIAL_FILE       = os.path.join(BASE_DIR, ".darb_trial")
TRIAL_DAYS       = 7
SHEET_CSV_URL    = "https://docs.google.com/spreadsheets/d/{}/export?format=csv&gid=0"


class LicenseClient:

    def __init__(self):
        self._cache = self._load_cache()

    # ── معرّف الجهاز ──────────────────────────────────────────
    def _machine_id(self) -> str:
        try:
            raw = "{}-{}-darb".format(uuid.getnode(), platform.node())
            return hashlib.sha256(raw.encode()).hexdigest()[:32]
        except:
            return hashlib.sha256(b"fallback").hexdigest()[:32]

    # ── كاش محلي ──────────────────────────────────────────────
    def _load_cache(self) -> dict:
        try:
            if os.path.exists(LICENSE_FILE):
                with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_cache(self, data: dict):
        try:
            with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[LICENSE] تحذير: لم يُحفظ الملف:", e)

    # ── الواجهة الرئيسية ──────────────────────────────────────
    def is_activated(self) -> bool:
        return self._cache.get("activated") is True

    def _get_trial(self) -> dict:
        """يُنشئ أو يقرأ فترة التجربة المجانية."""
        try:
            if os.path.exists(TRIAL_FILE):
                with open(TRIAL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"start": datetime.datetime.utcnow().isoformat()}
                with open(TRIAL_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            start     = datetime.datetime.fromisoformat(data["start"])
            elapsed   = (datetime.datetime.utcnow() - start).days
            days_left = max(0, TRIAL_DAYS - elapsed)
            return {"valid": days_left > 0, "days_left": days_left}
        except Exception:
            return {"valid": True, "days_left": TRIAL_DAYS}

    def check(self) -> tuple:
        """فحص محلي — بدون إنترنت بعد التفعيل."""
        if self.is_activated():
            school = self._cache.get("school_name", "")
            plan   = self._cache.get("plan", "basic")
            return True, "✅ البرنامج مُفعَّل — {}".format(school or plan), self._cache

        # فترة التجربة
        trial = self._get_trial()
        if trial["valid"]:
            days_left = trial["days_left"]
            return True, "⏳ فترة التجربة — متبقي {} يوم".format(days_left), {"trial": True, "days_left": days_left}

        return False, "انتهت فترة التجربة (7 أيام) — أدخل مفتاح الترخيص للاستمرار", {}

    def activate(self, license_key: str, school_name: str = "") -> tuple:
        """
        خطوات التفعيل:
        1. تحقق من الرمز في الـ Sheet (قراءة)
        2. احذفه من الـ Sheet عبر Apps Script (إلزامي)
        3. إذا نجح الحذف → احفظ التفعيل محلياً
        """
        license_key = license_key.strip().upper()
        if not license_key:
            return False, "أدخل مفتاح الترخيص", {}

        if SHEET_ID == "YOUR_SHEET_ID_HERE":
            return False, "❌ لم يُضبط SHEET_ID — تواصل مع الدعم", {}

        if APPS_SCRIPT_URL == "YOUR_APPS_SCRIPT_URL_HERE":
            return False, "❌ لم يُضبط APPS_SCRIPT_URL — تواصل مع الدعم", {}

        # ── الخطوة 1: تحقق من وجود الرمز في الـ Sheet
        rows, err = self._fetch_sheet()
        if err:
            return False, "❌ تعذّر الاتصال بالإنترنت:\n{}".format(err), {}

        found = None
        for row in rows:
            if row and row[0].strip().upper() == license_key:
                found = row
                break

        if not found:
            return False, "❌ الرمز غير صحيح أو استُخدم مسبقاً", {}

        # استخرج بيانات الخطة
        plan         = found[1].strip() if len(found) > 1 and found[1].strip() else "basic"
        max_students_raw = found[2].strip() if len(found) > 2 else "500"
        try:
            max_students = int(max_students_raw)
        except:
            max_students = 500

        # ── الخطوة 2: احذف الرمز (إلزامي)
        deleted, del_msg = self._delete_key(license_key)
        if not deleted:
            return False, "❌ فشل حذف الرمز — لم يكتمل التفعيل:\n{}".format(del_msg), {}

        # ── الخطوة 3: احفظ التفعيل محلياً
        cache = {
            "activated":    True,
            "license_key":  license_key,
            "plan":         plan,
            "max_students": max_students,
            "school_name":  school_name,
            "machine_id":   self._machine_id(),
            "activated_at": datetime.datetime.utcnow().isoformat(),
        }
        self._cache = cache
        self._save_cache(cache)
        return True, "✅ تم التفعيل بنجاح — مرحباً بـ {}".format(
            school_name or "مدرستكم"), cache

    # ── جلب الـ Sheet ──────────────────────────────────────────
    def _fetch_sheet(self) -> tuple:
        try:
            import csv, io
            url = SHEET_CSV_URL.format(SHEET_ID)
            req = urllib.request.Request(url, headers={"User-Agent": "DarbStu/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8")
            reader = csv.reader(io.StringIO(text))
            rows   = [r for r in reader if r and r[0].strip()]
            # تجاهل صف العناوين إذا لم يكن رمزاً
            if rows and not rows[0][0].strip()[0:4].isalpha():
                rows = rows[1:]
            return rows, None
        except urllib.error.URLError as e:
            return [], "خطأ شبكة: {}".format(e.reason)
        except Exception as e:
            return [], str(e)

    # ── حذف الرمز عبر Apps Script ─────────────────────────────
    def _delete_key(self, license_key: str) -> tuple:
        """يحذف الرمز عبر Apps Script مع متابعة الـ redirects."""
        try:
            import json as _j, urllib.parse

            params = urllib.parse.urlencode({"key": license_key})
            url    = "{}?{}".format(APPS_SCRIPT_URL, params)

            # opener يتبع الـ redirects تلقائياً
            opener = urllib.request.build_opener(
                urllib.request.HTTPRedirectHandler())
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"})

            with opener.open(req, timeout=15) as resp:
                body = resp.read().decode("utf-8").strip()

            data = _j.loads(body)
            return (True, "تم") if data.get("ok") else (False, data.get("msg", "فشل"))

        except urllib.error.URLError as e:
            return False, "لا يوجد اتصال: {}".format(e.reason)
        except Exception as e:
            return False, str(e)

    # ── معلومات ───────────────────────────────────────────────
    def plan(self) -> str:
        return self._cache.get("plan", "basic")

    def max_students(self) -> int:
        return int(self._cache.get("max_students", 500))


def check_license_on_startup(root=None) -> tuple:
    """يفحص الترخيص من الملف المحلي — بدون إنترنت بعد التفعيل."""
    try:
        client = LicenseClient()
        ok, msg, info = client.check()
        return ok, msg, info, client
    except Exception as e:
        return False, "خطأ في الترخيص: {}".format(e), {}, None


class ActivationWindow:
    """نافذة تفعيل البرنامج — تظهر عند أول تشغيل أو انتهاء الترخيص."""

    def __init__(self, root, msg="", on_success=None):
        self.root       = root
        self.on_success = on_success

        self.win = tk.Toplevel(root)
        self.win.title("تفعيل DarbStu")
        self.win.geometry("480x400")
        self.win.resizable(False, False)
        self.win.grab_set()
        self.win.lift()
        self.win.focus_force()
        self.win.attributes("-topmost", True)
        self.win.update_idletasks()
        w = 480; h = 400
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.win.geometry("{}x{}+{}+{}".format(w, h, x, y))
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        try: self.win.state("normal")
        except: pass

        hdr = tk.Frame(self.win, bg="#1565C0", height=70)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="تفعيل DarbStu",
                 bg="#1565C0", fg="white",
                 font=("Tahoma",15,"bold")).pack(pady=20)

        body = tk.Frame(self.win, bg="white", padx=30, pady=20)
        body.pack(fill="both", expand=True)

        if msg:
            tk.Label(body, text=msg, bg="white",
                     fg="#C62828", font=("Tahoma",9),
                     wraplength=400).pack(pady=(0,12))

        tk.Label(body, text="أدخل مفتاح الترخيص:",
                 bg="white", fg="#374151",
                 font=("Tahoma",10,"bold")).pack(anchor="e")

        self.key_var = tk.StringVar()
        key_entry = ttk.Entry(body, textvariable=self.key_var,
                              width=28, font=("Courier",13),
                              justify="center")
        key_entry.pack(pady=8, ipady=6)
        key_entry.focus()
        key_entry.bind("<Return>", lambda e: self._activate())

        tk.Label(body, text="مثال: DARB-A3B7-XY2K-P9QR",
                 bg="white", fg="#9CA3AF",
                 font=("Tahoma",8)).pack()

        ttk.Label(body, text="اسم المدرسة (اختياري):").pack(
            anchor="e", pady=(12,0))
        self.school_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.school_var,
                  width=32, justify="right").pack(pady=4)

        self.status_lbl = tk.Label(body, text="", bg="white",
                                    font=("Tahoma",9))
        self.status_lbl.pack(pady=6)

        ttk.Button(body, text="تفعيل",
                   command=self._activate).pack(ipadx=20, ipady=4)

        tk.Label(body,
            text="للحصول على مفتاح ترخيص تواصل مع المطور",
            bg="white", fg="#5A6A7E",
            font=("Tahoma",8)).pack(pady=(10,0))

    def _activate(self):
        key    = self.key_var.get().strip()
        school = self.school_var.get().strip()
        if not key:
            self.status_lbl.config(text="أدخل مفتاح الترخيص", foreground="#C62828")
            return

        self.status_lbl.config(text="جارٍ التحقق...", foreground="#1565C0")
        self.win.update_idletasks()

        import threading as _th
        def _run():
            try:
                client = LicenseClient()
                ok, msg, info = client.activate(key, school)
                def _done():
                    if ok:
                        self.status_lbl.config(text=msg, foreground="#2E7D32")
                        self.win.after(1000, self._success)
                    else:
                        self.status_lbl.config(text=msg, foreground="#C62828")
                self.win.after(0, _done)
            except Exception as e:
                def _err(m=str(e)):
                    self.status_lbl.config(text="خطأ: "+m, foreground="#C62828")
                self.win.after(0, _err)

        _th.Thread(target=_run, daemon=True).start()

    def _success(self):
        self.win.destroy()
        if self.on_success:
            self.on_success()

    def _on_close(self):
        """إغلاق نافذة التفعيل = إغلاق البرنامج."""
        self.root.destroy()
        sys.exit(0)
