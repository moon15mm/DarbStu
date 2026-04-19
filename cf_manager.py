# -*- coding: utf-8 -*-
"""
cf_manager.py — أداة إدارة Cloudflare Tunnel
تعمل على أي جهاز بشكل مستقل
"""
import os, sys, subprocess, threading, time, shutil, json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import urllib.request

# ── إعدادات ────────────────────────────────────────────────────────
PORT           = 8000
TUNNEL_DOMAIN  = "darbte.uk"
TUNNEL_NAME    = "darb-tunnel"
CF_DIR         = os.path.join(os.path.expanduser("~"), ".cloudflared")
NW             = dict(creationflags=subprocess.CREATE_NO_WINDOW) if sys.platform == 'win32' else {}

# ── ألوان ──────────────────────────────────────────────────────────
C_BG      = "#1e1e2e"
C_CARD    = "#2a2a3e"
C_GREEN   = "#22c55e"
C_RED     = "#ef4444"
C_YELLOW  = "#f59e0b"
C_BLUE    = "#3b82f6"
C_PURPLE  = "#8b5cf6"
C_ORANGE  = "#f97316"
C_TEXT    = "#f1f5f9"
C_MUTED   = "#94a3b8"
C_BORDER  = "#3f3f5a"


def find_cloudflared():
    candidates = [
        os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                     else os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe"),
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
        r"C:\Windows\System32\cloudflared.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return shutil.which("cloudflared.exe") or shutil.which("cloudflared")


def get_cf_processes():
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq cloudflared.exe", "/FO", "CSV"],
            encoding="utf-8", errors="replace", **NW)
        pids = []
        for line in out.splitlines()[1:]:
            parts = line.strip().strip('"').split('","')
            if len(parts) >= 2 and "cloudflared" in parts[0].lower():
                try: pids.append(int(parts[1]))
                except: pass
        return pids
    except:
        return []


def check_port(port=PORT):
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3)
        return True, r.status
    except urllib.error.HTTPError as e:
        return True, e.code
    except:
        return False, 0


def check_domain():
    try:
        r = urllib.request.urlopen(f"https://{TUNNEL_DOMAIN}/web/login", timeout=6)
        return True, r.status
    except urllib.error.HTTPError as e:
        return True, e.code
    except:
        return False, 0


def has_tunnel_config():
    config = os.path.join(CF_DIR, "config.yml")
    if os.path.exists(config):
        try:
            with open(config) as f:
                c = f.read()
            if "tunnel:" in c and "credentials-file:" in c:
                return True
        except:
            pass
    if os.path.exists(CF_DIR):
        for f in os.listdir(CF_DIR):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(CF_DIR, f)) as fh:
                        d = json.load(fh)
                    if "TunnelID" in d or "AccountTag" in d:
                        return True
                except:
                    pass
    return False


def get_tunnel_id(name=TUNNEL_NAME):
    """يجلب TunnelID من ملف credentials JSON"""
    if not os.path.exists(CF_DIR):
        return None
    for fname in os.listdir(CF_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(CF_DIR, fname)) as f:
                    d = json.load(f)
                if "TunnelID" in d:
                    return d["TunnelID"], os.path.join(CF_DIR, fname)
            except:
                pass
    return None


