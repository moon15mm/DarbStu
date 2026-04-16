# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os, json, datetime, threading, re, io, csv, base64, time
from constants import ROLES, ROLE_TABS
from database import (create_user, delete_user, get_all_users,
                       save_user_allowed_tabs, toggle_user_active,
                       update_user_password, DB_PATH)

class UsersTabMixin:
    """Mixin: UsersTabMixin"""
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
        ttk.Button(ctrl, text="توليد حسابات وإرسال بالواتساب",
                   command=self._user_generate_teachers).pack(side="right", padx=3)

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
            # يومي
            "لوحة المراقبة",        "روابط الفصول",         "التأخر",
            "الأعذار",               "الاستئذان",             "المراقبة الحية",
            "الموجّه الطلابي",       "استلام تحويلات",
            # السجلات
            "السجلات / التصدير",    "إدارة الغياب",          "التقارير / الطباعة",
            "تقرير الفصل",           "نشر النتائج",           "تحليل النتائج",           "تصدير نور",
            "الإشعارات الذكية",
            # الرسائل
            "إرسال رسائل الغياب",   "رسائل التأخر",          "مستلمو التأخر",
            "جدولة الروابط",         "إدارة الواتساب",
            # البيانات
            "إدارة الطلاب",          "إضافة طالب",            "إدارة الفصول",
            "إدارة أرقام الجوالات",
            # أدوات المعلم
            "تحويل طالب",            "نماذج المعلم",          "خطابات الاستفسار",
            "التعاميم والنشرات",
            # الإعدادات
            "إعدادات المدرسة",       "المستخدمون",            "النسخ الاحتياطية",
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

    def _user_generate_teachers(self):
        if not messagebox.askyesno("تأكيد", "سيتم توليد حسابات (اسم المستخدم وكلمة مرور عشوائية) للمعلمين وإرسالها لهم عبر واتساب.\nهل أنت متأكد؟"):
            return
        from database import load_teachers, create_user, save_user_allowed_tabs, get_all_users
        from config_manager import load_config
        from whatsapp_service import send_whatsapp_message
        import random

        teachers_data = load_teachers().get("teachers", [])
        if not teachers_data:
            messagebox.showwarning("تنبيه", "لا يوجد معلمين. تأكد من استيراد ملف المعلمين أولاً.")
            return

        cfg = load_config()
        public_url = cfg.get("public_url", "")
        if not public_url:
            messagebox.showwarning("تنبيه", "يرجى تعيين 'الرابط العالمي' من إعدادات المدرسة قبل الإرسال لتضمينه في رسالة الواتساب.")
            return

        existing_users = {u["username"]: u for u in get_all_users()}
        
        success_count = 0
        skip_count = 0

        self.root.config(cursor="wait")
        try:
            for t in teachers_data:
                name = t.get("اسم المعلم", "").strip()
                phone = t.get("رقم الجوال", "").strip()
                civ_id = t.get("رقم الهوية", "").strip()

                username = civ_id if civ_id else phone
                if not username:
                    skip_count += 1
                    continue
                
                if username not in existing_users:
                    password = str(random.randint(100000, 999999))
                    ok, _ = create_user(username, password, "teacher", name)
                    if ok:
                        save_user_allowed_tabs(username, ["لوحة القيادة", "تحليل النتائج", "تحويل طالب", "نماذج المعلم", "خطابات الاستفسار", "التعاميم والنشرات"])
                        
                        msg = (f"مرحباً أستاذ {name}\n\n"
                               f"يسعدنا انضمامك للنظام. بيانات الدخول عبر الويب:\n\n"
                               f"الرابط العام:\n{public_url}\n\n"
                               f"اسم المستخدم: {username}\n"
                               f"كلمة المرور: {password}\n"
                               f"\nمع تحيات إدارة المدرسة")
                        
                        if phone:
                            send_whatsapp_message(phone, msg)
                        success_count += 1
                else:
                    skip_count += 1
                    
            self._users_load()
            messagebox.showinfo("اكتمل", f"تم إنشاء وإرسال {success_count} حساب معلم.\nتم تخطي {skip_count} (موجود مسبقاً أو بياناته ناقصة).")
        finally:
            self.root.config(cursor="")

    # ══════════════════════════════════════════════════════════
    # تبويب النسخ الاحتياطية
    # ══════════════════════════════════════════════════════════
