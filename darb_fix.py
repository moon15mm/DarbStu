# -*- coding: utf-8 -*-
"""
darb_fix.py — أداة الإصلاح التلقائي الذكية لـ DarbStu
تفحص كل مشكلة وتحلها بالترتيب، وتتوقف فور الإصلاح.
"""
import os, sys, time, socket, subprocess, shutil, ssl, threading, datetime
import urllib.request, tkinter as tk
from tkinter import ttk, scrolledtext

# ── إعدادات ────────────────────────────────────────────────────────
CHECK_URL  = "https://darbte.uk/web/dashboard"
LOCAL_PORT = 8000
SSL_CTX    = ssl._create_unverified_context()
LOG_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darb_fix_log.txt")


# ══════════════════════════════════════════════════════════════════
class DarbFixApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🔧 DarbStu — الإصلاح التلقائي")
        self.root.geometry("720x560")
        self.root.resizable(True, True)
        self.root.configure(bg="white")
        self._build_ui()

    # ── بناء الواجهة ──────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#1565C0", height=64)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔧  أداة الإصلاح التلقائي — DarbStu",
                 bg="#1565C0", fg="white",
                 font=("Tahoma", 14, "bold")).pack(expand=True)

        # شريط الحالة
        bar = tk.Frame(self.root, bg="#f0f4ff", bd=0, pady=8)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        self._status_dot = tk.Label(bar, text="⬤", fg="#94a3b8",
                                     bg="#f0f4ff", font=("Tahoma", 14))
        self._status_dot.pack(side="right", padx=(0, 6))
        self._status_var = tk.StringVar(value="اضغط 'ابدأ' للفحص")
        tk.Label(bar, textvariable=self._status_var,
                 bg="#f0f4ff", fg="#1e40af",
                 font=("Tahoma", 11, "bold"),
                 anchor="e").pack(side="right", fill="x", expand=True)

        # منطقة السجل
        log_lf = ttk.LabelFrame(self.root, text=" سجل العمليات ", padding=5)
        log_lf.pack(fill="both", expand=True, padx=12, pady=8)

        self.log_box = scrolledtext.ScrolledText(
            log_lf, font=("Courier New", 9), wrap="word",
            state="disabled", bg="#0f172a", fg="#e2e8f0",
            insertbackground="white", height=22)
        self.log_box.pack(fill="both", expand=True)

        # ألوان السجل
        for tag, color in [("ok","#4ade80"), ("err","#f87171"),
                            ("warn","#fbbf24"), ("info","#93c5fd"),
                            ("head","#c084fc"), ("gray","#94a3b8")]:
            self.log_box.tag_config(tag, foreground=color)

        # الأزرار
        btn_f = tk.Frame(self.root, bg="white")
        btn_f.pack(fill="x", padx=12, pady=(0, 12))
        self._start_btn = tk.Button(
            btn_f, text="▶  ابدأ الفحص والإصلاح",
            bg="#1565C0", fg="white", font=("Tahoma", 11, "bold"),
            relief="flat", padx=20, pady=10, cursor="hand2",
            activebackground="#1e40af", activeforeground="white",
            command=self._start)
        self._start_btn.pack(side="right", padx=4)
        tk.Button(btn_f, text="مسح السجل", command=self._clear,
                  bg="#e5e7eb", relief="flat", padx=12, pady=10,
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

    def _clear(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def _set_btn(self, enabled, text="▶  ابدأ الفحص والإصلاح"):
        self.root.after(0, lambda: self._start_btn.config(
            state="normal" if enabled else "disabled", text=text))

    # ── دالة البدء ─────────────────────────────────────────────────
    def _start(self):
        self._set_btn(False, "⏳  جارٍ الفحص...")
        threading.Thread(target=self._run, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # منطق الإصلاح الرئيسية
    # ══════════════════════════════════════════════════════════════
    def _run(self):
        self._log("━" * 52, "head")
        self._log("  🔧  بدء جلسة الإصلاح التلقائي لـ DarbStu", "head")
        self._log("━" * 52, "head")
        self._status("🔍 فحص الموقع...", dot="#fbbf24")

        # ── الفحص الأولي ──────────────────────────────────────────
        if self._domain_ok():
            self._log("✅  الموقع يعمل بشكل صحيح — لا يحتاج إصلاح!", "ok")
            self._status("✅ الموقع يعمل — لا مشكلة", "#166534", "#4ade80")
            self._set_btn(True); return

        self._log("❌  الموقع لا يستجيب — سأبدأ بالتشخيص", "err")

        # ── فحص الإنترنت ──────────────────────────────────────────
        if not self._internet_ok():
            self._log("⚠️  لا يوجد اتصال بالإنترنت!", "warn")
            self._log("   → تأكد من أن الجهاز متصل بالشبكة ثم أعد المحاولة", "gray")
            self._status("❌ لا إنترنت — تعذّر الإصلاح", "#991b1b", "#f87171")
            self._set_btn(True); return

        self._log("✅  الإنترنت يعمل", "ok")

        # ── خطوات الإصلاح المرتبة ─────────────────────────────────
        steps = [
            ("إعادة تشغيل السيرفر المحلي",             self._fix1_restart_server,   20),
            ("إعادة تشغيل cloudflared",                self._fix2_restart_cf,        25),
            ("إغلاق كامل وإعادة تشغيل DarbStu",       self._fix3_full_restart,      35),
            ("تشغيل cloudflared بشكل مستقل",           self._fix4_standalone_cf,     25),
            ("مسح إعدادات cloudflared الفاسدة",        self._fix5_reset_cf_config,   25),
            ("تنزيل cloudflared جديد وتشغيله",         self._fix6_redownload_cf,     30),
        ]

        for name, fn, wait in steps:
            self._log(f"\n┌── الحل: {name} ──", "head")
            self._status(f"⚙️ {name}...", dot="#fbbf24")
            fn()
            self._log(f"⏳  انتظار {wait} ثانية للتحقق...", "gray")
            time.sleep(wait)

            if self._domain_ok():
                self._log(f"✅  تم الإصلاح بنجاح بـ: [{name}]", "ok")
                self._log("━" * 52, "head")
                self._status("✅ تم الإصلاح!", "#166534", "#4ade80")
                self._set_btn(True); return

            self._log("⬜  لم يُحل — الانتقال للخطوة التالية...", "warn")

        # ── لم تنجح كل الحلول ─────────────────────────────────────
        self._log("\n❌  جميع الحلول التلقائية فشلت", "err")
        self._log("→  أغلق DarbStu.exe يدوياً وأعد فتحه", "warn")
        self._log("→  إذا استمرت المشكلة تواصل مع الدعم الفني", "warn")
        self._log("━" * 52, "head")
        self._status("❌ تعذّر الإصلاح — راجع السجل", "#991b1b", "#f87171")
        self._set_btn(True)

    # ══════════════════════════════════════════════════════════════
    # دوال الفحص
    # ══════════════════════════════════════════════════════════════
    def _domain_ok(self):
        try:
            with urllib.request.urlopen(CHECK_URL, timeout=8, context=SSL_CTX) as r:
                ok = r.status < 500
            if ok: return True
        except: pass
        try:
            with urllib.request.urlopen(CHECK_URL, timeout=8) as r:
                return r.status < 500
        except: return False

    def _internet_ok(self):
        for host in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
            try:
                s = socket.socket(); s.settimeout(3)
                s.connect(host); s.close(); return True
            except: pass
        return False

    def _port_ok(self, port=None):
        port = port or LOCAL_PORT
        try:
            s = socket.socket(); s.settimeout(2)
            s.connect(("127.0.0.1", port)); s.close(); return True
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

    # ── البحث عن الملفات ──────────────────────────────────────────
    def _find_exe(self, filename):
        # 1. نفس مجلد هذا السكريبت
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(here): return here

        # 2. مجلد فوق (إذا السكريبت داخل مجلد dist)
        parent = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", filename)
        if os.path.exists(parent): return os.path.normpath(parent)

        # 3. سطح مكتب كل المستخدمين
        for base in [os.path.expanduser("~/Desktop"),
                     r"C:\Users\Public\Desktop"]:
            p = os.path.join(base, filename)
            if os.path.exists(p): return p

        # 4. البحث في سطح المكتب (مستوى واحد)
        for base in [os.path.expanduser("~"),
                     os.path.expanduser("~/Desktop")]:
            for d in os.listdir(base) if os.path.isdir(base) else []:
                p = os.path.join(base, d, filename)
                if os.path.exists(p): return p

        # 5. shutil.which
        found = shutil.which(filename)
        if found: return found

        # 6. مسارات ثابتة لـ cloudflared
        for p in [r"C:\Program Files\cloudflared\cloudflared.exe",
                  r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                  r"C:\Windows\System32\cloudflared.exe"]:
            if os.path.exists(p): return p

        return None

    # ══════════════════════════════════════════════════════════════
    # خطوات الإصلاح
    # ══════════════════════════════════════════════════════════════
    def _fix1_restart_server(self):
        """إذا السيرفر المحلي متوقف → أعد تشغيل DarbStu"""
        local = self._port_ok()
        darb  = self._find_exe("DarbStu.exe")
        running = self._proc_running("DarbStu.exe")

        self._log(f"   السيرفر المحلي :{LOCAL_PORT} → {'✅ يعمل' if local else '❌ متوقف'}", "ok" if local else "err")
        self._log(f"   DarbStu.exe    → {'✅ يعمل' if running else '❌ متوقف'}", "ok" if running else "err")

        if not darb:
            self._log("   ⚠️  لم يُعثر على DarbStu.exe", "warn"); return

        if not local or not running:
            if running: self._kill("DarbStu.exe"); time.sleep(2)
            self._log(f"   ⚙️  تشغيل: {darb}", "info")
            subprocess.Popen([darb], cwd=os.path.dirname(darb),
                             creationflags=subprocess.CREATE_NO_WINDOW)
            self._log("   ✅  تم إرسال أمر التشغيل", "ok")
        else:
            self._log("   ℹ️  السيرفر يعمل — المشكلة في النفق", "info")

    def _fix2_restart_cf(self):
        """إعادة تشغيل cloudflared مع الإعداد الصحيح"""
        cf      = self._find_exe("cloudflared.exe")
        running = self._proc_running("cloudflared.exe")

        self._log(f"   cloudflared → {'✅ يعمل' if running else '❌ متوقف'}", "ok" if running else "err")

        if not cf:
            self._log("   ⚠️  لم يُعثر على cloudflared.exe", "warn"); return

        if running:
            self._kill("cloudflared.exe"); time.sleep(3)

        # حاول Named Tunnel أولاً ثم Quick Tunnel
        cf_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
        has_named = any(
            f.endswith(".json") for f in os.listdir(cf_dir)
            if os.path.isdir(cf_dir)
        ) if os.path.isdir(cf_dir) else False

        if has_named:
            cmd = [cf, "tunnel", "--no-autoupdate", "run"]
            self._log("   ⚙️  تشغيل Named Tunnel...", "info")
        else:
            cmd = [cf, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}", "--no-autoupdate"]
            self._log("   ⚙️  تشغيل Quick Tunnel...", "info")

        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل cloudflared", "ok")

    def _fix3_full_restart(self):
        """إغلاق كل شيء وإعادة تشغيل DarbStu من صفر"""
        darb = self._find_exe("DarbStu.exe")
        self._log("   ⚙️  إغلاق كامل لكل العمليات...", "info")
        self._kill("DarbStu.exe")
        self._kill("cloudflared.exe")
        time.sleep(5)

        if not darb:
            self._log("   ❌  لم يُعثر على DarbStu.exe", "err"); return

        self._log(f"   ⚙️  إعادة تشغيل DarbStu كاملاً: {darb}", "info")
        subprocess.Popen([darb], cwd=os.path.dirname(darb),
                         creationflags=subprocess.CREATE_NO_WINDOW)
        self._log("   ✅  تم — DarbStu سيُهيئ السيرفر والنفق...", "ok")

    def _fix4_standalone_cf(self):
        """تشغيل cloudflared بشكل مستقل (backup إن لم يشغّله DarbStu)"""
        cf = self._find_exe("cloudflared.exe")
        if not cf:
            self._log("   ❌  لم يُعثر على cloudflared.exe", "err"); return

        running = self._proc_running("cloudflared.exe")
        if running:
            self._log("   ℹ️  cloudflared يعمل بالفعل — إعادة تشغيل قسري", "warn")
            self._kill("cloudflared.exe"); time.sleep(3)

        # تجربة مع دومين ثابت
        cmd = [cf, "tunnel",
               "--url",    f"http://localhost:{LOCAL_PORT}",
               "--hostname", "darbte.uk",
               "--no-autoupdate"]
        self._log("   ⚙️  تشغيل cloudflared مع darbte.uk...", "info")
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل cloudflared بشكل مستقل", "ok")

    def _fix5_reset_cf_config(self):
        """مسح ملفات إعداد cloudflared الفاسدة ثم Quick Tunnel"""
        cf = self._find_exe("cloudflared.exe")
        if not cf:
            self._log("   ❌  cloudflared.exe غير موجود", "err"); return

        # اختبار هل cloudflared يعمل أصلاً
        self._log("   🔍  اختبار ملف cloudflared...", "info")
        try:
            out = subprocess.check_output(
                [cf, "--version"],
                encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            self._log(f"   ✅  cloudflared يعمل: {out.strip()[:60]}", "ok")
        except Exception as e:
            self._log(f"   ❌  cloudflared معطوب: {e}", "err")
            self._log("   → سيتم تنزيل نسخة جديدة في الخطوة التالية", "warn")
            return

        # أوقف cloudflared أولاً
        self._kill("cloudflared.exe"); time.sleep(2)

        # مسح مجلد إعدادات cloudflared (~/.cloudflared)
        cf_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
        if os.path.isdir(cf_dir):
            self._log(f"   🗑️  مسح مجلد الإعدادات: {cf_dir}", "warn")
            try:
                shutil.rmtree(cf_dir, ignore_errors=True)
                self._log("   ✅  تم مسح الإعدادات الفاسدة", "ok")
            except Exception as e:
                self._log(f"   ⚠️  تعذّر المسح: {e}", "warn")
        else:
            self._log("   ℹ️  لا يوجد مجلد إعدادات — مشكلة في مكان آخر", "info")

        # تشغيل Quick Tunnel بدون أي إعداد
        self._log("   ⚙️  تشغيل Quick Tunnel (بدون إعداد)...", "info")
        subprocess.Popen(
            [cf, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}", "--no-autoupdate"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل Quick Tunnel", "ok")
        self._log("   ℹ️  ملاحظة: الرابط سيكون مؤقتاً (trycloudflare.com)", "gray")

    def _fix6_redownload_cf(self):
        """تنزيل cloudflared.exe جديد من Cloudflare مباشرة"""
        CF_URL = ("https://github.com/cloudflare/cloudflared/releases/latest"
                  "/download/cloudflared-windows-amd64.exe")

        # حدد مسار الحفظ بجانب DarbStu.exe
        darb = self._find_exe("DarbStu.exe")
        if darb:
            save_dir = os.path.dirname(darb)
        else:
            save_dir = os.path.dirname(os.path.abspath(__file__))

        cf_dest = os.path.join(save_dir, "cloudflared.exe")

        # أوقف النسخة القديمة
        self._kill("cloudflared.exe"); time.sleep(2)

        # إذا كانت قديمة وفاسدة احذفها
        if os.path.exists(cf_dest):
            try: os.remove(cf_dest)
            except: pass

        self._log(f"   ⬇️  جارٍ تنزيل cloudflared من GitHub...", "info")
        self._log(f"   📂  سيُحفظ في: {cf_dest}", "gray")

        try:
            urllib.request.urlretrieve(CF_URL, cf_dest,
                reporthook=lambda b, bs, t: self._log(
                    f"   ↓  {min(b*bs, t if t>0 else b*bs)//1024} KB...", "gray")
                    if b % 50 == 0 else None)
            self._log("   ✅  تم تنزيل cloudflared بنجاح", "ok")
        except Exception as e:
            # جرب بدون SSL
            try:
                ctx = ssl._create_unverified_context()
                req = urllib.request.Request(CF_URL)
                with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                    with open(cf_dest, "wb") as f: f.write(r.read())
                self._log("   ✅  تم التنزيل (بدون SSL)", "ok")
            except Exception as e2:
                self._log(f"   ❌  فشل التنزيل: {e2}", "err")
                self._log("   → تحقق من اتصال الإنترنت", "warn"); return

        # تشغيل النسخة الجديدة
        time.sleep(1)
        self._log("   ⚙️  تشغيل cloudflared الجديد...", "info")
        subprocess.Popen(
            [cf_dest, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}", "--no-autoupdate"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log("   ✅  تم تشغيل cloudflared الجديد", "ok")

    # ── تشغيل التطبيق ─────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    DarbFixApp().run()
