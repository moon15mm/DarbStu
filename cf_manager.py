# -*- coding: utf-8 -*-
"""
cf_manager.py — أداة إدارة Cloudflare Tunnel
تعمل على أي جهاز بشكل مستقل
"""
import os, sys, subprocess, threading, time, shutil, json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import urllib.request

# ── إعدادات ────────────────────────────────────────────────────────
PORT           = 8000
TUNNEL_DOMAIN  = "darbte.uk"
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
    """يعيد قائمة PIDs لعمليات cloudflared.exe"""
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
        return True, e.code  # الخادم يعمل حتى لو أعطى 404
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


class CFManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Cloudflare Manager — إدارة النفق")
        self.root.geometry("700x680")
        self.root.configure(bg=C_BG)
        self.root.resizable(False, False)

        self._cf_proc = None
        self._running = True
        self._build_ui()
        self._start_auto_refresh()

    # ── بناء الواجهة ───────────────────────────────────────────────
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
            ("cloudflared",  "cloudflared.exe"),
            ("port",         f"المنفذ {PORT} (FastAPI)"),
            ("config",       "بيانات النفق (.cloudflared)"),
            ("domain",       f"الموقع {TUNNEL_DOMAIN}"),
        ]
        for key, label in rows:
            row = tk.Frame(sf, bg=C_BG)
            row.pack(fill="x", padx=10, pady=3)
            dot = tk.Label(row, text="●", font=("Arial", 14), bg=C_BG, fg=C_MUTED)
            dot.pack(side="right", padx=(0, 4))
            lbl = tk.Label(row, text=label, font=("Tahoma", 11), bg=C_BG, fg=C_TEXT,
                           anchor="e")
            lbl.pack(side="right", fill="x", expand=True)
            info = tk.Label(row, text="...", font=("Consolas", 10), bg=C_BG, fg=C_MUTED,
                            anchor="w")
            info.pack(side="left")
            self._indicators[key] = (dot, info)

        # ── أزرار التحكم ─────────────────────────────────────────
        bf = tk.LabelFrame(self.root, text="  التحكم  ", font=("Tahoma", 11, "bold"),
                           bg=C_BG, fg=C_MUTED, bd=1, relief="flat",
                           highlightbackground=C_BORDER, highlightthickness=1)
        bf.pack(fill="x", padx=14, pady=4)

        btns = [
            ("⏹  إيقاف cloudflared",     C_RED,    self._kill_cf),
            ("▶  تشغيل النفق",            C_GREEN,  self._start_tunnel),
            ("🔄  إعادة التشغيل",          C_BLUE,   self._restart_cf),
            ("🗑  حذف بيانات النفق",       C_YELLOW, self._delete_cf_dir),
            ("🌐  فتح الموقع",             C_PURPLE, self._open_domain),
            ("💻  فتح المحلي 8000",        C_MUTED,  self._open_local),
        ]
        cols = 3
        for i, (txt, color, cmd) in enumerate(btns):
            btn = tk.Button(bf, text=txt, font=("Tahoma", 11, "bold"),
                            bg=color, fg="white", activebackground=color,
                            relief="flat", cursor="hand2", pady=8,
                            command=cmd)
            btn.grid(row=i//cols, column=i%cols, padx=6, pady=6, sticky="ew")
        for c in range(cols):
            bf.columnconfigure(c, weight=1)

        # ── زر التحديث ───────────────────────────────────────────
        tk.Button(self.root, text="🔃  تحديث الحالة الآن",
                  font=("Tahoma", 10), bg=C_CARD, fg=C_TEXT,
                  relief="flat", cursor="hand2", pady=4,
                  command=self._refresh).pack(pady=(6, 0))

        # ── سجل الأحداث ──────────────────────────────────────────
        lf = tk.LabelFrame(self.root, text="  السجل  ", font=("Tahoma", 11, "bold"),
                           bg=C_BG, fg=C_MUTED, bd=1, relief="flat",
                           highlightbackground=C_BORDER, highlightthickness=1)
        lf.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self._log = scrolledtext.ScrolledText(
            lf, font=("Consolas", 10), bg="#0f0f1a", fg="#a3e635",
            relief="flat", wrap="word", state="disabled", height=10)
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

        tk.Button(lf, text="مسح السجل", font=("Tahoma", 9),
                  bg=C_CARD, fg=C_MUTED, relief="flat",
                  command=self._clear_log).pack(anchor="e", padx=4, pady=(0, 4))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── تسجيل ─────────────────────────────────────────────────────
    def _log_msg(self, msg: str, color="#a3e635"):
        ts = time.strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] {msg}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    # ── تحديث المؤشرات ────────────────────────────────────────────
    def _set_indicator(self, key, ok: bool, text=""):
        dot, info = self._indicators[key]
        dot.configure(fg=C_GREEN if ok else C_RED)
        info.configure(fg=C_GREEN if ok else C_RED, text=text)

    def _refresh(self):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        # cloudflared
        pids = get_cf_processes()
        self.root.after(0, self._set_indicator, "cloudflared",
                        bool(pids), f"{len(pids)} عملية" if pids else "متوقف")

        # port
        alive, code = check_port()
        self.root.after(0, self._set_indicator, "port",
                        alive, f"يعمل (HTTP {code})" if alive else "لا يستجيب")

        # config
        has_cfg = has_tunnel_config()
        self.root.after(0, self._set_indicator, "config",
                        has_cfg, "موجود" if has_cfg else "غير موجود")

        # domain (في خيط منفصل لأنه أبطأ)
        def _check_domain():
            ok, code = check_domain()
            self.root.after(0, self._set_indicator, "domain",
                            ok, f"يعمل (HTTP {code})" if ok else "لا يستجيب (502/خطأ)")
        threading.Thread(target=_check_domain, daemon=True).start()

    def _start_auto_refresh(self):
        self._refresh()
        def _loop():
            while self._running:
                time.sleep(8)
                if self._running:
                    self._refresh()
        threading.Thread(target=_loop, daemon=True).start()

    # ── إجراءات ───────────────────────────────────────────────────
    def _kill_cf(self):
        def _do():
            pids = get_cf_processes()
            if not pids:
                self._log_msg("cloudflared غير موجود أصلاً")
                self._refresh()
                return
            subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                           capture_output=True, **NW)
            self._log_msg(f"✅ تم إيقاف {len(pids)} عملية cloudflared")
            time.sleep(1)
            self._refresh()
        threading.Thread(target=_do, daemon=True).start()

    def _start_tunnel(self):
        cf = find_cloudflared()
        if not cf:
            messagebox.showerror("خطأ", "cloudflared.exe غير موجود على هذا الجهاز")
            return
        if not has_tunnel_config():
            messagebox.showwarning("تنبيه",
                "لا توجد بيانات نفق في .cloudflared\n"
                "انسخ مجلد .cloudflared من جهاز المدرسة أولاً")
            return

        def _do():
            self._log_msg("▶ جارٍ تشغيل النفق...")
            try:
                self._cf_proc = subprocess.Popen(
                    [cf, "tunnel", "--no-autoupdate", "run"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    **NW)
                for line in self._cf_proc.stdout:
                    self._log_msg(line.rstrip(), "#a3e635")
                    if "Registered tunnel connection" in line or "Connected" in line:
                        self._log_msg(f"✅ متصل بـ {TUNNEL_DOMAIN}")
                        break
                self._refresh()
            except Exception as e:
                self._log_msg(f"❌ خطأ: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def _restart_cf(self):
        def _do():
            self._log_msg("🔄 إعادة تشغيل cloudflared...")
            subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                           capture_output=True, **NW)
            time.sleep(2)
            self.root.after(0, self._start_tunnel)
        threading.Thread(target=_do, daemon=True).start()

    def _delete_cf_dir(self):
        if not os.path.exists(CF_DIR):
            messagebox.showinfo("معلومة", "مجلد .cloudflared غير موجود أصلاً")
            return
        if not messagebox.askyesno("تأكيد",
                f"هل تريد حذف:\n{CF_DIR}\n\n"
                "سيتوقف هذا الجهاز عن الاتصال بالنفق نهائياً"):
            return
        # أوقف cloudflared أولاً
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       capture_output=True, **NW)
        time.sleep(1)
        try:
            shutil.rmtree(CF_DIR)
            self._log_msg(f"✅ تم حذف {CF_DIR}")
            messagebox.showinfo("تم", "تم حذف بيانات النفق\nهذا الجهاز لن يتصل بالنفق بعد الآن")
        except Exception as e:
            self._log_msg(f"❌ فشل الحذف: {e}")
        self._refresh()

    def _open_domain(self):
        import webbrowser
        webbrowser.open(f"https://{TUNNEL_DOMAIN}/web/login")

    def _open_local(self):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{PORT}/web/login")

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
    app = CFManager(root)
    root.mainloop()