def create_config_yml(tunnel_id: str, creds_path: str):
    """ينشئ config.yml داخل .cloudflared"""
    config = f"""tunnel: {tunnel_id}
credentials-file: {creds_path}

ingress:
  - hostname: {TUNNEL_DOMAIN}
    service: http://localhost:{PORT}
  - hostname: www.{TUNNEL_DOMAIN}
    service: http://localhost:{PORT}
  - service: http_status:404
"""
    path = os.path.join(CF_DIR, "config.yml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(config)
    return path


# ══════════════════════════════════════════════════════════════════
# نافذة معالج الإعداد
# ══════════════════════════════════════════════════════════════════
class SetupWizard(tk.Toplevel):
    STEPS = [
        ("1", "تسجيل الدخول لـ Cloudflare",  C_BLUE),
        ("2", "إنشاء النفق",                  C_PURPLE),
        ("3", "ربط الدومين بالنفق",           C_ORANGE),
        ("4", "إنشاء ملف الإعداد",            C_GREEN),
    ]

    def __init__(self, parent, log_fn):
        super().__init__(parent)
        self.title("معالج إعداد نفق جديد")
        self.geometry("580x560")
        self.configure(bg=C_BG)
        self.resizable(False, False)
        self.grab_set()
        self._log = log_fn
        self._cf  = find_cloudflared()
        self._step_labels = {}
        self._build()

    def _build(self):
        tk.Label(self, text="🧙  معالج إنشاء Named Tunnel جديد",
                 font=("Tahoma", 14, "bold"), bg=C_BG, fg=C_TEXT).pack(pady=(16, 4))
        tk.Label(self,
                 text=f"سيتم إنشاء نفق باسم  '{TUNNEL_NAME}'  مرتبط بـ  {TUNNEL_DOMAIN}",
                 font=("Tahoma", 10), bg=C_BG, fg=C_MUTED).pack(pady=(0, 12))

        # ── مؤشرات الخطوات ────────────────────────────────────
        sf = tk.Frame(self, bg=C_CARD, bd=0)
        sf.pack(fill="x", padx=20, pady=4)
        for num, label, color in self.STEPS:
            row = tk.Frame(sf, bg=C_CARD)
            row.pack(fill="x", padx=12, pady=4)
            badge = tk.Label(row, text=f" {num} ", font=("Tahoma", 11, "bold"),
                             bg=color, fg="white", width=3)
            badge.pack(side="right", padx=(6, 0))
            lbl = tk.Label(row, text=label, font=("Tahoma", 11),
                           bg=C_CARD, fg=C_TEXT, anchor="e")
            lbl.pack(side="right", fill="x", expand=True)
            status = tk.Label(row, text="⏳", font=("Arial", 12),
                              bg=C_CARD, fg=C_MUTED, width=4)
            status.pack(side="left")
            self._step_labels[num] = status

        # ── تنبيه المتصفح ────────────────────────────────────
        tk.Label(self,
                 text="⚠  الخطوة 1 ستفتح المتصفح — سجّل الدخول بحساب Cloudflare\n"
                      "   (Moon15mm@hotmail.com)  ثم ارجع لهنا",
                 font=("Tahoma", 10), bg=C_BG, fg=C_YELLOW,
                 justify="right").pack(pady=8)

        # ── تسمية اسم النفق ──────────────────────────────────
        nf = tk.Frame(self, bg=C_BG)
        nf.pack(pady=4)
        tk.Label(nf, text="اسم النفق:", font=("Tahoma", 11),
                 bg=C_BG, fg=C_TEXT).pack(side="right", padx=6)
        self._name_var = tk.StringVar(value=TUNNEL_NAME)
        tk.Entry(nf, textvariable=self._name_var, font=("Consolas", 11),
                 bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", width=22).pack(side="right")

        # ── سجل مصغر ────────────────────────────────────────
        self._mini_log = scrolledtext.ScrolledText(
            self, font=("Consolas", 9), bg="#0f0f1a", fg="#a3e635",
            relief="flat", wrap="word", state="disabled", height=7)
        self._mini_log.pack(fill="both", expand=True, padx=20, pady=8)

        # ── أزرار ───────────────────────────────────────────
        bf = tk.Frame(self, bg=C_BG)
        bf.pack(pady=8)
        self._start_btn = tk.Button(
            bf, text="▶  ابدأ الإعداد", font=("Tahoma", 12, "bold"),
            bg=C_GREEN, fg="white", relief="flat", cursor="hand2",
            padx=20, pady=8, command=self._run_setup)
        self._start_btn.pack(side="right", padx=8)
        tk.Button(bf, text="إغلاق", font=("Tahoma", 11),
                  bg=C_CARD, fg=C_TEXT, relief="flat", cursor="hand2",
                  padx=14, pady=8, command=self.destroy).pack(side="right")

    def _mlog(self, msg):
        self._mini_log.configure(state="normal")
        self._mini_log.insert("end", f"{msg}\n")
        self._mini_log.see("end")
        self._mini_log.configure(state="disabled")
        self._log(msg)

    def _set_step(self, num, state):
        icons = {"wait": ("⏳", C_MUTED), "ok": ("✅", C_GREEN),
                 "run": ("🔄", C_YELLOW), "err": ("❌", C_RED)}
        icon, color = icons.get(state, ("⏳", C_MUTED))
        lbl = self._step_labels.get(str(num))
        if lbl:
            lbl.configure(text=icon, fg=color)

    def _run_setup(self):
        if not self._cf:
            messagebox.showerror("خطأ",
                "cloudflared.exe غير موجود\n"
                "ضعه في نفس مجلد البرنامج أولاً", parent=self)
            return
        self._start_btn.configure(state="disabled", text="جارٍ الإعداد...")
        name = self._name_var.get().strip() or TUNNEL_NAME
        threading.Thread(target=self._do_setup, args=(name,), daemon=True).start()

    def _run_cmd(self, cmd, step_num, success_keyword=None, timeout=120):
        """ينفذ أمر ويعرض مخرجاته، يعيد True عند النجاح"""
        self._set_step(step_num, "run")
        self._mlog(f"$ {' '.join(cmd)}")
        try:
            # الخطوة 1 (login) تحتاج نافذة ظاهرة للمتصفح
            flags = {} if step_num == 1 else NW
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", **flags)

            output = []
            start = time.time()
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._mlog(line)
                    output.append(line)
                if success_keyword and success_keyword in line:
                    proc.wait()
                    self._set_step(step_num, "ok")
                    return True, "\n".join(output)
                if time.time() - start > timeout:
                    proc.kill()
                    self._mlog("⚠ انتهت المهلة")
                    break

            proc.wait()
            if proc.returncode == 0 or (success_keyword is None):
                self._set_step(step_num, "ok")
                return True, "\n".join(output)
            else:
                self._set_step(step_num, "err")
                return False, "\n".join(output)
        except Exception as e:
            self._mlog(f"❌ {e}")
            self._set_step(step_num, "err")
            return False, str(e)

    def _do_setup(self, name):
        os.makedirs(CF_DIR, exist_ok=True)

        # ── الخطوة 1: تسجيل الدخول ────────────────────────
        self._mlog("\n─── الخطوة 1: تسجيل الدخول ───")
        self._mlog("سيفتح المتصفح — سجّل الدخول بحساب Cloudflare ثم ارجع هنا")
        ok, out = self._run_cmd(
            [self._cf, "tunnel", "login"],
            step_num=1,
            success_keyword="You have successfully logged in",
            timeout=300)
        if not ok and "already" not in out.lower() and os.path.exists(
                os.path.join(CF_DIR, "cert.pem")):
            self._set_step(1, "ok")
            self._mlog("✅ cert.pem موجود — تم تخطي تسجيل الدخول")
            ok = True
        if not ok:
            self._mlog("❌ فشل تسجيل الدخول — أعد المحاولة")
            self.after(0, lambda: self._start_btn.configure(
                state="normal", text="▶ إعادة المحاولة"))
            return

        # ── الخطوة 2: إنشاء النفق ─────────────────────────
        self._mlog(f"\n─── الخطوة 2: إنشاء نفق '{name}' ───")
        ok, out = self._run_cmd(
            [self._cf, "tunnel", "create", name],
            step_num=2,
            success_keyword="Created tunnel",
            timeout=30)
        if not ok and "already exists" in out.lower():
            self._set_step(2, "ok")
            self._mlog(f"✅ النفق '{name}' موجود مسبقاً")
            ok = True
        if not ok:
            self._mlog("❌ فشل إنشاء النفق")
            self.after(0, lambda: self._start_btn.configure(
                state="normal", text="▶ إعادة المحاولة"))
            return

        # ── الخطوة 3: ربط الدومين ─────────────────────────
        self._mlog(f"\n─── الخطوة 3: ربط {TUNNEL_DOMAIN} بالنفق ───")
        ok, _ = self._run_cmd(
            [self._cf, "tunnel", "route", "dns", name, TUNNEL_DOMAIN],
            step_num=3, timeout=30)
        ok2, _ = self._run_cmd(
            [self._cf, "tunnel", "route", "dns", name, f"www.{TUNNEL_DOMAIN}"],
            step_num=3, timeout=30)
        self._set_step(3, "ok")

        # ── الخطوة 4: إنشاء config.yml ────────────────────
        self._mlog("\n─── الخطوة 4: إنشاء config.yml ───")
        self._set_step(4, "run")
        result = get_tunnel_id(name)
        if result:
            tid, creds = result
            try:
                path = create_config_yml(tid, creds)
                self._mlog(f"✅ تم إنشاء: {path}")
                self._mlog(f"   Tunnel ID: {tid}")
                self._set_step(4, "ok")
            except Exception as e:
                self._mlog(f"❌ فشل إنشاء config.yml: {e}")
                self._set_step(4, "err")
        else:
            self._mlog("⚠ لم يُعثر على credentials JSON — أنشئ config.yml يدوياً")
            self._set_step(4, "err")

        # ── انتهى ─────────────────────────────────────────
        self._mlog("\n✅✅ اكتمل الإعداد! النفق جاهز للتشغيل.")
        self.after(0, self._setup_done)

    def _setup_done(self):
        self._start_btn.configure(state="normal", text="✅ اكتمل")
        messagebox.showinfo("تم الإعداد",
            "✅ تم إنشاء النفق بنجاح!\n\n"
            "الآن اضغط  'تشغيل النفق'  في النافذة الرئيسية",
            parent=self)


# ══════════════════════════════════════════════════════════════════
# النافذة الرئيسية
# ══════════════════════════════════════════════════════════════════
class CFManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Cloudflare Manager — إدارة النفق")
        self.root.geometry("700x760")
        self.root.configure(bg=C_BG)
        self.root.resizable(False, False)
        self._cf_proc = None
        self._running = True
        self._build_ui()
        self._start_auto_refresh()

    def _build_ui(self):
        # عنوان
        hdr = tk.Frame(self.root, bg="#7c3aed", height=56)
        hdr.pack(fill="x")
        tk.Label(hdr, text="☁  Cloudflare Manager", font=("Tahoma", 18, "bold"),
                 bg="#7c3aed", fg="white").pack(side="right", padx=18, pady=10)
        tk.Label(hdr, text=TUNNEL_DOMAIN, font=("Consolas", 11),
                 bg="#7c3aed", fg="#c4b5fd").pack(side="left", padx=18, pady=10)

        # ── لوحة الحالة ──────────────────────────────────────────
        sf = tk.LabelFrame(self.root, text="  الحالة  ", font=("Tahoma", 11, "bold"),
                           bg=C_BG, fg=C_MUTED, bd=1, relief="flat",
                           highlightbackground=C_BORDER, highlightthickness=1)
        sf.pack(fill="x", padx=14, pady=(12, 4))

        self._indicators = {}
        rows = [
            ("cloudflared", "cloudflared.exe"),
            ("port",        f"المنفذ {PORT} (FastAPI)"),
            ("config",      "بيانات النفق (.cloudflared)"),
            ("domain",      f"الموقع {TUNNEL_DOMAIN}"),
        ]
        for key, label in rows:
            row = tk.Frame(sf, bg=C_BG)
            row.pack(fill="x", padx=10, pady=3)
            dot  = tk.Label(row, text="●", font=("Arial", 14), bg=C_BG, fg=C_MUTED)
            dot.pack(side="right", padx=(0, 4))
            tk.Label(row, text=label, font=("Tahoma", 11), bg=C_BG, fg=C_TEXT,
                     anchor="e").pack(side="right", fill="x", expand=True)
            info = tk.Label(row, text="...", font=("Consolas", 10), bg=C_BG,
                            fg=C_MUTED, anchor="w")
            info.pack(side="left")
            self._indicators[key] = (dot, info)

        # ── أزرار التحكم ─────────────────────────────────────────
        bf = tk.LabelFrame(self.root, text="  التحكم  ", font=("Tahoma", 11, "bold"),
                           bg=C_BG, fg=C_MUTED, bd=1, relief="flat",
                           highlightbackground=C_BORDER, highlightthickness=1)
        bf.pack(fill="x", padx=14, pady=4)

        btns = [
            ("⏹  إيقاف cloudflared",  C_RED,    self._kill_cf),
            ("▶  تشغيل النفق",         C_GREEN,  self._start_tunnel),
            ("🔄  إعادة التشغيل",       C_BLUE,   self._restart_cf),
            ("🗑  حذف بيانات النفق",   C_YELLOW, self._delete_cf_dir),
            ("🌐  فتح الموقع",          C_PURPLE, self._open_domain),
            ("💻  فتح المحلي 8000",    C_MUTED,  self._open_local),
        ]
        cols = 3
        for i, (txt, color, cmd) in enumerate(btns):
            tk.Button(bf, text=txt, font=("Tahoma", 11, "bold"),
                      bg=color, fg="white", activebackground=color,
                      relief="flat", cursor="hand2", pady=8,
                      command=cmd).grid(row=i//cols, column=i%cols,
                                        padx=6, pady=6, sticky="ew")
        for c in range(cols):
            bf.columnconfigure(c, weight=1)

        # ── قسم إعداد نفق جديد ───────────────────────────────────
        wf = tk.LabelFrame(self.root, text="  إعداد نفق جديد  ",
                           font=("Tahoma", 11, "bold"),
                           bg=C_BG, fg=C_MUTED, bd=1, relief="flat",
                           highlightbackground=C_BORDER, highlightthickness=1)
        wf.pack(fill="x", padx=14, pady=4)

        tk.Label(wf,
                 text="أنشئ Named Tunnel جديد مرتبط بـ darbte.uk على هذا الجهاز",
                 font=("Tahoma", 10), bg=C_BG, fg=C_MUTED).pack(pady=(6, 2))

        wbtns = [
            ("🧙  معالج إنشاء نفق جديد", C_PURPLE, self._open_wizard),
            ("📄  إنشاء config.yml فقط",  C_BLUE,   self._create_config_only),
            ("📋  عرض معلومات النفق",     C_ORANGE, self._show_tunnel_info),
        ]
        wbf = tk.Frame(wf, bg=C_BG)
        wbf.pack(fill="x", padx=8, pady=6)
        for i, (txt, color, cmd) in enumerate(wbtns):
            tk.Button(wbf, text=txt, font=("Tahoma", 10, "bold"),
                      bg=color, fg="white", activebackground=color,
                      relief="flat", cursor="hand2", pady=7,
                      command=cmd).grid(row=0, column=i, padx=5, sticky="ew")
        for c in range(3):
            wbf.columnconfigure(c, weight=1)

        # ── زر تحديث ─────────────────────────────────────────────
        tk.Button(self.root, text="🔃  تحديث الحالة الآن",
                  font=("Tahoma", 10), bg=C_CARD, fg=C_TEXT,
                  relief="flat", cursor="hand2", pady=4,
                  command=self._refresh).pack(pady=(4, 0))

        # ── سجل الأحداث ──────────────────────────────────────────
        lf = tk.LabelFrame(self.root, text="  السجل  ", font=("Tahoma", 11, "bold"),
                           bg=C_BG, fg=C_MUTED, bd=1, relief="flat",
                           highlightbackground=C_BORDER, highlightthickness=1)
        lf.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self._log_widget = scrolledtext.ScrolledText(
            lf, font=("Consolas", 10), bg="#0f0f1a", fg="#a3e635",
            relief="flat", wrap="word", state="disabled", height=8)
        self._log_widget.pack(fill="both", expand=True, padx=4, pady=4)

        tk.Button(lf, text="مسح السجل", font=("Tahoma", 9),
                  bg=C_CARD, fg=C_MUTED, relief="flat",
                  command=self._clear_log).pack(anchor="e", padx=4, pady=(0, 4))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── تسجيل ─────────────────────────────────────────────────────
    def _log_msg(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log_widget.configure(state="normal")
        self._log_widget.insert("end", f"[{ts}] {msg}\n")
        self._log_widget.see("end")
        self._log_widget.configure(state="disabled")

    def _clear_log(self):
        self._log_widget.configure(state="normal")
        self._log_widget.delete("1.0", "end")
        self._log_widget.configure(state="disabled")

    # ── تحديث المؤشرات ────────────────────────────────────────────
    def _set_indicator(self, key, ok: bool, text=""):
        dot, info = self._indicators[key]
        dot.configure(fg=C_GREEN if ok else C_RED)
        info.configure(fg=C_GREEN if ok else C_RED, text=text)

    def _refresh(self):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        pids = get_cf_processes()
        self.root.after(0, self._set_indicator, "cloudflared",
                        bool(pids), f"{len(pids)} عملية" if pids else "متوقف")
        alive, code = check_port()
        self.root.after(0, self._set_indicator, "port",
                        alive, f"يعمل (HTTP {code})" if alive else "لا يستجيب")
        has_cfg = has_tunnel_config()
        self.root.after(0, self._set_indicator, "config",
                        has_cfg, "موجود" if has_cfg else "غير موجود")

        def _check_domain():
            ok, code = check_domain()
            self.root.after(0, self._set_indicator, "domain",
                            ok, f"يعمل (HTTP {code})" if ok else "لا يستجيب")
        threading.Thread(target=_check_domain, daemon=True).start()

    def _start_auto_refresh(self):
        self._refresh()
        def _loop():
            while self._running:
                time.sleep(8)
                if self._running:
                    self._refresh()
        threading.Thread(target=_loop, daemon=True).start()

    # ── إجراءات التحكم ────────────────────────────────────────────
    def _kill_cf(self):
        def _do():
            pids = get_cf_processes()
            if not pids:
                self._log_msg("cloudflared غير موجود أصلاً")
                return
            subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                           capture_output=True, **NW)
            self._log_msg(f"✅ تم إيقاف {len(pids)} عملية cloudflared")
            time.sleep(1); self._refresh()
        threading.Thread(target=_do, daemon=True).start()

    def _start_tunnel(self):
        cf = find_cloudflared()
        if not cf:
            messagebox.showerror("خطأ", "cloudflared.exe غير موجود على هذا الجهاز")
            return
        if not has_tunnel_config():
            messagebox.showwarning("تنبيه",
                "لا توجد بيانات نفق\n"
                "استخدم 'معالج إنشاء نفق جديد' أولاً")
            return

        def _do():
            self._log_msg("▶ جارٍ تشغيل النفق...")
            try:
                self._cf_proc = subprocess.Popen(
                    [cf, "tunnel", "--no-autoupdate", "run"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", **NW)
                for line in self._cf_proc.stdout:
                    self._log_msg(line.rstrip())
                    if "Registered tunnel connection" in line:
                        self._log_msg(f"✅ متصل بـ {TUNNEL_DOMAIN}")
                        break
                self._refresh()
            except Exception as e:
                self._log_msg(f"❌ {e}")
        threading.Thread(target=_do, daemon=True).start()

    def _restart_cf(self):
        def _do():
            self._log_msg("🔄 إعادة تشغيل...")
            subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                           capture_output=True, **NW)
            time.sleep(2)
            self.root.after(0, self._start_tunnel)
        threading.Thread(target=_do, daemon=True).start()

    def _delete_cf_dir(self):
        if not os.path.exists(CF_DIR):
            messagebox.showinfo("معلومة", "مجلد .cloudflared غير موجود")
            return
        if not messagebox.askyesno("تأكيد",
                f"حذف:\n{CF_DIR}\n\nسيتوقف هذا الجهاز عن الاتصال بالنفق"):
            return
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       capture_output=True, **NW)
        time.sleep(1)
        try:
            shutil.rmtree(CF_DIR)
            self._log_msg(f"✅ تم حذف {CF_DIR}")
            messagebox.showinfo("تم", "تم حذف بيانات النفق")
        except Exception as e:
            self._log_msg(f"❌ {e}")
        self._refresh()

    def _open_domain(self):
        import webbrowser; webbrowser.open(f"https://{TUNNEL_DOMAIN}/web/login")

    def _open_local(self):
        import webbrowser; webbrowser.open(f"http://127.0.0.1:{PORT}/web/login")

    # ── إجراءات إعداد النفق ───────────────────────────────────────
    def _open_wizard(self):
        SetupWizard(self.root, self._log_msg)

    def _create_config_only(self):
        """ينشئ config.yml من credentials موجودة"""
        result = get_tunnel_id()
        if not result:
            messagebox.showerror("خطأ",
                "لم يُعثر على ملف credentials JSON في .cloudflared\n"
                "شغّل 'معالج إنشاء نفق جديد' أولاً")
            return
        tid, creds = result
        try:
            path = create_config_yml(tid, creds)
            self._log_msg(f"✅ تم إنشاء {path}")
            self._log_msg(f"   Tunnel ID: {tid}")
            messagebox.showinfo("تم", f"تم إنشاء config.yml\n\nTunnel ID:\n{tid}")
            self._refresh()
        except Exception as e:
            self._log_msg(f"❌ {e}")
            messagebox.showerror("خطأ", str(e))

    def _show_tunnel_info(self):
        """يعرض معلومات النفق الحالي"""
        lines = []
        lines.append(f"مجلد .cloudflared:\n  {CF_DIR}")
        lines.append(f"موجود: {'نعم' if os.path.exists(CF_DIR) else 'لا'}")

        config_path = os.path.join(CF_DIR, "config.yml")
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                lines.append(f"\nconfig.yml:\n{f.read()}")
        else:
            lines.append("\nconfig.yml: غير موجود")

        result = get_tunnel_id()
        if result:
            tid, creds = result
            lines.append(f"\nTunnel ID:\n  {tid}")
            lines.append(f"\nCredentials:\n  {creds}")

        cf = find_cloudflared()
        lines.append(f"\ncloudflared.exe:\n  {cf or 'غير موجود'}")

        win = tk.Toplevel(self.root)
        win.title("معلومات النفق")
        win.geometry("520x400")
        win.configure(bg=C_BG)
        st = scrolledtext.ScrolledText(win, font=("Consolas", 10),
                                        bg="#0f0f1a", fg="#a3e635",
                                        relief="flat", wrap="word")
        st.pack(fill="both", expand=True, padx=10, pady=10)
        st.insert("end", "\n".join(lines))
        st.configure(state="disabled")

    def _on_close(self):
        self._running = False
        self.root.destroy()


if __name__ == "__main__":
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    root = tk.Tk()
    CFManager(root)
    root.mainloop()
