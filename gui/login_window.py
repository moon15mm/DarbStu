# -*- coding: utf-8 -*-
"""
gui/login_window.py — نافذة تسجيل الدخول
"""
import tkinter as tk
from tkinter import ttk, messagebox
from constants import APP_VERSION, CURRENT_USER, ROLES
from database import authenticate, get_user_allowed_tabs

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


