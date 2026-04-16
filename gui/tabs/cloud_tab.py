# -*- coding: utf-8 -*-
"""
gui/tabs/cloud_tab.py — تبويب مخصص لإدارة الربط السحابي (Cloud Sync)
"""
import tkinter as tk
from tkinter import ttk, messagebox
import json
import qrcode
from PIL import ImageTk
from config_manager import load_config, save_config, invalidate_config_cache
from constants import CONFIG_JSON, PORT
from cloudflare_tunnel import find_cloudflared_executable

class CloudTabMixin:
    def _build_cloud_tab(self):
        """بناء واجهة الربط السحابي."""
        frame = self.cloud_frame
        
        # حاوية التمرير
        canvas = tk.Canvas(frame, bg="#f1f5f9", highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        container = tk.Frame(canvas, bg="#f1f5f9")
        canvas.create_window((0, 0), window=container, anchor="nw", width=800)
        
        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        container.bind("<Configure>", _on_frame_configure)

        cfg = load_config()
        is_cloud = cfg.get("cloud_mode", False)

        # ─── العنوان الرئيسي ─────────────────────────────
        header = tk.Frame(container, bg="#1e293b", pady=20)
        header.pack(fill="x")
        
        tk.Label(header, text="🌐 إدارة المزامنة والربط السحابي",
                 bg="#1e293b", fg="white", font=("Tahoma", 16, "bold")).pack()
        
        mode_text = "وضع العميل (متصل بسيرفر خارجي)" if is_cloud else "وضع السيرفر الرئيسي (المصدر)"
        tk.Label(header, text=mode_text,
                 bg="#1e293b", fg="#94a3b8", font=("Tahoma", 10)).pack(pady=5)

        # ─── المحتوى الرئيسي ────────────────────────────
        content = tk.Frame(container, bg="#f1f5f9", padx=30, pady=20)
        content.pack(fill="both", expand=True)

        if not is_cloud:
            self._build_master_cloud_ui(content, cfg)
        else:
            self._build_client_cloud_ui(content, cfg)

        # ─── إرشادات عامة ──────────────────────────────
        info_lf = ttk.LabelFrame(container, text=" 📖 كيف يعمل الربط السحابي؟ ", padding=15)
        info_lf.pack(fill="x", padx=30, pady=20)
        
        guide = (
            "1. هذا الجهاز يعمل حالياً كـ 'سيرفر رئيسي'، مما يعني أن قاعدة البيانات مخزنة هنا.\n"
            "2. للوصول للبرنامج من أجهزة أخرى (مثل لابتوب معلم)، قم بتثبيت البرنامج عليها.\n"
            "3. في الأجهزة الأخرى، اختر 'إعدادات المزامنة' من شاشة الدخول وأدخل الرابط والرمز الموضح أعلاه.\n"
            "4. يجب أن يكون هذا الجهاز (الرئيسي) متصلاً بالإنترنت ليعمل الربط في الأجهزة الأخرى."
        )
        if is_cloud:
            guide = (
                "1. هذا الجهاز يعمل كـ 'عميل'، وهو يقرأ البيانات مباشرة من السيرفر الرئيسي عبر الإنترنت.\n"
                "2. أي تعديلات تجريها هنا ستظهر فوراً في الجهاز الرئيسي وباقي الأجهزة المتصلة.\n"
                "3. في حال انقطاع الإنترنت، قد يتوقف البرنامج عن جلب البيانات حتى يعود الاتصال."
            )
            
        tk.Label(info_lf, text=guide, font=("Tahoma", 10), justify="right",
                 anchor="e", foreground="#475569", wraplength=700).pack(fill="x")

    def _build_master_cloud_ui(self, parent, cfg):
        """واجهة الجهاز الرئيسي."""
        card = tk.Frame(parent, bg="white", bd=1, relief="flat", padx=20, pady=20)
        card.pack(fill="x")
        
        # استايل الكروت (Shadow effect simple)
        def set_shadow(e): e.widget.config(highlightthickness=1, highlightbackground="#e2e8f0")
        card.config(highlightthickness=1, highlightbackground="#e2e8f0")

        tk.Label(card, text="بيانات الربط للأجهزة الفرعية",
                 bg="white", fg="#1e293b", font=("Tahoma", 12, "bold")).pack(anchor="e", pady=(0, 15))

        # رابط السيرفر
        url_row = tk.Frame(card, bg="white"); url_row.pack(fill="x", pady=8)
        tk.Label(url_row, text="رابط السيرفر (Server URL):", width=22, anchor="e", bg="white", font=("Tahoma", 9, "bold")).pack(side="right")
        
        current_url = cfg.get("cloud_url_internal", "جاري تشغيل النفق...")
        url_ent = tk.Entry(url_row, font=("Consolas", 11), fg="#2563eb", bd=2, relief="groove")
        url_ent.insert(0, current_url)
        url_ent.config(state="readonly")
        url_ent.pack(side="right", fill="x", expand=True, padx=10)

        def _copy_url():
            self.root.clipboard_clear()
            self.root.clipboard_append(current_url)
            messagebox.showinfo("تم النسخ", "تم نسخ الرابط بنجاح.")
        tk.Button(url_row, text="نسخ الرابط", bg="#2563eb", fg="white", font=("Tahoma", 9), padx=10, command=_copy_url).pack(side="right")

        # رمز الأمان
        token_row = tk.Frame(card, bg="white"); token_row.pack(fill="x", pady=8)
        tk.Label(token_row, text="رمز الأمان (Access Token):", width=22, anchor="e", bg="white", font=("Tahoma", 9, "bold")).pack(side="right")
        
        current_token = cfg.get("cloud_token", "")
        token_ent = tk.Entry(token_row, font=("Consolas", 11), fg="#dc2626", bd=2, relief="groove")
        token_ent.insert(0, current_token)
        token_ent.config(state="readonly")
        token_ent.pack(side="right", fill="x", expand=True, padx=10)

        def _copy_token():
            self.root.clipboard_clear()
            self.root.clipboard_append(current_token)
            messagebox.showinfo("تم النسخ", "تم نسخ رمز الأمان بنجاح.")
        tk.Button(token_row, text="نسخ الرمز", bg="#2563eb", fg="white", font=("Tahoma", 9), padx=10, command=_copy_token).pack(side="right")

        # QR Code Section
        qr_frame = tk.Frame(card, bg="white", pady=20)
        qr_frame.pack()
        
        if current_url and current_url != "جاري تشغيل النفق...":
            try:
                # توليد QR يحتوي على الرابط والتوكن مفصولين بفاصلة
                qr_data = f"{current_url}|{current_token}"
                qr_img = qrcode.make(qr_data).resize((180, 180))
                self._cloud_qr_img = ImageTk.PhotoImage(qr_img)
                qr_lbl = tk.Label(qr_frame, image=self._cloud_qr_img, bg="white")
                qr_lbl.pack()
                tk.Label(qr_frame, text="امسح الرمز للربط السريع (قريباً)", bg="white", fg="#64748b", font=("Tahoma", 8)).pack(pady=5)
            except Exception:
                pass
        
        # إضافة زر التشخيص هنا أيضاً للجهاز الرئيسي
        tk.Frame(card, bg="#e2e8f0", height=1).pack(fill="x", pady=15)
        tk.Button(card, text="🔎 تشخيص حالة النفق والاتصال", command=self._run_cloud_diagnostics,
                  bg="#fff7ed", fg="#c2410c", font=("Tahoma", 10, "bold"), padx=20, pady=5).pack(pady=5)

    def _build_client_cloud_ui(self, parent, cfg):
        """واجهة جهاز العميل."""
        card = tk.Frame(parent, bg="white", bd=1, relief="flat", padx=20, pady=20)
        card.pack(fill="x")
        card.config(highlightthickness=1, highlightbackground="#e2e8f0")

        tk.Label(card, text="بيانات الاتصال الحالية",
                 bg="white", fg="#1e293b", font=("Tahoma", 12, "bold")).pack(anchor="e", pady=(0, 15))

        # السيرفر المتصل به
        row1 = tk.Frame(card, bg="white"); row1.pack(fill="x", pady=5)
        tk.Label(row1, text="السيرفر المتصل به:", width=20, anchor="e", bg="white", font=("Tahoma", 9, "bold")).pack(side="right")
        tk.Label(row1, text=cfg.get("cloud_url", ""), bg="white", fg="#2563eb", font=("Consolas", 10)).pack(side="right", padx=10)

        # حالة الاتصال
        row2 = tk.Frame(card, bg="white"); row2.pack(fill="x", pady=5)
        tk.Label(row2, text="حالة الاتصال:", width=20, anchor="e", bg="white", font=("Tahoma", 9, "bold")).pack(side="right")
        self.conn_status_lbl = tk.Label(row2, text="يتم الفحص...", bg="white", fg="#64748b", font=("Tahoma", 9))
        self.conn_status_lbl.pack(side="right", padx=10)

        def _check_conn():
            import requests
            try:
                url = cfg.get("cloud_url", "").rstrip("/") + "/health"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    self.conn_status_lbl.config(text="● متصل (جيد)", fg="#10b981")
                else:
                    self.conn_status_lbl.config(text="● خطأ في السيرفر", fg="#ef4444")
            except Exception:
                self.conn_status_lbl.config(text="● تعذر الاتصال", fg="#ef4444")

        tk.Button(card, text="🔄 تحديث حالة الاتصال", command=_check_conn, 
                  bg="#f8fafc", font=("Tahoma", 9)).pack(pady=5)
        
        tk.Button(card, text="🔎 تشخيص وإصلاح المشاكل", command=self._run_cloud_diagnostics,
                  bg="#fff7ed", fg="#c2410c", font=("Tahoma", 9, "bold"), padx=15).pack(pady=5)
        
        # زر تغيير الإعدادات
        ttk.Separator(card, orient="horizontal").pack(fill="x", pady=15)
        tk.Label(card, text="لتغيير إعدادات الربط، يجب تسجيل الخروج والدخول من 'إعدادات المزامنة'.",
                 bg="white", fg="#64748b", font=("Tahoma", 9)).pack()

        # تشغيل الفحص الأول
        parent.after(1000, _check_conn)

    def _run_cloud_diagnostics(self):
        """إجراء فحص عميق لمشاكل الاتصال السحابي."""
        from tkinter import scrolledtext
        import requests
        import socket

        diag_win = tk.Toplevel(self.root)
        diag_win.title("أداة تشخيص الربط السحابي")
        diag_win.geometry("600x500")
        diag_win.transient(self.root)
        diag_win.grab_set()

        lbl = tk.Label(diag_win, text="🔍 جاري فحص حالة الربط السحابي...", font=("Tahoma", 12, "bold"), pady=15)
        lbl.pack()

        txt = scrolledtext.ScrolledText(diag_win, font=("Consolas", 10), bg="#1e293b", fg="#f1f5f9", padx=10, pady=10)
        txt.pack(fill="both", expand=True, padx=20, pady=10)

        def log(msg): 
            txt.insert(tk.END, msg + "\n")
            txt.see(tk.END)
            diag_win.update()

        cfg = load_config()
        
        # 1. فحص برنامج cloudflared
        log("--- [1] فحص ملفات النظام ---")
        cf_path = find_cloudflared_executable()
        if cf_path:
            log(f"✅ تم العثور على برنامج النفق: {cf_path}")
        else:
            log("❌ خطأ: برنامج cloudflared.exe غير موجود في الجهاز.")
            log("   الحل: تأكد من وجود ملف cloudflared.exe في مجلد البرنامج.")

        # 2. فحص الخادم المحلي
        log("\n--- [2] فحص الخادم المحلي (API) ---")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(('127.0.0.1', PORT))
            log(f"✅ الخادم المحلي يعمل على المنفذ {PORT}")
            s.close()
            
            # فحص الـ Health check المحلي
            resp = requests.get(f"http://127.0.0.1:{PORT}/health", timeout=2)
            if resp.status_code == 200:
                log("✅ استجابة مسار الصحة: OK")
            else:
                log(f"⚠️ الخادم المحلي استجاب برمز خطأ: {resp.status_code}")
        except Exception as e:
            log(f"❌ الخادم المحلي لا يستجيب: {e}")
            log("   الحل: أعد تشغيل البرنامج بالكامل.")

        # 3. فحص الرابط العام
        log("\n--- [3] فحص الرابط العام ---")
        public_url = cfg.get("cloud_url_internal", "").rstrip("/")
        if not public_url:
            log("⚠️ لا يوجد رابط عام مسجل حالياً.")
        else:
            log(f"فحص الرابط: {public_url}")
            try:
                resp = requests.get(f"{public_url}/health", timeout=5)
                if resp.status_code == 200:
                    log("✅ الرابط العام متصل ويعمل بشكل ممتاز!")
                elif resp.status_code == 530:
                    log("❌ خطأ 530: النفق متوقف أو غير متصل بـ Cloudflare.")
                    log("   الحل: تأكد من جودة الإنترنت أو أعد تشغيل النفق.")
                else:
                    log(f"⚠️ الرابط العام أعاد رمز: {resp.status_code}")
            except Exception as e:
                log(f"❌ تعذر الوصول للرابط العام: {e}")

        log("\n--- تم الفحص بنجاح ---")
        lbl.config(text="✅ اكتمل الفحص")
