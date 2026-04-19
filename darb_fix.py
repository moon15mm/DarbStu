# -*- coding: utf-8 -*-
"""
darb_fix.py — أداة الإصلاح التلقائي الشاملة لـ DarbStu
تشخّص المشكلة أولاً ثم تحلّها خطوة بخطوة.
"""
import os, sys, time, socket, subprocess, shutil, ssl, threading, datetime, re
import urllib.request, tkinter as tk
from tkinter import ttk, scrolledtext

# ── إعدادات ────────────────────────────────────────────────────────
CHECK_URL   = "https://darbte.uk/web/dashboard"
LOCAL_PORT  = 8000
SSL_CTX     = ssl._create_unverified_context()
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
LOG_FILE    = os.path.join(BASE_DIR, "darb_fix_log.txt")
CF_DL_URL   = ("https://github.com/cloudflare/cloudflared/releases/latest"
                "/download/cloudflared-windows-amd64.exe")
VERSION_URL = "https://raw.githubusercontent.com/moon15mm/DarbStu/main/version.json"
ZIP_URL     = "https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip"
PROTECTED   = {"data", "my-whatsapp-server", "__pycache__", ".git", ".github",
               "Output", "build", "dist"}
UPDATE_EXTS = {".py", ".txt", ".json", ".iss", ".bat", ".spec", ".ico"}
SKIP_FILES  = {"data/config.json","data/students.json",
               "data/users.json","data/teachers.json"}

# ══════════════════════════════════════════════════════════════════
class DarbFixApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🔧 DarbStu — الإصلاح التلقائي الشامل")
        self.root.geometry("780x680")
        self.root.resizable(True, True)
        self.root.configure(bg="white")
        self._diag_labels = {}
        self._build_ui()

    # ── بناء الواجهة ──────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#1565C0", height=60)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔧  أداة الإصلاح التلقائي الشاملة — DarbStu",
                 bg="#1565C0", fg="white",
                 font=("Tahoma", 13, "bold")).pack(expand=True)

        # ── لوحة التشخيص ──────────────────────────────────────────
        diag_lf = ttk.LabelFrame(self.root, text=" حالة المكوّنات ", padding=8)
        diag_lf.pack(fill="x", padx=12, pady=(8, 0))

        components = [
            ("internet",  "🌐  الإنترنت"),
            ("port",      f"🖥️  السيرفر المحلي :{LOCAL_PORT}"),
            ("darb",      "📦  DarbStu.exe"),
            ("cf",        "🔗  cloudflared.exe"),
            ("domain",    "🌍  darbte.uk"),
        ]
        for i, (key, label) in enumerate(components):
            row = i // 3
            col = i % 3
            cell = tk.Frame(diag_lf, bg="white", relief="solid", bd=1)
            cell.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            diag_lf.columnconfigure(col, weight=1)
            tk.Label(cell, text=label, bg="white",
                     font=("Tahoma", 9), anchor="w").pack(side="left", padx=6)
            lbl = tk.Label(cell, text="—", bg="white",
                           font=("Tahoma", 9, "bold"), fg="#94a3b8")
            lbl.pack(side="right", padx=6)
            self._diag_labels[key] = lbl

        # شريط الحالة
        bar = tk.Frame(self.root, bg="#f0f4ff", pady=6)
        bar.pack(fill="x", padx=12, pady=(6, 0))
        self._status_dot = tk.Label(bar, text="⬤", fg="#94a3b8",
                                     bg="#f0f4ff", font=("Tahoma", 13))
        self._status_dot.pack(side="right", padx=(0, 6))
        self._status_var = tk.StringVar(value="اضغط 'ابدأ' للتشخيص والإصلاح")
        tk.Label(bar, textvariable=self._status_var,
                 bg="#f0f4ff", fg="#1e40af",
                 font=("Tahoma", 11, "bold"), anchor="e").pack(side="right")

        # منطقة السجل
        log_lf = ttk.LabelFrame(self.root, text=" سجل العمليات ", padding=5)
        log_lf.pack(fill="both", expand=True, padx=12, pady=6)
        self.log_box = scrolledtext.ScrolledText(
            log_lf, font=("Courier New", 9), wrap="word",
            state="disabled", bg="#0f172a", fg="#e2e8f0",
            insertbackground="white", height=20)
        self.log_box.pack(fill="both", expand=True)
        for tag, color in [("ok","#4ade80"), ("err","#f87171"),
                            ("warn","#fbbf24"), ("info","#93c5fd"),
                            ("head","#c084fc"), ("gray","#94a3b8")]:
            self.log_box.tag_config(tag, foreground=color)

        # الأزرار
        btn_f = tk.Frame(self.root, bg="white")
        btn_f.pack(fill="x", padx=12, pady=(0, 10))
        self._start_btn = tk.Button(
            btn_f, text="▶  ابدأ الفحص والإصلاح",
            bg="#1565C0", fg="white", font=("Tahoma", 11, "bold"),
            relief="flat", padx=20, pady=9, cursor="hand2",
            command=self._start)
        self._start_btn.pack(side="right", padx=4)

        self._diag_btn = tk.Button(
            btn_f, text="🔍  فحص سريع فقط",
            bg="#0f766e", fg="white", font=("Tahoma", 10),
            relief="flat", padx=12, pady=9, cursor="hand2",
            command=self._quick_diag)
        self._diag_btn.pack(side="right", padx=4)

        self._upd_btn = tk.Button(
            btn_f, text="⬆️  تحديث يدوي",
            bg="#7c3aed", fg="white", font=("Tahoma", 10),
            relief="flat", padx=12, pady=9, cursor="hand2",
            command=self._manual_update)
        self._upd_btn.pack(side="right", padx=4)

        tk.Button(btn_f, text="مسح السجل", command=self._clear,
                  bg="#e5e7eb", relief="flat", padx=12, pady=9,
                  font=("Tahoma", 10), cursor="hand2").pack(side="right", padx=4)

    # ── دوال السجل والحالة ─────────────────────────────────────────
    def _log(self, msg, tag="info"):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{now}]  {msg}\n"
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", line, tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.root.after(0, _do)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(line)
        except: pass

    def _status(self, text, color="#1e40af", dot="#94a3b8"):
        self.root.after(0, lambda: (
            self._status_var.set(text),
            self._status_dot.config(fg=dot)
        ))

    def _set_diag(self, key, text, color):
        lbl = self._diag_labels.get(key)
        if lbl:
            self.root.after(0, lambda: lbl.config(text=text, fg=color))

    def _clear(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def _set_btn(self, enabled):
        text = "▶  ابدأ الفحص والإصلاح" if enabled else "⏳  جارٍ الإصلاح..."
        st = "normal" if enabled else "disabled"
        self.root.after(0, lambda: (
            self._start_btn.config(state=st, text=text),
            self._diag_btn.config(state=st),
            self._upd_btn.config(state=st),
        ))

    # ── دوال الفحص ─────────────────────────────────────────────────
    def _domain_ok(self):
        for ctx in [SSL_CTX, None]:
            try:
                kw = {"context": ctx} if ctx else {}
                with urllib.request.urlopen(CHECK_URL, timeout=8, **kw) as r:
                    if r.status < 500: return True
            except: pass
        return False

    def _internet_ok(self):
        for host in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
            try:
                s = socket.socket(); s.settimeout(3)
                s.connect(host); s.close(); return True
            except: pass
        return False

    def _port_ok(self, port=None):
        try:
            s = socket.socket(); s.settimeout(2)
            s.connect(("127.0.0.1", port or LOCAL_PORT)); s.close(); return True
        except: return False

    def _proc_running(self, name):
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW)
            return name.lower() in out.lower()
        except: return False

    def _kill(self, name):
        try:
            subprocess.run(["taskkill", "/F", "/IM", name],
                           capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            self._log(f"   ⛔  تم إيقاف {name}", "warn")
        except: pass

    def _find_exe(self, filename):
        candidates = [
            os.path.join(BASE_DIR, filename),
            os.path.join(BASE_DIR, "..", filename),
            os.path.join(os.path.expanduser("~/Desktop"), filename),
            os.path.join(os.path.expanduser("~/Desktop/DarbStu"), filename),
            r"C:\Program Files\cloudflared\cloudflared.exe",
            r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            r"C:\Windows\System32\cloudflared.exe",
        ]
        for p in candidates:
            if os.path.exists(os.path.normpath(p)): return os.path.normpath(p)
        found = shutil.which(filename)
        if found: return found
        # بحث في Desktop
        desktop = os.path.expanduser("~/Desktop")
        if os.path.isdir(desktop):
            for d in os.listdir(desktop):
                p = os.path.join(desktop, d, filename)
                if os.path.exists(p): return p
        return None

    def _get_pid_on_port(self, port):
        """يُعيد PID العملية التي تستخدم المنفذ، أو None"""
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"],
                encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW)
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts: return parts[-1]
        except: pass
        return None

    # ── التشخيص المرئي ─────────────────────────────────────────────
    def _run_diag(self):
        """يُحدّث لوحة التشخيص ويُعيد dict بالنتائج"""
        results = {}

        # إنترنت
        v = self._internet_ok()
        results["internet"] = v
        self._set_diag("internet", "✅ يعمل" if v else "❌ منقطع",
                        "#16a34a" if v else "#dc2626")

        # منفذ محلي
        v = self._port_ok()
        results["port"] = v
        self._set_diag("port", "✅ يستجيب" if v else "❌ متوقف",
                        "#16a34a" if v else "#dc2626")

        # DarbStu
        v = self._proc_running("DarbStu.exe")
        results["darb"] = v
        self._set_diag("darb", "✅ يعمل" if v else "❌ متوقف",
                        "#16a34a" if v else "#dc2626")

        # cloudflared
        v = self._proc_running("cloudflared.exe")
        results["cf"] = v
        self._set_diag("cf", "✅ يعمل" if v else "❌ متوقف",
                        "#16a34a" if v else "#dc2626")

        # الدومين
        self._set_diag("domain", "🔄 فحص...", "#f59e0b")
        v = self._domain_ok()
        results["domain"] = v
        self._set_diag("domain", "✅ يعمل" if v else "❌ 502",
                        "#16a34a" if v else "#dc2626")

        return results

    def _quick_diag(self):
        self._set_btn(False)
        def _do():
            self._log("━" * 52, "head")
            self._log("  🔍  فحص سريع لحالة المكوّنات", "head")
            self._log("━" * 52, "head")
            r = self._run_diag()
            self._log(f"   🌐  الإنترنت    : {'✅' if r['internet'] else '❌'}", "ok" if r['internet'] else "err")
            self._log(f"   🖥️  منفذ {LOCAL_PORT}  : {'✅' if r['port'] else '❌'}", "ok" if r['port'] else "err")
            self._log(f"   📦  DarbStu.exe : {'✅' if r['darb'] else '❌'}", "ok" if r['darb'] else "err")
            self._log(f"   🔗  cloudflared : {'✅' if r['cf'] else '❌'}", "ok" if r['cf'] else "err")
            self._log(f"   🌍  darbte.uk   : {'✅' if r['domain'] else '❌'}", "ok" if r['domain'] else "err")
            if r['domain']:
                self._status("✅ كل شيء يعمل", "#166534", "#4ade80")
            elif not r['internet']:
                self._status("❌ لا إنترنت", "#991b1b", "#f87171")
            elif not r['port']:
                self._status("⚠️ السيرفر المحلي متوقف", "#92400e", "#fbbf24")
            elif not r['cf']:
                self._status("⚠️ cloudflared متوقف", "#92400e", "#fbbf24")
            else:
                self._status("⚠️ مشكلة في الاتصال", "#92400e", "#fbbf24")
            self._set_btn(True)
        threading.Thread(target=_do, daemon=True).start()

    # ── البدء ─────────────────────────────────────────────────────
    def _start(self):
        self._set_btn(False)
        threading.Thread(target=self._run, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # منطق الإصلاح الرئيسي
    # ══════════════════════════════════════════════════════════════
    def _run(self):
        self._log("━" * 52, "head")
        self._log("  🔧  بدء جلسة الإصلاح التلقائي الشامل", "head")
        self._log("━" * 52, "head")
        self._status("🔍 جارٍ التشخيص...", dot="#fbbf24")

        # ── تشخيص أولي ────────────────────────────────────────────
        diag = self._run_diag()
        self._log(f"   🌐 إنترنت: {'✅' if diag['internet'] else '❌'}  |  "
                  f"🖥️ منفذ {LOCAL_PORT}: {'✅' if diag['port'] else '❌'}  |  "
                  f"📦 DarbStu: {'✅' if diag['darb'] else '❌'}  |  "
                  f"🔗 CF: {'✅' if diag['cf'] else '❌'}  |  "
                  f"🌍 Domain: {'✅' if diag['domain'] else '❌'}", "info")

        if diag["domain"]:
            self._log("✅  الموقع يعمل بشكل صحيح — لا يحتاج إصلاح!", "ok")
            self._status("✅ الموقع يعمل", "#166534", "#4ade80")
            self._set_btn(True); return

        if not diag["internet"]:
            self._log("❌  لا يوجد اتصال بالإنترنت!", "err")
            self._log("   → تأكد من الشبكة ثم أعد المحاولة", "gray")
            self._status("❌ لا إنترنت", "#991b1b", "#f87171")
            self._set_btn(True); return

        # ── اختيار استراتيجية الإصلاح ─────────────────────────────
        self._log("", "gray")
        if not diag["port"] and not diag["darb"]:
            self._log("🎯  التشخيص: DarbStu.exe متوقف → سأعيد تشغيله", "warn")
        elif not diag["port"] and diag["darb"]:
            self._log("🎯  التشخيص: DarbStu يعمل لكن uvicorn لا يستجيب → سأحرر المنفذ وأعيد التشغيل", "warn")
        elif diag["port"] and not diag["cf"]:
            self._log("🎯  التشخيص: السيرفر يعمل لكن cloudflared متوقف → سأعيد تشغيله", "warn")
        elif diag["port"] and diag["cf"]:
            self._log("🎯  التشخيص: كل شيء يعمل محلياً → مشكلة في إعدادات النفق", "warn")
        self._log("", "gray")

        # ── خطوات الإصلاح ─────────────────────────────────────────
        steps = [
            ("تحرير المنفذ وإعادة تشغيل DarbStu",    self._fix1_restart_server,  25),
            ("إعادة تشغيل cloudflared",               self._fix2_restart_cf,       25),
            ("إضافة استثناء Firewall للمنفذ 8000",    self._fix3_firewall,         10),
            ("إغلاق كامل وإعادة تشغيل DarbStu",      self._fix4_full_restart,     40),
            ("تشغيل uvicorn مباشرة (كشف الخطأ)",     self._fix5_direct_uvicorn,   15),
            ("مسح إعدادات cloudflared الفاسدة",       self._fix6_reset_cf_config,  25),
            ("تنزيل cloudflared جديد",                self._fix7_redownload_cf,    30),
        ]

        for name, fn, wait in steps:
            self._log(f"┌── الحل: {name}", "head")
            self._status(f"⚙️ {name}...", dot="#fbbf24")
            fn()
            self._log(f"⏳  انتظار {wait} ثانية...", "gray")
            time.sleep(wait)

            diag = self._run_diag()
            if diag["domain"]:
                self._log(f"✅  تم الإصلاح بنجاح بـ: [{name}]", "ok")
                self._log("━" * 52, "head")
                self._status("✅ تم الإصلاح! الموقع يعمل", "#166534", "#4ade80")
                self._set_btn(True); return

            status = (f"   النتيجة: منفذ {'✅' if diag['port'] else '❌'} | "
                      f"CF {'✅' if diag['cf'] else '❌'} | "
                      f"Domain {'✅' if diag['domain'] else '❌'}")
            self._log(status, "gray")
            self._log("└── لم يُحل — الانتقال للخطوة التالية...", "warn")
            self._log("", "gray")

        # ── فشلت كل الخطوات ───────────────────────────────────────
        self._log("━" * 52, "head")
        self._log("❌  جميع الحلول التلقائية استُنفدت", "err")
        self._log("", "gray")
        self._log("الخطوات اليدوية:", "warn")
        self._log("  1. أغلق DarbStu.exe يدوياً من Task Manager", "gray")
        self._log("  2. أعد تشغيل جهاز الكمبيوتر", "gray")
        self._log("  3. افتح DarbStu.exe وانتظر دقيقة كاملة", "gray")
        self._log("  4. راجع ملف darb_fix_log.txt للأخطاء التفصيلية", "gray")
        self._log("━" * 52, "head")
        self._status("❌ تعذّر الإصلاح التلقائي — راجع السجل", "#991b1b", "#f87171")
        self._set_btn(True)

    # ══════════════════════════════════════════════════════════════
    # خطوات الإصلاح التفصيلية
    # ══════════════════════════════════════════════════════════════

    def _fix1_restart_server(self):
        """تحرير المنفذ 8000 وإعادة تشغيل DarbStu"""
        darb = self._find_exe("DarbStu.exe")

        # فحص إن كانت عملية أخرى تحجز المنفذ
        pid = self._get_pid_on_port(LOCAL_PORT)
        if pid and not self._proc_running("DarbStu.exe"):
            self._log(f"   ⚠️  المنفذ {LOCAL_PORT} محجوز بعملية أخرى (PID={pid}) → سأوقفها", "warn")
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self._log(f"   ✅  تم تحرير المنفذ {LOCAL_PORT}", "ok")
                time.sleep(2)
            except Exception as e:
                self._log(f"   ❌  تعذّر إيقاف العملية: {e}", "err")

        if not darb:
            self._log("   ⚠️  لم يُعثر على DarbStu.exe في أي مسار", "warn"); return

        if self._proc_running("DarbStu.exe"):
            self._kill("DarbStu.exe"); time.sleep(3)

        self._log(f"   ⚙️  تشغيل: {darb}", "info")
        subprocess.Popen([darb], cwd=os.path.dirname(darb))
        self._log("   ✅  تم إرسال أمر التشغيل — انتظار التهيئة...", "ok")

    def _fix2_restart_cf(self):
        """إعادة تشغيل cloudflared مع الإعداد الصحيح"""
        cf      = self._find_exe("cloudflared.exe")
        running = self._proc_running("cloudflared.exe")

        self._log(f"   cloudflared: {'✅ يعمل' if running else '❌ متوقف'}", "ok" if running else "err")

        if not cf:
            self._log("   ⚠️  لم يُعثر على cloudflared.exe", "warn"); return

        if running:
            self._kill("cloudflared.exe"); time.sleep(3)

        # حاول Named Tunnel أولاً
        cf_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
        config_yml = os.path.join(cf_dir, "config.yml")
        has_config = os.path.exists(config_yml)

        if has_config:
            cmd = [cf, "tunnel", "--no-autoupdate", "run"]
            self._log("   ⚙️  تشغيل Named Tunnel (config.yml موجود)...", "info")
        else:
            cmd = [cf, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}", "--no-autoupdate"]
            self._log("   ⚙️  تشغيل Quick Tunnel...", "info")

        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل cloudflared", "ok")

    def _fix3_firewall(self):
        """إضافة استثناء Windows Firewall للمنفذ 8000"""
        self._log("   🔥  إضافة استثناء Firewall للمنفذ 8000...", "info")
        try:
            # أزل القاعدة القديمة أولاً إن وجدت
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", "name=DarbStu"],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            # أضف قاعدة جديدة
            r = subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 "name=DarbStu", "dir=in", "action=allow",
                 "protocol=TCP", f"localport={LOCAL_PORT}"],
                capture_output=True, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode == 0:
                self._log(f"   ✅  تم إضافة استثناء Firewall للمنفذ {LOCAL_PORT}", "ok")
            else:
                self._log(f"   ⚠️  الاستثناء يحتاج صلاحية Admin", "warn")
        except Exception as e:
            self._log(f"   ⚠️  Firewall: {e}", "warn")

    def _fix4_full_restart(self):
        """إغلاق كامل وإعادة تشغيل DarbStu من صفر"""
        darb = self._find_exe("DarbStu.exe")
        self._log("   ⚙️  إغلاق كامل...", "info")
        self._kill("DarbStu.exe")
        self._kill("cloudflared.exe")
        # أوقف أي uvicorn/python متبقي
        for proc in ["uvicorn.exe", "python.exe"]:
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", f"IMAGENAME eq {proc}"],
                    encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW)
                if proc.lower() in out.lower():
                    subprocess.run(["taskkill", "/F", "/IM", proc],
                                   capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                    self._log(f"   ⛔  تم إيقاف {proc}", "warn")
            except: pass
        time.sleep(5)

        if not darb:
            self._log("   ❌  لم يُعثر على DarbStu.exe", "err"); return

        self._log(f"   ⚙️  إعادة التشغيل الكاملة: {darb}", "info")
        subprocess.Popen([darb], cwd=os.path.dirname(darb))
        self._log("   ✅  تم — DarbStu سيُهيئ السيرفر والنفق...", "ok")

    def _fix5_direct_uvicorn(self):
        """تشغيل uvicorn مستقلاً لكشف الخطأ الحقيقي"""
        if self._port_ok():
            self._log("   ℹ️  المنفذ 8000 يعمل — هذه الخطوة غير مطلوبة", "info"); return

        darb = self._find_exe("DarbStu.exe")
        if not darb:
            self._log("   ❌  لم يُعثر على DarbStu.exe", "err"); return

        server_py = os.path.join(os.path.dirname(darb), "server.py")
        if not os.path.exists(server_py):
            self._log("   ⚠️  server.py غير موجود في مجلد DarbStu", "warn"); return

        self._log("   ⚙️  تشغيل uvicorn مباشرة لكشف الأخطاء...", "info")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server:app",
                 "--host", "127.0.0.1", "--port", str(LOCAL_PORT), "--timeout-keep-alive", "5"],
                cwd=os.path.dirname(darb),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace")
            time.sleep(5)
            out, _ = proc.communicate(timeout=3)
            if out:
                for line in out.splitlines()[:20]:
                    tag = "err" if "Error" in line or "error" in line else "gray"
                    self._log(f"   {line}", tag)
        except subprocess.TimeoutExpired:
            self._log("   ✅  uvicorn بدأ (لم يتوقف خلال 5 ثوانٍ = جيد)", "ok")
        except Exception as e:
            self._log(f"   ❌  خطأ في تشغيل uvicorn: {e}", "err")

    def _fix6_reset_cf_config(self):
        """مسح ملفات إعداد cloudflared الفاسدة"""
        cf = self._find_exe("cloudflared.exe")
        if not cf:
            self._log("   ❌  cloudflared.exe غير موجود — انتقل للخطوة التالية", "err"); return

        try:
            out = subprocess.check_output([cf, "--version"],
                encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            self._log(f"   ✅  cloudflared: {out.strip()[:60]}", "ok")
        except:
            self._log("   ❌  cloudflared.exe معطوب → سيُنزَّل جديد في الخطوة التالية", "err")
            return

        self._kill("cloudflared.exe"); time.sleep(2)

        cf_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
        if os.path.isdir(cf_dir):
            self._log(f"   🗑️  مسح: {cf_dir}", "warn")
            try:
                shutil.rmtree(cf_dir, ignore_errors=True)
                self._log("   ✅  تم مسح الإعدادات الفاسدة", "ok")
            except Exception as e:
                self._log(f"   ⚠️  تعذّر المسح: {e}", "warn")
        else:
            self._log("   ℹ️  لا يوجد مجلد إعدادات", "info")

        self._log("   ⚙️  تشغيل Quick Tunnel بدون إعداد...", "info")
        subprocess.Popen(
            [cf, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}", "--no-autoupdate"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل Quick Tunnel", "ok")
        self._log("   ℹ️  الرابط مؤقت (trycloudflare.com) — يُستخدم للطوارئ فقط", "gray")

    def _fix7_redownload_cf(self):
        """تنزيل cloudflared.exe جديد من GitHub"""
        darb = self._find_exe("DarbStu.exe")
        save_dir = os.path.dirname(darb) if darb else BASE_DIR
        cf_dest  = os.path.join(save_dir, "cloudflared.exe")

        self._kill("cloudflared.exe"); time.sleep(2)
        if os.path.exists(cf_dest):
            try: os.remove(cf_dest)
            except: pass

        self._log(f"   ⬇️  تنزيل من GitHub...", "info")
        self._log(f"   📂  المسار: {cf_dest}", "gray")
        try:
            req = urllib.request.Request(CF_DL_URL)
            with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r:
                data = r.read()
            with open(cf_dest, "wb") as f: f.write(data)
            self._log(f"   ✅  تم التنزيل ({len(data)//1024} KB)", "ok")
        except Exception as e:
            self._log(f"   ❌  فشل التنزيل: {e}", "err")
            self._log("   → تحقق من اتصال الإنترنت أو نزّل cloudflared يدوياً", "warn")
            return

        time.sleep(1)
        self._log("   ⚙️  تشغيل cloudflared الجديد...", "info")
        subprocess.Popen(
            [cf_dest, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}", "--no-autoupdate"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل cloudflared الجديد", "ok")

    # ══════════════════════════════════════════════════════════════
    # التحديث اليدوي
    # ══════════════════════════════════════════════════════════════
    def _manual_update(self):
        """زر التحديث اليدوي — مستقل عن دورة الإصلاح"""
        self._set_btn(False)
        threading.Thread(target=self._run_manual_update, daemon=True).start()

    def _run_manual_update(self):
        import io, zipfile, json as _j
        self._log("━" * 52, "head")
        self._log("  ⬆️  بدء التحديث اليدوي من GitHub", "head")
        self._log("━" * 52, "head")

        darb = self._find_exe("DarbStu.exe")
        install_dir = os.path.dirname(darb) if darb else BASE_DIR

        # ── فحص الإصدار ───────────────────────────────────────────
        self._log("   🔍  فحص إصدار GitHub...", "info")
        try:
            for ctx in [SSL_CTX, None]:
                try:
                    kw = {"context": ctx} if ctx else {}
                    with urllib.request.urlopen(VERSION_URL, timeout=8, **kw) as r:
                        data = _j.loads(r.read().decode())
                    break
                except: continue
            else:
                raise Exception("تعذّر الوصول إلى GitHub")

            latest = data.get("version", "?")
            notes  = data.get("notes", "")

            # قراءة الإصدار المحلي
            vfile = os.path.join(install_dir, "version.json")
            local = "0.0.0"
            if os.path.exists(vfile):
                try:
                    local = _j.load(open(vfile, encoding="utf-8")).get("version", "0.0.0")
                except: pass

            def _v(v):
                try: return tuple(int(x) for x in str(v).split("."))
                except: return (0,)

            self._log(f"   📌  الإصدار المحلي : {local}", "info")
            self._log(f"   🆕  إصدار GitHub  : {latest}", "info")
            if notes:
                self._log(f"   📝  الجديد        : {notes}", "gray")

            if _v(latest) <= _v(local):
                self._log("   ✅  أنت على أحدث إصدار — لا يحتاج تحديث", "ok")
                self._status("✅ أحدث إصدار مثبّت", "#166534", "#4ade80")
                self._set_btn(True); return

        except Exception as e:
            self._log(f"   ⚠️  تعذّر فحص الإصدار: {e}", "warn")
            self._log("   → سأتابع التحديث على أي حال...", "gray")
            latest = "?"

        # ── تنزيل ZIP ─────────────────────────────────────────────
        self._log(f"   ⬇️  تنزيل حزمة التحديث...", "info")
        self._status("⬇️ جارٍ التنزيل...", dot="#fbbf24")
        try:
            for ctx in [SSL_CTX, None]:
                try:
                    kw = {"context": ctx} if ctx else {}
                    with urllib.request.urlopen(ZIP_URL, timeout=120, **kw) as r:
                        zip_bytes = r.read()
                    break
                except: continue
            else:
                raise Exception("فشل التنزيل من GitHub")
            self._log(f"   ✅  تم التنزيل ({len(zip_bytes)//1024} KB)", "ok")
        except Exception as e:
            self._log(f"   ❌  فشل التنزيل: {e}", "err")
            self._status("❌ فشل التنزيل", "#991b1b", "#f87171")
            self._set_btn(True); return

        # ── استخراج الملفات ───────────────────────────────────────
        self._log("   📦  استخراج ملفات الكود...", "info")
        self._status("📦 جارٍ التثبيت...", dot="#fbbf24")
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                names = zf.namelist()
                prefix = ""
                if names:
                    top = names[0].split("/")[0]
                    if all(n.startswith(top+"/") or n == top+"/" for n in names[:5]):
                        prefix = top + "/"

                updated = skipped = 0
                for item in names:
                    rel = item[len(prefix):] if prefix and item.startswith(prefix) else item
                    if not rel or rel.endswith("/"): continue
                    top_dir = rel.split("/")[0]
                    if top_dir in PROTECTED: skipped += 1; continue
                    if rel in SKIP_FILES: skipped += 1; continue
                    ext = os.path.splitext(rel)[1].lower()
                    if ext not in UPDATE_EXTS: skipped += 1; continue

                    dest = os.path.join(install_dir, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(item) as src:
                        content = src.read()
                    with open(dest, "wb") as dst:
                        dst.write(content)
                    updated += 1

            self._log(f"   ✅  تم تحديث {updated} ملف  |  تجاوز {skipped}", "ok")
        except Exception as e:
            self._log(f"   ❌  خطأ في الاستخراج: {e}", "err")
            self._status("❌ فشل الاستخراج", "#991b1b", "#f87171")
            self._set_btn(True); return

        # ── إعادة التشغيل ─────────────────────────────────────────
        self._log("━" * 52, "head")
        self._log(f"   ✅  تم التحديث إلى الإصدار {latest} بنجاح!", "ok")
        self._log("   🔄  سيُعاد تشغيل DarbStu خلال 5 ثوانٍ...", "warn")
        self._status("✅ تم التحديث! إعادة تشغيل...", "#166534", "#4ade80")
        time.sleep(5)

        if darb and os.path.exists(darb):
            self._kill("DarbStu.exe")
            time.sleep(2)
            subprocess.Popen([darb], cwd=os.path.dirname(darb))
            self._log("   ✅  تم تشغيل DarbStu بالإصدار الجديد", "ok")
        else:
            self._log("   ℹ️  أغلق هذه الأداة وافتح DarbStu يدوياً", "gray")

        self._set_btn(True)

    # ── تشغيل التطبيق ─────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    DarbFixApp().run()
