# -*- coding: utf-8 -*-
"""
gui/app_gui.py — الواجهة الرئيسية للتطبيق
مُبنية باستخدام Python Mixins لفصل كل تبويب في ملف منفصل
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os, sys, json, datetime, threading, time, re, io, csv, base64
import sqlite3, subprocess, webbrowser, zipfile, urllib.request, urllib.parse
from typing import List, Dict, Any, Optional
try:
    from PIL import ImageTk
    import qrcode
except ImportError:
    ImageTk = qrcode = None

# ─── استيراد Mixins كل التبويبات ─────────────────────
from gui.tabs.dashboard_tab    import DashboardTabMixin
from gui.tabs.links_tab        import LinksTabMixin
from gui.tabs.absence_tab      import AbsenceTabMixin
from gui.tabs.reports_tab      import ReportsTabMixin
from gui.tabs.phones_tab       import PhonesTabMixin
from gui.tabs.messages_tab     import MessagesTabMixin
from gui.tabs.students_tab     import StudentsTabMixin
from gui.tabs.tardiness_tab    import TardinessTabMixin
from gui.tabs.whatsapp_tab     import WhatsappTabMixin
from gui.tabs.excuses_tab      import ExcusesTabMixin
from gui.tabs.users_tab        import UsersTabMixin
from gui.tabs.settings_tab     import SettingsTabMixin
from gui.tabs.tardiness_msg_tab import TardinessMessagesTabMixin
from gui.tabs.alerts_tab       import AlertsTabMixin
from gui.tabs.noor_tab         import NoorTabMixin
from gui.tabs.counselor_tab    import CounselorTabMixin
from gui.tabs.permissions_tab  import PermissionsTabMixin
from gui.tabs.term_report_tab  import TermReportTabMixin
from gui.tabs.results_tab      import ResultsTabMixin
from gui.tabs.monitor_tab      import MonitorTabMixin
from gui.tabs.schedule_tab     import ScheduleTabMixin
from gui.tabs.add_student_tab  import AddStudentTabMixin
from gui.tabs.grade_analysis_tab import GradeAnalysisTabMixin

# ─── استيراد كل الوحدات اللازمة ───────────────────────
from constants import (APP_TITLE, APP_VERSION, DB_PATH, DATA_DIR, HOST, PORT,
                       BASE_DIR, WHATS_PATH, STUDENTS_JSON, TEACHERS_JSON,
                       CONFIG_JSON, BACKUP_DIR, TZ_OFFSET, STATIC_DOMAIN,
                       CURRENT_USER, ROLES, ROLE_TABS, now_riyadh_date,
                       local_ip, debug_on, navbar_html, STUDENTS_STORE)

# ── استيراد المكتبات الثقيلة بشكل مباشر (تُحمَّل مرة واحدة عند أول استخدام) ──
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        arabic_reshaper = get_display = None
except ImportError:
    Figure = FigureCanvasTkAgg = matplotlib = arabic_reshaper = get_display = None

try:
    from tkinterweb import HtmlFrame
except ImportError:
    HtmlFrame = None

try:
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None
from config_manager import (load_config, save_config, get_terms, ar,
                             logo_img_tag_from_config, render_message,
                             get_message_template, invalidate_config_cache,
                             DEFAULT_CONFIG, get_window_title)
from database import (get_db, init_db, load_students, load_teachers,
                      query_absences, query_tardiness, insert_tardiness,
                      delete_tardiness, query_excuses, insert_excuse,
                      delete_excuse, student_has_excuse, compute_tardiness_metrics,
                      create_backup, get_backup_list,
                      get_all_users, create_user, delete_user, toggle_user_active,
                      hash_password, update_user_password, authenticate,
                      get_user_allowed_tabs, save_user_allowed_tabs,
                      norm_token, normalize_legacy_class_id, _apply_class_name_fix,
                      section_label_from_value, display_name_from_legacy,
                      level_name_from_value, import_students_from_excel_sheet2_format,
                      import_teachers_from_excel, insert_absences,
                      _cleanup_old_backups, schedule_auto_backup,
                      EXCUSE_REASONS)
from report_builder import (build_daily_report_df, build_total_absences_with_dates_by_class,
                             compute_today_metrics, get_live_monitor_status,
                             export_to_noor_excel, generate_report_html,
                             generate_daily_report, generate_monthly_report,
                             generate_weekly_report, generate_student_report,
                             generate_term_report_html, generate_monitor_table_html,
                             detect_suspicious_patterns, parent_portal_html)
from pdf_generator import (generate_session_pdf, generate_behavioral_contract_pdf,
                            _render_pdf_page_as_png, _render_page_pillow,
                            parse_results_pdf, save_results_to_db, get_student_result,
                            results_portal_html, student_result_html)
from whatsapp_service import (send_whatsapp_message, send_whatsapp_pdf,
                               check_whatsapp_server_status, get_wa_servers,
                               start_whatsapp_server)
from api.mobile_routes import send_tardiness_link_to_all
from pdf_generator import (generate_session_pdf, generate_behavioral_contract_pdf,
                            _render_pdf_page_as_png, _render_page_pillow,
                            parse_results_pdf)
from alerts_service import (log_message_status, query_today_messages,
                             run_smart_alerts, send_alert_for_student,
                             build_daily_summary_message, send_daily_report_to_admin,
                             schedule_daily_alerts, schedule_daily_report,
                             get_students_exceeding_threshold,
                             get_student_full_analysis,
                             get_top_absent_students, get_student_absence_count,
                             safe_send_absence_alert, get_tardiness_recipients,
                             save_tardiness_recipients,
                             load_schedule, save_schedule,
                             query_permissions, insert_permission,
                             update_permission_status, delete_permission,
                             send_permission_request,
                             PERMISSION_REASONS, PERM_APPROVED, PERM_WAITING,
                             build_absent_groups, get_absence_by_day_of_week,
                             get_week_comparison)
from license_manager import (check_license, LicenseWindow, LicenseClient,
                              activate_license, try_renew_license,
                              generate_tokens, consume_token,
                              _get_machine_id,
                              get_all_tokens, delete_all_tokens, get_tokens_count)
from updater import check_for_updates


class AppGUI(
    DashboardTabMixin,
    LinksTabMixin,
    AbsenceTabMixin,
    ReportsTabMixin,
    PhonesTabMixin,
    MessagesTabMixin,
    StudentsTabMixin,
    TardinessTabMixin,
    WhatsappTabMixin,
    ExcusesTabMixin,
    UsersTabMixin,
    SettingsTabMixin,
    TardinessMessagesTabMixin,
    AlertsTabMixin,
    NoorTabMixin,
    CounselorTabMixin,
    PermissionsTabMixin,
    TermReportTabMixin,
    ResultsTabMixin,
    MonitorTabMixin,
    ScheduleTabMixin,
    AddStudentTabMixin,
    GradeAnalysisTabMixin,
):
    """الواجهة الرئيسية للتطبيق — تجمع كل Mixins في class واحد."""
    def __init__(self, root, public_url=None):
        # 1. تعيين المتغيرات الأساسية أولاً
        self.root = root
        self.root.title(APP_TITLE)
        self.public_url = public_url
        
        self.scheduler_running = False
        self.scheduler_timers = []

        try:
            # مسار الأيقونة (يجب أن يكون ملف .ico)
            # icon_path = 'icon.ico' 
            # self.root.iconbitmap(icon_path)
            pass # تم تعطيله مؤقتاً
        except Exception as e:
            print(f"Could not load icon: {e}")

        self.store = load_students()
        self.ip = local_ip()
        # عرض الدور في عنوان النافذة
        role_label = CURRENT_USER.get("label","")
        user_name  = CURRENT_USER.get("name", CURRENT_USER.get("username",""))
        role_color = ROLES.get(CURRENT_USER.get("role","admin"),{}).get("color","#1565C0")
        root.title(f"{get_window_title()} — {user_name} ({role_label})")
        self.cfg = load_config()

        # ─── كل التبويبات المتاحة في البرنامج ──────────────────────
        all_tabs = {
            "لوحة المراقبة":        "_build_dashboard_tab",
            "روابط الفصول":         "_build_links_tab",
            "التأخر":               "_build_tardiness_tab",
            "الأعذار":              "_build_excuses_tab",
            "الاستئذان":           "_build_permissions_tab",
            "المراقبة الحية":       "_build_live_monitor_tab",
            "السجلات / التصدير":    "_build_logs_tab",
            "إدارة الغياب":         "_build_absence_management_tab",
            "التقارير / الطباعة":   "_build_reports_tab",
            "تقرير الفصل":         "_build_term_report_tab",
            "نشر النتائج":          "_build_results_tab",
            "تحليل النتائج":        "_build_grade_analysis_tab",
            "تصدير نور":            "_build_noor_export_tab",
            "الإشعارات الذكية":     "_build_alerts_tab",
            "إرسال رسائل الغياب":   "_build_messages_tab",
            "رسائل التأخر":         "_build_tardiness_messages_tab",
            "مستلمو التأخر":        "_build_tardiness_recipients_tab",
            "جدولة الروابط":        "_build_schedule_tab",
            "إدارة الواتساب":       "_build_whatsapp_manager_tab",
            "إدارة الطلاب":         "_build_student_management_tab",
            "إضافة طالب":           "_build_add_student_tab",
            "إدارة الفصول":         "_build_class_naming_tab",
            "إدارة أرقام الجوالات": "_build_phones_tab",
            "إعدادات المدرسة":      "_build_school_settings_tab",
            "المستخدمون":           "_build_users_tab",
            "النسخ الاحتياطية":     "_build_backup_tab",
            "الموجّه الطلابي":      "_build_counselor_tab",
        }

        # مجموعات القائمة الجانبية
        _username = CURRENT_USER.get("username", "admin")
        _allowed  = get_user_allowed_tabs(_username)  # None = مدير = كل شيء

        def _vis(t): return _allowed is None or t in _allowed

        sidebar_groups = [
            ("⬤  يومي", [t for t in [
                "لوحة المراقبة","روابط الفصول","التأخر",
                "الأعذار","الاستئذان","المراقبة الحية","الموجّه الطلابي"] if _vis(t)]),
            ("⬤  السجلات", [t for t in [
                "السجلات / التصدير","إدارة الغياب",
                "التقارير / الطباعة","تقرير الفصل","نشر النتائج","تحليل النتائج","تصدير نور","الإشعارات الذكية"] if _vis(t)]),
            ("⬤  الرسائل", [t for t in [
                "إرسال رسائل الغياب","رسائل التأخر",
                "مستلمو التأخر","جدولة الروابط","إدارة الواتساب"] if _vis(t)]),
            ("⬤  البيانات", [t for t in [
                "إدارة الطلاب","إضافة طالب",
                "إدارة الفصول","إدارة أرقام الجوالات"] if _vis(t)]),
            ("⬤  الإعدادات", [t for t in [
                "إعدادات المدرسة","المستخدمون","النسخ الاحتياطية","معلومات الترخيص"] if _vis(t)]),
        ]

        # ─── فلترة التبويبات حسب صلاحيات المستخدم ───────────────
        username = CURRENT_USER.get("username", "admin")
        allowed  = get_user_allowed_tabs(username)

        if allowed is None:
            self.tabs_config = all_tabs
        else:
            self.tabs_config = {k: v for k, v in all_tabs.items() if k in allowed}
            if not self.tabs_config:
                self.tabs_config = {"لوحة المراقبة": "_build_dashboard_tab"}

        # ─── بناء الواجهة الجانبية ────────────────────────────────
        self._tabs_built   = set()
        self._tab_frames   = {}
        self._nav_buttons  = {}
        self._current_tab  = tk.StringVar()

        # الإطار الرئيسي: sidebar + content
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(fill="both", expand=True)

        # ── منطقة المحتوى ──
        self._content_area = tk.Frame(main_frame, bg="white")
        self._content_area.pack(side="left", fill="both", expand=True)

        # فاصل عمودي
        tk.Frame(main_frame, bg="#d0d0d0", width=1).pack(side="left", fill="y")

        # ── القائمة الجانبية ──
        sidebar_outer = tk.Frame(main_frame, bg="#f0f0f0", width=185)
        sidebar_outer.pack(side="left", fill="y")
        sidebar_outer.pack_propagate(False)

        sidebar_canvas = tk.Canvas(sidebar_outer, bg="#f0f0f0",
                                    highlightthickness=0, bd=0)
        sidebar_scroll = ttk.Scrollbar(sidebar_outer, orient="vertical",
                                        command=sidebar_canvas.yview)
        sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar_scroll.pack(side="right", fill="y")
        sidebar_canvas.pack(side="left", fill="both", expand=True)

        sidebar = tk.Frame(sidebar_canvas, bg="#f0f0f0")
        sidebar_win = sidebar_canvas.create_window((0, 0), window=sidebar,
                                                    anchor="nw")

        def _on_sidebar_configure(e):
            sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))
        sidebar.bind("<Configure>", _on_sidebar_configure)
        _sb_last_w = [0]
        def _on_sidebar_canvas_conf(e):
            w = sidebar_canvas.winfo_width()
            if w == _sb_last_w[0]: return
            _sb_last_w[0] = w
            sidebar_canvas.itemconfig(sidebar_win, width=w)
        sidebar_canvas.bind("<Configure>", _on_sidebar_canvas_conf)

        # ── بناء عناصر القائمة ──
        for group_title, group_tabs in sidebar_groups:
            # تصفية حسب الصلاحيات
            visible = [t for t in group_tabs if t in self.tabs_config]
            if not visible:
                continue

            # عنوان المجموعة
            grp_lbl = tk.Label(sidebar, text=group_title,
                               bg="#f0f0f0", fg="#888888",
                               font=("Tahoma", 8, "bold"),
                               anchor="w", padx=10, pady=2)
            grp_lbl.pack(fill="x")

            for tab_name in visible:
                btn = tk.Label(sidebar, text=tab_name,
                               bg="#f0f0f0", fg="#333333",
                               font=("Tahoma", 10),
                               anchor="w", padx=14, pady=6,
                               cursor="hand2")
                btn.pack(fill="x")

                def _make_click(name):
                    def _click(e=None):
                        self._switch_tab(name)
                    return _click

                btn.bind("<Button-1>", _make_click(tab_name))
                btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#e0e8f0") if self._current_tab.get() != b.cget("text") else None)
                btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#f0f0f0") if self._current_tab.get() != b.cget("text") else None)
                self._nav_buttons[tab_name] = btn

            # فاصل بين المجموعات
            tk.Frame(sidebar, bg="#d8d8d8", height=1).pack(fill="x", padx=8, pady=2)

        # ── إنشاء frames للتبويبات (باستخدام place للتحكم الكامل) ──
        for tab_name, builder_name in self.tabs_config.items():
            frame_attr = builder_name.replace("_build_", "").replace("_tab", "") + "_frame"
            f = tk.Frame(self._content_area, bg="white")
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            f.place_forget()
            setattr(self, frame_attr, f)
            self._tab_frames[tab_name] = f

        self.add_student_frame = self._tab_frames.get("إضافة طالب",
                                  tk.Frame(self._content_area, bg="white"))

        # ── دالة التبديل بين التبويبات ──
        def _switch_tab(name):
            if name not in self._tab_frames:
                return

            # أوقف auto-refresh الجدول عند مغادرة تبويبه
            if hasattr(self, '_schedule_auto_refresh_active') and self._current_tab.get() == "جدولة الروابط":
                self._schedule_auto_refresh_active = False

            # أخفِ كل التبويبات
            for f in self._tab_frames.values():
                f.place_forget()

            # تحديث تمييز القائمة
            prev = self._current_tab.get()
            if prev and prev in self._nav_buttons:
                self._nav_buttons[prev].config(bg="#f0f0f0", fg="#333333",
                                                font=("Tahoma", 10))
            self._current_tab.set(name)
            if name in self._nav_buttons:
                self._nav_buttons[name].config(bg="#1565C0", fg="white",
                                                font=("Tahoma", 10, "bold"))

            # بناء التبويب عند أول فتح (Lazy Loading)
            builder_name = self.tabs_config.get(name)
            if builder_name and builder_name not in self._tabs_built:
                self._tabs_built.add(builder_name)
                getattr(self, builder_name)()
                if builder_name == "_build_dashboard_tab" and hasattr(self, "tree_dash"):
                    self.root.after(500, self.update_dashboard_metrics)
                    self._start_dashboard_tick()

            # أظهر التبويب المطلوب
            self._tab_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)

            # أعد تشغيل auto-refresh الجدول عند العودة إليه
            if name == "جدولة الروابط" and hasattr(self, '_schedule_auto_refresh_active'):
                self._schedule_auto_refresh_active = True

        self._switch_tab = _switch_tab
        self._main_notebook = None  # للتوافق مع الكود القديم

        # افتح أول تبويب
        first_tab = next(iter(self.tabs_config.keys()))
        _switch_tab(first_tab)

        # تحقق من التحديثات بعد 5 ثوان من بدء التشغيل
        root.after(5000, lambda: check_for_updates(root, silent=True))

        self._build_menu(root)

    def _build_menu(self, root):
        m = tk.Menu(root); root.config(menu=m)
        filem = tk.Menu(m, tearoff=0); m.add_cascade(label="ملف", menu=filem)
        filem.add_command(label="إعادة استيراد الطلاب...", command=self.reimport_students)
        filem.add_command(label="إعادة استيراد المعلمين...", command=self.reimport_teachers)
        filem.add_separator()
        filem.add_command(label="إعدادات المدرسة...", command=self._open_school_settings_tab)
        filem.add_command(label="فتح ملف الإعدادات (JSON)...", command=self.open_config_json)
        filem.add_separator()
        filem.add_command(label=f"التحقق من التحديثات... (v{APP_VERSION})",
                          command=lambda: check_for_updates(self.root, silent=False))
        filem.add_separator()
        filem.add_command(label="خروج", command=self.root.destroy)

    def _build_dashboard_tab(self):
        style = ttk.Style(); style.theme_use("arc")
        style.configure("Card.TFrame",      background="#ffffff")
        style.configure("CardTitle.TLabel", background="#ffffff",
                        foreground="#6b7280", font=("Tahoma", 9, "bold"))
        style.configure("CardValue.TLabel", background="#ffffff",
                        font=("Tahoma", 22, "bold"))
        style.configure("Treeview",         rowheight=26, font=("Tahoma", 10))
        style.configure("Treeview.Heading", font=("Tahoma", 10, "bold"))

        # ─ شريط التحكم العلوي
        top_bar = ttk.Frame(self.dashboard_frame)
        top_bar.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top_bar, text="تاريخ اليوم:",
                  font=("Tahoma",10)).pack(side="right", padx=(0,6))
        self.dash_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(top_bar, textvariable=self.dash_date_var,
                  width=12).pack(side="right", padx=4)
        ttk.Button(top_bar, text="🔄 تحديث الآن",
                   command=self.update_dashboard_metrics).pack(side="right", padx=4)
        self.dash_week_lbl = ttk.Label(top_bar, text="",
                                        foreground="#5A6A7E", font=("Tahoma",9))
        self.dash_week_lbl.pack(side="left", padx=8)

        # ─ بطاقات الإحصاء (صف واحد)
        cards_row = ttk.Frame(self.dashboard_frame)
        cards_row.pack(fill="x", padx=10, pady=6)

        def make_card(parent, title, color, sub=""):
            fr = ttk.Frame(parent, style="Card.TFrame")
            fr.pack(side="right", padx=6, fill="x", expand=True,
                    ipadx=10, ipady=10)
            ttk.Label(fr, text=title,
                      style="CardTitle.TLabel").pack(anchor="w", padx=10, pady=(8,0))
            val = ttk.Label(fr, text="—", style="CardValue.TLabel",
                             foreground=color)
            val.pack(anchor="w", padx=10)
            sub_lbl = ttk.Label(fr, text=sub, background="#ffffff",
                                 foreground="#9CA3AF", font=("Tahoma",8))
            sub_lbl.pack(anchor="w", padx=10, pady=(0,8))
            return val, sub_lbl

        self.lbl_total,   self.lbl_total_sub   = make_card(cards_row, "إجمالي الطلاب",  "#3B82F6")
        self.lbl_present, self.lbl_present_sub  = make_card(cards_row, "الحضور اليوم",   "#10B981")
        self.lbl_absent,  self.lbl_absent_sub   = make_card(cards_row, "الغياب اليوم",   "#EF4444")
        self.lbl_tard,    self.lbl_tard_sub      = make_card(cards_row, "التأخر اليوم",   "#F59E0B")
        self.lbl_week,    self.lbl_week_sub      = make_card(cards_row, "غياب الأسبوع",   "#8B5CF6",
                                                              "مقارنة بالأسبوع الماضي")

        # ─ الجسم الرئيسي: جدول + رسوم بيانية
        body = ttk.Frame(self.dashboard_frame)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        # ── العمود الأيسر: جدول الفصول + أكثر الطلاب غياباً
        left = ttk.Frame(body); left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        left.rowconfigure(0, weight=2); left.rowconfigure(1, weight=1)

        # جدول الفصول
        cls_lf = ttk.LabelFrame(left, text=" 📋 الفصول — الحضور والغياب ", padding=4)
        cls_lf.grid(row=0, column=0, sticky="nsew", pady=(0,6))
        cols = ("class_id","class_name","total","present","absent","pct")
        self.tree_dash = ttk.Treeview(cls_lf, columns=cols, show="headings", height=9)
        for c, h, w in zip(cols,
            ["المعرّف","اسم الفصل","الإجمالي","🟢 حاضر","🔴 غائب","نسبة الغياب"],
            [80, 200, 80, 90, 90, 100]):
            self.tree_dash.heading(c, text=h)
            self.tree_dash.column(c, width=w, anchor="center")
        self.tree_dash.tag_configure("high",   background="#FFF0F0")
        self.tree_dash.tag_configure("normal", background="#F0FFF4")
        sb1 = ttk.Scrollbar(cls_lf, orient="vertical",
                             command=self.tree_dash.yview)
        self.tree_dash.configure(yscrollcommand=sb1.set)
        self.tree_dash.pack(side="left", fill="both", expand=True)
        sb1.pack(side="right", fill="y")
        self.tree_dash.bind("<Double-1>", self._on_dash_dblclick)

        # أكثر الطلاب غياباً
        top_lf = ttk.LabelFrame(left, text=" 🏆 أكثر الطلاب غياباً هذا الشهر ", padding=4)
        top_lf.grid(row=1, column=0, sticky="nsew")
        top_cols = ("name","class_name","days","last_date")
        self.tree_top_absent = ttk.Treeview(
            top_lf, columns=top_cols, show="headings", height=5)
        for c, h, w in zip(top_cols,
            ["اسم الطالب","الفصل","أيام الغياب","آخر غياب"],
            [200, 150, 90, 100]):
            self.tree_top_absent.heading(c, text=h)
            self.tree_top_absent.column(c, width=w, anchor="center")
        self.tree_top_absent.tag_configure("top1", background="#FFEBEE",
                                            foreground="#C62828")
        self.tree_top_absent.tag_configure("top3", background="#FFF8E1",
                                            foreground="#E65100")
        self.tree_top_absent.pack(fill="both", expand=True)
        self.tree_top_absent.bind("<Double-1>", self._on_top_absent_dblclick)

        # ── العمود الأيمن: الرسوم البيانية
        right = ttk.Frame(body); right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1); right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        # دائرة الحضور/الغياب
        pie_lf = ttk.LabelFrame(right, text=" نسبة الحضور/الغياب اليوم ", padding=4)
        pie_lf.grid(row=0, column=0, sticky="nsew", pady=(0,4))
        self.fig_pie = Figure(figsize=(4, 2.5), dpi=90)
        self.ax_pie  = self.fig_pie.add_subplot(111)
        self.canvas_pie = FigureCanvasTkAgg(self.fig_pie, pie_lf)
        self.canvas_pie.get_tk_widget().pack(fill="both", expand=True)

        # مقارنة الأسبوعين
        week_lf = ttk.LabelFrame(right, text=" مقارنة هذا الأسبوع بالماضي ", padding=4)
        week_lf.grid(row=1, column=0, sticky="nsew", pady=(0,4))
        self.fig_week = Figure(figsize=(4, 2.3), dpi=90)
        self.ax_week  = self.fig_week.add_subplot(111)
        self.canvas_week = FigureCanvasTkAgg(self.fig_week, week_lf)
        self.canvas_week.get_tk_widget().pack(fill="both", expand=True)

        # أكثر الأيام غياباً
        dow_lf = ttk.LabelFrame(right, text=" أكثر أيام الأسبوع غياباً ", padding=4)
        dow_lf.grid(row=2, column=0, sticky="nsew")
        self.fig_dow = Figure(figsize=(4, 2.3), dpi=90)
        self.ax_dow  = self.fig_dow.add_subplot(111)
        self.canvas_dow = FigureCanvasTkAgg(self.fig_dow, dow_lf)
        self.canvas_dow.get_tk_widget().pack(fill="both", expand=True)


    def _start_dashboard_tick(self):
        """يبدأ دورة التحديث التلقائي — مرة واحدة فقط."""
        if getattr(self, "_dash_tick_running", False):
            return
        self._dash_tick_running = True
        self._dash_tick_id = None
        self._dashboard_tick()

    def _dashboard_tick(self):
        """يُحدَّث كل 30 ث — guard flag يمنع تراكم الاستدعاءات."""
        if getattr(self, "_current_tab", None) and self._current_tab.get() == "لوحة المراقبة":
            try:
                self.update_dashboard_metrics()
            except Exception as e:
                print("[DASH-TICK]", e)
        # ألغِ أي after() سابق قبل جدولة جديد
        if getattr(self, "_dash_tick_id", None):
            try:
                self.root.after_cancel(self._dash_tick_id)
            except Exception:
                pass
        self._dash_tick_id = self.root.after(30000, self._dashboard_tick)

    def update_dashboard_metrics(self):
        """Fetch all dashboard data in a background thread, then update UI on main thread."""
        date_str = self.dash_date_var.get().strip() or now_riyadh_date()

        def do_fetch():
            try:
                metrics = compute_today_metrics(date_str)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("خطأ", str(e)))
                return
            try:
                tard_today = len(query_tardiness(date_filter=date_str))
            except Exception:
                tard_today = 0
            try:
                wk = get_week_comparison()
            except Exception:
                wk = None
            try:
                top_absent = get_top_absent_students(date_str[:7], limit=8)
            except Exception:
                top_absent = []
            try:
                dow_data = get_absence_by_day_of_week()
            except Exception:
                dow_data = {}
            self.root.after(0, lambda: self._update_dashboard_ui(
                date_str, metrics, tard_today, wk, top_absent, dow_data))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _update_dashboard_ui(self, date_str, metrics, tard_today, wk, top_absent, dow_data):
        """Apply fetched dashboard data to UI widgets (must run on main thread)."""
        t = metrics["totals"]
        pct_absent = round(t["absent"] / max(t["students"], 1) * 100, 1)

        # ─ بطاقات الإحصاء
        self.lbl_total.config(text=str(t["students"]))
        self.lbl_present.config(text=str(t["present"]))
        self.lbl_absent.config(text=str(t["absent"]))
        if hasattr(self, "lbl_absent_sub"):
            self.lbl_absent_sub.config(text="{}% من الإجمالي".format(pct_absent))

        # التأخر اليوم
        if hasattr(self, "lbl_tard"):
            self.lbl_tard.config(text=str(tard_today))

        # مقارنة الأسبوع
        if wk is not None:
            try:
                if hasattr(self, "lbl_week"):
                    self.lbl_week.config(text=str(wk["this_total"]))
                if hasattr(self, "lbl_week_sub"):
                    arrow = "▲" if wk["change"] > 0 else ("▼" if wk["change"] < 0 else "=")
                    color = "#EF4444" if wk["change"] > 0 else "#10B981"
                    self.lbl_week_sub.config(
                        text="{} {}% عن الأسبوع الماضي".format(arrow, abs(wk["pct"])),
                        foreground=color)
                if hasattr(self, "dash_week_lbl"):
                    self.dash_week_lbl.config(
                        text="الأسبوع الماضي: {} غياب".format(wk["last_total"]))
            except Exception as e:
                print("[DASH-WEEK]", e)

        # ─ جدول الفصول
        for i in self.tree_dash.get_children():
            self.tree_dash.delete(i)
        for r in metrics["by_class"]:
            pct = round(r["absent"] / max(r["total"], 1) * 100, 0)
            tag = "high" if pct >= 20 else "normal"
            self.tree_dash.insert("", "end", tags=(tag,),
                values=(r["class_id"], r["class_name"],
                        r["total"],
                        "🟢 {}".format(r["present"]),
                        "🔴 {}".format(r["absent"]),
                        "{}%".format(int(pct))))

        # ─ أكثر الطلاب غياباً
        if hasattr(self, "tree_top_absent"):
            for i in self.tree_top_absent.get_children():
                self.tree_top_absent.delete(i)
            for idx, s in enumerate(top_absent):
                tag = "top1" if idx == 0 else ("top3" if idx < 3 else "")
                self.tree_top_absent.insert("", "end", tags=(tag,),
                    values=(s["name"], s["class_name"],
                            "{} يوم".format(s["days"]), s["last_date"]))

        # ─ رسم الدائرة
        try:
            self.ax_pie.clear()
            sizes = [t["present"], t["absent"]]
            if sum(sizes) > 0:
                self.ax_pie.pie(
                    sizes,
                    labels=[ar("الحضور"), ar("الغياب")],
                    autopct="%1.1f%%", startangle=90,
                    colors=["#10B981", "#EF4444"])
            self.ax_pie.set_title(ar("الحضور/الغياب اليوم"), fontsize=9)
            self.canvas_pie.draw_idle()
        except Exception as e:
            print("[DASH-PIE]", e)

        # ─ رسم مقارنة الأسبوعين
        if wk is not None:
            try:
                self.ax_week.clear()
                day_names_short = ["أحد", "إثنين", "ثلاث", "أربع", "خميس"]
                x = range(5)
                this_vals = [wk["this_daily"].get(
                    (datetime.date.fromisoformat(wk["this_week_start"]) +
                     datetime.timedelta(days=i)).isoformat(), 0) for i in range(5)]
                last_vals = [wk["last_daily"].get(
                    (datetime.date.fromisoformat(wk["last_week_start"]) +
                     datetime.timedelta(days=i)).isoformat(), 0) for i in range(5)]
                w_bar = 0.35
                self.ax_week.bar([i - w_bar / 2 for i in x], last_vals,
                                 w_bar, label=ar("الأسبوع الماضي"), color="#93C5FD")
                self.ax_week.bar([i + w_bar / 2 for i in x], this_vals,
                                 w_bar, label=ar("هذا الأسبوع"), color="#3B82F6")
                self.ax_week.set_xticks(list(x))
                self.ax_week.set_xticklabels([ar(d) for d in day_names_short], fontsize=7)
                self.ax_week.legend(fontsize=7)
                self.ax_week.set_title(ar("مقارنة الأسبوعين"), fontsize=9)
                self.canvas_week.draw_idle()
            except Exception as e:
                print("[DASH-WEEK-CHART]", e)

        # ─ رسم أكثر الأيام غياباً
        try:
            self.ax_dow.clear()
            days_ar = list(dow_data.keys())
            vals = list(dow_data.values())
            if vals:
                bars = self.ax_dow.bar(
                    [ar(d) for d in days_ar], vals,
                    color=["#EF4444" if v == max(vals) else "#FCA5A5" for v in vals])
                self.ax_dow.set_title(ar("متوسط الغياب حسب اليوم"), fontsize=9)
                for bar_r, v in zip(bars, vals):
                    if v > 0:
                        self.ax_dow.text(bar_r.get_x() + bar_r.get_width() / 2,
                                         bar_r.get_height(),
                                         "{:.0f}".format(v),
                                         ha="center", va="bottom", fontsize=7)
            self.canvas_dow.draw_idle()
        except Exception as e:
            print("[DASH-DOW]", e)

    def _build_links_tab(self):
        if self.public_url:
            ttk.Label(self.links_frame, text=f"الرابط العام: {self.public_url}", foreground="blue", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0,4))
            ttk.Label(self.links_frame, text="امسح الـ QR Code للوصول من الإنترنت.").pack(anchor="w", pady=(0,8))
        else:
            ttk.Label(self.links_frame, text=f"الخادم المحلي: http://{self.ip}:{PORT} (يعمل على نفس الشبكة فقط )").pack(anchor="w", pady=(0,8))
        main_container = ttk.Frame(self.links_frame)
        main_container.pack(fill="both", expand=True)
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side="left", fill="both", expand=True, padx=5)
        cols = ("class_id", "class_name", "students", "link")
        tree = ttk.Treeview(left_frame, columns=cols, show="headings", height=8)
        for c, t, w in zip(cols, ["المعرّف","اسم الفصل","عدد الطلاب","الرابط"], [80, 180, 80, 300]):
            tree.heading(c, text=t); tree.column(c, width=w, anchor="center")
        tree.pack(fill="x", expand=True); self.tree_links = tree
        self.qr_canvas = tk.Label(left_frame); self.qr_canvas.pack(pady=8, anchor="center")
        send_controls_frame = ttk.LabelFrame(main_container, text=" إرسال الرابط إلى معلم ", padding=10)
        send_controls_frame.pack(side="right", fill="y", padx=5, anchor="n")
        ttk.Label(send_controls_frame, text="اختر المعلم:").pack(anchor="e")
        self.teacher_var = tk.StringVar()
        self.teacher_combo = ttk.Combobox(send_controls_frame, textvariable=self.teacher_var, state="readonly", width=30)
        self.teacher_combo.pack(anchor="e", pady=5, fill="x")
        self.send_link_button = ttk.Button(send_controls_frame, text="إرسال الرابط المحدد عبر واتساب", command=self.on_send_link_to_teacher, state="disabled")
        self.send_link_button.pack(anchor="e", pady=10)
        self.tree_links.bind("<<TreeviewSelect>>", self.on_class_select)
        self.teacher_combo.bind("<<ComboboxSelected>>", self.on_teacher_select)
        self._refresh_links_and_teachers()

    def _refresh_links_and_teachers(self):
        if not hasattr(self, "tree_links") or not self.tree_links.winfo_exists():
            return
        for i in self.tree_links.get_children(): self.tree_links.delete(i)
        base_url = self.public_url or f"http://{self.ip}:{PORT}"
        for c in self.store["list"]:
            link = f"{base_url}/c/{c['id']}"
            self.tree_links.insert("", "end", values=(c["id"], c["name"], len(c["students"] ), link))
        self.teachers_data = load_teachers()
        teacher_names = [t["اسم المعلم"] for t in self.teachers_data.get("teachers", [])]
        self.teacher_combo['values'] = teacher_names
        self.teacher_var.set("")
        self.send_link_button.config(state="disabled")
        self.qr_img = None
        self.qr_canvas.config(image=None)

    def on_class_select(self, event=None):
        if not (sel := self.tree_links.selection()): return
        link = self.tree_links.item(sel[0])["values"][3]
        img = qrcode.make(link).resize((220,220)); self.qr_img = ImageTk.PhotoImage(img)
        self.qr_canvas.config(image=self.qr_img)
        if self.teacher_var.get():
            self.send_link_button.config(state="normal")

    def on_teacher_select(self, event=None):
        if self.tree_links.selection():
            self.send_link_button.config(state="normal")

    def on_send_link_to_teacher(self):
        if not (sel := self.tree_links.selection()):
            messagebox.showwarning("تنبيه", "الرجاء تحديد فصل من القائمة أولاً.")
            return
        if not (teacher_name := self.teacher_var.get()):
            messagebox.showwarning("تنبيه", "الرجاء اختيار معلم من القائمة.")
            return
        class_name, link = self.tree_links.item(sel[0])["values"][1], self.tree_links.item(sel[0])["values"][3]
        teacher = next((t for t in self.teachers_data.get("teachers", []) if t["اسم المعلم"] == teacher_name), None)
        if not teacher:
            messagebox.showerror("خطأ", "لم يتم العثور على بيانات المعلم المحدد.")
            return
        teacher_phone = teacher.get("رقم الجوال")
        if not teacher_phone:
            messagebox.showwarning("تنبيه", f"لا يوجد رقم جوال مسجل للمعلم '{teacher_name}'.")
            return
        if not messagebox.askyesno("تأكيد الإرسال", f"هل أنت متأكد من إرسال رابط فصل '{class_name}' إلى المعلم '{teacher_name}'؟"):
            return
        self.send_link_button.config(state="disabled"); self.root.update_idletasks()
        # Note: send_link_to_teacher is not defined in the provided code, assuming it's a wrapper for send_whatsapp_message
        message_body = f"السلام عليكم أ. {teacher_name},\nإليك رابط تسجيل غياب فصل: {class_name}\n{link}"
        success, message = send_whatsapp_message(teacher_phone, message_body)
        messagebox.showinfo("نتيجة الإرسال", message)
        self.send_link_button.config(state="normal")

    def _build_logs_tab(self):
        top = ttk.Frame(self.logs_frame); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="تاريخ:").pack(side="right")
        self.date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(top, textvariable=self.date_var, width=12).pack(side="right", padx=5)
        ttk.Label(top, text="فصل:").pack(side="right")
        self.class_var = tk.StringVar()
        class_ids = ["(الكل)"] + [c["id"] for c in self.store["list"]]
        cb = ttk.Combobox(top, textvariable=self.class_var, values=class_ids, width=12, state="readonly"); cb.current(0); cb.pack(side="right", padx=5)
        ttk.Button(top, text="تحديث", command=self.refresh_logs).pack(side="right", padx=5)
        ttk.Button(top, text="تقرير رسائل اليوم", command=self._open_today_messages_report).pack(side="left", padx=5)

        cols = ("date","class_id","class_name","student_id","student_name","teacher_name","period","created_at")
        tree = ttk.Treeview(self.logs_frame, columns=cols, show="headings", height=12)
        for c,h,w in zip(cols, ["التاريخ","المعرّف","الفصل","رقم الطالب","اسم الطالب","المعلم","الحصة","وقت التسجيل"], [90,90,200,120,240,140,60,170]):
            tree.heading(c, text=h); tree.column(c, width=w, anchor="center")
        tree.pack(fill="both", expand=True); self.tree_logs = tree
        self.tree_logs.bind("<Double-1>", self._on_log_dblclick)
        self.refresh_logs()
    
    def refresh_logs(self):
        try:
            date_f = self.date_var.get().strip() if hasattr(self, "date_var") else now_riyadh_date()
            class_id = self.class_var.get() if hasattr(self, "class_var") else None
            if class_id == "(الكل)":
                class_id = None

            rows = _apply_class_name_fix(query_absences(date_f or None, class_id))

            if not hasattr(self, "tree_logs"):
                return

            for i in self.tree_logs.get_children():
                self.tree_logs.delete(i)

            for r in rows:
                self.tree_logs.insert(
                    "", "end",
                    values=(
                        r.get("date", ""),
                        r.get("class_id", ""),
                        r.get("class_name", ""),
                        r.get("student_id", ""),
                        r.get("student_name", ""),
                        r.get("teacher_name", ""),
                        r.get("period", ""),
                        r.get("created_at", "")
                    )
                )
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر تحديث السجلات:\n{e}")

    def _build_absence_management_tab(self):
        frame = self.absence_management_frame
        controls_frame = ttk.LabelFrame(frame, text=" بحث وتعديل ", padding=10)
        controls_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(controls_frame, text="اسم الطالب أو رقمه:").pack(side="right", padx=(0, 5))
        self.absence_search_var = tk.StringVar()
        ttk.Entry(controls_frame, textvariable=self.absence_search_var, width=25).pack(side="right", padx=5)
        ttk.Label(controls_frame, text="في تاريخ:").pack(side="right", padx=(10, 5))
        self.absence_date_entry = DateEntry(controls_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd', locale='ar_SA')
        self.absence_date_entry.pack(side="right", padx=5)
        search_button = ttk.Button(controls_frame, text="🔍 بحث", command=self.search_absences_for_student)
        search_button.pack(side="right", padx=10)
        self.delete_absence_button = ttk.Button(controls_frame, text="🗑️ حذف الغياب المحدد", state="disabled", command=self.delete_selected_absence)
        self.delete_absence_button.pack(side="left", padx=10)

        results_frame = ttk.Frame(frame); results_frame.pack(fill="both", expand=True, padx=10, pady=5)
        cols = ("record_id", "student_id", "student_name", "class_name", "period", "teacher_name")
        self.tree_absences = ttk.Treeview(results_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["ID", "رقم الطالب", "اسم الطالب", "الفصل", "الحصة", "مسجل بواسطة"], [60, 100, 250, 180, 60, 150]):
            self.tree_absences.heading(col, text=header); self.tree_absences.column(col, width=w, anchor="center")
        self.tree_absences.pack(fill="both", expand=True)
        self.tree_absences.bind("<<TreeviewSelect>>", self.on_absence_record_select)

    def on_absence_record_select(self, event=None):
        if self.tree_absences.selection():
            self.delete_absence_button.config(state="normal")
        else:
            self.delete_absence_button.config(state="disabled")

    def search_absences_for_student(self):
        for item in self.tree_absences.get_children():
            self.tree_absences.delete(item)
        query = self.absence_search_var.get().strip()
        date_filter = self.absence_date_entry.get()
        if not query:
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم أو رقم الطالب للبحث.")
            return
        if not date_filter:
            messagebox.showwarning("تنبيه", "الرجاء تحديد التاريخ للبحث.")
            return
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        sql_query = "SELECT id, student_id, student_name, class_name, period, teacher_name FROM absences WHERE date = ? AND (student_name LIKE ? OR student_id = ?)"
        params = (date_filter, f'%{query}%', query)
        cur.execute(sql_query, params); rows = cur.fetchall(); con.close()
        if not rows:
            messagebox.showinfo("لا توجد نتائج", f"لم يتم العثور على أي سجلات غياب للطالب '{query}' في تاريخ {date_filter}.")
        else:
            for row in rows:
                self.tree_absences.insert("", "end", values=(row['id'], row['student_id'], row['student_name'], row['class_name'], row['period'], row['teacher_name']))
        self.delete_absence_button.config(state="disabled")

    def delete_selected_absence(self):
        if not (selected_items := self.tree_absences.selection()):
            messagebox.showwarning("تنبيه", "الرجاء تحديد سجل الغياب الذي تريد حذفه أولاً.")
            return
        item_id = selected_items[0]
        record_values = self.tree_absences.item(item_id, "values")
        db_id = record_values[0]; student_name = record_values[2]; class_name = record_values[3]; period = record_values[4]
        confirmation_message = (f"هل أنت متأكد من حذف سجل الغياب التالي؟\n\nالطالب: {student_name}\nالفصل: {class_name}\nالحصة: {period}\n\nهذا الإجراء سيحول الطالب إلى 'حاضر' في هذه الحصة ولا يمكن التراجع عنه.")
        if not messagebox.askyesno("تأكيد الحذف", confirmation_message): return
        try:
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM absences WHERE id = ?", (db_id,)); con.commit(); con.close()
            self.tree_absences.delete(item_id)
            messagebox.showinfo("تم الحذف", "تم حذف سجل الغياب بنجاح.")
            self.update_dashboard_metrics()
            self.delete_absence_button.config(state="disabled")
        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ أثناء محاولة الحذف من قاعدة البيانات:\n{e}")

    def _build_reports_tab(self):
        controls_frame = ttk.LabelFrame(self.reports_frame, text="خيارات التقرير", padding=10)
        controls_frame.pack(fill="x", padx=5, pady=5)
        self.report_type_var = tk.StringVar(value="daily")
        types_frame = ttk.Frame(controls_frame); types_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(types_frame, text="نوع التقرير:").pack(side="right", padx=(0, 10))
        report_types = [("يومي", "daily"), ("أسبوعي", "weekly"), ("شهري", "monthly"), ("طالب محدد", "student")]
        for text, value in report_types:
            ttk.Radiobutton(types_frame, text=text, variable=self.report_type_var, value=value, command=self._update_report_controls).pack(side="right", padx=5)
        self.inputs_frame = ttk.Frame(controls_frame); self.inputs_frame.pack(fill="x", pady=5)
        self.report_date_label = ttk.Label(self.inputs_frame, text="تاريخ:")
        self.report_date_var = tk.StringVar(value=now_riyadh_date())
        self.report_date_entry = ttk.Entry(self.inputs_frame, textvariable=self.report_date_var, width=15)
        self.report_class_label = ttk.Label(self.inputs_frame, text="الفصل:")
        self.report_class_var = tk.StringVar()
        class_ids = ["(كل الفصول)"] + [c["id"] for c in self.store["list"]]
        self.report_class_combo = ttk.Combobox(self.inputs_frame, textvariable=self.report_class_var, values=class_ids, width=15, state="readonly")
        self.report_class_combo.current(0)
        self.report_student_label = ttk.Label(self.inputs_frame, text="ابحث عن الطالب (بالاسم أو الرقم):")
        self.report_student_var = tk.StringVar()
        self.report_student_entry = ttk.Entry(self.inputs_frame, textvariable=self.report_student_var, width=30)
        
        buttons_frame = ttk.Frame(controls_frame)
        buttons_frame.pack(pady=5)
        ttk.Button(buttons_frame, text="إنشاء التقرير", command=self.on_generate_report).pack(side="right", padx=5)
        self.print_button = ttk.Button(buttons_frame, text="طباعة التقرير الحالي", command=self.on_print_report, state="disabled")
        self.print_button.pack(side="right", padx=5)
        
        ttk.Button(buttons_frame, text="📤 تصدير لـ نور", command=self.export_to_noor_from_ui).pack(side="right", padx=5)

        view_frame = ttk.LabelFrame(self.reports_frame, text="عرض التقرير", padding=10)
        view_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.report_browser = HtmlFrame(view_frame, horizontal_scrollbar="auto", messages_enabled=False)
        self.report_browser.pack(fill="both", expand=True)
        self.report_browser.load_html("<html><body style='font-family:sans-serif; text-align:center; color:#888;'><h1>جاهز لإنشاء التقارير</h1><p>اختر نوع التقرير من الأعلى ثم اضغط على 'إنشاء التقرير'</p></body></html>")
        self._update_report_controls()

    def _update_report_controls(self):
        for widget in [self.report_date_label, self.report_date_entry, self.report_class_label, self.report_class_combo, self.report_student_label, self.report_student_entry]:
            widget.pack_forget()
        report_type = self.report_type_var.get()
        if report_type in ["daily", "weekly", "monthly"]:
            self.report_date_label.pack(side="right", padx=(0, 5))
            self.report_date_entry.pack(side="right", padx=5)
            self.report_class_label.pack(side="right", padx=(15, 5))
            self.report_class_combo.pack(side="right", padx=5)
            if report_type == "daily": self.report_date_label.config(text="تاريخ اليوم:")
            elif report_type == "weekly": self.report_date_label.config(text="أي يوم في الأسبوع:")
            elif report_type == "monthly": self.report_date_label.config(text="أي يوم في الشهر:")
        elif report_type == "student":
            self.report_student_label.pack(side="right", padx=(0, 5))
            self.report_student_entry.pack(side="right", padx=5)

    def on_generate_report(self):
        report_type = self.report_type_var.get()
        html_content = ""
        self.current_report_html = "" 
        try:
            self.root.config(cursor="wait"); self.root.update_idletasks()
            class_id_filter = self.report_class_var.get()
            if class_id_filter == "(كل الفصول)": class_id_filter = None
            if report_type == "student":
                search_query = self.report_student_var.get().strip()
                if not search_query:
                    messagebox.showwarning("بيانات ناقصة", "الرجاء إدخال اسم أو رقم الطالب للبحث عنه.")
                    return
                found_student = None
                for c in self.store['list']:
                    for s in c['students']:
                        if search_query.lower() in s['name'].lower() or search_query == s['id']:
                            found_student = s
                            break
                    if found_student: break
                
                # --- START: هذا هو السطر الذي تم إصلاحه ---
                if not found_student:
                    messagebox.showerror("غير موجود", f"لم يتم العثور على طالب يطابق البحث: '{search_query}'")
                    return
                # --- END: هذا هو السطر الذي تم إصلاحه ---

                if not messagebox.askyesno("تأكيد", f"هل تريد إنشاء تقرير للطالب:\n\nالاسم: {found_student['name']}\nالرقم: {found_student['id']}"):
                    return
                html_content = generate_student_report(found_student['id'])
            else:
                date_str = self.report_date_var.get()
                if not date_str:
                    messagebox.showerror("خطأ", "الرجاء إدخال تاريخ صالح.")
                    return
                if report_type == "daily":
                    html_content = generate_daily_report(date_str, class_id_filter)
                elif report_type == "weekly":
                    html_content = generate_weekly_report(date_str, class_id_filter)
                elif report_type == "monthly":
                    html_content = generate_monthly_report(date_str, class_id_filter)
            
            if html_content and "لا توجد بيانات" not in html_content:
                self.current_report_html = html_content
                self.report_browser.load_html(html_content)
                self.print_button.config(state="normal")
            else:
                self.current_report_html = ""
                self.report_browser.load_html(html_content or "<html><body><h2>لم يتم إنشاء التقرير أو لا توجد بيانات.</h2></body></html>")
                self.print_button.config(state="disabled")
        except Exception as e:
            messagebox.showerror("خطأ فادح", f"حدث خطأ أثناء إنشاء التقرير:\n{e}")
            self.print_button.config(state="disabled")
        finally:
            self.root.config(cursor="")


    def on_print_report(self):
        if not hasattr(self, 'current_report_html') or not self.current_report_html:
            messagebox.showwarning("لا يوجد تقرير", "الرجاء إنشاء تقرير أولاً قبل محاولة الطباعة.")
            return
        
        try:
            temp_report_path = os.path.join(DATA_DIR, "temp_report_to_print.html")
            with open(temp_report_path, "w", encoding="utf-8") as f:
                f.write(self.current_report_html)
            webbrowser.open(f"file://{os.path.abspath(temp_report_path)}")
            messagebox.showinfo("جاهز للطباعة", "تم فتح التقرير في متصفحك. الرجاء استخدام أمر الطباعة من هناك (Ctrl+P).")
        except Exception as e:
            messagebox.showerror("خطأ في تجهيز الطباعة", f"لم يتمكن من إنشاء ملف الطباعة المؤقت:\n{e}")

    def export_to_noor_from_ui(self):
        date_str = self.report_date_var.get().strip()
        if not date_str:
            messagebox.showerror("خطأ", "الرجاء تحديد تاريخ صالح.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="حفظ ملف نور"
        )
        if file_path:
            export_to_noor_excel(date_str, file_path)

    def _build_phones_tab(self):
        top_frame = ttk.Frame(self.phones_frame); top_frame.pack(fill="x", pady=(8, 8))
        ttk.Label(top_frame, text="بحث:").pack(side="left", padx=(0, 5)); self.search_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.search_var, width=30).pack(side="left", padx=5)
        ttk.Button(top_frame, text="بحث", command=self.search_students).pack(side="left", padx=5)
        ttk.Button(top_frame, text="مسح", command=self.clear_search).pack(side="left", padx=5)
        ttk.Button(top_frame, text="حفظ التعديلات", command=self.save_phone_edits).pack(side="right", padx=5)
        cols = ("student_id", "student_name", "phone", "class_name")
        self.tree_phones = ttk.Treeview(self.phones_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["رقم الطالب", "اسم الطالب", "رقم الجوال", "الفصل"], [120, 250, 180, 200]):
            self.tree_phones.heading(col, text=header); self.tree_phones.column(col, width=w, anchor="center")
        self.tree_phones.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_phones.bind("<Double-1>", self.on_double_click_phone)
        self.load_students_to_treeview()

    def load_students_to_treeview(self):
        for item in self.tree_phones.get_children(): self.tree_phones.delete(item)
        self.all_students_data = [{"student_id": s.get("id", ""), "student_name": s.get("name", ""), "phone": s.get("phone", ""), "class_name": c["name"]} for c in self.store["list"] for s in c["students"]]
        self.display_students(self.all_students_data)

    def display_students(self, students_list):
        for student in students_list: self.tree_phones.insert("", "end", values=(student["student_id"], student["student_name"], student["phone"], student["class_name"]))
        self.highlight_phone_numbers()

    def highlight_phone_numbers(self):
        def _is_valid_phone(phone: str) -> bool:
            """يقبل الأرقام بصيغة 05xxxxxxxx أو 966xxxxxxxxx أو +966 أو 00966."""
            d = phone.replace("+", "").replace(" ", "").replace("-", "")
            if not d.isdigit():
                return False
            if d.startswith("05") and len(d) == 10:
                return True
            if d.startswith("966") and len(d) == 12:
                return True
            if d.startswith("00966") and len(d) == 14:
                return True
            return False

        all_phones = [self.tree_phones.item(i, "values")[2].strip() for i in self.tree_phones.get_children() if self.tree_phones.item(i, "values")[2].strip()]
        phone_counts = {p: all_phones.count(p) for p in all_phones}
        for item in self.tree_phones.get_children():
            phone = self.tree_phones.item(item, "values")[2].strip()
            tags = ()
            if not phone:
                pass
            elif not _is_valid_phone(phone):
                tags = ("invalid",)
            elif phone_counts.get(phone, 0) > 1:
                tags = ("duplicate",)
            self.tree_phones.item(item, tags=tags)
        self.tree_phones.tag_configure("invalid", background="#ffebee", foreground="#c62828")
        self.tree_phones.tag_configure("duplicate", background="#e8f5e9", foreground="#2e7d32")

    def on_double_click_phone(self, event):
        if self.tree_phones.identify("region", event.x, event.y) != "cell" or self.tree_phones.identify_column(event.x) != "#3": return
        if not (item_id := self.tree_phones.focus()): return
        current_values = list(self.tree_phones.item(item_id, "values"))
        entry = ttk.Entry(self.tree_phones); entry.insert(0, current_values[2]); entry.select_range(0, tk.END); entry.focus()
        if not (bbox := self.tree_phones.bbox(item_id, column="#3")): return
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        def save_edit(e=None):
            current_values[2] = entry.get().strip(); self.tree_phones.item(item_id, values=current_values); entry.destroy(); self.highlight_phone_numbers()
        entry.bind("<Return>", save_edit); entry.bind("<FocusOut>", save_edit); entry.bind("<Escape>", lambda e: entry.destroy())

    def save_phone_edits(self):
        updated_phones = {self.tree_phones.item(i, "values")[0]: self.tree_phones.item(i, "values")[2] for i in self.tree_phones.get_children()}
        for c in self.store["list"]:
            for s in c["students"]:
                if (sid := s.get("id")) in updated_phones: s["phone"] = updated_phones[sid]
        with open(STUDENTS_JSON, "w", encoding="utf-8") as f: json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("تم الحفظ", "تم حفظ أرقام الجوالات بنجاح."); self.load_students_to_treeview()

    def search_students(self):
        query = self.search_var.get().strip().lower()
        filtered = [s for s in self.all_students_data if not query or query in str(s["student_id"]).lower() or query in str(s["student_name"]).lower()]
        for item in self.tree_phones.get_children(): self.tree_phones.delete(item)
        self.display_students(filtered)

    def clear_search(self): self.search_var.set(""); self.search_students()

    def _build_messages_tab(self):
        self.msg_template_var = tk.StringVar(value=get_message_template())
        self.msg_date_var = tk.StringVar(value=now_riyadh_date())
        self.msg_groups = {}
        self.msg_vars = {}
        self.class_select_vars = {}
        self.global_select_var = tk.BooleanVar(value=False)

        top = ttk.Frame(self.messages_frame); top.pack(fill="x", pady=(6,6))
        ttk.Label(top, text="تاريخ الغياب:").pack(side="right", padx=(0,5))
        ttk.Entry(top, textvariable=self.msg_date_var, width=12).pack(side="right", padx=5)
        ttk.Button(top, text="تحميل الغياب", command=self._msg_load_groups).pack(side="right", padx=5)

        chk_all = ttk.Checkbutton(top, text="اختيار الجميع", variable=self.global_select_var, command=self._msg_toggle_all)
        chk_all.pack(side="right", padx=10)

        ttk.Button(top, text="تعديل نص الرسالة", command=self._msg_open_template_editor).pack(side="right", padx=5)
        ttk.Button(top, text="تشغيل WhatsApp Server", command=start_whatsapp_server).pack(side="right", padx=5)
        self.send_button = ttk.Button(top, text="إرسال للمحددين", command=self._msg_send_selected)
        self.send_button.pack(side="right", padx=5)

        status_bar = ttk.Frame(self.messages_frame); status_bar.pack(fill="x", padx=5)
        ttk.Label(status_bar, text="الحالة:").pack(side="right")
        self.status_label = ttk.Label(status_bar, text="جاهز", foreground="green")
        self.status_label.pack(side="right")

        wrapper = ttk.Frame(self.messages_frame); wrapper.pack(fill="both", expand=True, padx=5, pady=5)

        self.msg_scroll = ttk.Scrollbar(wrapper, orient="vertical")
        self.msg_scroll.pack(side="right", fill="y")

        self.msg_canvas = tk.Canvas(wrapper, yscrollcommand=self.msg_scroll.set, highlightthickness=0)
        self.msg_canvas.pack(side="left", fill="both", expand=True)

        self.msg_scroll.config(command=self.msg_canvas.yview)

        self.msg_inner = ttk.Frame(self.msg_canvas)
        self._msg_canvas_window = self.msg_canvas.create_window((0, 0), window=self.msg_inner, anchor="nw")

        self.msg_inner.bind(
            "<Configure>",
            lambda e: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all"))
        )

        self.msg_canvas.bind(
            "<Configure>",
            lambda e: self.msg_canvas.itemconfigure(self._msg_canvas_window, width=e.width)
        )

        self._msg_load_groups()

    def _msg_load_groups(self):
        date_str = self.msg_date_var.get().strip()
        if not date_str:
            if hasattr(self, 'msg_inner') and self.msg_inner.winfo_children():
                 messagebox.showerror("خطأ", "الرجاء إدخال تاريخ.")
            return

        for child in self.msg_inner.winfo_children():
            child.destroy()
        self.msg_vars.clear()
        self.class_select_vars.clear()

        self.msg_groups = build_absent_groups(date_str)
        total_students = sum(len(v["students"]) for v in self.msg_groups.values())
        if not self.msg_groups or total_students == 0:
            self.status_label.config(text=f"لا توجد غيابات بتاريخ {date_str}", foreground="orange")
            ttk.Label(self.msg_inner, text="لا توجد بيانات لعرضها.", foreground="#888").pack(pady=20)
            self.msg_inner.update_idletasks()
            self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all"))
            return

        for cid, obj in sorted(self.msg_groups.items(), key=lambda kv: kv[0]):
            self._msg_build_class_section(cid, obj["class_name"], obj["students"])

        self.status_label.config(text=f"تم تحميل {total_students} طالبًا غائبًا.", foreground="green")

        self.msg_inner.update_idletasks()
        self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all"))


    def _msg_build_class_section(self, class_id: str, class_name: str, students: List[Dict[str, str]]):
        frame = ttk.LabelFrame(self.msg_inner, text=class_name, padding=10)
        frame.pack(fill="x", expand=True, pady=6)

        top_row = ttk.Frame(frame)
        top_row.pack(fill="x", pady=(0, 6))
        var_all = tk.BooleanVar(value=False)
        self.class_select_vars[class_id] = var_all

        chk = ttk.Checkbutton(top_row, text="اختيار جميع طلاب هذا الفصل", variable=var_all,
                              command=lambda cid=class_id: self._msg_toggle_class(cid))
        chk.pack(side="right")

        ttk.Label(top_row, text=f"عدد الطلاب: {len(students)}").pack(side="left")

        grid = ttk.Frame(frame)
        grid.pack(fill="x", expand=True)

        cols = 2
        for i, s in enumerate(students):
            r = i // cols
            c = i % cols
            cell = ttk.Frame(grid)
            cell.grid(row=r, column=c, sticky="ew", padx=4, pady=3)

            var = tk.BooleanVar(value=False)
            self.msg_vars[s["id"]] = var

            phone_txt = s.get("phone", "")
            label = f"{s['name']} — {phone_txt if phone_txt else 'لا يوجد رقم'}"
            ttk.Checkbutton(cell, text=label, variable=var).pack(anchor="w")

        for c in range(cols):
            grid.columnconfigure(c, weight=1)


    def _msg_toggle_class(self, class_id: str):
        checked = self.class_select_vars.get(class_id, tk.BooleanVar(value=False)).get()
        for s in self.msg_groups.get(class_id, {}).get("students", []):
            sid = s["id"]
            if sid in self.msg_vars:
                self.msg_vars[sid].set(checked)

    def _msg_toggle_all(self):
        checked = self.global_select_var.get()
        for var in self.class_select_vars.values():
            var.set(checked)
        for v in self.msg_vars.values():
            v.set(checked)

    def _msg_open_template_editor(self):
        win = tk.Toplevel(self.root)
        win.title("تعديل نص رسالة الغياب")
        win.geometry("650x350")
        win.transient(self.root)
        win.grab_set()

        info_frame = ttk.Frame(win)
        info_frame.pack(fill="x", padx=15, pady=(10, 5))
        ttk.Label(info_frame, text="المتغيّرات المدعومة:", anchor="e").pack(side="right")
        ttk.Label(info_frame, text="{school_name}, {student_name}, {class_name}, {date}", foreground="#007bff", anchor="w").pack(side="left")
        ttk.Separator(win, orient='horizontal').pack(fill='x', padx=10, pady=5)

        fields_frame = ttk.Frame(win, padding="10")
        fields_frame.pack(fill="both", expand=True)

        current_template = (load_config().get("message_template") or DEFAULT_CONFIG["message_template"]).strip()
        lines = current_template.split('\n')

        entries = []
        labels = [
            "السطر الأول (تنبيه):",
            "السطر الثاني (ولي الأمر):",
            "السطر الثالث (نص الإفادة):",
            "السطر الرابع (الحث على المتابعة):",
            "السطر الخامس (التحية):",
            "السطر السادس (التوقيع):"
        ]
        
        for i in range(6):
            row_frame = ttk.Frame(fields_frame)
            row_frame.pack(fill="x", pady=4)
            
            label_text = labels[i] if i < len(labels) else f"السطر الإضافي {i+1}:"
            lbl = ttk.Label(row_frame, text=label_text, width=25, anchor="e")
            lbl.pack(side="right", padx=5)
            
            entry = ttk.Entry(row_frame, font=("Tahoma", 10), justify='right')
            entry.pack(side="left", fill="x", expand=True)
            
            if i < len(lines):
                entry.insert(0, lines[i])
            
            entries.append(entry)

        def save_and_close():
            new_lines = [e.get().strip() for e in entries if e.get().strip()]
            new_template = "\n".join(new_lines)

            if not new_template:
                messagebox.showwarning("تنبيه", "لا يمكن حفظ قالب فارغ.", parent=win)
                return
            
            try:
                cfg = load_config()
                cfg["message_template"] = new_template
                with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                
                if hasattr(self, 'msg_template_var'):
                    self.msg_template_var.set(new_template)

                messagebox.showinfo("تم الحفظ", "تم تحديث نص الرسالة بنجاح.", parent=win)
                win.destroy()

            except Exception as e:
                messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ القالب:\n{e}", parent=win)

        buttons_frame = ttk.Frame(win)
        buttons_frame.pack(fill="x", padx=10, pady=(10, 10))

        ttk.Button(buttons_frame, text="حفظ وإغلاق", command=save_and_close).pack(side="left", padx=5)
        ttk.Button(buttons_frame, text="إلغاء", command=win.destroy).pack(side="right", padx=5)

    def _msg_send_selected(self):
        date_str = self.msg_date_var.get().strip()
        if not date_str:
            messagebox.showerror("خطأ", "الرجاء إدخال تاريخ.")
            return

        selected = []
        for cid, obj in self.msg_groups.items():
            cname = obj["class_name"]
            for s in obj["students"]:
                if self.msg_vars.get(s["id"], tk.BooleanVar()).get():
                    selected.append((cid, cname, s))

        if not selected:
            messagebox.showinfo("تنبيه", "الرجاء تحديد طالب واحد على الأقل.")
            return

        self.status_label.config(text="جارٍ الإرسال...", foreground="blue")
        self.send_button.config(state="disabled")

        def do_send():
            s_ok, s_fail = 0, 0
            for cid, cname, s in selected:
                student_name = s["name"]
                phone = s.get("phone", "")
                body = render_message(student_name, class_name=cname, date_str=date_str)
                success, msg = safe_send_absence_alert(s["id"], student_name, cname, date_str)
                status_text = "تم الإرسال" if success else f"فشل: {msg}"
                if success:
                    s_ok += 1
                else:
                    s_fail += 1

                try:
                    log_message_status(date_str, s["id"], student_name, cid, cname, phone, status_text, body)
                except Exception as e:
                    print("log_message_status error:", e)

                ok_snap, fail_snap = s_ok, s_fail
                self.root.after(0, lambda ok=ok_snap, fail=fail_snap:
                    self.status_label.config(
                        text=f"جاري الإرسال... ✅{ok} / ❌{fail}", foreground="blue"))

            summary = f"اكتمل: نجح {s_ok}، فشل {s_fail}."
            self.root.after(0, lambda: (
                self.send_button.config(state="normal"),
                self.status_label.config(
                    text=summary, foreground="green" if s_fail == 0 else "red"),
                messagebox.showinfo("نتيجة الإرسال", summary)
            ))

        threading.Thread(target=do_send, daemon=True).start()
    
    def _open_today_messages_report(self):
        date_str = now_riyadh_date()
        rows = query_today_messages(date_str)
        win = tk.Toplevel(self.root)
        win.title(f"تقرير رسائل اليوم ({date_str})")
        win.geometry("800x500")

        cols = ("student_name", "class_name", "phone", "status")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, h, w in zip(cols, ["اسم الطالب", "الفصل", "رقم الجوال", "حالة الرسالة"], [220, 220, 140, 200]):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="center")
        tree.pack(fill="both", expand=True)

        for r in rows:
            tree.insert("", "end", values=(r["student_name"], r["class_name"], r["phone"], r["status"]))

    def _build_student_management_tab(self):
        top_frame = ttk.Frame(self.student_management_frame); top_frame.pack(fill="x", pady=(8, 8))
        ttk.Label(top_frame, text="بحث:").pack(side="left", padx=(0, 5))
        self.student_search_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.student_search_var, width=30).pack(side="left", padx=5)
        ttk.Button(top_frame, text="بحث", command=self.search_students_for_management).pack(side="left", padx=5)
        ttk.Button(top_frame, text="مسح", command=self.clear_student_search).pack(side="left", padx=5)
        ttk.Button(top_frame, text="حفظ التعديلات", command=self.save_student_class_edits).pack(side="right", padx=5)
        cols = ("student_id", "student_name", "current_class", "new_class")
        self.tree_student_management = ttk.Treeview(self.student_management_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["رقم الطالب", "اسم الطالب", "الفصل الحالي", "الفصل الجديد"], [120, 250, 200, 200]):
            self.tree_student_management.heading(col, text=header); self.tree_student_management.column(col, width=w, anchor="center")
        self.tree_student_management.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_student_management.bind("<Double-1>", self.on_double_click_student_class)
                # أزرار الحذف
        delete_frame = ttk.Frame(top_frame)
        delete_frame.pack(side="right", padx=10)
        ttk.Button(delete_frame, text="🗑️ حذف الطالب المحدد", command=self.delete_selected_student).pack(pady=2)
        ttk.Button(delete_frame, text="🗑️ حذف فصل محدد", command=self.delete_selected_class).pack(pady=2)
        
        self.load_students_to_management_treeview()

    def load_students_to_management_treeview(self):
        for item in self.tree_student_management.get_children():
            self.tree_student_management.delete(item)
        self.all_students_class_data = []
        for c in self.store["list"]:
            for s in c["students"]:
                self.all_students_class_data.append({"student_id": s.get("id", ""), "student_name": s.get("name", ""), "current_class_id": c["id"], "current_class_name": c["name"]})
        self.display_students_for_management(self.all_students_class_data)

    def display_students_for_management(self, students_list):
        all_class_names = [c["name"] for c in self.store["list"]]
        for student in students_list:
            self.tree_student_management.insert("", "end", values=(student["student_id"], student["student_name"], student["current_class_name"], student["current_class_name"]))
        self.all_class_names_for_student_mng = all_class_names

    def on_double_click_student_class(self, event):
        if self.tree_student_management.identify("region", event.x, event.y) != "cell" or self.tree_student_management.identify_column(event.x) != "#4":
            return
        if not (item_id := self.tree_student_management.focus()): return
        current_values = list(self.tree_student_management.item(item_id, "values"))
        combo = ttk.Combobox(self.tree_student_management, values=self.all_class_names_for_student_mng, state="readonly"); combo.set(current_values[3]); combo.focus()
        if not (bbox := self.tree_student_management.bbox(item_id, column="#4")): return
        combo.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        def save_edit(e=None):
            selected_class = combo.get(); current_values[3] = selected_class
            self.tree_student_management.item(item_id, values=current_values); combo.destroy()
        combo.bind("<<ComboboxSelected>>", save_edit); combo.bind("<FocusOut>", save_edit); combo.bind("<Escape>", lambda e: combo.destroy())

    def search_students_for_management(self):
        query = self.student_search_var.get().strip().lower()
        filtered = [s for s in self.all_students_class_data if not query or query in str(s["student_id"]).lower() or query in str(s["student_name"]).lower()]
        for item in self.tree_student_management.get_children():
            self.tree_student_management.delete(item)
        self.display_students_for_management(filtered)

    def clear_student_search(self):
        self.student_search_var.set("")
        self.search_students_for_management()

    def save_student_class_edits(self):
        changes_made = False
        for item in self.tree_student_management.get_children():
            values = self.tree_student_management.item(item, "values")
            student_id, current_class_name, new_class_name = values[0], values[2], values[3]
            if current_class_name != new_class_name:
                changes_made = True
                student_data = None; old_class_index = -1
                for i, c in enumerate(self.store["list"]):
                    for j, s in enumerate(c["students"]):
                        if s.get("id") == student_id:
                            student_data = c["students"].pop(j)
                            old_class_index = i
                            break
                    if student_data: break
                
                if not student_data: continue

                new_class_found = False
                for c in self.store["list"]:
                    if c["name"] == new_class_name:
                        c["students"].append(student_data)
                        new_class_found = True
                        break
                
                if not new_class_found:
                    self.store["list"][old_class_index]["students"].append(student_data)

        if changes_made:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم الحفظ", "تم نقل الطلاب وحفظ التعديلات بنجاح.")
            self.update_all_tabs_after_data_change()
        else:
            messagebox.showinfo("لا توجد تغييرات", "لم يتم إجراء أي تغييرات على فصول الطلاب.")

    def _build_class_naming_tab(self):
        top_frame = ttk.Frame(self.class_naming_frame)
        top_frame.pack(fill="x", pady=(8, 8), padx=5)
        ttk.Label(top_frame, text="انقر نقرًا مزدوجًا على الاسم الجديد لتعديله.").pack(side="right")
        ttk.Button(top_frame, text="حفظ التعديلات", command=self.save_class_name_edits).pack(side="left")

        cols = ("class_id", "current_name", "new_name")
        self.tree_class_naming = ttk.Treeview(self.class_naming_frame, columns=cols, show="headings", height=15)
        for col, header, w in zip(cols, ["المعرّف", "الاسم الحالي", "الاسم الجديد"], [150, 300, 300]):
            self.tree_class_naming.heading(col, text=header)
            self.tree_class_naming.column(col, width=w, anchor="center")
        self.tree_class_naming.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_class_naming.bind("<Double-1>", self.on_double_click_class_name)
        self.load_class_names_to_treeview()

    def load_class_names_to_treeview(self):
        for item in self.tree_class_naming.get_children():
            self.tree_class_naming.delete(item)
        sorted_classes = sorted(self.store["list"], key=lambda c: c.get("id", ""))
        for c in sorted_classes:
            class_id = c.get("id", "")
            class_name = c.get("name", "")
            self.tree_class_naming.insert("", "end", values=(class_id, class_name, class_name))

    def on_double_click_class_name(self, event):
        if self.tree_class_naming.identify("region", event.x, event.y) != "cell" or self.tree_class_naming.identify_column(event.x) != "#3":
            return
        if not (item_id := self.tree_class_naming.focus()): return
        
        current_values = list(self.tree_class_naming.item(item_id, "values"))
        entry = ttk.Entry(self.tree_class_naming)
        entry.insert(0, current_values[2])
        entry.select_range(0, tk.END)
        entry.focus()
        
        if not (bbox := self.tree_class_naming.bbox(item_id, column="#3")): return
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        
        def save_edit(e=None):
            current_values[2] = entry.get().strip()
            self.tree_class_naming.item(item_id, values=current_values)
            entry.destroy()
        
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def save_class_name_edits(self):
        changes_made = False
        new_names_map = {self.tree_class_naming.item(i, "values")[0]: self.tree_class_naming.item(i, "values")[2] for i in self.tree_class_naming.get_children()}

        for c in self.store["list"]:
            class_id = c.get("id")
            if class_id in new_names_map:
                new_name = new_names_map[class_id]
                if c["name"] != new_name:
                    c["name"] = new_name
                    changes_made = True
        
        if changes_made:
            try:
                with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                    json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
                
                messagebox.showinfo("تم الحفظ", "تم تحديث أسماء الفصول بنجاح.")
                self.update_all_tabs_after_data_change()

            except Exception as e:
                messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ أسماء الفصول:\n{e}")
        else:
            messagebox.showinfo("لا توجد تغييرات", "لم يتم إجراء أي تغييرات على أسماء الفصول.")


    # ══════════════════════════════════════════════════════════
    # تبويب التأخر
    # ══════════════════════════════════════════════════════════
    def _build_tardiness_tab(self):
        frame = self.tardiness_frame

        # شريط التحكم
        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", pady=(8,4), padx=5)
        ttk.Label(ctrl, text="التاريخ:").pack(side="right", padx=(0,5))
        self.tard_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(ctrl, textvariable=self.tard_date_var, width=12).pack(side="right", padx=5)
        ttk.Label(ctrl, text="الفصل:").pack(side="right", padx=(10,5))
        self.tard_class_var = tk.StringVar()
        class_ids = ["(الكل)"] + [c["id"] for c in self.store["list"]]
        ttk.Combobox(ctrl, textvariable=self.tard_class_var,
                     values=class_ids, width=12, state="readonly").pack(side="right", padx=5)
        ttk.Button(ctrl, text="🔍 عرض", command=self._tard_load).pack(side="right", padx=5)
        ttk.Button(ctrl, text="➕ إضافة تأخر", command=self._tard_add_dialog).pack(side="right", padx=5)
        ttk.Button(ctrl, text="🗑️ حذف المحدد", command=self._tard_delete).pack(side="left", padx=5)

        # إحصائيات سريعة
        stats_row = ttk.Frame(frame); stats_row.pack(fill="x", padx=5, pady=4)
        self.tard_stat_lbl = ttk.Label(stats_row, text="", foreground="#1565C0",
                                        font=("Tahoma",10,"bold"))
        self.tard_stat_lbl.pack(side="right")

        # الجدول
        cols = ("id","date","class_name","student_name","student_id",
                "teacher_name","period","minutes_late")
        self.tree_tard = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for col, hdr, w in zip(cols,
            ["ID","التاريخ","الفصل","اسم الطالب","رقم الطالب","المعلم","الحصة","دقائق التأخر"],
            [40,90,160,220,110,140,60,100]):
            self.tree_tard.heading(col, text=hdr)
            self.tree_tard.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_tard.yview)
        self.tree_tard.configure(yscrollcommand=sb.set)
        self.tree_tard.pack(side="left", fill="both", expand=True, padx=(5,0))
        sb.pack(side="right", fill="y", padx=(0,5))

        # ألوان التأخر
        self.tree_tard.tag_configure("late_heavy", background="#FFEBEE", foreground="#C62828")
        self.tree_tard.tag_configure("late_mild",  background="#FFF8E1", foreground="#E65100")
        self._tard_load()

    def _tard_load(self):
        date_f  = self.tard_date_var.get().strip() if hasattr(self,"tard_date_var") else now_riyadh_date()
        cls_id  = self.tard_class_var.get() if hasattr(self,"tard_class_var") else None
        if cls_id == "(الكل)": cls_id = None
        rows = query_tardiness(date_filter=date_f or None, class_id=cls_id)
        if not hasattr(self,"tree_tard"): return
        for i in self.tree_tard.get_children(): self.tree_tard.delete(i)
        total_min = 0
        for r in rows:
            mins = r.get("minutes_late", 0)
            total_min += mins
            tag = "late_heavy" if mins >= 15 else "late_mild" if mins >= 5 else ""
            self.tree_tard.insert("", "end", tags=(tag,),
                values=(r["id"], r["date"], r["class_name"], r["student_name"],
                        r["student_id"], r.get("teacher_name",""), r.get("period",""),
                        f"{mins} دقيقة"))
        if hasattr(self,"tard_stat_lbl"):
            self.tard_stat_lbl.config(
                text=f"الإجمالي: {len(rows)} طالب متأخر | متوسط التأخر: {total_min//max(len(rows),1)} دقيقة")

    def _tard_add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("إضافة تأخر")
        win.geometry("460x420")
        win.transient(self.root); win.grab_set()

        ttk.Label(win, text="إضافة سجل تأخر", font=("Tahoma",13,"bold")).pack(pady=(16,8))

        form = ttk.Frame(win, padding=20); form.pack(fill="both", expand=True)

        def row(lbl, widget_fn):
            f = ttk.Frame(form); f.pack(fill="x", pady=4)
            ttk.Label(f, text=lbl, width=14, anchor="e").pack(side="right")
            w = widget_fn(f); w.pack(side="right", fill="x", expand=True, padx=(0,6))
            return w

        date_var = tk.StringVar(value=self.tard_date_var.get())
        row("التاريخ:", lambda p: ttk.Entry(p, textvariable=date_var))

        cls_var = tk.StringVar()
        cls_combo = row("الفصل:", lambda p: ttk.Combobox(
            p, textvariable=cls_var,
            values=[c["name"] for c in self.store["list"]],
            state="readonly"))

        stu_var = tk.StringVar()
        stu_combo = row("الطالب:", lambda p: ttk.Combobox(
            p, textvariable=stu_var, state="readonly"))

        def on_cls_change(*_):
            cls = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if cls:
                stu_combo["values"] = [f'{s["name"]} ({s["id"]})' for s in cls["students"]]
        cls_combo.bind("<<ComboboxSelected>>", on_cls_change)

        tch_var = tk.StringVar()
        teachers = load_teachers()
        tch_names = [t["اسم المعلم"] for t in teachers.get("teachers",[])]
        row("المعلم:", lambda p: ttk.Combobox(p, textvariable=tch_var,
                                               values=tch_names, state="readonly"))

        period_var = tk.StringVar(value="1")
        row("الحصة:", lambda p: ttk.Combobox(p, textvariable=period_var,
                                              values=[str(i) for i in range(1,8)],
                                              state="readonly", width=6))

        mins_var = tk.StringVar(value="10")
        mins_entry = row("دقائق التأخر:", lambda p: ttk.Entry(p, textvariable=mins_var, width=8))

        status_lbl = ttk.Label(win, text="", foreground="green")
        status_lbl.pack()

        def save():
            cls_obj = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if not cls_obj: messagebox.showwarning("تنبيه","اختر فصلاً",parent=win); return
            stu_txt = stu_var.get()
            if not stu_txt: messagebox.showwarning("تنبيه","اختر طالباً",parent=win); return
            sid   = stu_txt.split("(")[-1].rstrip(")")
            sname = stu_txt.split("(")[0].strip()
            try: mins = int(mins_var.get())
            except ValueError: mins = 0
            ok = insert_tardiness(
                date_var.get(), cls_obj["id"], cls_obj["name"],
                sid, sname, tch_var.get(),
                int(period_var.get() or 1), mins)
            if ok:
                status_lbl.config(text="✅ تم التسجيل")
                self._tard_load()
            else:
                status_lbl.config(text="⚠️ السجل موجود مسبقاً", foreground="orange")

        ttk.Button(win, text="💾 حفظ", command=save).pack(pady=10)

    def _tard_delete(self):
        sel = self.tree_tard.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد سجلاً أولاً"); return
        rid = self.tree_tard.item(sel[0])["values"][0]
        if not messagebox.askyesno("تأكيد","هل تريد حذف هذا السجل؟"): return
        delete_tardiness(rid)
        self._tard_load()

    # ══════════════════════════════════════════════════════════
    def _build_whatsapp_bot_section(self, parent_frame):
        """قسم إدارة بوت الواتساب."""

        wa_lf = ttk.LabelFrame(parent_frame, text=" 🤖 بوت واتساب الأعذار ", padding=8)
        wa_lf.pack(fill="x", padx=5, pady=(6, 6))

        # ─── صف الحالة ──────────────────────────────────────
        wa_top = ttk.Frame(wa_lf); wa_top.pack(fill="x", pady=(0, 4))
        self._wa_status_dot  = tk.Label(wa_top, text="⬤", font=("Tahoma", 14), fg="#aaaaaa")
        self._wa_status_dot.pack(side="right", padx=(0, 4))
        self._wa_status_text = ttk.Label(wa_top, text="اضغط 'فحص الحالة' للتحقق",
                                          font=("Tahoma", 10))
        self._wa_status_text.pack(side="right", padx=(0, 8))

        # ─── أزرار التشغيل والفحص ───────────────────────────
        btn_row = ttk.Frame(wa_lf); btn_row.pack(fill="x", pady=(0, 4))

        def _start_wa():
            if not os.path.isdir(WHATS_PATH):
                messagebox.showerror("خطأ", "مجلد الواتساب غير موجود:\n" + WHATS_PATH)
                return
            try:
                cmd = rf'cmd.exe /k "cd /d {WHATS_PATH} && node server.js"'
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self._wa_status_text.config(
                    text="⏳ جارٍ التشغيل... اضغط 'فحص الحالة' بعد 15 ثانية")
            except Exception as e:
                messagebox.showerror("خطأ", "تعذّر التشغيل:\n" + str(e))

        def _check_once():
            self._wa_status_text.config(text="⏳ جارٍ الفحص...")
            def do_check():
                try:
                    import urllib.request, json as _j
                    r    = urllib.request.urlopen("http://localhost:3000/status", timeout=2)
                    data = _j.loads(r.read())
                    if data.get("ready"):
                        pending = data.get("pending", 0)
                        self.root.after(0, lambda: (
                            self._wa_status_dot.config(fg="#22c55e"),
                            self._wa_status_text.config(
                                text="✅ متصل  |  طلبات معلّقة: {}".format(pending),
                                foreground="#166534")))
                    else:
                        self.root.after(0, lambda: (
                            self._wa_status_dot.config(fg="#f59e0b"),
                            self._wa_status_text.config(
                                text="⏳ يعمل لكن لم يتصل — امسح QR",
                                foreground="#92400e")))
                except Exception:
                    self.root.after(0, lambda: (
                        self._wa_status_dot.config(fg="#ef4444"),
                        self._wa_status_text.config(
                            text="🔴 الخادم غير متصل", foreground="#991b1b")))
            threading.Thread(target=do_check, daemon=True).start()

        ttk.Button(btn_row, text="▶ تشغيل خادم الواتساب",
                   command=_start_wa).pack(side="right", padx=(0, 4))
        ttk.Button(btn_row, text="🔍 فحص الحالة",
                   command=_check_once).pack(side="right", padx=(0, 4))

        # ─── حالة البوت ─────────────────────────────────────
        bot_row = ttk.Frame(wa_lf); bot_row.pack(fill="x", pady=(0, 4))
        ttk.Label(bot_row, text="حالة البوت:", font=("Tahoma", 9, "bold")).pack(side="right", padx=(0, 6))
        self._bot_toggle_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bot_row,
            text="البوت مفعّل (يرد على الأعذار تلقائياً)",
            variable=self._bot_toggle_var,
            command=lambda: _toggle_bot(self._bot_toggle_var.get())
        ).pack(side="right")

        def _toggle_bot(enabled: bool):
            def do_toggle():
                try:
                    import urllib.request as _ur
                    data = json.dumps({"enabled": enabled}).encode()
                    req = _ur.Request("http://localhost:3000/bot-toggle",
                                      data=data, headers={"Content-Type": "application/json"},
                                      method="POST")
                    _ur.urlopen(req, timeout=3)
                    status = "مفعّل ✅" if enabled else "موقوف ⏸"
                    self.root.after(0, lambda: self._wa_status_text.config(
                        text=f"البوت {status}",
                        foreground="#166634" if enabled else "#92400e"))
                except Exception:
                    pass
            threading.Thread(target=do_toggle, daemon=True).start()

        # ─── الكلمات المفتاحية ───────────────────────────────
        ttk.Separator(wa_lf, orient="horizontal").pack(fill="x", pady=(4, 6))

        kw_hdr = ttk.Frame(wa_lf); kw_hdr.pack(fill="x", pady=(0, 2))
        ttk.Label(kw_hdr, text="🔑 الكلمات المفتاحية للأعذار:",
                  font=("Tahoma", 9, "bold")).pack(side="right")
        ttk.Button(kw_hdr, text="💾 حفظ الكلمات",
                   command=lambda: _save_keywords()).pack(side="left", padx=(0, 4))
        ttk.Button(kw_hdr, text="🔄 تحميل من الخادم",
                   command=lambda: _load_keywords()).pack(side="left")

        ttk.Label(wa_lf,
            text="أدخل الكلمات مفصولة بفاصلة — مثال: عذر، مريض، سفر، ok",
            font=("Tahoma", 8), foreground="#666").pack(anchor="e", pady=(0, 2))

        self._kw_text = tk.Text(wa_lf, height=3, font=("Tahoma", 10),
                                 wrap="word", relief="solid", bd=1)
        self._kw_text.pack(fill="x", pady=(0, 4))
        self._kw_text.insert("1.0",
            "عذر، معذور، مريض، مرض، علاج، مستشفى، وفاة، سفر، ظروف، إجازة، اجازة، excuse، ok، اوك، نعم، موافق، 1")

        def _load_keywords():
            try:
                import urllib.request as _ur, json as _j
                r = _ur.urlopen("http://localhost:3000/bot-config", timeout=1)
                cfg = _j.loads(r.read())
                kws = cfg.get("keywords", [])
                enabled = cfg.get("bot_enabled", True)
                self._kw_text.delete("1.0", "end")
                self._kw_text.insert("1.0", "، ".join(kws))
                self._bot_toggle_var.set(enabled)
            except Exception:
                pass

        def _save_keywords():
            raw = self._kw_text.get("1.0", "end").strip()
            import re as _re
            kws = [k.strip() for k in _re.split(r'[،,،\n]+', raw) if k.strip()]
            if not kws:
                messagebox.showerror("خطأ", "لا توجد كلمات للحفظ!")
                return
            try:
                import urllib.request as _ur, json as _j
                data = json.dumps({"keywords": kws}, ensure_ascii=False).encode("utf-8")
                req = _ur.Request("http://localhost:3000/bot-keywords",
                                  data=data, headers={"Content-Type": "application/json"},
                                  method="POST")
                resp = _ur.urlopen(req, timeout=3)
                result = _j.loads(resp.read())
                if result.get("ok"):
                    messagebox.showinfo("تم", f"تم حفظ {len(kws)} كلمة مفتاحية بنجاح.")
                    _load_keywords()
            except Exception as e:
                messagebox.showerror("خطأ", "تعذّر حفظ الكلمات.\nتأكد من تشغيل الخادم أولاً.\n" + str(e))

        parent_frame.after(600, _load_keywords)


    # ═══════════════════════════════════════════════════════════════
    # تبويب إدارة الواتساب
    # ═══════════════════════════════════════════════════════════════
    def _build_whatsapp_manager_tab(self):
        frame = self.whatsapp_manager_frame
        frame.config(bg="white")

        hdr = tk.Frame(frame, bg="#1565C0", height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="📱  إدارة الواتساب", bg="#1565C0", fg="white",
                 font=("Tahoma", 14, "bold")).pack(side="right", padx=16, pady=10)

        scroll_canvas = tk.Canvas(frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(scroll_canvas, bg="white")
        inner_win = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        # inner فقط يُحدّث scrollregion — canvas فقط يُحدّث العرض (بلا حلقة)
        def _on_inner_conf(e):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_conf)
        _wm_last_w = [0]
        def _on_canvas_conf(e):
            w = scroll_canvas.winfo_width()
            if w == _wm_last_w[0]: return
            _wm_last_w[0] = w
            scroll_canvas.itemconfig(inner_win, width=w)
        scroll_canvas.bind("<Configure>", _on_canvas_conf)

        PAD = dict(padx=18, pady=8)

        def _card(parent, title, color="#1565C0"):
            lf = tk.LabelFrame(parent, text="  {}  ".format(title),
                               font=("Tahoma", 10, "bold"),
                               fg=color, bg="white",
                               relief="groove", bd=2)
            lf.pack(fill="x", **PAD)
            return lf

        # ── بطاقة 1: خادم الواتساب ──────────────────────────────
        srv_card = _card(inner, "🖥️  خادم الواتساب", "#1565C0")

        status_row = tk.Frame(srv_card, bg="white")
        status_row.pack(fill="x", padx=10, pady=(8, 4))
        self._wm_dot = tk.Label(status_row, text="⬤", font=("Tahoma", 16),
                                 fg="#aaaaaa", bg="white")
        self._wm_dot.pack(side="right", padx=(0, 6))
        self._wm_lbl = tk.Label(status_row,
                                 text="اضغط فحص الحالة للتحقق من الاتصال",
                                 font=("Tahoma", 10), bg="white", fg="#555555")
        self._wm_lbl.pack(side="right")

        btn_row = tk.Frame(srv_card, bg="white")
        btn_row.pack(fill="x", padx=10, pady=(2, 10))

        def _wm_start():
            if not os.path.isdir(WHATS_PATH):
                messagebox.showerror("خطأ", "مجلد الواتساب غير موجود:\n" + WHATS_PATH)
                return
            try:
                cmd = r'cmd.exe /k "cd /d ' + WHATS_PATH + r' && node server.js"'
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self._wm_lbl.config(
                    text="⏳ جارٍ التشغيل... اضغط فحص الحالة بعد 15 ثانية",
                    fg="#92400e")
                self._wm_dot.config(fg="#f59e0b")
            except Exception as ex:
                messagebox.showerror("خطأ", "تعذّر التشغيل:\n" + str(ex))

        def _wm_check():
            self._wm_lbl.config(text="⏳ جارٍ الفحص...", fg="#555555")
            self._wm_dot.config(fg="#aaaaaa")
            def do_check():
                try:
                    import urllib.request as _ur, json as _j
                    servers = get_wa_servers()
                    results = []
                    for srv in servers:
                        port = srv.get("port", 3000)
                        try:
                            r = _ur.urlopen("http://localhost:{}/status".format(port), timeout=2)
                            data = _j.loads(r.read())
                            results.append((port, data.get("ready", False), data.get("pending", 0)))
                        except Exception:
                            results.append((port, False, 0))
                    ready_count = sum(1 for _, r, _ in results if r)
                    total = len(results)
                    if ready_count == total and total > 0:
                        self.root.after(0, lambda: (
                            self._wm_dot.config(fg="#22c55e"),
                            self._wm_lbl.config(
                                text="✅ متصل ({}/{} خادم)  |  معلّقة: {}".format(
                                    ready_count, total, sum(p for _, _, p in results)),
                                fg="#166534")))
                    elif ready_count > 0:
                        self.root.after(0, lambda: (
                            self._wm_dot.config(fg="#f59e0b"),
                            self._wm_lbl.config(
                                text="⚠️ متصل جزئياً ({}/{})".format(ready_count, total),
                                fg="#92400e")))
                    else:
                        self.root.after(0, lambda: (
                            self._wm_dot.config(fg="#ef4444"),
                            self._wm_lbl.config(
                                text="🔴 الخادم غير متصل — امسح QR أو شغّل الخادم",
                                fg="#991b1b")))
                except Exception:
                    self.root.after(0, lambda: (
                        self._wm_dot.config(fg="#ef4444"),
                        self._wm_lbl.config(text="🔴 الخادم غير متصل", fg="#991b1b")))
            threading.Thread(target=do_check, daemon=True).start()

        tk.Button(btn_row, text="▶  تشغيل الخادم",
                  bg="#1565C0", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=14, pady=6,
                  command=_wm_start).pack(side="right", padx=(0, 8))
        tk.Button(btn_row, text="🔍  فحص الحالة",
                  bg="#0d47a1", fg="white", font=("Tahoma", 10),
                  relief="flat", cursor="hand2", padx=14, pady=6,
                  command=_wm_check).pack(side="right", padx=(0, 4))

        # ── بطاقة 2: بوت الغياب ─────────────────────────────────
        abs_card = _card(inner, "📋  بوت رسائل الغياب", "#7c3aed")
        tk.Label(abs_card,
                 text="عند تسجيل غياب طالب يُرسل تلقائياً رسالة واتساب لولي أمره.",
                 font=("Tahoma", 9), bg="white", fg="#6b7280").pack(anchor="e", padx=10, pady=(6, 2))
        abs_row = tk.Frame(abs_card, bg="white")
        abs_row.pack(fill="x", padx=10, pady=(0, 10))
        self._wm_abs_lbl = tk.Label(abs_row, text="", font=("Tahoma", 10, "bold"), bg="white")
        self._wm_abs_lbl.pack(side="right", padx=(0, 14))

        def _set_absence_bot(enabled):
            cfg = load_config()
            cfg["absence_bot_enabled"] = enabled
            save_config(cfg)
            invalidate_config_cache()
            if enabled:
                self._wm_abs_lbl.config(text="✅  البوت مفعّل", fg="#166534")
                self._wm_abs_on.config(relief="sunken", bg="#bbf7d0")
                self._wm_abs_off.config(relief="flat", bg="#f3f4f6")
            else:
                self._wm_abs_lbl.config(text="⏸  البوت موقوف", fg="#991b1b")
                self._wm_abs_on.config(relief="flat", bg="#f3f4f6")
                self._wm_abs_off.config(relief="sunken", bg="#fecaca")
        self._set_absence_bot = _set_absence_bot

        self._wm_abs_off = tk.Button(abs_row, text="⏸  إيقاف",
            font=("Tahoma", 10), relief="flat", cursor="hand2",
            padx=12, pady=5, bg="#f3f4f6",
            command=lambda: _set_absence_bot(False))
        self._wm_abs_off.pack(side="left", padx=(0, 4))
        self._wm_abs_on = tk.Button(abs_row, text="▶  تشغيل",
            font=("Tahoma", 10, "bold"), relief="flat", cursor="hand2",
            padx=12, pady=5, bg="#f3f4f6",
            command=lambda: _set_absence_bot(True))
        self._wm_abs_on.pack(side="left")

        # ── بطاقة 3: بوت الاستئذان ──────────────────────────────
        perm_card = _card(inner, "🚪  بوت رسائل الاستئذان", "#0891b2")
        tk.Label(perm_card,
                 text="عند طلب استئذان طالب يُرسل تلقائياً رسالة لولي أمره لأخذ الموافقة.",
                 font=("Tahoma", 9), bg="white", fg="#6b7280").pack(anchor="e", padx=10, pady=(6, 2))
        perm_row = tk.Frame(perm_card, bg="white")
        perm_row.pack(fill="x", padx=10, pady=(0, 10))
        self._wm_perm_lbl = tk.Label(perm_row, text="", font=("Tahoma", 10, "bold"), bg="white")
        self._wm_perm_lbl.pack(side="right", padx=(0, 14))

        def _set_permission_bot(enabled):
            cfg = load_config()
            cfg["permission_bot_enabled"] = enabled
            save_config(cfg)
            invalidate_config_cache()
            if enabled:
                self._wm_perm_lbl.config(text="✅  البوت مفعّل", fg="#166534")
                self._wm_perm_on.config(relief="sunken", bg="#bbf7d0")
                self._wm_perm_off.config(relief="flat", bg="#f3f4f6")
            else:
                self._wm_perm_lbl.config(text="⏸  البوت موقوف", fg="#991b1b")
                self._wm_perm_on.config(relief="flat", bg="#f3f4f6")
                self._wm_perm_off.config(relief="sunken", bg="#fecaca")
        self._set_permission_bot = _set_permission_bot

        self._wm_perm_off = tk.Button(perm_row, text="⏸  إيقاف",
            font=("Tahoma", 10), relief="flat", cursor="hand2",
            padx=12, pady=5, bg="#f3f4f6",
            command=lambda: _set_permission_bot(False))
        self._wm_perm_off.pack(side="left", padx=(0, 4))
        self._wm_perm_on = tk.Button(perm_row, text="▶  تشغيل",
            font=("Tahoma", 10, "bold"), relief="flat", cursor="hand2",
            padx=12, pady=5, bg="#f3f4f6",
            command=lambda: _set_permission_bot(True))
        self._wm_perm_on.pack(side="left")

        # ── بطاقة 4: بوت ردود الأعذار ───────────────────────────
        exc_card = _card(inner, "💬  بوت ردود الأعذار", "#059669")
        tk.Label(exc_card,
                 text="يرد تلقائياً على أولياء الأمور ويقبل الأعذار عبر واتساب.",
                 font=("Tahoma", 9), bg="white", fg="#6b7280").pack(anchor="e", padx=10, pady=(6, 2))
        exc_row = tk.Frame(exc_card, bg="white")
        exc_row.pack(fill="x", padx=10, pady=(0, 10))
        self._wm_exc_lbl = tk.Label(exc_row, text="", font=("Tahoma", 10, "bold"), bg="white")
        self._wm_exc_lbl.pack(side="right", padx=(0, 14))

        def _set_excuse_bot(enabled):
            try:
                import urllib.request as _ur, json as _j
                data = _j.dumps({"enabled": enabled}).encode()
                req = _ur.Request("http://localhost:3000/bot-toggle",
                                  data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
                _ur.urlopen(req, timeout=3)
            except Exception:
                pass
            if enabled:
                self._wm_exc_lbl.config(text="✅  البوت مفعّل", fg="#166534")
                self._wm_exc_on.config(relief="sunken", bg="#bbf7d0")
                self._wm_exc_off.config(relief="flat", bg="#f3f4f6")
            else:
                self._wm_exc_lbl.config(text="⏸  البوت موقوف", fg="#991b1b")
                self._wm_exc_on.config(relief="flat", bg="#f3f4f6")
                self._wm_exc_off.config(relief="sunken", bg="#fecaca")
        self._set_excuse_bot = _set_excuse_bot

        self._wm_exc_off = tk.Button(exc_row, text="⏸  إيقاف",
            font=("Tahoma", 10), relief="flat", cursor="hand2",
            padx=12, pady=5, bg="#f3f4f6",
            command=lambda: _set_excuse_bot(False))
        self._wm_exc_off.pack(side="left", padx=(0, 4))
        self._wm_exc_on = tk.Button(exc_row, text="▶  تشغيل",
            font=("Tahoma", 10, "bold"), relief="flat", cursor="hand2",
            padx=12, pady=5, bg="#f3f4f6",
            command=lambda: _set_excuse_bot(True))
        self._wm_exc_on.pack(side="left")

        tk.Frame(inner, bg="white", height=20).pack()

        def _load_initial():
            cfg = load_config()
            _set_absence_bot(cfg.get("absence_bot_enabled", True))
            _set_permission_bot(cfg.get("permission_bot_enabled", True))
            def do_fetch():
                try:
                    import urllib.request as _ur, json as _j
                    r = _ur.urlopen("http://localhost:3000/bot-config", timeout=1)
                    d = _j.loads(r.read())
                    self.root.after(0, lambda: _set_excuse_bot(d.get("bot_enabled", True)))
                except Exception:
                    self.root.after(0, lambda: _set_excuse_bot(True))
            threading.Thread(target=do_fetch, daemon=True).start()

        frame.after(400, _load_initial)

    def _build_excuses_tab(self):
        frame = self.excuses_frame

        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", pady=(8,4), padx=5)
        ttk.Label(ctrl, text="التاريخ:").pack(side="right", padx=(0,5))
        self.exc_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(ctrl, textvariable=self.exc_date_var, width=12).pack(side="right", padx=5)
        ttk.Button(ctrl, text="🔍 عرض", command=self._exc_load).pack(side="right", padx=5)
        ttk.Button(ctrl, text="➕ إضافة عذر", command=self._exc_add_dialog).pack(side="right", padx=5)
        ttk.Button(ctrl, text="🗑️ حذف", command=self._exc_delete).pack(side="left", padx=5)

        # شرح
        ttk.Label(frame,
            text="ملاحظة: الطلاب الذين لديهم عذر مقبول سيظهر غيابهم بلون مختلف في التقارير.",
            foreground="#5A6A7E", font=("Tahoma",9)).pack(anchor="e", padx=5)

        # ─── إطار الجدول (منفصل حتى لا يتعارض fill مع قسم البوت) ─
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(2, 2))

        cols = ("id","date","student_name","student_id","class_name","reason","source","approved_by")
        self.tree_excuses = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10)
        for col, hdr, w in zip(cols,
            ["ID","التاريخ","اسم الطالب","رقم الطالب","الفصل","سبب العذر","المصدر","الموافق"],
            [40,90,220,110,160,160,80,120]):
            self.tree_excuses.heading(col, text=hdr)
            self.tree_excuses.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_excuses.yview)
        self.tree_excuses.configure(yscrollcommand=sb.set)
        self.tree_excuses.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree_excuses.tag_configure("wa_excuse", background="#E8F5E9", foreground="#2E7D32")
        self.tree_excuses.tag_configure("admin_excuse", background="#E3F2FD", foreground="#1565C0")
        frame.after(100, self._exc_load)

        # ─── قسم بوت الواتساب ────────────────────────────────
        self._build_whatsapp_bot_section(frame)

    def _exc_load(self):
        date_f = self.exc_date_var.get().strip() if hasattr(self,"exc_date_var") else now_riyadh_date()
        rows   = query_excuses(date_filter=date_f or None)
        if not hasattr(self,"tree_excuses"): return
        for i in self.tree_excuses.get_children(): self.tree_excuses.delete(i)
        for r in rows:
            tag = "wa_excuse" if r.get("source")=="whatsapp" else "admin_excuse"
            self.tree_excuses.insert("", "end", tags=(tag,),
                values=(r["id"], r["date"], r["student_name"], r["student_id"],
                        r["class_name"], r["reason"],
                        "واتساب" if r.get("source")=="whatsapp" else "إداري",
                        r.get("approved_by","")))

    def _exc_add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("إضافة عذر غياب")
        win.geometry("500x420")
        win.transient(self.root); win.grab_set()

        ttk.Label(win, text="إضافة عذر لطالب", font=("Tahoma",13,"bold")).pack(pady=(16,8))
        form = ttk.Frame(win, padding=20); form.pack(fill="both", expand=True)

        def row(lbl, widget_fn):
            f = ttk.Frame(form); f.pack(fill="x", pady=5)
            ttk.Label(f, text=lbl, width=14, anchor="e").pack(side="right")
            w = widget_fn(f); w.pack(side="right", fill="x", expand=True, padx=(0,6))
            return w

        date_var = tk.StringVar(value=self.exc_date_var.get())
        row("التاريخ:", lambda p: ttk.Entry(p, textvariable=date_var))

        cls_var = tk.StringVar()
        cls_combo = row("الفصل:", lambda p: ttk.Combobox(
            p, textvariable=cls_var,
            values=[c["name"] for c in self.store["list"]],
            state="readonly"))

        stu_var = tk.StringVar()
        stu_combo = row("الطالب:", lambda p: ttk.Combobox(
            p, textvariable=stu_var, state="readonly"))

        def on_cls(*_):
            cls = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if cls:
                stu_combo["values"] = [f'{s["name"]} ({s["id"]})' for s in cls["students"]]
        cls_combo.bind("<<ComboboxSelected>>", on_cls)

        reason_var = tk.StringVar(value=EXCUSE_REASONS[0])
        row("سبب العذر:", lambda p: ttk.Combobox(
            p, textvariable=reason_var, values=EXCUSE_REASONS, state="readonly"))

        approved_var = tk.StringVar(value=CURRENT_USER.get("name","المدير"))
        row("الموافق:", lambda p: ttk.Entry(p, textvariable=approved_var))

        status_lbl = ttk.Label(win, text=""); status_lbl.pack()

        def save():
            cls_obj = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if not cls_obj: messagebox.showwarning("تنبيه","اختر فصلاً",parent=win); return
            stu_txt = stu_var.get()
            if not stu_txt: messagebox.showwarning("تنبيه","اختر طالباً",parent=win); return
            sid   = stu_txt.split("(")[-1].rstrip(")")
            sname = stu_txt.split("(")[0].strip()
            insert_excuse(date_var.get(), sid, sname,
                          cls_obj["id"], cls_obj["name"],
                          reason_var.get(), "admin", approved_var.get())
            status_lbl.config(text="✅ تم حفظ العذر", foreground="green")
            self._exc_load()

        ttk.Button(win, text="💾 حفظ العذر", command=save).pack(pady=10)

    def _exc_delete(self):
        sel = self.tree_excuses.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد سجلاً"); return
        rid = self.tree_excuses.item(sel[0])["values"][0]
        if not messagebox.askyesno("تأكيد","حذف هذا العذر؟"): return
        delete_excuse(rid); self._exc_load()

    # ══════════════════════════════════════════════════════════
    # تبويب المستخدمين (للمدير فقط)
    # ══════════════════════════════════════════════════════════
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
            "الموجّه الطلابي",
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

        def _on_tabs_inner_conf(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        self._tabs_inner.bind("<Configure>", _on_tabs_inner_conf)
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
        self._users_load()
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
                win.destroy()
                self._users_load()
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
        self._users_load()

    def _user_delete(self):
        sel = self.tree_users.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد مستخدماً"); return
        vals    = self.tree_users.item(sel[0])["values"]
        user_id, username = vals[0], vals[1]
        if username == "admin":
            messagebox.showwarning("تنبيه","لا يمكن حذف حساب المدير الرئيسي"); return
        if not messagebox.askyesno("تأكيد",f"حذف المستخدم '{username}'؟"): return
        delete_user(user_id); self._users_load()

    # ══════════════════════════════════════════════════════════
    # تبويب النسخ الاحتياطية
    # ══════════════════════════════════════════════════════════
    def _build_school_settings_tab(self):
        """تبويب إعدادات المدرسة — تعديل بيانات المدرسة والإدارة."""
        frame = self.school_settings_frame

        # عنوان
        hdr = tk.Frame(frame, bg="#1565C0", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="\U0001f3eb إعدادات المدرسة",
                 bg="#1565C0", fg="white",
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=16, pady=12)

        # ── إطار تمرير للمحتوى ──────────────────────────────────
        _canvas = tk.Canvas(frame, highlightthickness=0)
        _vsb = ttk.Scrollbar(frame, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="left", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Frame(_canvas)
        _canvas_win = _canvas.create_window((0, 0), window=scroll, anchor="nw")

        def _on_frame_configure(e):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        _set_last_w = [0]
        def _on_canvas_configure(e):
            w = _canvas.winfo_width()
            if w == _set_last_w[0]: return
            _set_last_w[0] = w
            _canvas.itemconfig(_canvas_win, width=w)
        scroll.bind("<Configure>", _on_frame_configure)
        _canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e):
            _canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        def _ss_bind_mw(e=None):  _canvas.bind("<MouseWheel>", _on_mousewheel)
        def _ss_unbind_mw(e=None): _canvas.unbind("<MouseWheel>")
        _canvas.bind("<Enter>", _ss_bind_mw)
        _canvas.bind("<Leave>", _ss_unbind_mw)
        scroll.bind("<Enter>", _ss_bind_mw)
        scroll.bind("<Leave>", _ss_unbind_mw)
        # ────────────────────────────────────────────────────────

        lf = ttk.LabelFrame(scroll, text=" بيانات المدرسة والإدارة ", padding=16)
        lf.pack(fill="x", padx=20, pady=16)

        cfg = load_config()

        fields = [
            ("school_name",      "اسم المدرسة:"),
            ("assistant_title",  "لقب الوكيل:"),
            ("assistant_name",   "اسم الوكيل:"),
            ("principal_title",  "لقب المدير:"),
            ("principal_name",   "اسم المدير:"),
        ]

        self._school_vars = {}
        for key, label in fields:
            row = ttk.Frame(lf); row.pack(fill="x", pady=6)
            ttk.Label(row, text=label, width=16, anchor="e",
                      font=("Tahoma", 10, "bold")).pack(side="right", padx=(0, 8))
            var = tk.StringVar(value=cfg.get(key, ""))
            ttk.Entry(row, textvariable=var, width=40,
                      font=("Tahoma", 10), justify="right").pack(side="right", fill="x", expand=True)
            self._school_vars[key] = var

        # ── قسم أرقام الجوال ─────────────────────────────────────
        ttk.Separator(lf, orient="horizontal").pack(fill="x", pady=(10, 8))

        phones_hdr = tk.Frame(lf, bg="#7c3aed", pady=5)
        phones_hdr.pack(fill="x", pady=(0, 8))
        tk.Label(phones_hdr, text="📱 أرقام الجوال — للإرسال والإشعارات",
                 bg="#7c3aed", fg="white",
                 font=("Tahoma", 10, "bold")).pack(side="right", padx=12)

        # ── حقلا اسم الموجّهَين ──────────────────────────────────
        counselor_names_hdr = tk.Frame(lf, bg="#5b21b6", pady=4)
        counselor_names_hdr.pack(fill="x", pady=(4, 6))
        tk.Label(counselor_names_hdr, text="👨‍🏫 أسماء الموجّهَين الطلابيّين",
                 bg="#5b21b6", fg="white",
                 font=("Tahoma", 10, "bold")).pack(side="right", padx=12)

        for cn_key, cn_label in [("counselor1_name", "اسم الموجّه الطلابي 1:"),
                                   ("counselor2_name", "اسم الموجّه الطلابي 2:")]:
            cn_row = ttk.Frame(lf); cn_row.pack(fill="x", pady=4)
            ttk.Label(cn_row, text=cn_label, width=20, anchor="e",
                      font=("Tahoma", 10, "bold")).pack(side="right", padx=(0, 8))
            cn_var = tk.StringVar(value=cfg.get(cn_key, ""))
            ttk.Entry(cn_row, textvariable=cn_var, width=35,
                      font=("Tahoma", 10), justify="right").pack(side="right", fill="x", expand=True)
            self._school_vars[cn_key] = cn_var

        ttk.Separator(lf, orient="horizontal").pack(fill="x", pady=(6, 8))

        phone_fields = [
            ("principal_phone",  "📞 جوال مدير المدرسة:",       "#1d4ed8",
             "يُستخدم لإرسال الجلسات الإرشادية والتقارير اليومية"),
            ("alert_admin_phone","📞 جوال وكيل المدرسة:",        "#0369a1",
             "يُستخدم لإرسال الجلسات الإرشادية وتنبيهات الغياب"),
            ("counselor1_phone", "📞 جوال الموجّه الطلابي 1:",   "#7c3aed",
             "يستقبل تنبيهات التحويل من الوكيل وإرسال الجلسات الإرشادية"),
            ("counselor2_phone", "📞 جوال الموجّه الطلابي 2:",   "#6d28d9",
             "يستقبل تنبيهات التحويل من الوكيل وإرسال الجلسات الإرشادية"),
        ]

        for key, label, color, hint in phone_fields:
            ph_row = tk.Frame(lf, bg="white", relief="groove", bd=1)
            ph_row.pack(fill="x", pady=4, ipady=4)

            # الصف العلوي: الليبل + حقل الإدخال
            top = tk.Frame(ph_row, bg="white"); top.pack(fill="x", padx=8, pady=(4,0))
            tk.Label(top, text=label, bg="white", fg=color,
                     font=("Tahoma", 10, "bold"), width=20, anchor="e").pack(side="right")
            var = tk.StringVar(value=cfg.get(key, ""))
            ent = tk.Entry(top, textvariable=var, width=22,
                           font=("Tahoma", 11), justify="center",
                           relief="solid", bd=1, fg="#1a1a1a")
            ent.pack(side="right", padx=8)

            # زر اختبار الإرسال
            def _test_send(v=var, lbl=label):
                phone = v.get().strip()
                if not phone:
                    messagebox.showwarning("تنبيه", f"أدخل رقم {lbl} أولاً", parent=frame)
                    return
                ok, res = send_whatsapp_message(phone,
                    f"✅ رسالة اختبار من نظام درب\nتم التحقق من رقم {lbl} بنجاح.")
                if ok:
                    messagebox.showinfo("✅ نجح الاختبار", f"تم إرسال رسالة اختبار لـ {lbl}", parent=frame)
                else:
                    messagebox.showerror("فشل", f"فشل الإرسال:\n{res}", parent=frame)

            tk.Button(top, text="🧪 اختبار", command=_test_send,
                      bg=color, fg="white", font=("Tahoma", 9, "bold"),
                      relief="flat", padx=8, pady=2, cursor="hand2").pack(side="right", padx=4)

            # التلميح
            tk.Label(ph_row, text=hint, bg="white", fg="#6b7280",
                     font=("Tahoma", 8), anchor="e").pack(fill="x", padx=12, pady=(0,4))

            self._school_vars[key] = var

        tk.Label(lf,
                 text="⚠️  أدخل الرقم بصيغة دولية بدون + مثل: 966501234567",
                 bg="#fffbeb", fg="#92400e",
                 font=("Tahoma", 8), relief="flat", pady=4, padx=8,
                 anchor="e").pack(fill="x", pady=(4, 2))

        # ── خيار جنس المدرسة ────────────────────────────────────
        gender_row = ttk.Frame(lf); gender_row.pack(fill="x", pady=6)
        ttk.Label(gender_row, text="نوع المدرسة:", width=16, anchor="e",
                  font=("Tahoma", 10, "bold")).pack(side="right", padx=(0, 8))
        self._gender_var = tk.StringVar(value=cfg.get("school_gender", "boys"))
        gender_frame = ttk.Frame(gender_row); gender_frame.pack(side="right")

        # أزرار اختيار النوع بدون emoji لتجنب مشاكل Windows
        btn_boys  = tk.Button(gender_frame, text="بنين",
                              font=("Tahoma", 10, "bold"), relief="raised",
                              cursor="hand2", width=8, bd=2)
        btn_girls = tk.Button(gender_frame, text="بنات",
                              font=("Tahoma", 10, "bold"), relief="raised",
                              cursor="hand2", width=8, bd=2)

        def _update_gender_style(*_):
            g = self._gender_var.get()
            if g == "boys":
                btn_boys.config( bg="#1565C0", fg="white",  relief="sunken")
                btn_girls.config(bg="#F1F5F9", fg="#555555", relief="raised")
            else:
                btn_boys.config( bg="#F1F5F9", fg="#555555", relief="raised")
                btn_girls.config(bg="#7C3AED", fg="white",  relief="sunken")

        btn_boys.config( command=lambda: [self._gender_var.set("boys"),  _update_gender_style()])
        btn_girls.config(command=lambda: [self._gender_var.set("girls"), _update_gender_style()])
        btn_boys.pack(side="right", padx=4)
        btn_girls.pack(side="right", padx=4)
        self._school_vars["school_gender"] = self._gender_var
        _update_gender_style()

        ttk.Separator(lf, orient="horizontal").pack(fill="x", pady=(12, 8))

        btn_row = ttk.Frame(lf); btn_row.pack(fill="x")
        self._school_status = ttk.Label(btn_row, text="", foreground="green",
                                         font=("Tahoma", 10))
        self._school_status.pack(side="right", padx=12)

        def _save():
            cfg = load_config()
            for key, var in self._school_vars.items():
                v = var.get().strip() if key != "school_gender" else var.get()
                cfg[key] = v
            try:
                with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                invalidate_config_cache()
                gender_lbl = "بنات" if cfg.get("school_gender") == "girls" else "بنين"
                self._school_status.config(
                    text=f"✅ تم الحفظ — النوع: {gender_lbl}", foreground="green")
                frame.after(3000, lambda: self._school_status.config(text=""))
                # تحديث عنوان النافذة فوراً ليعكس النوع الجديد
                _role_label = CURRENT_USER.get("label", "")
                _user_name  = CURRENT_USER.get("name", CURRENT_USER.get("username", ""))
                self.root.title(f"{get_window_title()} — {_user_name} ({_role_label})")
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل الحفظ:\n{e}")

        def _reset():
            cfg = load_config()
            for key, var in self._school_vars.items():
                var.set(cfg.get(key, ""))
            self._school_status.config(text="تم إعادة التحميل", foreground="#555")
            frame.after(2000, lambda: self._school_status.config(text=""))

        ttk.Button(btn_row, text="💾 حفظ التغييرات", command=_save).pack(side="right", padx=4)
        ttk.Button(btn_row, text="🔄 إعادة تحميل", command=_reset).pack(side="right", padx=4)

        # ─ قسم أرقام واتساب المتعددة
        wa_lf = ttk.LabelFrame(frame,
            text=" 📱 خوادم واتساب المتعددة (لتوزيع الإرسال وتجنب الحجب) ",
            padding=12)
        wa_lf.pack(fill="x", padx=8, pady=(0,10))

        ttk.Label(wa_lf,
            text="أضف خادم واتساب لكل رقم — الرسائل تُوزَّع تلقائياً بالتناوب",
            foreground="#5A6A7E", font=("Tahoma",8)).pack(anchor="e", pady=(0,8))

        # جدول الخوادم
        wa_cols = ("port", "note")
        self._tree_wa_servers = ttk.Treeview(
            wa_lf, columns=wa_cols, show="headings", height=4)
        self._tree_wa_servers.heading("port", text="المنفذ (Port)")
        self._tree_wa_servers.heading("note", text="ملاحظة")
        self._tree_wa_servers.column("port", width=100, anchor="center")
        self._tree_wa_servers.column("note", width=250, anchor="center")
        self._tree_wa_servers.pack(fill="x", pady=(0,6))

        # أزرار
        wa_btn = ttk.Frame(wa_lf); wa_btn.pack(fill="x")
        port_var = tk.IntVar(value=3001)
        note_var = tk.StringVar(value="رقم 2")
        ttk.Label(wa_btn, text="المنفذ:").pack(side="right", padx=(0,4))
        ttk.Spinbox(wa_btn, from_=3000, to=3010,
                    textvariable=port_var, width=6).pack(side="right", padx=4)
        ttk.Label(wa_btn, text="ملاحظة:").pack(side="right", padx=(8,4))
        ttk.Entry(wa_btn, textvariable=note_var, width=14).pack(side="right", padx=4)
        ttk.Button(wa_btn, text="➕ إضافة",
                   command=lambda: self._wa_server_add(
                       port_var.get(), note_var.get())).pack(side="right", padx=4)
        ttk.Button(wa_btn, text="🗑️ حذف المحدد",
                   command=self._wa_server_del).pack(side="left", padx=4)

        ttk.Label(wa_lf,
            text="⚠️ المنفذ 3000 هو الافتراضي — أضف المنافذ الإضافية فقط (3001، 3002...)\n"
                 "لكل منفذ شغّل نسخة منفصلة من server.js على جهاز مختلف أو نفس الجهاز",
            foreground="#E65100", font=("Tahoma",8),
            justify="right").pack(anchor="e", pady=(8,0))

        self._wa_servers_load()

        # ─── قسم إدارة الفصل الدراسي (للمدير فقط) ───────────────
        if CURRENT_USER.get("role") == "admin":
            self._build_term_management_section(scroll)

    def _build_term_management_section(self, parent_frame):
        """قسم إنهاء الفصل الدراسي ونهاية السنة — للمدير فقط."""

        sep = ttk.Separator(parent_frame, orient="horizontal")
        sep.pack(fill="x", padx=20, pady=(0, 8))

        lf = ttk.LabelFrame(parent_frame,
                             text=" 🔐 إدارة الفصل الدراسي — للمدير فقط ",
                             padding=16)
        lf.pack(fill="x", padx=20, pady=(0, 16))

        # تحذير
        warn = tk.Label(lf,
            text="⚠️  هذه الإجراءات لا يمكن التراجع عنها. ستُنشأ نسخة احتياطية تلقائياً قبل كل إجراء.",
            bg="#fff8e1", fg="#7c4a00", font=("Tahoma", 9),
            wraplength=700, justify="right", pady=6, padx=10, relief="flat")
        warn.pack(fill="x", pady=(0, 12))

        # ── الزر 1: نهاية الفصل الدراسي ──
        term_lf = ttk.LabelFrame(lf, text=" نهاية الفصل الدراسي ", padding=10)
        term_lf.pack(fill="x", pady=(0, 10))

        tk.Label(term_lf,
            text="يحذف جميع سجلات الغياب والتأخر ويبقي الطلاب والإعدادات والجداول كما هي.",
            font=("Tahoma", 9), fg="#555", wraplength=650, justify="right"
        ).pack(anchor="e", pady=(0, 8))

        ttk.Button(term_lf, text="📋 إنهاء الفصل الدراسي",
                   command=self._end_semester).pack(side="right")

        # ── الزر 2: نهاية السنة الدراسية ──
        year_lf = ttk.LabelFrame(lf, text=" نهاية السنة الدراسية ", padding=10)
        year_lf.pack(fill="x", pady=(0, 10))

        tk.Label(year_lf,
            text="يُرقّي الطلاب: أول→ثاني، ثاني→ثالث، ثالث يُحذفون. ثم يحذف الغياب والتأخر.",
            font=("Tahoma", 9), fg="#555", wraplength=650, justify="right"
        ).pack(anchor="e", pady=(0, 8))

        ttk.Button(year_lf, text="🎓 إنهاء السنة الدراسية وترقية الطلاب",
                   command=self._end_academic_year).pack(side="right")

        # ── النسخ الاحتياطية الخاصة بالفصول ──
        backup_lf = ttk.LabelFrame(lf, text=" 💾 نسخ احتياطية الفصول الدراسية ", padding=10)
        backup_lf.pack(fill="x", pady=(0,4))

        # أزرار في صف واحد: تحديث + فتح المجلد + استعادة
        btn_row2 = ttk.Frame(backup_lf); btn_row2.pack(fill="x", pady=(0, 4))
        ttk.Button(btn_row2, text="🔄 تحديث",
                   command=self._load_term_backups).pack(side="right", padx=4)
        ttk.Button(btn_row2, text="📂 فتح المجلد",
                   command=lambda: (
                       os.makedirs(os.path.join(BACKUP_DIR, "terms"), exist_ok=True),
                       os.startfile(os.path.join(BACKUP_DIR, "terms"))
                   )).pack(side="right", padx=4)
        tk.Button(btn_row2,
                   text="↩️ استعادة المحددة",
                   command=self._restore_term_backup,
                   bg="#c62828", fg="white",
                   font=("Tahoma", 9, "bold"),
                   relief="flat", cursor="hand2").pack(side="right", padx=4)

        # القائمة
        list_frame = ttk.Frame(backup_lf)
        list_frame.pack(fill="x")
        sb = ttk.Scrollbar(list_frame, orient="vertical")
        self._term_backup_list = tk.Listbox(list_frame, height=6,
                                             font=("Courier", 9), selectmode="single",
                                             bg="#f9f9f9",
                                             yscrollcommand=sb.set)
        sb.config(command=self._term_backup_list.yview)
        sb.pack(side="right", fill="y")
        self._term_backup_list.pack(side="left", fill="x", expand=True)

        parent_frame.after(200, self._load_term_backups)

    def _load_term_backups(self):
        """يحمّل قائمة نسخ الفصول الاحتياطية."""
        if not hasattr(self, "_term_backup_list"):
            return
        self._term_backup_list.delete(0, "end")
        terms_dir = os.path.join(BACKUP_DIR, "terms")
        if not os.path.exists(terms_dir):
            self._term_backup_list.insert("end", "(لا توجد نسخ احتياطية بعد)")
            return
        files = sorted(
            [f for f in os.listdir(terms_dir) if f.endswith(".zip")],
            reverse=True
        )
        if not files:
            self._term_backup_list.insert("end", "(لا توجد نسخ احتياطية بعد)")
            return
        for f in files:
            size = os.path.getsize(os.path.join(terms_dir, f)) // 1024
            self._term_backup_list.insert("end", f"  {f}   ({size} KB)")

    def _create_term_backup(self, label: str) -> tuple:
        """ينشئ نسخة احتياطية خاصة بالفصل/السنة."""
        terms_dir = os.path.join(BACKUP_DIR, "terms")
        os.makedirs(terms_dir, exist_ok=True)
        ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = os.path.join(terms_dir, f"{label}_{ts}.zip")
        try:
            with zipfile.ZipFile(fname, "w", zipfile.ZIP_DEFLATED) as zf:
                if os.path.exists(DB_PATH):
                    zf.write(DB_PATH, os.path.basename(DB_PATH))
                for jf in [STUDENTS_JSON, TEACHERS_JSON, CONFIG_JSON]:
                    if os.path.exists(jf):
                        zf.write(jf, os.path.basename(jf))
            return True, fname
        except Exception as e:
            return False, str(e)

    def _end_semester(self):
        """إنهاء الفصل الدراسي — حذف الغياب والتأخر فقط."""
        if CURRENT_USER.get("role") != "admin":
            messagebox.showerror("غير مسموح", "هذا الإجراء للمدير فقط.")
            return

        # تأكيد مزدوج
        if not messagebox.askyesno("تأكيد إنهاء الفصل",
            "سيتم حذف جميع سجلات الغياب والتأخر.\nستُنشأ نسخة احتياطية تلقائياً قبل الحذف.\n\nهل أنت متأكد؟", icon="warning"):
            return

        pw = simpledialog.askstring("تأكيد الهوية",
            "أدخل كلمة مرور المدير للمتابعة:", show="*")
        if not pw:
            return
        from hashlib import sha256
        if authenticate(CURRENT_USER.get("username", "admin"), pw) is None:
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return

        # نسخة احتياطية
        ok, path = self._create_term_backup("نهاية_فصل")
        if not ok:
            messagebox.showerror("خطأ", "فشل إنشاء النسخة الاحتياطية:\n" + str(path))
            return

        # حذف الغياب والتأخر
        try:
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM absences")
            cur.execute("DELETE FROM tardiness")
            try:
                cur.execute("DELETE FROM message_log")
            except Exception:
                pass
            con.commit(); con.close()

            global STUDENTS_STORE
            STUDENTS_STORE = None

            messagebox.showinfo("تم", "✅ تم إنهاء الفصل الدراسي بنجاح.\nالنسخة الاحتياطية: " + os.path.basename(path))
            self._load_term_backups()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

    def _end_academic_year(self):
        """إنهاء السنة الدراسية — ترقية الطلاب + حذف الغياب والتأخر."""
        if CURRENT_USER.get("role") != "admin":
            messagebox.showerror("غير مسموح", "هذا الإجراء للمدير فقط.")
            return

        if not messagebox.askyesno("تأكيد إنهاء السنة",
            "سيتم:\n• ترقية طلاب أول ثانوي → ثاني ثانوي\n• ترقية طلاب ثاني ثانوي → ثالث ثانوي\n• حذف طلاب ثالث ثانوي من البرنامج\n• حذف جميع سجلات الغياب والتأخر\n\nستُنشأ نسخة احتياطية تلقائياً قبل الإجراء.\n\nهل أنت متأكد؟", icon="warning"):
            return

        pw = simpledialog.askstring("تأكيد الهوية",
            "أدخل كلمة مرور المدير للمتابعة:", show="*")
        if not pw:
            return
        if authenticate(CURRENT_USER.get("username", "admin"), pw) is None:
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return

        # نسخة احتياطية
        ok, path = self._create_term_backup("نهاية_سنة")
        if not ok:
            messagebox.showerror("خطأ", "فشل إنشاء النسخة الاحتياطية:\n" + str(path))
            return

        # ── ترقية الطلاب ──
        try:
            store = load_students(force_reload=True)
            classes = store["list"]

            # خريطة الترقية: ID الفصل → المستوى والقسم
            # نفترض أن ID الفصل بصيغة "1-أ", "2-ب", "3-ج" إلخ
            upgraded = 0
            deleted  = 0
            errors   = []

            # جمّع الطلاب حسب المستوى
            level1_classes = [c for c in classes if str(c["id"]).startswith("1-")]
            level2_classes = [c for c in classes if str(c["id"]).startswith("2-")]
            level3_classes = [c for c in classes if str(c["id"]).startswith("3-")]

            # 1. احذف طلاب المستوى 3
            for cls in level3_classes:
                deleted += len(cls["students"])
                cls["students"] = []

            # 2. انقل طلاب المستوى 2 → المستوى 3
            for cls2 in level2_classes:
                suffix = str(cls2["id"])[2:]  # مثلاً "أ" من "2-أ"
                target_id = f"3-{suffix}"
                target = next((c for c in level3_classes if c["id"] == target_id), None)
                if target:
                    target["students"] = cls2["students"]
                    upgraded += len(cls2["students"])
                    cls2["students"] = []
                else:
                    errors.append(f"لم يُوجد فصل {target_id}")

            # 3. انقل طلاب المستوى 1 → المستوى 2
            for cls1 in level1_classes:
                suffix = str(cls1["id"])[2:]
                target_id = f"2-{suffix}"
                target = next((c for c in level2_classes if c["id"] == target_id), None)
                if target:
                    target["students"] = cls1["students"]
                    upgraded += len(cls1["students"])
                    cls1["students"] = []
                else:
                    errors.append(f"لم يُوجد فصل {target_id}")

            # احفظ الطلاب المُحدَّثين
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)

            global STUDENTS_STORE
            STUDENTS_STORE = None

            # احذف الغياب والتأخر
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM absences")
            cur.execute("DELETE FROM tardiness")
            try:
                cur.execute("DELETE FROM message_log")
            except Exception:
                pass
            con.commit(); con.close()

            msg = ("✅ تمت إنهاء السنة الدراسية بنجاح.\n\n"
                   f"• طلاب مُرقَّون: {upgraded}\n"
                   f"• طلاب محذوفون (ثالث): {deleted}\n"
                   f"• النسخة الاحتياطية: {os.path.basename(path)}")
            if errors:
                msg += "\n\n⚠️ تحذيرات:\n" + "\n".join(errors)
            messagebox.showinfo("تم", msg)
            self._load_term_backups()
            self.update_all_tabs_after_data_change()

        except Exception as e:
            messagebox.showerror("خطأ", f"فشل ترقية الطلاب:\n{e}")

    def _restore_term_backup(self):
        """استعادة نسخة احتياطية من نسخ الفصول."""
        if CURRENT_USER.get("role") != "admin":
            messagebox.showerror("غير مسموح", "هذا الإجراء للمدير فقط.")
            return

        sel = self._term_backup_list.curselection()
        if not sel:
            messagebox.showwarning("تنبيه", "اختر نسخة احتياطية من القائمة أولاً.")
            return

        item = self._term_backup_list.get(sel[0]).strip()
        if item.startswith("("):
            return

        fname = item.split("(")[0].strip()
        terms_dir = os.path.join(BACKUP_DIR, "terms")
        fpath = os.path.join(terms_dir, fname)

        if not os.path.exists(fpath):
            messagebox.showerror("خطأ", "الملف غير موجود.")
            return

        if not messagebox.askyesno("تأكيد الاستعادة",
            f"سيتم استبدال جميع البيانات الحالية بالنسخة:\n{fname}\n\nهل أنت متأكد؟", icon="warning"):
            return

        pw = simpledialog.askstring("تأكيد الهوية",
            "أدخل كلمة مرور المدير للمتابعة:", show="*")
        if not pw:
            return
        if authenticate(CURRENT_USER.get("username", "admin"), pw) is None:
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return

        try:
            # نسخة احتياطية من الوضع الحالي قبل الاستعادة
            self._create_term_backup("قبل_استعادة")

            with zipfile.ZipFile(fpath, "r") as zf:
                # استعد DB
                if "absences.db" in zf.namelist():
                    zf.extract("absences.db", os.path.dirname(DB_PATH))
                # استعد JSON
                for jname in ["students.json", "teachers.json", "config.json"]:
                    if jname in zf.namelist():
                        zf.extract(jname, DATA_DIR)

            global STUDENTS_STORE
            STUDENTS_STORE = None
            invalidate_config_cache()

            messagebox.showinfo("تم", f"✅ تمت الاستعادة بنجاح من:\n{fname}\n\nأعد تشغيل البرنامج لتطبيق التغييرات.")
            try:
                self.update_all_tabs_after_data_change()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الاستعادة:\n{e}")

    def _build_backup_tab(self):
        frame = self.backup_frame

        ttk.Label(frame, text="النسخ الاحتياطية",
                  font=("Tahoma",13,"bold")).pack(pady=(12,4))

        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", padx=10, pady=8)
        ttk.Button(ctrl, text="💾 نسخ احتياطي الآن",
                   command=self._do_backup).pack(side="right", padx=4)
        ttk.Button(ctrl, text="📂 فتح مجلد النسخ",
                   command=self._open_backup_dir).pack(side="right", padx=4)
        ttk.Button(ctrl, text="🗑️ حذف المحدد",
                   command=self._delete_backup).pack(side="right", padx=4)

        # معلومات المجلد
        info = ttk.LabelFrame(frame, text=" إعدادات النسخ الاحتياطية ", padding=10)
        info.pack(fill="x", padx=10, pady=4)

        r1 = ttk.Frame(info); r1.pack(fill="x", pady=3)
        ttk.Label(r1, text="مجلد الحفظ:", width=16, anchor="e").pack(side="right")
        self.backup_dir_var = tk.StringVar(value=os.path.abspath(BACKUP_DIR))
        ttk.Entry(r1, textvariable=self.backup_dir_var, state="readonly",
                  font=("Courier",9)).pack(side="right", fill="x", expand=True, padx=4)
        ttk.Button(r1, text="تغيير", width=8,
                   command=self._change_backup_dir).pack(side="left")

        r2 = ttk.Frame(info); r2.pack(fill="x", pady=3)
        ttk.Label(r2, text="النسخ كل:", width=16, anchor="e").pack(side="right")
        self.backup_interval_var = tk.StringVar(value="24")
        ttk.Spinbox(r2, from_=1, to=168, textvariable=self.backup_interval_var,
                    width=6).pack(side="right", padx=4)
        ttk.Label(r2, text="ساعة").pack(side="right")

        self.backup_status = ttk.Label(frame, text="", foreground="green",
                                        font=("Tahoma",10))
        self.backup_status.pack(pady=4)

        # سجل النسخ
        ttk.Label(frame, text="سجل النسخ السابقة:",
                  font=("Tahoma",10,"bold")).pack(anchor="e", padx=10)
        cols = ("filename","size_kb","created_at")
        self.tree_backup = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        for col, hdr, w in zip(cols,
            ["اسم الملف","الحجم (KB)","تاريخ الإنشاء"],
            [280,100,200]):
            self.tree_backup.heading(col, text=hdr)
            self.tree_backup.column(col, width=w, anchor="center")
        self.tree_backup.pack(fill="both", expand=True, padx=10, pady=5)
        frame.after(100, self._backup_load)

    def _backup_load(self):
        if not hasattr(self,"tree_backup"): return
        for i in self.tree_backup.get_children(): self.tree_backup.delete(i)
        for b in get_backup_list():
            self.tree_backup.insert("","end",
                values=(os.path.basename(b["filename"]),
                        b.get("size_kb",0),
                        b["created_at"][:19]))

    def _do_backup(self):
        backup_dir = self.backup_dir_var.get() if hasattr(self,"backup_dir_var") else BACKUP_DIR
        ok, path, size = create_backup(backup_dir)
        if ok:
            self.backup_status.config(
                text=f"✅ تم إنشاء النسخة: {os.path.basename(path)} ({size} KB)",
                foreground="green")
            frame.after(100, self._backup_load)
        else:
            self.backup_status.config(text=f"❌ فشل: {path}", foreground="red")

    def _open_backup_dir(self):
        d = self.backup_dir_var.get() if hasattr(self,"backup_dir_var") else BACKUP_DIR
        os.makedirs(d, exist_ok=True)
        try: os.startfile(os.path.abspath(d))
        except Exception: webbrowser.open(f"file://{os.path.abspath(d)}")

    def _change_backup_dir(self):
        d = filedialog.askdirectory(title="اختر مجلد النسخ الاحتياطية")
        if d and hasattr(self,"backup_dir_var"):
            self.backup_dir_var.set(d)

    def _delete_backup(self):
        sel = self.tree_backup.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد نسخة"); return
        fname = self.tree_backup.item(sel[0])["values"][0]
        d = self.backup_dir_var.get() if hasattr(self,"backup_dir_var") else BACKUP_DIR
        full_path = os.path.join(d, fname)
        if not messagebox.askyesno("تأكيد",f"حذف النسخة: {fname}؟"): return
        try:
            if os.path.exists(full_path): os.remove(full_path)
            messagebox.showinfo("تم","تم حذف النسخة الاحتياطية")
            frame.after(100, self._backup_load)
        except Exception as e:
            messagebox.showerror("خطأ",str(e))




    # ══════════════════════════════════════════════════════════
    # تبويب رسائل التأخر
    # ══════════════════════════════════════════════════════════
    def _build_tardiness_messages_tab(self):
        frame = self.tardiness_messages_frame

        # ─ رأس
        hdr = tk.Frame(frame, bg="#E65100", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📲 إرسال رسائل ولي الأمر — المتأخرون",
                 bg="#E65100", fg="white",
                 font=("Tahoma",13,"bold")).pack(side="right", padx=16, pady=12)

        # ─ شريط الأدوات العلوي
        top = ttk.Frame(frame); top.pack(fill="x", padx=10, pady=(8,4))

        ttk.Label(top, text="التاريخ:").pack(side="right", padx=(0,4))
        self.tard_msg_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(top, textvariable=self.tard_msg_date_var,
                  width=12).pack(side="right", padx=4)
        ttk.Button(top, text="تحميل المتأخرين",
                   command=self._tard_msg_load).pack(side="right", padx=4)
        ttk.Button(top, text="تشغيل WhatsApp Server",
                   command=start_whatsapp_server).pack(side="right", padx=4)

        self.tard_global_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="اختيار الجميع",
                        variable=self.tard_global_var,
                        command=self._tard_msg_toggle_all).pack(side="right", padx=8)

        self.tard_send_msg_btn = ttk.Button(
            top, text="📤 إرسال للمحددين",
            command=self._tard_msg_send_selected)
        self.tard_send_msg_btn.pack(side="right", padx=4)

        # ── تأخير بين الرسائل لتجنب حظر الواتساب ──────────────────
        delay_row = ttk.Frame(frame); delay_row.pack(fill="x", padx=10, pady=(0,2))
        ttk.Label(delay_row,
                  text="⏱ تأخير بين الرسائل:",
                  font=("Tahoma",9,"bold")).pack(side="right", padx=(0,4))
        cfg_d = load_config()
        self.tard_msg_delay_var = tk.IntVar(value=cfg_d.get("tard_msg_delay_sec", 8))
        ttk.Spinbox(delay_row, from_=1, to=60,
                    textvariable=self.tard_msg_delay_var, width=5).pack(side="right", padx=2)
        ttk.Label(delay_row, text="ثانية بين كل رسالة",
                  foreground="#374151").pack(side="right")
        ttk.Label(delay_row,
                  text="⚠️ القيمة الموصى بها: 8–15 ث لتجنب حظر الرقم",
                  foreground="#E65100", font=("Tahoma",8)).pack(side="left", padx=8)
        ttk.Button(delay_row, text="💾 حفظ",
                   command=self._tard_save_delay_setting).pack(side="left", padx=4)

        # حالة الإرسال
        self.tard_msg_status = ttk.Label(
            frame, text="", foreground="green", font=("Tahoma",10))
        self.tard_msg_status.pack(anchor="e", padx=10)

        # ─ قالب الرسالة (قابل للتعديل)
        tpl_lf = ttk.LabelFrame(frame, text=" ✏️ نص الرسالة ", padding=8)
        tpl_lf.pack(fill="x", padx=10, pady=(0,6))

        tpl_top = ttk.Frame(tpl_lf); tpl_top.pack(fill="x", pady=(0,4))
        ttk.Label(tpl_top,
                  text="المتغيرات: {student_name} {class_name} {date} {minutes_late} {school_name}",
                  foreground="#5A6A7E", font=("Tahoma",9)).pack(side="right")
        ttk.Button(tpl_top, text="حفظ القالب",
                   command=self._tard_msg_save_template).pack(side="left")

        cfg = load_config()
        self.tard_msg_tpl_text = tk.Text(
            tpl_lf, height=5, font=("Tahoma",10), wrap="word")
        self.tard_msg_tpl_text.insert("1.0",
            cfg.get("tardiness_message_template", ""))
        self.tard_msg_tpl_text.pack(fill="x")

        # ─ قائمة المتأخرين
        list_lf = ttk.LabelFrame(
            frame, text=" 📋 المتأخرون ", padding=6)
        list_lf.pack(fill="both", expand=True, padx=10, pady=(0,6))

        cols = ("chk","student_name","class_name","minutes_late",
                "register_time","parent_phone","msg_status")
        self.tree_tard_msg = ttk.Treeview(
            list_lf, columns=cols, show="headings", height=12)
        headers = ["☐","اسم الطالب","الفصل","دقائق التأخر",
                   "وقت التسجيل","جوال ولي الأمر","حالة الرسالة"]
        widths   = [30, 220, 150, 100, 90, 130, 110]
        for col, hdr_t, w in zip(cols, headers, widths):
            self.tree_tard_msg.heading(col, text=hdr_t)
            self.tree_tard_msg.column(col, width=w, anchor="center")

        self.tree_tard_msg.tag_configure("no_phone",  background="#FFEBEE", foreground="#9E9E9E")
        self.tree_tard_msg.tag_configure("has_phone", background="#F5F5F5")
        self.tree_tard_msg.tag_configure("sent_ok",   background="#E8F5E9", foreground="#2E7D32")
        self.tree_tard_msg.tag_configure("sent_fail", background="#FFEBEE", foreground="#C62828")

        sb = ttk.Scrollbar(list_lf, orient="vertical",
                            command=self.tree_tard_msg.yview)
        self.tree_tard_msg.configure(yscrollcommand=sb.set)
        self.tree_tard_msg.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree_tard_msg.bind("<Button-1>", self._tard_msg_toggle_row)

        # ─ سجل الإرسال
        log_lf = ttk.LabelFrame(frame, text=" 📝 سجل الإرسال ", padding=4)
        log_lf.pack(fill="x", padx=10, pady=(0,8))
        self.tard_msg_log = tk.Text(
            log_lf, height=4, state="disabled",
            font=("Tahoma",9), wrap="word")
        self.tard_msg_log.pack(fill="x")

        self._tard_msg_checked = set()
        self._tard_msg_vars    = {}   # student_id -> BooleanVar
        frame.after(100, self._tard_msg_load)

    def _tard_save_delay_setting(self):
        """يحفظ إعداد التأخير بين رسائل التأخر في الإعدادات."""
        delay = max(1, self.tard_msg_delay_var.get() if hasattr(self, "tard_msg_delay_var") else 8)
        cfg = load_config()
        cfg["tard_msg_delay_sec"] = delay
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        invalidate_config_cache()
        messagebox.showinfo("تم", f"✅ تم حفظ التأخير: {delay} ثانية بين كل رسالة")

    def _tard_msg_load(self):
        """يُحمّل المتأخرين لليوم المحدد."""
        if not hasattr(self, "tree_tard_msg"): return
        for i in self.tree_tard_msg.get_children():
            self.tree_tard_msg.delete(i)
        self._tard_msg_checked.clear()
        self._tard_msg_vars.clear()

        date_str = self.tard_msg_date_var.get().strip()                    if hasattr(self,"tard_msg_date_var") else now_riyadh_date()
        rows = query_tardiness(date_filter=date_str)

        if not rows:
            self.tard_msg_status.configure(
                text="لا يوجد متأخرون بتاريخ {}".format(date_str),
                foreground="orange")
            return

        # ابحث عن أرقام جوالات الطلاب
        store = load_students()
        phone_map = {s["id"]: s.get("phone","")
                     for cls in store["list"] for s in cls["students"]}

        # فحص الرسائل المُرسَلة مسبقاً
        sent_map = self._tard_msg_get_sent_map(date_str)

        count = 0
        for r in rows:
            sid       = r["student_id"]
            phone     = phone_map.get(sid, "")
            mins      = r.get("minutes_late", 0)
            reg_time  = r.get("created_at","")[:5] if r.get("created_at") else ""
            sent_stat = sent_map.get(sid, "")

            tag = ("sent_ok"   if sent_stat == "تم الإرسال" else
                   "sent_fail" if "فشل" in sent_stat        else
                   "no_phone"  if not phone                  else
                   "has_phone")

            self.tree_tard_msg.insert(
                "", "end", iid=sid, tags=(tag,),
                values=("☐", r["student_name"], r.get("class_name",""),
                        "{} دقيقة".format(mins), reg_time,
                        phone or "— لا يوجد رقم",
                        sent_stat or ""))
            count += 1

        self.tard_msg_status.configure(
            text="{} متأخر — {} لديهم رقم جوال".format(
                count, sum(1 for r in rows if phone_map.get(r["student_id"]))),
            foreground="#1565C0")

    def _tard_msg_get_sent_map(self, date_str: str) -> dict:
        """يستعلم عن الرسائل المُرسَلة للمتأخرين من جدول message_log."""
        try:
            con = get_db()
            con.row_factory = sqlite3.Row; cur = con.cursor()
            cur.execute("""SELECT student_id, status FROM messages_log
                           WHERE date=? AND message_type='tardiness'""",
                        (date_str,))
            result = {r["student_id"]: r["status"] for r in cur.fetchall()}
            con.close(); return result
        except Exception:
            return {}

    def _tard_msg_toggle_row(self, event):
        region = self.tree_tard_msg.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree_tard_msg.identify_column(event.x)
        if col != "#1": return
        iid = self.tree_tard_msg.identify_row(event.y)
        if not iid: return
        if iid in self._tard_msg_checked:
            self._tard_msg_checked.discard(iid)
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[0] = "☐"
            self.tree_tard_msg.item(iid, values=vals)
        else:
            self._tard_msg_checked.add(iid)
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[0] = "☑"
            self.tree_tard_msg.item(iid, values=vals)

    def _tard_msg_toggle_all(self):
        checked = self.tard_global_var.get()
        for iid in self.tree_tard_msg.get_children():
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[0] = "☑" if checked else "☐"
            self.tree_tard_msg.item(iid, values=vals)
            if checked: self._tard_msg_checked.add(iid)
            else:        self._tard_msg_checked.discard(iid)

    def _tard_msg_save_template(self):
        tpl = self.tard_msg_tpl_text.get("1.0","end").strip()               if hasattr(self,"tard_msg_tpl_text") else ""
        if not tpl: return
        cfg = load_config()
        cfg["tardiness_message_template"] = tpl
        with open(CONFIG_JSON,"w",encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("تم","تم حفظ قالب رسالة التأخر")

    def _tard_msg_send_selected(self):
        if not self._tard_msg_checked:
            messagebox.showwarning("تنبيه","حدد طلاباً أولاً"); return

        date_str = self.tard_msg_date_var.get().strip()                    if hasattr(self,"tard_msg_date_var") else now_riyadh_date()
        cfg      = load_config()
        school   = cfg.get("school_name","المدرسة")
        tpl      = cfg.get("tardiness_message_template","")
        store    = load_students()
        phone_map = {s["id"]: s.get("phone","")
                     for cls in store["list"] for s in cls["students"]}
        tard_rows = {r["student_id"]: r
                     for r in query_tardiness(date_filter=date_str)}

        if not messagebox.askyesno("تأكيد",
            "إرسال رسائل التأخر لـ {} طالب؟".format(
                len(self._tard_msg_checked))):
            return

        self.tard_send_msg_btn.configure(state="disabled")
        self.root.update_idletasks()

        def do_send():
            ok_cnt = fail_cnt = skip_cnt = 0
            for sid in list(self._tard_msg_checked):
                row   = tard_rows.get(sid)
                phone = phone_map.get(sid,"")
                if not row:
                    skip_cnt += 1; continue
                if not phone:
                    skip_cnt += 1
                    self._tard_msg_log_append("⚠️ {} — لا يوجد رقم جوال".format(
                        row.get("student_name",sid)))
                    self._tard_msg_update_row(sid, "لا يوجد رقم")
                    continue
                try:
                    mins = row.get("minutes_late",0)
                    msg  = tpl.format(
                        school_name=school,
                        student_name=row.get("student_name",""),
                        class_name=row.get("class_name",""),
                        date=date_str,
                        minutes_late=mins)
                except Exception:
                    msg = "تنبيه: تأخّر ابنكم {} دقيقة بتاريخ {}".format(
                        row.get("minutes_late",0), date_str)

                ok, status = send_whatsapp_message(phone, msg)
                log_status = "تم الإرسال" if ok else "فشل: {}".format(status)

                # ── تأخير بين الرسائل لتجنب حظر الواتساب ──
                delay_sec = self.tard_msg_delay_var.get() if hasattr(self, "tard_msg_delay_var") else 8
                time.sleep(max(1, delay_sec))

                # سجّل في message_log
                try:
                    created = datetime.datetime.utcnow().isoformat()
                    con = get_db(); cur = con.cursor()
                    cur.execute("""INSERT INTO messages_log
                        (date,student_id,student_name,class_id,class_name,
                         phone,status,template_used,message_type,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (date_str, sid,
                         row.get("student_name",""),
                         row.get("class_id",""),
                         row.get("class_name",""),
                         phone, log_status, msg, "tardiness", created))
                    con.commit(); con.close()
                except Exception: pass

                if ok:
                    ok_cnt += 1
                    self._tard_msg_log_append(
                        "✅ {} ({} دقيقة)".format(
                            row.get("student_name",""), mins))
                    self._tard_msg_update_row(sid, "تم الإرسال", "sent_ok")
                else:
                    fail_cnt += 1
                    short_err = status[:40] if len(status) > 40 else status
                    self._tard_msg_log_append(
                        "❌ {} — {}".format(
                            row.get("student_name",""), status))
                    self._tard_msg_update_row(sid, short_err, "sent_fail")

            summary = "اكتمل — نجح: {} | فشل: {} | تخطّى: {}".format(
                ok_cnt, fail_cnt, skip_cnt)
            self.root.after(0, lambda: (
                self.tard_msg_status.configure(
                    text=summary,
                    foreground="green" if fail_cnt==0 else "orange"),
                self.tard_send_msg_btn.configure(state="normal"),
                messagebox.showinfo("نتيجة الإرسال", summary)
            ))

        threading.Thread(target=do_send, daemon=True).start()

    def _tard_msg_log_append(self, msg: str):
        def _do():
            if not hasattr(self,"tard_msg_log"): return
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.tard_msg_log.configure(state="normal")
            self.tard_msg_log.insert("end","[{}] {}\n".format(ts, msg))
            self.tard_msg_log.see("end")
            self.tard_msg_log.configure(state="disabled")
        self.root.after(0, _do)

    def _tard_msg_update_row(self, iid: str, status: str, tag: str = ""):
        def _do():
            if not self.tree_tard_msg.exists(iid): return
            vals = list(self.tree_tard_msg.item(iid,"values"))
            vals[-1] = status
            self.tree_tard_msg.item(iid, values=vals,
                                     tags=(tag,) if tag else ())
        self.root.after(0, _do)

    # ══════════════════════════════════════════════════════════
    # تبويب الإشعارات الذكية
    # ══════════════════════════════════════════════════════════
    def _build_alerts_tab(self):
        frame = self.alerts_frame

        # ══ رأس ═══════════════════════════════════════════════════
        hdr = tk.Frame(frame, bg="#7C3AED", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔔 الإشعارات الذكية — الغياب والتأخر",
                 bg="#7C3AED", fg="white",
                 font=("Tahoma",13,"bold")).pack(side="right", padx=16, pady=12)

        # ══ إعدادات (ثابتة في الأعلى بدون canvas) ════════════════
        cfg_lf = ttk.LabelFrame(frame, text=" ⚙️ إعدادات التنبيه ", padding=8)
        cfg_lf.pack(fill="x", padx=8, pady=(6,4))

        cfg = load_config()
        r1 = ttk.Frame(cfg_lf); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="تنبيه عند تجاوز:", width=18, anchor="e").pack(side="right")
        self.alert_thresh_var = tk.IntVar(value=cfg.get("alert_absence_threshold", 5))
        ttk.Spinbox(r1, from_=1, to=30, textvariable=self.alert_thresh_var,
                    width=6).pack(side="right", padx=4)
        ttk.Label(r1, text="يوم غياب").pack(side="right")
        self.alert_enabled_var = tk.BooleanVar(value=cfg.get("alert_enabled", True))
        ttk.Checkbutton(r1, text="تفعيل الإشعارات التلقائية",
                        variable=self.alert_enabled_var).pack(side="left", padx=16)

        r2 = ttk.Frame(cfg_lf); r2.pack(fill="x", pady=2)
        self.alert_parent_var = tk.BooleanVar(value=cfg.get("alert_notify_parent", True))
        ttk.Checkbutton(r2, text="إشعار ولي الأمر",
                        variable=self.alert_parent_var).pack(side="right", padx=4)
        self.alert_admin_var = tk.BooleanVar(value=cfg.get("alert_notify_admin", True))
        ttk.Checkbutton(r2, text="إشعار الإدارة",
                        variable=self.alert_admin_var).pack(side="right", padx=4)
        ttk.Label(r2, text="جوال الإدارة:", anchor="e").pack(side="right", padx=(10,2))
        self.alert_admin_phone_var = tk.StringVar(value=cfg.get("alert_admin_phone", ""))
        ttk.Entry(r2, textvariable=self.alert_admin_phone_var,
                  width=18, justify="right").pack(side="right", padx=2)

        r3 = ttk.Frame(cfg_lf); r3.pack(fill="x", pady=2)
        self.alert_hour_var = tk.IntVar(value=14)
        ttk.Label(r3, text="وقت التشغيل اليومي:", anchor="e").pack(side="right")
        ttk.Spinbox(r3, from_=8, to=20, textvariable=self.alert_hour_var,
                    width=5).pack(side="right", padx=4)
        ttk.Label(r3, text=":00 أحد–خميس").pack(side="right")

        # التقرير اليومي
        self.daily_report_var = tk.BooleanVar(value=cfg.get("daily_report_enabled", False))
        ttk.Checkbutton(r3, text="تقرير يومي تلقائي",
                        variable=self.daily_report_var,
                        command=self._toggle_daily_report).pack(side="left", padx=16)
        self.dr_hour_var   = tk.IntVar(value=cfg.get("daily_report_hour",   13))
        self.dr_minute_var = tk.IntVar(value=cfg.get("daily_report_minute", 30))
        ttk.Spinbox(r3, from_=8, to=17, textvariable=self.dr_hour_var,
                    width=4).pack(side="left", padx=2)
        ttk.Label(r3, text=":").pack(side="left")
        ttk.Spinbox(r3, from_=0, to=59, textvariable=self.dr_minute_var,
                    width=4, format="%02.0f").pack(side="left", padx=2)
        self.dr_status_lbl = ttk.Label(r3, text="", foreground="#5A6A7E",
                                        font=("Tahoma", 8))
        self.dr_status_lbl.pack(side="left", padx=6)
        self._update_dr_status_label()

        btn_row = ttk.Frame(cfg_lf); btn_row.pack(fill="x", pady=(4,0))
        ttk.Button(btn_row, text="💾 حفظ الإعدادات",
                   command=self._save_alert_settings).pack(side="right", padx=4)
        ttk.Button(btn_row, text="▶ تشغيل الإشعارات الآن",
                   command=self._run_alerts_now).pack(side="right", padx=4)
        ttk.Button(btn_row, text="📊 إرسال التقرير اليومي الآن",
                   command=self._send_daily_report_now).pack(side="right", padx=4)

        # ══ Notebook داخلي — قسم الغياب / قسم التأخر / الأنماط ═══
        nb = ttk.Notebook(frame)
        nb.pack(fill="both", expand=True, padx=8, pady=(4,8))

        # ─────────────────────────────────────────────────────────
        # تبويب الغياب
        # ─────────────────────────────────────────────────────────
        tab_abs = ttk.Frame(nb); nb.add(tab_abs, text=" 🔴 الغياب ")

        abs_ctrl = ttk.Frame(tab_abs); abs_ctrl.pack(fill="x", padx=6, pady=6)
        self.alert_month_var = tk.StringVar(
            value=datetime.datetime.now().strftime("%Y-%m"))
        ttk.Label(abs_ctrl, text="الشهر (YYYY-MM):").pack(side="right", padx=(0,4))
        ttk.Entry(abs_ctrl, textvariable=self.alert_month_var,
                  width=10).pack(side="right")
        ttk.Button(abs_ctrl, text="🔍 تحديث",
                   command=self._load_alert_students).pack(side="right", padx=4)
        ttk.Button(abs_ctrl, text="📤 إرسال للمحددين",
                   command=self._send_alerts_selected).pack(side="left", padx=4)
        ttk.Button(abs_ctrl, text="👨‍🏫 تحويل للموجّه",
                   command=lambda: self._refer_to_counselor("غياب")).pack(side="left", padx=4)
        self.alert_sel_lbl = ttk.Label(abs_ctrl, text="", foreground="#7C3AED")
        self.alert_sel_lbl.pack(side="left", padx=8)

        cols = ("chk","student_name","class_name","absence_count",
                "last_date","parent_phone","status")
        tree_frame_abs = ttk.Frame(tab_abs)
        tree_frame_abs.pack(fill="both", expand=True, padx=6, pady=(0,6))
        self.tree_alerts = ttk.Treeview(tree_frame_abs, columns=cols,
                                         show="headings", height=14)
        for col, hd, w in zip(cols,
            ["☐","اسم الطالب","الفصل","أيام الغياب","آخر غياب","جوال ولي الأمر","الحالة"],
            [30,200,140,100,100,130,110]):
            self.tree_alerts.heading(col, text=hd)
            self.tree_alerts.column(col, width=w, anchor="center")
        self.tree_alerts.tag_configure("high",     background="#FFEBEE", foreground="#C62828")
        self.tree_alerts.tag_configure("medium",   background="#FFF8E1", foreground="#E65100")
        self.tree_alerts.tag_configure("sent",     background="#E8F5E9", foreground="#2E7D32")
        self.tree_alerts.tag_configure("referred", background="#EDE9FE", foreground="#5B21B6")
        abs_sb = ttk.Scrollbar(tree_frame_abs, orient="vertical",
                                command=self.tree_alerts.yview)
        self.tree_alerts.configure(yscrollcommand=abs_sb.set)
        self.tree_alerts.pack(side="left", fill="both", expand=True)
        abs_sb.pack(side="right", fill="y")
        self.tree_alerts.bind("<Button-1>", self._alert_toggle_check)

        # سجل إرسال الغياب
        log_abs_lf = ttk.LabelFrame(tab_abs, text=" 📝 سجل الإرسال ", padding=4)
        log_abs_lf.pack(fill="x", padx=6, pady=(0,6))
        self.alert_log = tk.Text(log_abs_lf, height=4, state="disabled",
                                  font=("Tahoma",9), wrap="word")
        self.alert_log.pack(fill="x")

        # ─────────────────────────────────────────────────────────
        # تبويب التأخر
        # ─────────────────────────────────────────────────────────
        tab_tard = ttk.Frame(nb); nb.add(tab_tard, text=" 🟠 التأخر ")

        tard_ctrl = ttk.Frame(tab_tard); tard_ctrl.pack(fill="x", padx=6, pady=6)
        self.alert_tard_thresh_var = tk.IntVar(value=cfg.get("alert_tardiness_threshold", 3))
        ttk.Label(tard_ctrl, text="تنبيه عند تجاوز:").pack(side="right", padx=(0,2))
        ttk.Spinbox(tard_ctrl, from_=1, to=30,
                    textvariable=self.alert_tard_thresh_var, width=5).pack(side="right")
        ttk.Label(tard_ctrl, text="مرة  |  الشهر:").pack(side="right", padx=(4,2))
        self.alert_tard_month_var = tk.StringVar(
            value=datetime.datetime.now().strftime("%Y-%m"))
        ttk.Entry(tard_ctrl, textvariable=self.alert_tard_month_var,
                  width=10).pack(side="right")
        ttk.Button(tard_ctrl, text="🔍 تحديث",
                   command=self._load_tardiness_alert_students).pack(side="right", padx=4)
        ttk.Button(tard_ctrl, text="👨‍🏫 تحويل للموجّه",
                   command=lambda: self._refer_to_counselor("تأخر")).pack(side="left", padx=4)
        self.alert_tard_sel_lbl = ttk.Label(tard_ctrl, text="", foreground="#EA580C")
        self.alert_tard_sel_lbl.pack(side="left", padx=8)

        cols_t = ("chk","student_name","class_name","tardiness_count",
                  "last_date","parent_phone","status")
        tree_frame_tard = ttk.Frame(tab_tard)
        tree_frame_tard.pack(fill="both", expand=True, padx=6, pady=(0,6))
        self.tree_alerts_tard = ttk.Treeview(tree_frame_tard, columns=cols_t,
                                              show="headings", height=14)
        for col, hd, w in zip(cols_t,
            ["☐","اسم الطالب","الفصل","مرات التأخر","آخر تأخر","جوال ولي الأمر","الحالة"],
            [30,200,140,110,100,130,110]):
            self.tree_alerts_tard.heading(col, text=hd)
            self.tree_alerts_tard.column(col, width=w, anchor="center")
        self.tree_alerts_tard.tag_configure("high",     background="#FFF3E0", foreground="#E65100")
        self.tree_alerts_tard.tag_configure("medium",   background="#FFF8E1", foreground="#F57C00")
        self.tree_alerts_tard.tag_configure("referred", background="#EDE9FE", foreground="#5B21B6")
        tard_sb = ttk.Scrollbar(tree_frame_tard, orient="vertical",
                                 command=self.tree_alerts_tard.yview)
        self.tree_alerts_tard.configure(yscrollcommand=tard_sb.set)
        self.tree_alerts_tard.pack(side="left", fill="both", expand=True)
        tard_sb.pack(side="right", fill="y")
        self.tree_alerts_tard.bind("<Button-1>", self._tard_alert_toggle_check)

        # ─────────────────────────────────────────────────────────
        # تبويب الأنماط المشبوهة
        # ─────────────────────────────────────────────────────────
        tab_pat = ttk.Frame(nb); nb.add(tab_pat, text=" 🔍 الأنماط المشبوهة ")

        pat_ctrl = ttk.Frame(tab_pat); pat_ctrl.pack(fill="x", padx=6, pady=6)
        ttk.Button(pat_ctrl, text="🔍 تحليل الأنماط الآن",
                   command=self._detect_patterns).pack(side="right", padx=4)
        ttk.Label(pat_ctrl,
            text="يكتشف: غياب متكرر الأحد/الخميس | غياب جماعي +30%",
            foreground="#5A6A7E", font=("Tahoma",8)).pack(side="right", padx=8)

        cols_p = ("type","name_or_class","desc","count")
        self.tree_patterns = ttk.Treeview(tab_pat, columns=cols_p,
                                           show="headings", height=14)
        for c,h,w in zip(cols_p,
            ["النوع","الطالب/الفصل","التفاصيل","العدد"],
            [110,200,360,70]):
            self.tree_patterns.heading(c, text=h)
            self.tree_patterns.column(c, width=w, anchor="center")
        self.tree_patterns.tag_configure("repeated", background="#FFF8E1", foreground="#E65100")
        self.tree_patterns.tag_configure("mass",     background="#FFEBEE", foreground="#C62828")
        pat_sb = ttk.Scrollbar(tab_pat, orient="vertical",
                                command=self.tree_patterns.yview)
        self.tree_patterns.configure(yscrollcommand=pat_sb.set)
        self.tree_patterns.pack(side="left", fill="both", expand=True, padx=(6,0))
        pat_sb.pack(side="right", fill="y", pady=6, padx=(0,6))

        # ══ تهيئة ══════════════════════════════════════════════════
        self._alert_checked      = set()
        self._tard_alert_checked = set()
        self._load_alert_students()
        self._load_tardiness_alert_students()

    def _detect_patterns(self):
        """يحلل أنماط الغياب ويعرضها في الجدول."""
        if not hasattr(self,"tree_patterns"): return
        for i in self.tree_patterns.get_children(): self.tree_patterns.delete(i)

        import threading as _th
        def _run():
            patterns = detect_suspicious_patterns()
            def _show():
                for p in patterns:
                    if p["type"] == "repeated_day":
                        self.tree_patterns.insert("","end", tags=("repeated",),
                            values=("تكرار يومي",
                                    p["name"]+" / "+p["class_name"],
                                    p["desc"], p["count"]))
                    elif p["type"] == "mass_absence":
                        self.tree_patterns.insert("","end", tags=("mass",),
                            values=("غياب جماعي",
                                    p["class_name"],
                                    p["desc"], "{}%".format(p["pct"])))
                if not patterns:
                    self.tree_patterns.insert("","end",
                        values=("✅","—","لا توجد أنماط مشبوهة","—"))
            self.root.after(0, _show)
        _th.Thread(target=_run, daemon=True).start()

    # ── قسم التأخر: تحميل الطلاب ────────────────────────────────
    def _load_tardiness_alert_students(self):
        """يحمّل الطلاب المتأخرين المتكررين في قسم التأخر."""
        if not hasattr(self, "tree_alerts_tard"): return
        for i in self.tree_alerts_tard.get_children():
            self.tree_alerts_tard.delete(i)
        if hasattr(self, "_tard_alert_checked"):
            self._tard_alert_checked.clear()

        month     = self.alert_tard_month_var.get().strip() if hasattr(self, "alert_tard_month_var") else datetime.datetime.now().strftime("%Y-%m")
        threshold = self.alert_tard_thresh_var.get() if hasattr(self, "alert_tard_thresh_var") else 3

        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("""
            SELECT student_id,
                   MAX(student_name) as student_name,
                   MAX(class_name)   as class_name,
                   COUNT(*)          as tardiness_count,
                   MAX(date)         as last_date
            FROM tardiness
            WHERE date LIKE ?
            GROUP BY student_id
            HAVING tardiness_count >= ?
            ORDER BY tardiness_count DESC
        """, (month + "%", threshold))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()

        # أضف جوال ولي الأمر
        store = load_students()
        phone_map = {s["id"]: s.get("phone","") for cls in store["list"] for s in cls["students"]}

        # اقرأ المحوّلين لتلوين الصف
        con2 = get_db(); con2.row_factory = sqlite3.Row; cur2 = con2.cursor()
        cur2.execute("SELECT student_id FROM counselor_referrals WHERE referral_type='تأخر'")
        referred_ids = {r["student_id"] for r in cur2.fetchall()}
        con2.close()

        for r in rows:
            cnt   = r["tardiness_count"]
            tag   = "referred" if r["student_id"] in referred_ids else ("high" if cnt >= threshold * 2 else "medium")
            phone = phone_map.get(r["student_id"], "") or "—"
            status = "✅ محوّل للموجّه" if r["student_id"] in referred_ids else ""
            self.tree_alerts_tard.insert("", "end", tags=(tag,),
                iid="tard_" + r["student_id"],
                values=("☐", r["student_name"], r["class_name"],
                        "{} مرة".format(cnt), r["last_date"], phone, status))

        lbl_text = "إجمالي: {} طالب".format(len(rows))
        if hasattr(self, "alert_tard_sel_lbl"):
            self.alert_tard_sel_lbl.configure(text=lbl_text)

    def _tard_alert_toggle_check(self, event):
        """تبديل تحديد الطلاب في قسم التأخر."""
        region = self.tree_alerts_tard.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree_alerts_tard.identify_column(event.x)
        if col != "#1": return
        iid = self.tree_alerts_tard.identify_row(event.y)
        if not iid: return
        if iid in self._tard_alert_checked:
            self._tard_alert_checked.discard(iid)
            vals = list(self.tree_alerts_tard.item(iid, "values"))
            vals[0] = "☐"
            self.tree_alerts_tard.item(iid, values=vals)
        else:
            self._tard_alert_checked.add(iid)
            vals = list(self.tree_alerts_tard.item(iid, "values"))
            vals[0] = "☑"
            self.tree_alerts_tard.item(iid, values=vals)
        if hasattr(self, "alert_tard_sel_lbl"):
            self.alert_tard_sel_lbl.configure(
                text="محدد: {} | إجمالي: {}".format(
                    len(self._tard_alert_checked),
                    len(self.tree_alerts_tard.get_children())))

    def _refer_to_counselor(self, referral_type: str = "غياب"):
        """
        يحوّل الطلاب المحددين (☑) للموجّه الطلابي.
        referral_type: 'غياب' أو 'تأخر'
        """
        if referral_type == "غياب":
            checked   = self._alert_checked
            tree      = self.tree_alerts
            month     = self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else datetime.datetime.now().strftime("%Y-%m")
            threshold = self.alert_thresh_var.get() if hasattr(self,"alert_thresh_var") else 5
            all_stu   = {s["student_id"]: s for s in get_students_exceeding_threshold(threshold, month)}
        else:
            checked   = self._tard_alert_checked
            tree      = self.tree_alerts_tard
            month     = self.alert_tard_month_var.get().strip() if hasattr(self,"alert_tard_month_var") else datetime.datetime.now().strftime("%Y-%m")
            threshold = self.alert_tard_thresh_var.get() if hasattr(self,"alert_tard_thresh_var") else 3
            all_stu   = None  # سنقرأ من الـ tree مباشرة

        if not checked:
            messagebox.showwarning("تنبيه",
                "انقر على ☐ لتحديد الطلاب أولاً", parent=self.root); return

        if not messagebox.askyesno("تأكيد",
            "تحويل {} طالب للموجّه الطلابي كـ '{}'؟".format(len(checked), referral_type),
            parent=self.root): return

        now_str  = datetime.datetime.now().isoformat()
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        con = get_db(); cur = con.cursor()
        count_new = 0

        for iid in checked:
            # استخرج بيانات الطالب من الـ tree
            vals = tree.item(iid, "values")
            # vals: (chk, student_name, class_name, count_col, last_date, phone, status)
            sname = vals[1]; sclass = vals[2]; cnt_str = vals[3]
            # استخرج الـ student_id من iid
            if referral_type == "غياب":
                sid = iid  # في قسم الغياب iid == student_id
                abs_c  = int(str(cnt_str).split()[0]) if cnt_str else 0
                tard_c = 0
            else:
                sid = iid.replace("tard_", "", 1)  # في قسم التأخر iid == "tard_" + student_id
                tard_c = int(str(cnt_str).split()[0]) if cnt_str else 0
                abs_c  = 0

            # تجنب التكرار: أضف فقط إذا لم يكن موجوداً بنفس النوع والشهر
            cur.execute("""SELECT id FROM counselor_referrals
                           WHERE student_id=? AND referral_type=? AND date LIKE ?""",
                        (sid, referral_type, date_str[:7] + "%"))
            if cur.fetchone():
                continue  # مُحوَّل مسبقاً هذا الشهر

            cur.execute("""
                INSERT INTO counselor_referrals
                    (date, student_id, student_name, class_name, referral_type,
                     absence_count, tardiness_count, notes, referred_by, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (date_str, sid, sname, sclass, referral_type,
                  abs_c, tard_c, "", "وكيل شؤون الطلاب", "جديد", now_str))
            count_new += 1

        con.commit(); con.close()

        # لوّن الصفوف المحوّلة وحدّث حقل الحالة
        for iid in checked:
            if tree.exists(iid):
                v = list(tree.item(iid, "values"))
                v[-1] = "✅ محوّل للموجّه"
                tree.item(iid, values=v, tags=("referred",))

        skipped = len(checked) - count_new
        msg = "✅ تم تحويل {} طالب للموجّه الطلابي".format(count_new)
        if skipped:
            msg += "\n(تم تجاهل {} طالب محوّل مسبقاً هذا الشهر)".format(skipped)
        messagebox.showinfo("تم التحويل", msg, parent=self.root)

        # ── إرسال تنبيه واتساب لجوالَي الموجّهَين تلقائياً ─────────────
        if count_new > 0:
            _cfg_ref = load_config()
            _c1 = _cfg_ref.get("counselor1_phone", "").strip()
            _c2 = _cfg_ref.get("counselor2_phone", "").strip()
            if _c1 or _c2:
                # بناء قائمة أسماء الطلاب المحوّلين
                _names = []
                for _iid in checked:
                    if tree.exists(_iid):
                        _v = tree.item(_iid, "values")
                        if _v:
                            _names.append("• {} ({})".format(_v[1], _v[2]))
                _extra = ""
                if len(_names) > 10:
                    _extra = "\n... و{} طلاب آخرين".format(len(_names) - 10)
                _alert_msg = (
                    "🔔 تنبيه جديد من نظام درب\n"
                    "━━━━━━━━━━━━━━━━━━━\n"
                    "📋 تم تحويل {} طالب إليك كـ ({})\n\n"
                    "{}{}\n\n"
                    "👤 بواسطة: وكيل شؤون الطلاب\n"
                    "📅 التاريخ: {}"
                ).format(
                    count_new, referral_type,
                    "\n".join(_names[:10]), _extra,
                    date_str
                )
                for _phone in [_c1, _c2]:
                    if _phone:
                        threading.Thread(
                            target=send_whatsapp_message,
                            args=(_phone, _alert_msg),
                            daemon=True
                        ).start()
        # ────────────────────────────────────────────────────────────────

        checked.clear()

    def _save_alert_settings(self):
        cfg = load_config()
        cfg["alert_absence_threshold"] = self.alert_thresh_var.get()
        cfg["alert_enabled"]           = self.alert_enabled_var.get()
        cfg["alert_notify_parent"]     = self.alert_parent_var.get()
        cfg["alert_notify_admin"]      = self.alert_admin_var.get()
        cfg["alert_admin_phone"]       = self.alert_admin_phone_var.get().strip()
        if hasattr(self, "daily_report_var"):
            cfg["daily_report_enabled"] = self.daily_report_var.get()
            cfg["daily_report_hour"]    = self.dr_hour_var.get()
            cfg["daily_report_minute"]  = self.dr_minute_var.get()
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        invalidate_config_cache()
        # أعد جدولة التقرير بالإعدادات الجديدة
        schedule_daily_report(self.root)
        self._update_dr_status_label()
        messagebox.showinfo("تم", "تم حفظ إعدادات الإشعارات بنجاح")

    def _toggle_daily_report(self):
        """تفعيل/إيقاف التقرير اليومي فوراً."""
        cfg = load_config()
        cfg["daily_report_enabled"] = self.daily_report_var.get()
        cfg["daily_report_hour"]    = self.dr_hour_var.get()
        cfg["daily_report_minute"]  = self.dr_minute_var.get()
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        invalidate_config_cache()
        schedule_daily_report(self.root)
        self._update_dr_status_label()

    def _update_dr_status_label(self):
        if not hasattr(self, "dr_status_lbl"): return
        cfg = load_config()
        if cfg.get("daily_report_enabled"):
            h = cfg.get("daily_report_hour", 13)
            m = cfg.get("daily_report_minute", 30)
            phone = cfg.get("alert_admin_phone", "")
            self.dr_status_lbl.config(
                text="✅ مفعّل — يُرسَل كل يوم أحد–خميس في {:02d}:{:02d} → {}".format(
                    h, m, phone or "لم يُحدَّد رقم"),
                foreground="#2E7D32")
        else:
            self.dr_status_lbl.config(
                text="⏸ معطّل — فعّله بالخيار أعلاه",
                foreground="#9CA3AF")

    def _send_daily_report_now(self):
        ok, status = send_daily_report_to_admin()
        if ok:
            messagebox.showinfo("تم", "✅ تم إرسال التقرير اليومي للإدارة")
        else:
            messagebox.showwarning("فشل", "❌ تعذّر الإرسال:\n" + status)

    def _load_alert_students(self):
        if not hasattr(self, "tree_alerts"): return
        for i in self.tree_alerts.get_children(): self.tree_alerts.delete(i)
        self._alert_checked.clear()
        month     = self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else datetime.datetime.now().strftime("%Y-%m")
        threshold = self.alert_thresh_var.get() if hasattr(self,"alert_thresh_var") else 5
        students  = get_students_exceeding_threshold(threshold, month)
        for s in students:
            cnt   = s["absence_count"]
            tag   = "high" if cnt >= threshold * 2 else "medium"
            phone = s.get("parent_phone","") or "—"
            self.tree_alerts.insert("", "end", tags=(tag,),
                iid=s["student_id"],
                values=("☐", s["student_name"], s["class_name"],
                        "{} يوم".format(cnt), s["last_date"],
                        phone, ""))
        self.alert_sel_lbl.configure(
            text="إجمالي: {} طالب".format(len(students)))

    def _alert_toggle_check(self, event):
        region = self.tree_alerts.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree_alerts.identify_column(event.x)
        if col != "#1": return  # عمود الـ checkbox فقط
        iid = self.tree_alerts.identify_row(event.y)
        if not iid: return
        if iid in self._alert_checked:
            self._alert_checked.discard(iid)
            vals = list(self.tree_alerts.item(iid, "values"))
            vals[0] = "☐"
            self.tree_alerts.item(iid, values=vals)
        else:
            self._alert_checked.add(iid)
            vals = list(self.tree_alerts.item(iid, "values"))
            vals[0] = "☑"
            self.tree_alerts.item(iid, values=vals)
        self.alert_sel_lbl.configure(
            text="محدد: {} | إجمالي: {}".format(
                len(self._alert_checked),
                len(self.tree_alerts.get_children())))

    def _run_alerts_now(self):
        if not messagebox.askyesno("تأكيد",
            "سيتم إرسال تنبيهات لجميع الطلاب المتجاوزين للعتبة.\nهل تريد المتابعة؟"):
            return
        self._append_alert_log("▶ بدء الإشعارات التلقائية...")
        def do():
            result = run_smart_alerts(
                month=self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else None,
                log_cb=lambda m: self.root.after(0, lambda msg=m: self._append_alert_log(msg)))
            summary = "✅ اكتمل — ولي أمر: {} | إدارة: {} | فشل: {}".format(
                result.get("sent_parent",0),
                result.get("sent_admin",0),
                result.get("failed",0))
            self.root.after(0, lambda: self._append_alert_log(summary))
            self.root.after(0, self._load_alert_students)
        threading.Thread(target=do, daemon=True).start()

    def _send_alerts_selected(self):
        if not self._alert_checked:
            messagebox.showwarning("تنبيه","انقر على ☐ لتحديد الطلاب أولاً"); return
        if not messagebox.askyesno("تأكيد",
            "إرسال تنبيهات لـ {} طالب؟".format(len(self._alert_checked))):
            return
        month  = self.alert_month_var.get().strip() if hasattr(self,"alert_month_var") else datetime.datetime.now().strftime("%Y-%m")
        thresh = self.alert_thresh_var.get() if hasattr(self,"alert_thresh_var") else 5
        all_s  = {s["student_id"]: s for s in get_students_exceeding_threshold(thresh, month)}
        selected = [all_s[sid] for sid in self._alert_checked if sid in all_s]
        self._append_alert_log("▶ إرسال لـ {} طالب محدد...".format(len(selected)))
        def do():
            cfg = load_config(); ok_p = ok_a = fail = 0
            _delay = max(1, cfg.get("tard_msg_delay_sec", 8))
            for s in selected:
                res = send_alert_for_student(s, cfg)
                if res["parent"]: ok_p += 1
                if res["admin"]:  ok_a += 1
                if res["errors"]: fail += 1
                status = "✅" if (res["parent"] or res["admin"]) else "❌"
                msg = "{} {} — ولي أمر: {} | إدارة: {}".format(
                    status, s["student_name"],
                    "تم" if res["parent"] else "فشل/لا رقم",
                    "تم" if res["admin"]  else "فشل/لا رقم")
                sid = s["student_id"]
                self.root.after(0, lambda m=msg, i=sid: (
                    self._append_alert_log(m),
                    self._update_alert_row(i, "✅ أُرسل" if "✅" in m else "❌ فشل")))
                time.sleep(_delay)  # تأخير بين الرسائل لتجنب حظر الواتساب
            summary = "اكتمل — ولي أمر: {} | إدارة: {} | فشل: {}".format(ok_p, ok_a, fail)
            self.root.after(0, lambda: self._append_alert_log(summary))
        threading.Thread(target=do, daemon=True).start()

    def _update_alert_row(self, iid, status):
        if not self.tree_alerts.exists(iid): return
        vals = list(self.tree_alerts.item(iid, "values"))
        vals[-1] = status
        self.tree_alerts.item(iid, values=vals,
                               tags=("sent" if "✅" in status else "high",))

    def _append_alert_log(self, msg: str):
        if not hasattr(self, "alert_log"): return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.alert_log.configure(state="normal")
        self.alert_log.insert("end", "[{}] {}\n".format(ts, msg))
        self.alert_log.see("end")
        self.alert_log.configure(state="disabled")

    # ══════════════════════════════════════════════════════════
    # تبويب تصدير نور التلقائي
    # ══════════════════════════════════════════════════════════
    def _build_noor_export_tab(self):
        frame = self.noor_export_frame

        hdr = tk.Frame(frame, bg="#1565C0", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📤 تصدير ملف نور — يدوي وتلقائي",
                 bg="#1565C0", fg="white",
                 font=("Tahoma",13,"bold")).pack(side="right", padx=16, pady=12)

        body = ttk.Frame(frame); body.pack(fill="both", expand=True, padx=15, pady=15)

        # ─ تصدير يدوي
        manual = ttk.LabelFrame(body, text=" 📋 تصدير يدوي ", padding=12)
        manual.pack(fill="x", pady=(0,12))

        mr1 = ttk.Frame(manual); mr1.pack(fill="x", pady=4)
        ttk.Label(mr1, text="التاريخ:", width=14, anchor="e").pack(side="right")
        self.noor_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(mr1, textvariable=self.noor_date_var, width=14).pack(side="right", padx=4)

        mr2 = ttk.Frame(manual); mr2.pack(fill="x", pady=4)
        ttk.Label(mr2, text="مجلد الحفظ:", width=14, anchor="e").pack(side="right")
        self.noor_dir_var = tk.StringVar(value=os.path.abspath(DATA_DIR))
        ttk.Entry(mr2, textvariable=self.noor_dir_var, state="readonly",
                  font=("Courier",9), width=40).pack(side="right", padx=4)
        ttk.Button(mr2, text="تغيير", width=8,
                   command=self._noor_choose_dir).pack(side="left")

        ttk.Button(manual, text="💾 تصدير الآن",
                   command=self._noor_export_now).pack(anchor="e", pady=6)
        self.noor_status = ttk.Label(manual, text="", foreground="green")
        self.noor_status.pack(anchor="e")

        # ─ تصدير تلقائي
        auto = ttk.LabelFrame(body, text=" ⏰ تصدير تلقائي في نهاية اليوم ", padding=12)
        auto.pack(fill="x", pady=(0,12))

        ar1 = ttk.Frame(auto); ar1.pack(fill="x", pady=4)
        self.noor_auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ar1, text="تفعيل التصدير التلقائي اليومي",
                        variable=self.noor_auto_var).pack(side="right")

        ar2 = ttk.Frame(auto); ar2.pack(fill="x", pady=4)
        ttk.Label(ar2, text="وقت التصدير:", width=14, anchor="e").pack(side="right")
        self.noor_hour_var = tk.IntVar(value=13)
        ttk.Spinbox(ar2, from_=10, to=17,
                    textvariable=self.noor_hour_var, width=5).pack(side="right", padx=4)
        ttk.Label(ar2, text=":30 (يومياً أيام الأحد–الخميس)").pack(side="right")

        ttk.Button(auto, text="💾 حفظ إعدادات التصدير التلقائي",
                   command=self._noor_save_auto).pack(anchor="e", pady=6)

        # ─ سجل الملفات المُصدَّرة
        hist = ttk.LabelFrame(body, text=" 📁 ملفات نور المُصدَّرة ", padding=8)
        hist.pack(fill="both", expand=True)

        cols = ("filename","date","size","path")
        self.tree_noor = ttk.Treeview(hist, columns=cols, show="headings", height=8)
        for col, hdr_t, w in zip(cols,
            ["اسم الملف","التاريخ","الحجم","المسار"],
            [200,100,80,300]):
            self.tree_noor.heading(col, text=hdr_t)
            self.tree_noor.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(hist, orient="vertical", command=self.tree_noor.yview)
        self.tree_noor.configure(yscrollcommand=sb.set)
        self.tree_noor.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        ttk.Button(hist, text="📂 فتح المجلد",
                   command=self._noor_open_dir).pack(pady=4)
        frame.after(100, self._noor_load_history)

    def _noor_choose_dir(self):
        d = filedialog.askdirectory(title="اختر مجلد حفظ ملفات نور")
        if d and hasattr(self, "noor_dir_var"):
            self.noor_dir_var.set(d)

    def _noor_export_now(self):
        date_str = self.noor_date_var.get().strip() if hasattr(self,"noor_date_var") else now_riyadh_date()
        save_dir = self.noor_dir_var.get().strip() if hasattr(self,"noor_dir_var") else DATA_DIR
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, "noor_{}.xlsx".format(date_str))
        try:
            export_to_noor_excel(date_str, filename)
            size_kb = os.path.getsize(filename) // 1024
            if hasattr(self,"noor_status"):
                self.noor_status.configure(
                    text="✅ تم التصدير: {} ({} KB)".format(
                        os.path.basename(filename), size_kb),
                    foreground="green")
            frame.after(100, self._noor_load_history)
            messagebox.showinfo("تم التصدير", "تم حفظ ملف نور:\n{}".format(filename))
        except Exception as e:
            if hasattr(self,"noor_status"):
                self.noor_status.configure(
                    text="❌ فشل: {}".format(e), foreground="red")

    def _noor_save_auto(self):
        messagebox.showinfo("تم","إعدادات التصدير التلقائي محفوظة. سيعمل كل يوم عمل في الوقت المحدد.")

    def _noor_open_dir(self):
        d = self.noor_dir_var.get() if hasattr(self,"noor_dir_var") else DATA_DIR
        try: os.startfile(os.path.abspath(d))
        except Exception: webbrowser.open("file://{}".format(os.path.abspath(d)))

    def _noor_load_history(self):
        if not hasattr(self,"tree_noor"): return
        for i in self.tree_noor.get_children(): self.tree_noor.delete(i)
        save_dir = self.noor_dir_var.get().strip() if hasattr(self,"noor_dir_var") else DATA_DIR
        if not os.path.isdir(save_dir): return
        files = sorted(
            [f for f in os.listdir(save_dir) if f.startswith("noor_") and f.endswith(".xlsx")],
            reverse=True)
        for f in files[:30]:
            full = os.path.join(save_dir, f)
            size = "{} KB".format(os.path.getsize(full)//1024) if os.path.exists(full) else "—"
            date = f.replace("noor_","").replace(".xlsx","")
            self.tree_noor.insert("","end", values=(f, date, size, full))


    def open_student_analysis(self, student_id: str):
        """نافذة تحليل شاملة للطالب — تُفتح بنقرة مزدوجة."""
        import threading as _th

        win = tk.Toplevel(self.root)
        win.title("تحليل الطالب...")
        win.geometry("980x660")
        try: win.state("zoomed")
        except: pass

        loading = ttk.Label(win, text="⏳ جارٍ التحميل...", font=("Tahoma",14))
        loading.pack(expand=True)

        def _load():
            data = get_student_full_analysis(student_id)
            win.after(0, lambda: _build(data))

        def _build(d):
            loading.destroy()
            win.title("تحليل: {} — {}".format(d["name"], d["class_name"]))
            cfg_thresh = load_config().get("alert_absence_threshold", 5)

            # رأس
            hdr = tk.Frame(win, bg="#1565C0", height=54)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            tk.Label(hdr,
                text="👤 {}    {}    📞 {}".format(
                    d["name"], d["class_name"], d["phone"] or "لا رقم"),
                bg="#1565C0", fg="white",
                font=("Tahoma",12,"bold")).pack(side="right", padx=14, pady=14)

            # بطاقات
            cards = tk.Frame(win, bg="#F5F7FA")
            cards.pack(fill="x", padx=10, pady=6)

            def card(parent, title, val, color, sub=""):
                fr = tk.Frame(parent, bg="white", relief="groove", bd=1)
                fr.pack(side="right", padx=5, fill="x", expand=True, ipadx=8, ipady=6)
                tk.Label(fr, text=title, bg="white", fg="#5A6A7E",
                         font=("Tahoma",8,"bold")).pack(anchor="w", padx=6)
                tk.Label(fr, text=str(val), bg="white", fg=color,
                         font=("Tahoma",20,"bold")).pack(anchor="w", padx=6)
                if sub: tk.Label(fr, text=sub, bg="white", fg="#9CA3AF",
                                  font=("Tahoma",8)).pack(anchor="w", padx=6)

            ab_color = "#C62828" if d["total_absences"] >= cfg_thresh else "#1565C0"
            card(cards, "إجمالي الغياب",  d["total_absences"],  ab_color,
                 "العتبة: {} أيام".format(cfg_thresh))
            card(cards, "غياب مبرر",       d["excused_days"],    "#2E7D32")
            card(cards, "غياب غير مبرر",   d["unexcused_days"],  "#C62828")
            card(cards, "حالات التأخر",    d["total_tardiness"], "#E65100")
            card(cards, "استئذانات",       d.get("total_permissions",0), "#0277BD")
            card(cards, "متوسط الفصل",    d["class_avg"],       "#5A6A7E",
                 "مقارنة بالزملاء")

            # Notebook
            nb = ttk.Notebook(win)
            nb.pack(fill="both", expand=True, padx=10, pady=(0,6))

            # ── سجل الغياب
            tab_abs = ttk.Frame(nb); nb.add(tab_abs, text="📋 سجل الغياب")
            tr1 = ttk.Treeview(tab_abs,
                columns=("date","period","teacher"), show="headings", height=14)
            for c,h,w in zip(("date","period","teacher"),
                             ["التاريخ","الحصة","المعلم"],[130,80,200]):
                tr1.heading(c,text=h); tr1.column(c,width=w,anchor="center")
            excused_set = {r["date"] for r in d["excuse_rows"]}
            tr1.tag_configure("ok",  background="#E8F5E9", foreground="#2E7D32")
            tr1.tag_configure("nok", background="#FFEBEE", foreground="#C62828")
            for r in d["absence_rows"]:
                tag = "ok" if r["date"] in excused_set else "nok"
                tr1.insert("","end", tags=(tag,),
                    values=(r["date"], r.get("period",""), r.get("teacher_name","")))
            sb1 = ttk.Scrollbar(tab_abs, orient="vertical", command=tr1.yview)
            tr1.configure(yscrollcommand=sb1.set)
            tr1.pack(side="left", fill="both", expand=True)
            sb1.pack(side="right", fill="y")

            # ── رسم شهري
            tab_m = ttk.Frame(nb); nb.add(tab_m, text="📊 شهري")
            try:
                from matplotlib.figure import Figure
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                fig = Figure(figsize=(8,3.2), dpi=90)
                ax  = fig.add_subplot(111)
                if d["monthly"]:
                    months = [r["month"] for r in reversed(d["monthly"])]
                    days   = [r["days"]  for r in reversed(d["monthly"])]
                    colors = ["#C62828" if v>=cfg_thresh else "#1565C0" for v in days]
                    ax.bar(months, days, color=colors)
                    ax.axhline(cfg_thresh, color="#E65100", linestyle="--",
                               linewidth=1.2, label=ar("العتبة"))
                    ax.legend(fontsize=8)
                ax.set_title(ar("الغياب الشهري"), fontsize=10)
                FigureCanvasTkAgg(fig, tab_m).get_tk_widget().pack(
                    fill="both", expand=True, padx=6, pady=6)
            except Exception as e:
                ttk.Label(tab_m, text="تعذّر الرسم: {}".format(e)).pack(pady=20)

            # ── أيام الأسبوع
            tab_d = ttk.Frame(nb); nb.add(tab_d, text="📅 أيام الأسبوع")
            try:
                from matplotlib.figure import Figure
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                fig2 = Figure(figsize=(6,3), dpi=90)
                ax2  = fig2.add_subplot(111)
                dow  = d["dow_count"]
                vals = list(dow.values())
                mx   = max(vals) if vals else 1
                ax2.bar([ar(k) for k in dow],vals,
                        color=["#C62828" if v==mx and v>0 else "#90CAF9" for v in vals])
                ax2.set_title(ar("توزيع الغياب على أيام الأسبوع"), fontsize=10)
                FigureCanvasTkAgg(fig2, tab_d).get_tk_widget().pack(
                    fill="both", expand=True, padx=6, pady=6)
            except Exception as e:
                ttk.Label(tab_d, text="تعذّر الرسم: {}".format(e)).pack(pady=20)

            # ── التأخر
            tab_t = ttk.Frame(nb); nb.add(tab_t, text="⏱ التأخر")
            tr2 = ttk.Treeview(tab_t, columns=("date","mins"), show="headings", height=14)
            for c,h,w in zip(("date","mins"),["التاريخ","الدقائق"],[150,120]):
                tr2.heading(c,text=h); tr2.column(c,width=w,anchor="center")
            tr2.tag_configure("heavy", background="#FFF8E1", foreground="#E65100")
            for r in d["tardiness_rows"]:
                mins = r.get("minutes_late",0)
                tr2.insert("","end", tags=("heavy",) if mins>=15 else (),
                    values=(r["date"], "{} دقيقة".format(mins)))
            tr2.pack(fill="both", expand=True, padx=5, pady=5)

            # ── الأعذار
            tab_e = ttk.Frame(nb); nb.add(tab_e, text="📋 الأعذار")
            tr3 = ttk.Treeview(tab_e,
                columns=("date","reason","source"), show="headings", height=14)
            for c,h,w in zip(("date","reason","source"),
                             ["التاريخ","السبب","المصدر"],[130,220,100]):
                tr3.heading(c,text=h); tr3.column(c,width=w,anchor="center")
            tr3.tag_configure("wa", background="#E8F5E9")
            for r in d["excuse_rows"]:
                tag = "wa" if r.get("source")=="whatsapp" else ""
                tr3.insert("","end", tags=(tag,) if tag else (),
                    values=(r["date"], r.get("reason",""),
                            "واتساب" if r.get("source")=="whatsapp" else "إداري"))
            tr3.pack(fill="both", expand=True, padx=5, pady=5)

            # ── الاستئذانات
            tab_p = ttk.Frame(nb); nb.add(tab_p, text="🚪 الاستئذانات")
            tr4 = ttk.Treeview(tab_p,
                columns=("date","reason","status","approved_by"),
                show="headings", height=14)
            for c,h,w in zip(
                ("date","reason","status","approved_by"),
                ["التاريخ","السبب","الحالة","الموافق"],
                [120,180,90,140]):
                tr4.heading(c,text=h); tr4.column(c,width=w,anchor="center")
            tr4.tag_configure("approved", background="#E8F5E9", foreground="#2E7D32")
            tr4.tag_configure("rejected", background="#FFEBEE", foreground="#C62828")
            tr4.tag_configure("waiting",  background="#FFF8E1", foreground="#E65100")
            for r in d.get("perm_rows",[]):
                s   = r.get("status","انتظار")
                tag = {"موافق":"approved","مرفوض":"rejected","انتظار":"waiting"}.get(s,"waiting")
                tr4.insert("","end", tags=(tag,),
                    values=(r["date"], r.get("reason",""), s, r.get("approved_by","")))
            tr4.pack(fill="both", expand=True, padx=5, pady=5)

            # ── تبويب إجراءات الموجّه الطلابي ─────────────────────────
            tab_c = ttk.Frame(nb); nb.add(tab_c, text="📋 إجراءات الموجّه")

            # رأس ملوّن
            c_hdr = tk.Frame(tab_c, bg="#7c3aed", pady=6)
            c_hdr.pack(fill="x")
            tk.Label(c_hdr, text="📋 سجل إجراءات الموجّه الطلابي",
                     bg="#7c3aed", fg="white", font=("Tahoma",11,"bold")).pack(side="right", padx=10)
            tk.Button(c_hdr, text="➕ عقد جلسة إرشادية جديدة",
                      bg="#5b21b6", fg="white", font=("Tahoma",9,"bold"),
                      relief="flat", padx=10, pady=3, cursor="hand2",
                      command=lambda: self._open_session_dialog(
                          sid=student_id,
                          sname=d["name"], sclass=d["class_name"],
                          sabs=str(d["total_absences"]), stard=str(d["total_tardiness"])
                      )).pack(side="left", padx=10)
            tk.Button(c_hdr, text="📋 عقد سلوكي جديد",
                      bg="#d97706", fg="white", font=("Tahoma",9,"bold"),
                      relief="flat", padx=10, pady=3, cursor="hand2",
                      command=lambda: self._open_behavioral_contract_dialog(
                          sid=student_id,
                          sname=d["name"], sclass=d["class_name"]
                      )).pack(side="left", padx=4)

            # بطاقات ملخص
            c_cards = tk.Frame(tab_c, bg="#f5f3ff", pady=4)
            c_cards.pack(fill="x", padx=6, pady=4)

            con_c = get_db(); con_c.row_factory = sqlite3.Row; cur_c = con_c.cursor()
            cur_c.execute("SELECT COUNT(*) as cnt FROM counselor_sessions WHERE student_id=?", (student_id,))
            sess_count = (cur_c.fetchone() or {"cnt":0})["cnt"]
            cur_c.execute("SELECT COUNT(*) as cnt FROM counselor_alerts WHERE student_id=?", (student_id,))
            alert_count = (cur_c.fetchone() or {"cnt":0})["cnt"]
            cur_c.execute("SELECT COUNT(*) as cnt FROM behavioral_contracts WHERE student_id=?", (student_id,))
            contract_count = (cur_c.fetchone() or {"cnt":0})["cnt"]
            cur_c.execute("SELECT * FROM counselor_sessions WHERE student_id=? ORDER BY date DESC", (student_id,))
            sessions_list = [dict(r) for r in cur_c.fetchall()]
            cur_c.execute("SELECT * FROM counselor_alerts WHERE student_id=? ORDER BY date DESC", (student_id,))
            alerts_list = [dict(r) for r in cur_c.fetchall()]
            cur_c.execute("SELECT * FROM behavioral_contracts WHERE student_id=? ORDER BY date DESC", (student_id,))
            contracts_list = [dict(r) for r in cur_c.fetchall()]
            con_c.close()

            for val, lbl, color in [
                (str(sess_count),      "جلسات إرشادية",      "#7c3aed"),
                (str(contract_count),  "عقود سلوكية",         "#d97706"),
                (str(alert_count),     "تنبيهات/استدعاءات",  "#1d4ed8"),
                (str(d["total_absences"]), "أيام الغياب",     "#C62828"),
                (str(d["total_tardiness"]), "مرات التأخر",    "#E65100"),
            ]:
                cf = tk.Frame(c_cards, bg="white", relief="groove", bd=1)
                cf.pack(side="right", padx=5, pady=2, ipadx=10, ipady=4)
                tk.Label(cf, text=val, bg="white", fg=color,
                         font=("Tahoma",18,"bold")).pack()
                tk.Label(cf, text=lbl, bg="white", fg="#5A6A7E",
                         font=("Tahoma",8)).pack()

            # Notebook داخلي للجلسات والتنبيهات
            c_nb = ttk.Notebook(tab_c)
            c_nb.pack(fill="both", expand=True, padx=6, pady=4)

            # تبويب الجلسات
            c_tab_s = ttk.Frame(c_nb); c_nb.add(c_tab_s, text="📝 الجلسات الإرشادية")
            c_tr_s = ttk.Treeview(c_tab_s,
                columns=("date","title","goals","recs"), show="headings", height=8)
            for col, hd, wd in zip(
                ("date","title","goals","recs"),
                ["التاريخ","عنوان الجلسة","الأهداف","التوصيات"],
                [110, 160, 280, 280]):
                c_tr_s.heading(col, text=hd)
                c_tr_s.column(col, width=wd, anchor="center")
            c_tr_s.tag_configure("sess", background="#f5f3ff")
            for s in sessions_list:
                notes_raw = s.get("notes","")
                goals_part = ""
                recs_part  = ""
                for part in notes_raw.split("\n"):
                    if part.startswith("الأهداف:"): goals_part = part.replace("الأهداف:","").strip()[:60]
                    if part.startswith("التوصيات:"): recs_part = part.replace("التوصيات:","").strip()[:60]
                c_tr_s.insert("","end", tags=("sess",),
                    values=(s["date"], s.get("reason",""),
                            goals_part or s.get("reason",""),
                            recs_part  or s.get("action_taken","")))
            c_sb_s = ttk.Scrollbar(c_tab_s, orient="vertical", command=c_tr_s.yview)
            c_tr_s.configure(yscrollcommand=c_sb_s.set)
            c_tr_s.pack(side="left", fill="both", expand=True)
            c_sb_s.pack(side="right", fill="y")

            # تبويب التنبيهات والاستدعاءات
            c_tab_a = ttk.Frame(c_nb); c_nb.add(c_tab_a, text="🔔 التنبيهات والاستدعاءات")
            c_tr_a = ttk.Treeview(c_tab_a,
                columns=("date","type","method","status"), show="headings", height=8)
            for col, hd, wd in zip(
                ("date","type","method","status"),
                ["التاريخ","النوع","الوسيلة","الحالة"],
                [120, 150, 120, 120]):
                c_tr_a.heading(col, text=hd)
                c_tr_a.column(col, width=wd, anchor="center")
            c_tr_a.tag_configure("sent",    background="#E8F5E9", foreground="#2E7D32")
            c_tr_a.tag_configure("pending", background="#FFF8E1", foreground="#E65100")
            for a in alerts_list:
                tag = "sent" if a.get("status","") == "sent" else "pending"
                c_tr_a.insert("","end", tags=(tag,),
                    values=(a["date"], a.get("type",""), a.get("method",""),
                            "تم الإرسال" if a.get("status","")=="sent" else a.get("status","")))
            c_sb_a = ttk.Scrollbar(c_tab_a, orient="vertical", command=c_tr_a.yview)
            c_tr_a.configure(yscrollcommand=c_sb_a.set)
            c_tr_a.pack(side="left", fill="both", expand=True)
            c_sb_a.pack(side="right", fill="y")

            # تبويب العقود السلوكية
            c_tab_bc = ttk.Frame(c_nb)
            c_nb.add(c_tab_bc, text="📄 العقود السلوكية ({})".format(len(contracts_list)))
            bc_hdr2 = tk.Frame(c_tab_bc, bg="#d97706", pady=4)
            bc_hdr2.pack(fill="x")
            tk.Label(bc_hdr2, text="📄 العقود السلوكية",
                     bg="#d97706", fg="white", font=("Tahoma",10,"bold")).pack(side="right", padx=10)
            tk.Button(bc_hdr2, text="➕ عقد سلوكي جديد",
                      bg="#92400e", fg="white", font=("Tahoma",9,"bold"),
                      relief="flat", padx=8, pady=2, cursor="hand2",
                      command=lambda: self._open_behavioral_contract_dialog(
                          sid=student_id, sname=d["name"], sclass=d["class_name"]
                      )).pack(side="left", padx=8)
            bc_cols2 = ("date","subject","period_from","period_to","notes")
            c_tr_bc = ttk.Treeview(c_tab_bc, columns=bc_cols2, show="headings", height=8)
            for col, hd, wd in zip(bc_cols2,
                                    ["التاريخ","المادة","الفترة من","الفترة إلى","الملاحظات"],
                                    [110,140,100,100,260]):
                c_tr_bc.heading(col, text=hd); c_tr_bc.column(col, width=wd, anchor="center")
            c_tr_bc.tag_configure("contract", background="#fff7ed")
            c_sb_bc = ttk.Scrollbar(c_tab_bc, orient="vertical", command=c_tr_bc.yview)
            c_tr_bc.configure(yscrollcommand=c_sb_bc.set)
            c_tr_bc.pack(side="left", fill="both", expand=True)
            c_sb_bc.pack(side="right", fill="y")
            for ct in contracts_list:
                c_tr_bc.insert("","end", tags=("contract",),
                    values=(ct.get("date",""), ct.get("subject",""),
                            ct.get("period_from",""), ct.get("period_to",""),
                            (ct.get("notes","") or "")[:80]))
            if not contracts_list:
                tk.Label(c_tab_bc, text="لا توجد عقود سلوكية مسجّلة لهذا الطالب.",
                         fg="#9CA3AF", font=("Tahoma",10)).pack(pady=20)

            # تبويب ملف الطالب الإرشادي المجمّع
            c_tab_f = ttk.Frame(c_nb); c_nb.add(c_tab_f, text="📄 الملف الإرشادي")
            c_txt = tk.Text(c_tab_f, font=("Tahoma",9), relief="flat", wrap="word",
                            bg="#fafafa", state="normal")
            c_txt.pack(fill="both", expand=True, padx=6, pady=6)

            # بناء الملف النصي
            file_lines = []
            file_lines.append(f"{'='*55}")
            file_lines.append(f"  الملف الإرشادي للطالب: {d['name']}")
            file_lines.append(f"  الفصل: {d['class_name']}   |   إجمالي الغياب: {d['total_absences']} يوم")
            file_lines.append(f"{'='*55}")
            if sessions_list:
                file_lines.append("\n📝 الجلسات الإرشادية:")
                for i, s in enumerate(sessions_list, 1):
                    file_lines.append(f"\n  [{i}] التاريخ: {s['date']} — {s.get('reason','')}")
                    if s.get("notes"):
                        for ln in s["notes"].split("\n"):
                            if ln.strip(): file_lines.append(f"       {ln.strip()}")
                    if s.get("action_taken"):
                        file_lines.append(f"       الإجراء: {s['action_taken']}")
            else:
                file_lines.append("\n  لا توجد جلسات إرشادية مسجّلة.")

            if alerts_list:
                file_lines.append(f"\n{'─'*50}")
                file_lines.append("🔔 التنبيهات والاستدعاءات:")
                for i, a in enumerate(alerts_list, 1):
                    file_lines.append(f"  [{i}] {a['date']} — {a.get('type','')} عبر {a.get('method','')}")
            else:
                file_lines.append("\n  لا توجد تنبيهات مسجّلة.")

            if contracts_list:
                file_lines.append(f"\n{'─'*50}")
                file_lines.append("📄 العقود السلوكية:")
                for i, ct in enumerate(contracts_list, 1):
                    period = f"  |  الفترة: {ct.get('period_from','')} — {ct.get('period_to','')}" if (ct.get("period_from") or ct.get("period_to")) else ""
                    file_lines.append(f"  [{i}] {ct.get('date','')} — مادة: {ct.get('subject','')}{period}")
                    if ct.get("notes"):
                        file_lines.append(f"       ملاحظات: {ct['notes'][:100]}")
            else:
                file_lines.append("\n  لا توجد عقود سلوكية مسجّلة.")

            file_lines.append(f"\n{'='*55}")
            c_txt.insert("1.0", "\n".join(file_lines))
            c_txt.configure(state="disabled")

            # أزرار
            acts = tk.Frame(win, bg="white"); acts.pack(fill="x", padx=10, pady=(0,8))
            ttk.Button(acts, text="🖨️ طباعة التقرير",
                       command=lambda: self._print_student_report(
                           student_id)).pack(side="right", padx=4)
            base = (STATIC_DOMAIN if STATIC_DOMAIN else
                    "http://{}:{}".format(local_ip(), PORT))
            portal_url = "{}/parent/{}".format(base, student_id)
            ttk.Button(acts, text="🔗 نسخ رابط ولي الأمر",
                       command=lambda u=portal_url: (
                           self.root.clipboard_clear(),
                           self.root.clipboard_append(u),
                           messagebox.showinfo("تم","✅ تم نسخ الرابط:\n"+u,parent=win)
                       )).pack(side="right", padx=4)
            ttk.Button(acts, text="🌐 فتح لوحة ولي الأمر",
                       command=lambda u=portal_url: webbrowser.open(u)
                       ).pack(side="right", padx=4)

        _th.Thread(target=_load, daemon=True).start()

    def _print_student_report(self, student_id):
        try:
            html = generate_student_report(student_id)
            tmp  = os.path.join(DATA_DIR, "stu_report.html")
            with open(tmp,"w",encoding="utf-8") as f: f.write(html)
            webbrowser.open("file://{}".format(os.path.abspath(tmp)))
        except Exception as e:
            messagebox.showerror("خطأ", str(e))


    def _on_log_dblclick(self, event):
        sel = self.tree_logs.selection()
        if not sel: return
        vals = self.tree_logs.item(sel[0], "values")
        # vals = (date, class_id, class_name, student_id, student_name, ...)
        if len(vals) > 3 and vals[3]:
            self.open_student_analysis(vals[3])


    def _on_dash_dblclick(self, event):
        """نقرة مزدوجة على فصل في لوحة المراقبة → نافذة طلاب الفصل."""
        if not hasattr(self,"tree_dash"): return
        sel = self.tree_dash.selection()
        if not sel: return
        vals = self.tree_dash.item(sel[0], "values")
        # vals = (class_id, class_name, total, present, absent, pct)
        if not vals: return
        class_id   = vals[0]
        class_name = vals[1]
        self._open_class_students_dialog(class_id, class_name)

    def _on_top_absent_dblclick(self, event):
        """نقرة مزدوجة على طالب في قائمة الأكثر غياباً → تحليله مباشرة."""
        if not hasattr(self,"tree_top_absent"): return
        sel = self.tree_top_absent.selection()
        if not sel: return
        vals = self.tree_top_absent.item(sel[0], "values")
        # vals = (name, class_name, days, last_date)
        if not vals: return
        name = vals[0]
        # ابحث عن student_id بالاسم
        store = load_students()
        for cls in store["list"]:
            for s in cls["students"]:
                if s["name"] == name:
                    self.open_student_analysis(s["id"])
                    return


    def _refresh_counselor_data(self):
        """تحديث القائمة مع مسح حقل البحث."""
        self.counselor_search_var.set("")
        self._load_counselor_data()

    def _open_class_students_dialog(self, class_id: str, class_name: str):
        """نافذة تعرض طلاب الفصل — نقرة مزدوجة على أي منهم تفتح تحليله."""
        win = tk.Toplevel(self.root)
        win.title("طلاب {} — اختر طالباً لتحليله".format(class_name))
        win.geometry("500x420")
        win.transient(self.root)

        tk.Label(win, text="طلاب {} — انقر مزدوجاً لتحليل أي طالب".format(class_name),
                 font=("Tahoma",11,"bold"),
                 bg="#1565C0", fg="white").pack(fill="x", ipady=10)

        cols = ("student_id","name","absences")
        tr = ttk.Treeview(win, columns=cols, show="headings", height=16)
        for c,h,w in zip(cols,["رقم الطالب","اسم الطالب","أيام الغياب"],[120,250,100]):
            tr.heading(c,text=h); tr.column(c,width=w,anchor="center")
        tr.tag_configure("has_abs", background="#FFEBEE", foreground="#C62828")

        # حمّل الطلاب وغيابهم
        store = load_students()
        cls_obj = next((c for c in store["list"] if c["id"]==class_id), None)
        if cls_obj:
            import sqlite3 as _sq
            con = _sq.connect(DB_PATH); con.row_factory = _sq.Row; cur = con.cursor()
            month = datetime.datetime.now().strftime("%Y-%m")
            cur.execute("""SELECT student_id, COUNT(DISTINCT date) as cnt
                           FROM absences WHERE class_id=? AND date LIKE ?
                           GROUP BY student_id""", (class_id, month+"%"))
            abs_map = {r["student_id"]: r["cnt"] for r in cur.fetchall()}
            con.close()

            for s in sorted(cls_obj["students"], key=lambda x: x["name"]):
                cnt = abs_map.get(s["id"], 0)
                tag = "has_abs" if cnt > 0 else ""
                tr.insert("","end", iid=s["id"], tags=(tag,) if tag else (),
                    values=(s["id"], s["name"],
                            "{} يوم".format(cnt) if cnt else "—"))

        sb = ttk.Scrollbar(win, orient="vertical", command=tr.yview)
        tr.configure(yscrollcommand=sb.set)
        tr.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def on_dbl(event):
            sel = tr.selection()
            if not sel: return
            self.open_student_analysis(sel[0])

        tr.bind("<Double-1>", on_dbl)
        ttk.Label(win, text="انقر مزدوجاً على أي طالب لفتح تحليله",
                  foreground="#5A6A7E").pack(pady=6)


    # ─── تبويب الموجّه الطلابي ─────────────────────────────────────────
    # ─── تبويب الموجّه الطلابي ─────────────────────────────────────────
    def _build_counselor_tab(self):
        """بناء واجهة الموجّه الطلابي."""
        frame = self.counselor_frame

        # رأس التبويب
        hdr = tk.Frame(frame, bg="#7c3aed", height=60)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="👨\u200d🏫 مكتب الموجّه الطلابي", bg="#7c3aed", fg="white",
                 font=("Tahoma", 14, "bold")).pack(side="right", padx=20, pady=15)

        # ── شريط اختيار الموجّه النشط ──────────────────────────────
        _cfg_c = load_config()
        c1_name = _cfg_c.get("counselor1_name", "").strip() or "الموجّه الطلابي 1"
        c2_name = _cfg_c.get("counselor2_name", "").strip() or "الموجّه الطلابي 2"

        active_bar = tk.Frame(frame, bg="#ede9fe", pady=6)
        active_bar.pack(fill="x")

        tk.Label(active_bar, text="الموجّه العامل الآن:", bg="#ede9fe",
                 font=("Tahoma", 10, "bold"), fg="#5b21b6").pack(side="right", padx=(0, 14))

        self._active_counselor_var = tk.StringVar(
            value=_cfg_c.get("active_counselor", "1"))

        def _on_counselor_change(*_):
            """حفظ الاختيار فوراً في الإعداد."""
            cfg2 = load_config()
            cfg2["active_counselor"] = self._active_counselor_var.get()
            try:
                with open(CONFIG_JSON, "w", encoding="utf-8") as _f:
                    json.dump(cfg2, _f, ensure_ascii=False, indent=2)
                invalidate_config_cache()
                self._refresh_active_counselor_label()
            except Exception as _e:
                print("[counselor] خطأ حفظ:", _e)

        rb1 = tk.Radiobutton(active_bar, text=c1_name,
                             variable=self._active_counselor_var, value="1",
                             bg="#ede9fe", font=("Tahoma", 10, "bold"),
                             fg="#5b21b6", activebackground="#ede9fe",
                             selectcolor="#7c3aed", command=_on_counselor_change)
        rb1.pack(side="right", padx=8)

        rb2 = tk.Radiobutton(active_bar, text=c2_name,
                             variable=self._active_counselor_var, value="2",
                             bg="#ede9fe", font=("Tahoma", 10, "bold"),
                             fg="#5b21b6", activebackground="#ede9fe",
                             selectcolor="#7c3aed", command=_on_counselor_change)
        rb2.pack(side="right", padx=8)

        self._active_lbl = tk.Label(active_bar, text="", bg="#ede9fe",
                                    font=("Tahoma", 9, "italic"), fg="#7c3aed")
        self._active_lbl.pack(side="left", padx=16)
        self._refresh_active_counselor_label()
        # ────────────────────────────────────────────────────────────

        # منطقة البحث والاختيار
        search_fr = tk.Frame(frame, bg="#f8fafc", pady=10)
        search_fr.pack(fill="x", padx=20, pady=10)

        tk.Label(search_fr, text="بحث عن طالب:", bg="#f8fafc").pack(side="right", padx=5)
        self.counselor_search_var = tk.StringVar()
        search_ent = ttk.Entry(search_fr, textvariable=self.counselor_search_var, width=30)
        search_ent.pack(side="right", padx=5)
        search_ent.bind("<KeyRelease>", lambda e: self._filter_counselor_students())

        # قائمة الطلاب (الذين لديهم غياب أو تأخر متكرر)
        list_fr = tk.Frame(frame, bg="white")
        list_fr.pack(fill="both", expand=True, padx=20, pady=5)

        cols = ("id", "name", "class", "absences", "tardiness", "last_action")
        self.tree_counselor = ttk.Treeview(list_fr, columns=cols, show="headings", height=10)

        headings = {"id":"ID", "name":"اسم الطالب", "class":"الفصل",
                    "absences":"أيام الغياب", "tardiness":"مرات التأخر", "last_action":"آخر إجراء"}
        for c, h in headings.items():
            self.tree_counselor.heading(c, text=h)
            self.tree_counselor.column(c, width=100 if c in ("absences","tardiness") else 150, anchor="center")

        self.tree_counselor.column("id", width=0, stretch=False)  # إخفاء المعرف

        sb = ttk.Scrollbar(list_fr, orient="vertical", command=self.tree_counselor.yview)
        self.tree_counselor.configure(yscrollcommand=sb.set)
        self.tree_counselor.pack(side="right", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self.tree_counselor.bind("<<TreeviewSelect>>", self._on_counselor_student_select)

        # أزرار الإجراءات
        btn_fr = tk.Frame(frame, bg="white", pady=10)
        btn_fr.pack(fill="x", padx=20)

        ttk.Button(btn_fr, text="📝 عقد جلسة إرشادية", command=self._open_session_dialog).pack(side="right", padx=5)
        ttk.Button(btn_fr, text="📋 عقد سلوكي", command=self._open_behavioral_contract_dialog,
                   style="Accent.TButton").pack(side="right", padx=5)
        ttk.Button(btn_fr, text="🔔 إرسال تنبيه (واتساب)", command=lambda: self._send_counselor_alert("تنبيه")).pack(side="right", padx=5)
        ttk.Button(btn_fr, text="✉️ توجيه استدعاء رسمي", command=lambda: self._send_counselor_alert("استدعاء")).pack(side="right", padx=5)
        ttk.Button(btn_fr, text="📊 سجل الطالب الإرشادي", command=self._show_student_counseling_history).pack(side="right", padx=5)
        ttk.Button(btn_fr, text="🔄 تحديث القائمة", command=self._refresh_counselor_data).pack(side="left", padx=5)
        # ── زر إضافة طالب يدوياً للموجّه ─────────────────────────
        tk.Button(btn_fr, text="➕ إضافة طالب يدوياً",
                  bg="#7c3aed", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._add_student_to_counselor_manually).pack(side="left", padx=8)
        # ── زر حذف الطالب من قائمة الموجّه ───────────────────────
        tk.Button(btn_fr, text="🗑️ حذف الطالب",
                  bg="#dc2626", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._delete_student_from_counselor).pack(side="left", padx=4)

        # ── شريط أرشيف الجلسات ──────────────────────────────────
        arch_bar = tk.Frame(frame, bg="#f5f3ff", pady=6, relief="groove", bd=1)
        arch_bar.pack(fill="x", padx=20, pady=(4, 4))
        tk.Label(arch_bar, text="📚 أرشيف الجلسات الإرشادية:", bg="#f5f3ff",
                 font=("Tahoma", 10, "bold"), fg="#5b21b6").pack(side="right", padx=10)
        tk.Button(arch_bar, text="🗂️ عرض جميع الجلسات القديمة",
                  bg="#7c3aed", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=4,
                  command=self._open_sessions_archive).pack(side="right", padx=8)
        tk.Label(arch_bar, text="اضغط لاسترجاع أي جلسة وطباعتها أو إرسالها",
                 bg="#f5f3ff", font=("Tahoma", 9), fg="#7c3aed").pack(side="right", padx=4)

        # ── شريط أرشيف العقود السلوكية ──────────────────────────
        contract_bar = tk.Frame(frame, bg="#fef3c7", pady=6, relief="groove", bd=1)
        contract_bar.pack(fill="x", padx=20, pady=(2, 8))
        tk.Label(contract_bar, text="📄 أرشيف العقود السلوكية:", bg="#fef3c7",
                 font=("Tahoma", 10, "bold"), fg="#92400e").pack(side="right", padx=10)
        tk.Button(contract_bar, text="🗂️ عرض جميع العقود السلوكية",
                  bg="#d97706", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=4,
                  command=self._open_contracts_archive).pack(side="right", padx=8)
        tk.Label(contract_bar, text="اضغط لاسترجاع أي عقد وطباعته أو إرساله",
                 bg="#fef3c7", font=("Tahoma", 9), fg="#92400e").pack(side="right", padx=4)
        # ────────────────────────────────────────────────────────

        self._load_counselor_data()

    def _get_active_counselor_name(self) -> str:
        """يُرجع اسم الموجّه النشط حالياً."""
        cfg = load_config()
        which = cfg.get("active_counselor", "1")
        if which == "2":
            name = cfg.get("counselor2_name", "").strip()
            return name if name else "الموجّه الطلابي 2"
        else:
            name = cfg.get("counselor1_name", "").strip()
            return name if name else "الموجّه الطلابي 1"

    def _refresh_active_counselor_label(self):
        """يحدّث نص التسمية التوضيحية للموجّه النشط."""
        if not hasattr(self, "_active_lbl"):
            return
        name = self._get_active_counselor_name()
        self._active_lbl.config(text=f"✅ يعمل الآن: {name}")

    def _add_student_to_counselor_manually(self):
        """إضافة أي طالب يدوياً لقائمة الموجّه الطلابي بدون الحاجة لتحويل من وكيل شؤون الطلاب."""
        win = tk.Toplevel(self.root)
        win.title("➕ إضافة طالب يدوياً للموجّه")
        win.geometry("500x420")
        win.resizable(False, False)
        win.grab_set()

        # رأس النافذة
        hdr = tk.Frame(win, bg="#7c3aed", height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="➕ إضافة طالب يدوياً لقائمة الموجّه",
                 bg="#7c3aed", fg="white", font=("Tahoma", 12, "bold")).pack(pady=13)

        body = tk.Frame(win, bg="white", padx=20, pady=15)
        body.pack(fill="both", expand=True)

        # ── اختيار الطالب من قائمة الفصول ──────────────────────
        tk.Label(body, text="الفصل:", bg="white", font=("Tahoma", 10, "bold"),
                 anchor="e").grid(row=0, column=1, sticky="e", pady=6, padx=5)
        class_var = tk.StringVar()
        class_cb = ttk.Combobox(body, textvariable=class_var, state="readonly", width=28, font=("Tahoma", 10))
        class_cb.grid(row=0, column=0, sticky="w", pady=6)

        tk.Label(body, text="الطالب:", bg="white", font=("Tahoma", 10, "bold"),
                 anchor="e").grid(row=1, column=1, sticky="e", pady=6, padx=5)
        student_var = tk.StringVar()
        student_cb = ttk.Combobox(body, textvariable=student_var, state="readonly", width=28, font=("Tahoma", 10))
        student_cb.grid(row=1, column=0, sticky="w", pady=6)

        tk.Label(body, text="سبب الإضافة:", bg="white", font=("Tahoma", 10, "bold"),
                 anchor="e").grid(row=2, column=1, sticky="e", pady=6, padx=5)
        reason_var = tk.StringVar(value="غياب")
        reason_cb = ttk.Combobox(body, textvariable=reason_var, state="readonly", width=28, font=("Tahoma", 10),
                                  values=["غياب", "تأخر", "سلوك", "أكاديمي", "أخرى"])
        reason_cb.grid(row=2, column=0, sticky="w", pady=6)

        tk.Label(body, text="ملاحظات:", bg="white", font=("Tahoma", 10, "bold"),
                 anchor="e").grid(row=3, column=1, sticky="ne", pady=6, padx=5)
        notes_txt = tk.Text(body, width=30, height=4, font=("Tahoma", 10))
        notes_txt.grid(row=3, column=0, sticky="w", pady=6)

        # ── تحميل بيانات الطلاب ──────────────────────────────────
        store = load_students()
        classes_data = {}  # {class_name: [(student_id, student_name), ...]}
        for cls in store.get("list", []):
            cname = cls.get("name", "")
            classes_data[cname] = [(s["id"], s["name"]) for s in cls.get("students", [])]

        class_cb["values"] = sorted(classes_data.keys())

        def _on_class_change(event=None):
            chosen = class_var.get()
            students = classes_data.get(chosen, [])
            student_cb["values"] = [f"{s[1]} ({s[0]})" for s in students]
            student_cb.set("")
        class_cb.bind("<<ComboboxSelected>>", _on_class_change)

        # ── زر الحفظ ─────────────────────────────────────────────
        def _do_save():
            cname   = class_var.get().strip()
            stu_sel = student_var.get().strip()
            reason  = reason_var.get().strip()
            notes   = notes_txt.get("1.0", "end").strip()

            if not cname or not stu_sel:
                messagebox.showwarning("تنبيه", "الرجاء اختيار الفصل والطالب", parent=win)
                return

            # استخراج الـ id والاسم من النص المختار (الصيغة: "اسم الطالب (id)")
            import re as _re
            m = _re.match(r"^(.*)\s+\((\w+)\)$", stu_sel)
            if not m:
                messagebox.showerror("خطأ", "لم يتم التعرف على الطالب المختار", parent=win)
                return
            sname = m.group(1).strip()
            sid   = m.group(2).strip()

            # حساب الغياب والتأخر الفعلي
            con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
            cur.execute("SELECT COUNT(DISTINCT date) as c FROM absences WHERE student_id=?", (sid,))
            row = cur.fetchone(); abs_c = row["c"] if row else 0
            cur.execute("SELECT COUNT(*) as c FROM tardiness WHERE student_id=?", (sid,))
            row = cur.fetchone(); tard_c = row["c"] if row else 0

            # التحقق أن الطالب غير موجود مسبقاً هذا الشهر
            now_str  = datetime.datetime.now().isoformat()
            date_str = now_str[:10]
            month_prefix = date_str[:7]
            cur.execute("""SELECT id FROM counselor_referrals
                           WHERE student_id=? AND date LIKE ?""", (sid, month_prefix + "%"))
            existing = cur.fetchone()

            if existing:
                if not messagebox.askyesno("طالب موجود",
                        f"الطالب {sname} موجود بالفعل في قائمة الموجّه هذا الشهر.\nهل تريد إضافته مرة أخرى؟",
                        parent=win):
                    con.close(); return

            cur.execute("""
                INSERT INTO counselor_referrals
                    (date, student_id, student_name, class_name, referral_type,
                     absence_count, tardiness_count, notes, referred_by, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (date_str, sid, sname, cname, reason,
                  abs_c, tard_c, notes, "إضافة يدوية", "جديد", now_str))
            con.commit(); con.close()

            messagebox.showinfo("تم", f"✅ تم إضافة الطالب {sname} لقائمة الموجّه بنجاح", parent=win)
            win.destroy()
            self._load_counselor_data()

        btn_fr2 = tk.Frame(body, bg="white")
        btn_fr2.grid(row=4, column=0, columnspan=2, pady=14)
        tk.Button(btn_fr2, text="✅ حفظ", bg="#7c3aed", fg="white",
                  font=("Tahoma", 11, "bold"), relief="flat", cursor="hand2",
                  padx=20, pady=6, command=_do_save).pack(side="right", padx=8)
        tk.Button(btn_fr2, text="إلغاء", bg="#e5e7eb", fg="#374151",
                  font=("Tahoma", 11), relief="flat", cursor="hand2",
                  padx=20, pady=6, command=win.destroy).pack(side="right", padx=8)

    def _delete_student_from_counselor(self):
        """حذف الطالب المحدد من قائمة الموجّه الطلابي (جميع سجلاته في counselor_referrals)."""
        sel = self.tree_counselor.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء اختيار طالب أولاً لحذفه")
            return

        values = self.tree_counselor.item(sel[0], "values")
        sid   = values[0]
        sname = values[1]
        scls  = values[2]

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل أنت متأكد من حذف الطالب:\n\n👤 {sname}\n🏫 {scls}\n\nمن قائمة الموجّه الطلابي؟\n"
            "(سيتم حذف جميع سجلات تحويله فقط، ولن يُحذف من بيانات المدرسة)"
        ):
            return

        try:
            con = get_db(); cur = con.cursor()
            cur.execute("DELETE FROM counselor_referrals WHERE student_id=?", (sid,))
            con.commit(); con.close()
            messagebox.showinfo("تم الحذف", f"✅ تم حذف الطالب {sname} من قائمة الموجّه بنجاح")
            self._load_counselor_data()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

    def _load_counselor_data(self):
        """تحميل الطلاب المحوّلين من وكيل شؤون الطلاب فقط."""
        # حذف جميع العناصر بشكل آمن (بما فيها المخفية بـ detach)
        self.tree_counselor.delete(*self.tree_counselor.get_children())

        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()

        # جلب المحوّلين من جدول counselor_referrals (مرتبين بالأحدث أولاً)
        cur.execute("""
            SELECT student_id, student_name, class_name,
                   referral_type, absence_count, tardiness_count,
                   date, status, notes
            FROM counselor_referrals
            ORDER BY date DESC
        """)
        referrals = [dict(r) for r in cur.fetchall()]

        # إزالة التكرار (نفس الطالب قد يُحوَّل أكثر من مرة — نُبقي الأحدث)
        seen = set()
        unique_referrals = []
        for ref in referrals:
            if ref["student_id"] not in seen:
                seen.add(ref["student_id"])
                unique_referrals.append(ref)

        # حفظ بيانات الطلاب لاستخدامها في الفلتر
        self._all_counselor_rows = []

        for ref in unique_referrals:
            sid  = ref["student_id"]
            name = ref["student_name"]
            cls  = ref["class_name"]

            # احسب الغياب والتأخر الفعلي من جداول الأحداث
            cur.execute("SELECT COUNT(DISTINCT date) as c FROM absences WHERE student_id=?", (sid,))
            row = cur.fetchone(); abs_c = row["c"] if row else ref["absence_count"]

            cur.execute("SELECT COUNT(*) as c FROM tardiness WHERE student_id=?", (sid,))
            row = cur.fetchone(); tard_c = row["c"] if row else ref["tardiness_count"]

            # آخر إجراء
            cur.execute("""SELECT type, date FROM counselor_alerts
                           WHERE student_id=? ORDER BY date DESC LIMIT 1""", (sid,))
            last = cur.fetchone()
            last_action = "{} ({})".format(last["type"], last["date"]) if last else "لا يوجد"

            tag = "referred_absence" if ref["referral_type"] == "غياب" else "referred_tardiness"
            row_data = (sid, name, cls, abs_c, tard_c, last_action, tag)
            self._all_counselor_rows.append(row_data)
            self.tree_counselor.insert("", "end", values=(sid, name, cls, abs_c, tard_c, last_action), tags=(tag,))

        con.close()

        # تلوين الصفوف حسب نوع التحويل
        self.tree_counselor.tag_configure("referred_absence",
            background="#FFF0F0", foreground="#991B1B")
        self.tree_counselor.tag_configure("referred_tardiness",
            background="#FFF7ED", foreground="#9A3412")

    def _filter_counselor_students(self):
        query = self.counselor_search_var.get().strip().lower()
        if not query:
            # بحث فارغ → أعد تحميل الكل من قاعدة البيانات
            self._load_counselor_data()
            return
        # أعد بناء القائمة بالعناصر المطابقة فقط (بدون detach لتجنب مشكلة بقاء العناصر المخفية)
        self.tree_counselor.delete(*self.tree_counselor.get_children())
        if not hasattr(self, "_all_counselor_rows"):
            self._load_counselor_data()
            return
        for row_data in self._all_counselor_rows:
            sid, name, cls, abs_c, tard_c, last_action, tag = row_data
            if query in str(name).lower() or query in str(cls).lower() or query in str(sid).lower():
                self.tree_counselor.insert("", "end", values=(sid, name, cls, abs_c, tard_c, last_action), tags=(tag,))
        self.tree_counselor.tag_configure("referred_absence",
            background="#FFF0F0", foreground="#991B1B")
        self.tree_counselor.tag_configure("referred_tardiness",
            background="#FFF7ED", foreground="#9A3412")

    def _on_counselor_student_select(self, event):
        pass

    def _open_session_dialog(self, sid=None, sname=None, sclass=None, sabs=None, stard=None):
        """نافذة جلسة إرشادية فردية وفق نموذج وزارة التعليم — مع خانات اختيار."""
        if sid is None:
            sel = self.tree_counselor.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "الرجاء اختيار طالب أولاً")
                return
            sid, sname, sclass, sabs, stard, _ = self.tree_counselor.item(sel[0], "values")

        cfg    = load_config()
        school = cfg.get("school_name", "المدرسة")
        # استخدم اسم الموجّه النشط حالياً كتوقيع على كل الأعمال
        counselor_name  = self._get_active_counselor_name()
        principal_phone = cfg.get("principal_phone", "")
        deputy_phone    = cfg.get("alert_admin_phone", "")

        today_h = datetime.datetime.now().strftime("%Y/%m/%d")

        win = tk.Toplevel(self.root)
        win.title(f"جلسة إرشاد فردي — {sname}")
        win.geometry("820x860")
        win.resizable(True, True)
        win.configure(bg="#f0f4f8")
        try: win.state("zoomed")
        except: pass

        outer = tk.Frame(win, bg="#f0f4f8"); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg="#f0f4f8", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#f0f4f8")
        sf_win = canvas.create_window((0,0), window=scroll_frame, anchor="nw")
        def _on_sf_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        scroll_frame.bind("<Configure>", _on_sf_configure)
        _sf_last_w = [0]
        def _on_sf_canvas_conf(e):
            w = canvas.winfo_width()
            if w == _sf_last_w[0]: return
            _sf_last_w[0] = w
            canvas.itemconfig(sf_win, width=w)
        canvas.bind("<Configure>", _on_sf_canvas_conf)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        def _on_mw(e): canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        win.bind("<MouseWheel>", _on_mw)
        win.protocol("WM_DELETE_WINDOW", lambda: (win.unbind("<MouseWheel>"), win.destroy()))

        main = scroll_frame
        BORDER   = dict(relief="solid", bd=1)
        FONT_H   = ("Tahoma", 11, "bold")
        FONT_N   = ("Tahoma", 10)
        FONT_S   = ("Tahoma", 9)
        PURPLE   = "#7c3aed"
        BG_WHITE = "white"

        # رأس النموذج
        hdr_fr = tk.Frame(main, bg=PURPLE, pady=8); hdr_fr.pack(fill="x", padx=12, pady=(12,4))
        tk.Label(hdr_fr, text="جلسة إرشاد فردي", bg=PURPLE, fg="white",
                 font=("Tahoma",14,"bold")).pack()
        tk.Label(hdr_fr, text=school, bg=PURPLE, fg="#ddd6fe", font=("Tahoma",9)).pack()

        # بيانات الطالب
        info_fr = tk.LabelFrame(main, text=" بيانات الطالب ", font=FONT_H,
                                bg=BG_WHITE, **BORDER, padx=10, pady=8)
        info_fr.pack(fill="x", padx=12, pady=4)
        info_fr.configure(fg=PURPLE)

        row1 = tk.Frame(info_fr, bg=BG_WHITE); row1.pack(fill="x", pady=2)
        tk.Label(row1, text="اسم الطالب:", bg=BG_WHITE, font=FONT_N, width=12, anchor="e").pack(side="right")
        tk.Label(row1, text=str(sname), bg="#f5f3ff", font=("Tahoma",10,"bold"),
                 relief="sunken", bd=1, width=25, anchor="center").pack(side="right", padx=6)
        tk.Label(row1, text="الفصل:", bg=BG_WHITE, font=FONT_N, width=8, anchor="e").pack(side="right")
        tk.Label(row1, text=str(sclass), bg="#f5f3ff", font=("Tahoma",10,"bold"),
                 relief="sunken", bd=1, width=14, anchor="center").pack(side="right", padx=6)

        row2 = tk.Frame(info_fr, bg=BG_WHITE); row2.pack(fill="x", pady=2)
        tk.Label(row2, text="عنوان الجلسة:", bg=BG_WHITE, font=FONT_N, width=12, anchor="e").pack(side="right")
        session_title_var = tk.StringVar(value="الانضباط المدرسي")
        ttk.Entry(row2, textvariable=session_title_var, width=25, font=FONT_N).pack(side="right", padx=6)
        tk.Label(row2, text="مكانها:", bg=BG_WHITE, font=FONT_N, width=8, anchor="e").pack(side="right")
        tk.Label(row2, text="مكتب المرشد الطلابي", bg="#f5f3ff", font=FONT_S,
                 relief="sunken", bd=1, width=16, anchor="center").pack(side="right", padx=6)

        row3 = tk.Frame(info_fr, bg=BG_WHITE); row3.pack(fill="x", pady=2)
        tk.Label(row3, text="زمن الجلسة:", bg=BG_WHITE, font=FONT_N, width=12, anchor="e").pack(side="right")
        tk.Label(row3, text="30 دقيقة", bg="#f5f3ff", font=FONT_S,
                 relief="sunken", bd=1, width=10, anchor="center").pack(side="right", padx=6)
        tk.Label(row3, text="تاريخها:", bg=BG_WHITE, font=FONT_N, width=8, anchor="e").pack(side="right")
        date_var = tk.StringVar(value=today_h)
        ttk.Entry(row3, textvariable=date_var, width=14, font=FONT_N).pack(side="right", padx=6)

        # أهداف الجلسة
        goals_fr = tk.LabelFrame(main, text=" الهدف من الجلسة :- ", font=FONT_H,
                                 bg=BG_WHITE, **BORDER, padx=10, pady=8)
        goals_fr.pack(fill="x", padx=12, pady=4)
        goals_fr.configure(fg=PURPLE)

        DEFAULT_GOALS = [
            ("الحد من غياب الطالب المتكرر بلا عذر",              True),
            ("أن يدرك الطالب أضرار الغياب على تحصيله الدراسي",  True),
            ("أن ينظم الطالب وقته ويجتهد في دراسته",             True),
        ]
        goal_vars = []
        for i, (text, default) in enumerate(DEFAULT_GOALS):
            fr = tk.Frame(goals_fr, bg=BG_WHITE); fr.pack(fill="x", pady=2)
            var = tk.BooleanVar(value=default)
            goal_vars.append((var, text))
            tk.Label(fr, text=str(i+1), bg=BG_WHITE, font=FONT_S, width=3, anchor="center").pack(side="right")
            tk.Checkbutton(fr, variable=var, bg=BG_WHITE, activebackground=BG_WHITE,
                           selectcolor="#ede9fe").pack(side="right")
            tk.Label(fr, text=text, bg=BG_WHITE, font=FONT_N, anchor="e").pack(side="right", padx=4)

        cg_fr = tk.Frame(goals_fr, bg=BG_WHITE); cg_fr.pack(fill="x", pady=2)
        tk.Label(cg_fr, text="هدف إضافي:", bg=BG_WHITE, font=FONT_S).pack(side="right")
        custom_goal_var = tk.StringVar()
        ttk.Entry(cg_fr, textvariable=custom_goal_var, width=50, font=FONT_S).pack(side="right", padx=4)

        # المداولات
        disc_fr = tk.LabelFrame(main, text=" المداولات :- ", font=FONT_H,
                                bg=BG_WHITE, **BORDER, padx=10, pady=8)
        disc_fr.pack(fill="x", padx=12, pady=4)
        disc_fr.configure(fg=PURPLE)

        DEFAULT_DISCUSSIONS = [
            ("حوار ونقاش وعصف ذهني مع الطالب حول أضرار الغياب",             True),
            ("معرفة أسباب الغياب ومساعدة الطالب للتغلب عليها",               True),
            ("استخدام أسلوب الضبط الذاتي وشرحه للطالب للحد من الغياب بلا عذر", True),
        ]
        disc_vars = []
        for i, (text, default) in enumerate(DEFAULT_DISCUSSIONS):
            fr = tk.Frame(disc_fr, bg=BG_WHITE); fr.pack(fill="x", pady=2)
            var = tk.BooleanVar(value=default)
            disc_vars.append((var, text))
            tk.Label(fr, text=str(i+1), bg=BG_WHITE, font=FONT_S, width=3, anchor="center").pack(side="right")
            tk.Checkbutton(fr, variable=var, bg=BG_WHITE, activebackground=BG_WHITE,
                           selectcolor="#ede9fe").pack(side="right")
            lbl = tk.Label(fr, text=text, bg=BG_WHITE, font=FONT_N, anchor="e",
                           wraplength=560, justify="right")
            lbl.pack(side="right", padx=4, fill="x", expand=True)

        cd_fr = tk.Frame(disc_fr, bg=BG_WHITE); cd_fr.pack(fill="x", pady=2)
        tk.Label(cd_fr, text="مداولة إضافية:", bg=BG_WHITE, font=FONT_S).pack(side="right")
        custom_disc_var = tk.StringVar()
        ttk.Entry(cd_fr, textvariable=custom_disc_var, width=48, font=FONT_S).pack(side="right", padx=4)

        # التوصيات
        rec_fr = tk.LabelFrame(main, text=" التوصيات :- ", font=FONT_H,
                               bg=BG_WHITE, **BORDER, padx=10, pady=8)
        rec_fr.pack(fill="x", padx=12, pady=4)
        rec_fr.configure(fg=PURPLE)

        DEFAULT_RECS = [
            ("التزام الطالب بالحضور للمدرسة وعدم غيابه إلا بعذر مقبول",       True),
            ("التزام الطالب بتنظيم الوقت والضبط الذاتي",                       True),
            ("التأكيد على إدارة المدرسة بعدم التساهل في تطبيق لائحة المواظبة في جميع المراحل، وتكثيف التوعية الإعلامية لنشر ثقافة الانتباط، واحترام أوقات الدراسة، وجعل المدرسة بيئة جاذبة للطالب", True),
        ]
        rec_vars = []
        for i, (text, default) in enumerate(DEFAULT_RECS):
            fr = tk.Frame(rec_fr, bg=BG_WHITE); fr.pack(fill="x", pady=3)
            var = tk.BooleanVar(value=default)
            rec_vars.append((var, text))
            tk.Label(fr, text=str(i+1), bg=BG_WHITE, font=FONT_S, width=3, anchor="center").pack(side="right")
            tk.Checkbutton(fr, variable=var, bg=BG_WHITE, activebackground=BG_WHITE,
                           selectcolor="#ede9fe").pack(side="right")
            lbl = tk.Label(fr, text=text, bg=BG_WHITE, font=FONT_S,
                           anchor="e", wraplength=560, justify="right")
            lbl.pack(side="right", padx=4, fill="x", expand=True)

        cr_fr = tk.Frame(rec_fr, bg=BG_WHITE); cr_fr.pack(fill="x", pady=2)
        tk.Label(cr_fr, text="توصية إضافية:", bg=BG_WHITE, font=FONT_S).pack(side="right")
        custom_rec_var = tk.StringVar()
        ttk.Entry(cr_fr, textvariable=custom_rec_var, width=48, font=FONT_S).pack(side="right", padx=4)

        # ملاحظات
        notes_lf = tk.LabelFrame(main, text=" ملاحظات إضافية ", font=FONT_H,
                                 bg=BG_WHITE, **BORDER, padx=10, pady=6)
        notes_lf.pack(fill="x", padx=12, pady=4)
        notes_lf.configure(fg=PURPLE)
        notes_txt = tk.Text(notes_lf, height=3, font=FONT_S, relief="sunken", bd=1)
        notes_txt.pack(fill="x")

        # التواقيع
        sig_fr = tk.Frame(main, bg=BG_WHITE, relief="solid", bd=1, padx=10, pady=10)
        sig_fr.pack(fill="x", padx=12, pady=4)
        tk.Label(sig_fr, text=f"المرشد الطلابي: {counselor_name}", bg=BG_WHITE,
                 font=("Tahoma",10,"bold"), fg="#7c3aed").pack(side="right", padx=40)
        tk.Label(sig_fr, text="قائد المدرسة", bg=BG_WHITE,
                 font=("Tahoma",10,"bold"), fg="#374151").pack(side="left", padx=40)

        # ── دوال المساعدة الداخلية ───────────────────────────────────────
        def _collect():
            goals = [t for v,t in goal_vars if v.get()]
            cg = custom_goal_var.get().strip()
            if cg: goals.append(cg)
            discs = [t for v,t in disc_vars if v.get()]
            cd = custom_disc_var.get().strip()
            if cd: discs.append(cd)
            recs = [t for v,t in rec_vars if v.get()]
            cr = custom_rec_var.get().strip()
            if cr: recs.append(cr)
            return goals, discs, recs

        def _build_msg(goals, discs, recs, role=""):
            lines = []
            if role: lines.append(f"📋 جلسة إرشادية — {role}")
            lines.append("="*40)
            lines.append(f"جلسة إرشاد فردي — {session_title_var.get()}")
            lines.append(f"الطالب: {sname}  |  الفصل: {sclass}  |  التاريخ: {date_var.get()}")
            lines.append(f"المدرسة: {school}")
            lines.append("")
            lines.append("📌 الأهداف:")
            for i,g in enumerate(goals,1): lines.append(f"  {i}. {g}")
            lines.append("")
            lines.append("🗣 المداولات:")
            for i,d in enumerate(discs,1): lines.append(f"  {i}. {d}")
            lines.append("")
            lines.append("✅ التوصيات:")
            for i,r in enumerate(recs,1): lines.append(f"  {i}. {r}")
            extra = notes_txt.get("1.0","end-1c").strip()
            if extra: lines.append("\n📝 ملاحظات: " + extra)
            lines.append("\nالمرشد الطلابي: " + counselor_name)
            return "\n".join(lines)

        def _save_to_db(goals, discs, recs):
            reason   = session_title_var.get()
            notes_db = "الأهداف: " + "; ".join(goals) + "\nالمداولات: " + "; ".join(discs) + "\nالتوصيات: " + "; ".join(recs)
            extra    = notes_txt.get("1.0","end-1c").strip()
            if extra: notes_db += "\nملاحظات: " + extra
            action   = "; ".join(recs) if recs else "تنبيه الطالب"
            date_db  = datetime.datetime.now().strftime("%Y-%m-%d")
            con = get_db(); cur = con.cursor()
            cur.execute("""
                INSERT INTO counselor_sessions (date, student_id, student_name, class_name, reason, notes, action_taken, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (date_db, sid, sname, sclass, reason, notes_db, action, datetime.datetime.now().isoformat()))
            con.commit(); con.close()
            try: self._load_counselor_data()
            except: pass

        def save_session():
            goals, discs, recs = _collect()
            _save_to_db(goals, discs, recs)
            messagebox.showinfo("✅ تم", "تم حفظ الجلسة الإرشادية بنجاح", parent=win)

        def send_to(phone, role):
            if not phone:
                messagebox.showerror("خطأ", f"لم يُسجَّل رقم جوال {role} في الإعدادات", parent=win)
                return False
            goals, discs, recs = _collect()
            # ── بناء بيانات الجلسة ───────────────────────────────────
            session_data = {
                "student_name":    sname,
                "class_name":      sclass,
                "date":            date_var.get(),
                "title":           session_title_var.get(),
                "goals":           goals,
                "discussions":     discs,
                "recommendations": recs,
                "notes":           notes_txt.get("1.0","end-1c").strip(),
                "counselor_name":  counselor_name,
            }
            # ── إنشاء PDF ────────────────────────────────────────────
            try:
                pdf_bytes = generate_session_pdf(session_data)
            except Exception as _pdf_err:
                messagebox.showerror("خطأ PDF", f"تعذّر إنشاء ملف PDF:\n{_pdf_err}", parent=win)
                return False
            fname   = "جلسة_ارشادية_{}_{}.pdf".format(sname, date_var.get())
            caption = "📋 جلسة إرشادية — {} — {} | {}".format(sname, sclass, role)
            # ── إرسال PDF ────────────────────────────────────────────
            ok, res = send_whatsapp_pdf(phone, pdf_bytes, fname, caption)
            if ok:
                _save_to_db(goals, discs, recs)
                messagebox.showinfo("✅ تم", f"✅ تم إرسال الجلسة كـ PDF لـ{role} بنجاح", parent=win)
                return True
            else:
                # اسأل المستخدم: هل يرسل نصاً بدلاً عن PDF؟
                retry = messagebox.askyesno(
                    "فشل إرسال PDF",
                    f"فشل إرسال الجلسة كـ PDF لـ{role}:\n{res}\n\nهل تريد إرسالها كرسالة نصية بدلاً عن ذلك؟",
                    parent=win
                )
                if retry:
                    msg = _build_msg(goals, discs, recs, role)
                    ok2, res2 = send_whatsapp_message(phone, msg)
                    if ok2:
                        _save_to_db(goals, discs, recs)
                        messagebox.showinfo("✅ تم", f"تم الإرسال كنص لـ{role}", parent=win)
                        return True
                    else:
                        messagebox.showerror("فشل", f"فشل الإرسال النصي: {res2}", parent=win)
                return False

        def send_to_both():
            goals, discs, recs = _collect()
            session_data = {
                "student_name":    sname,
                "class_name":      sclass,
                "date":            date_var.get(),
                "title":           session_title_var.get(),
                "goals":           goals,
                "discussions":     discs,
                "recommendations": recs,
                "notes":           notes_txt.get("1.0","end-1c").strip(),
                "counselor_name":  counselor_name,
            }
            try:
                pdf_bytes = generate_session_pdf(session_data)
            except Exception as _pdf_err:
                messagebox.showerror("خطأ PDF", f"تعذّر إنشاء ملف PDF:\n{_pdf_err}", parent=win)
                return
            sent = 0; failed_pdf = []
            fname = "جلسة_ارشادية_{}_{}.pdf".format(sname, date_var.get())
            for phone, role in [(principal_phone, "مدير المدرسة"), (deputy_phone, "وكيل المدرسة")]:
                if not phone: continue
                caption = "📋 جلسة إرشادية — {} — {} | {}".format(sname, sclass, role)
                ok_pdf, _ = send_whatsapp_pdf(phone, pdf_bytes, fname, caption)
                if ok_pdf:
                    sent += 1
                else:
                    failed_pdf.append(role)
            if sent:
                _save_to_db(goals, discs, recs)
                msg_ok = f"✅ تم إرسال الجلسة كـ PDF لـ {sent} جهة"
                if failed_pdf:
                    msg_ok += f"\n⚠️ فشل PDF لـ: {', '.join(failed_pdf)}"
                messagebox.showinfo("✅ تم", msg_ok, parent=win)
            else:
                messagebox.showwarning("تحذير",
                    "لم يتم الإرسال — تحقق من أرقام الجوال وتأكد من تحديث server.js",
                    parent=win)

        # أزرار الإرسال
        btn_fr = tk.Frame(main, bg="#f0f4f8", pady=10)
        btn_fr.pack(fill="x", padx=12, pady=(4,16))

        # قراءة أرقام الموجّهَين
        _cfg_sess = load_config()
        counselor1_phone = _cfg_sess.get("counselor1_phone", "").strip()
        counselor2_phone = _cfg_sess.get("counselor2_phone", "").strip()

        def send_to_counselors():
            """إرسال نسخة PDF للموجّهَين معاً."""
            goals, discs, recs = _collect()
            session_data = {
                "student_name":    sname,
                "class_name":      sclass,
                "date":            date_var.get(),
                "title":           session_title_var.get(),
                "goals":           goals,
                "discussions":     discs,
                "recommendations": recs,
                "notes":           notes_txt.get("1.0","end-1c").strip(),
                "counselor_name":  counselor_name,
            }
            if not counselor1_phone and not counselor2_phone:
                messagebox.showwarning("تنبيه",
                    "لا توجد أرقام موجّهين مسجّلة.\nأضفها من: إعدادات المدرسة  أرقام الجوال", parent=win)
                return
            try:
                pdf_bytes = generate_session_pdf(session_data)
            except Exception as _pdf_err:
                messagebox.showerror("خطأ PDF", f"تعذّر إنشاء ملف PDF:\n{_pdf_err}", parent=win)
                return
            sent = 0
            fname = "جلسة_ارشادية_{}_{}.pdf".format(sname, date_var.get())
            for _ph in [counselor1_phone, counselor2_phone]:
                if not _ph: continue
                caption = "📋 جلسة إرشادية — {} — {}".format(sname, sclass)
                ok_pdf, _ = send_whatsapp_pdf(_ph, pdf_bytes, fname, caption)
                if ok_pdf:
                    sent += 1
            if sent:
                _save_to_db(goals, discs, recs)
                messagebox.showinfo("✅ تم", f"✅ تم إرسال الجلسة كـ PDF للموجّه{'ين' if sent==2 else ''}", parent=win)
            else:
                messagebox.showwarning("فشل PDF",
                    "فشل إرسال PDF للموجهين.\nتاكد من تحديث server.js ثم اعادة تشغيل خادم الواتساب.", parent=win)

        btns = [
            ("💾 حفظ الجلسة",              "#6d28d9", save_session),
            ("📲 إرسال لمدير المدرسة",     "#1d4ed8", lambda: send_to(principal_phone, "مدير المدرسة")),
            ("📲 إرسال لوكيل المدرسة",     "#0369a1", lambda: send_to(deputy_phone,    "وكيل المدرسة")),
            ("📨 إرسال للمدير والوكيل",    "#065f46", send_to_both),
            ("🧭 إرسال للموجّهَين",        "#7c3aed", send_to_counselors),
            ("❌ إغلاق",                    "#6b7280", win.destroy),
        ]
        for txt, color, cmd in btns:
            tk.Button(btn_fr, text=txt, command=cmd,
                      bg=color, fg="white", font=("Tahoma",10,"bold"),
                      relief="flat", padx=12, pady=6, cursor="hand2").pack(side="right", padx=5)

    def _send_counselor_alert(self, alert_type):
        sel = self.tree_counselor.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء اختيار طالب أولاً")
            return
        
        sid, sname, sclass, sabs, stard, _ = self.tree_counselor.item(sel[0], "values")
        
        # جلب رقم الجوال
        store = load_students()
        phone = ""
        for cls in store["list"]:
            for s in cls["students"]:
                if s["id"] == sid:
                    phone = s.get("phone", "")
                    break
        
        if not phone:
            messagebox.showerror("خطأ", "رقم جوال ولي الأمر غير مسجل لهذا الطالب")
            return
        
        # اسم الموجّه النشط حالياً للتوقيع
        active_name = self._get_active_counselor_name()

        if alert_type == "تنبيه":
            msg = f"المكرم ولي أمر الطالب: {sname}\nنفيدكم بأن ابنكم قد تكرر غيابه/تأخره ({sabs} أيام غياب / {stard} مرات تأخر). نأمل منكم حثه على الانضباط.\nالموجّه الطلابي"
            msg = f"المكرم ولي أمر الطالب: {sname}\nنفيدكم بأن ابنكم قد تكرر غيابه/تأخره ({sabs} أيام غياب / {stard} مرات تأخر). نأمل منكم حثه على الانضباط.\n{active_name}"
            msg = f"المكرم ولي أمر الطالب: {sname}\nنظراً لتكرار غياب/تأخر ابنكم بشكل ملحوظ، نرجو منكم مراجعة مكتب التوجيه الطلابي بالمدرسة في أقرب وقت ممكن.\nالموجّه الطلابي"
            msg = f"المكرم ولي أمر الطالب: {sname}\nنظراً لتكرار غياب/تأخر ابنكم بشكل ملحوظ، نرجو منكم مراجعة مكتب التوجيه الطلابي بالمدرسة في أقرب وقت ممكن.\n{active_name}"
        if not messagebox.askyesno("تأكيد", f"هل تريد إرسال {alert_type} لولي الأمر عبر الواتساب؟"):
            return
        
        ok, res = send_whatsapp_message(phone, msg)
        if ok:
            date = datetime.datetime.now().strftime("%Y-%m-%d")
            con = get_db(); cur = con.cursor()
            cur.execute("""
                INSERT INTO counselor_alerts (date, student_id, student_name, type, method, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date, sid, sname, alert_type, "whatsapp", "sent", datetime.datetime.now().isoformat()))
            con.commit(); con.close()
            messagebox.showinfo("تم", f"تم إرسال {alert_type} بنجاح")
            self._load_counselor_data()
        else:
            messagebox.showerror("فشل", f"فشل الإرسال: {res}")

    def _show_student_counseling_history(self):
        sel = self.tree_counselor.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء اختيار طالب أولاً")
            return
        sid, sname, _, _, _, _ = self.tree_counselor.item(sel[0], "values")
        self._open_sessions_archive(filter_sid=sid, filter_name=sname)

    def _open_sessions_archive(self, filter_sid=None, filter_name=None):
        """
        أرشيف الجلسات الإرشادية — يعرض كل الجلسات المحفوظة
        مع إمكانية البحث والتصفية وإعادة الطباعة أو الإرسال.
        """
        win = tk.Toplevel(self.root)
        title_txt = f"📚 أرشيف الجلسات — {filter_name}" if filter_name else "📚 أرشيف الجلسات الإرشادية"
        win.title(title_txt)
        win.geometry("1050x680")
        win.configure(bg="#f0f4f8")
        try: win.state("zoomed")
        except: pass

        cfg    = load_config()

        # ── رأس النافذة ──────────────────────────────────────────
        hdr = tk.Frame(win, bg="#5b21b6", height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📚 أرشيف الجلسات الإرشادية",
                 bg="#5b21b6", fg="white",
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=20, pady=14)
        if filter_name:
            tk.Label(hdr, text=f"طالب: {filter_name}",
                     bg="#5b21b6", fg="#ddd6fe",
                     font=("Tahoma", 10)).pack(side="right", padx=10, pady=14)

        # ── شريط البحث والفلترة ──────────────────────────────────
        ctrl = tk.Frame(win, bg="#ede9fe", pady=8)
        ctrl.pack(fill="x")

        tk.Label(ctrl, text="🔍 بحث:", bg="#ede9fe",
                 font=("Tahoma", 10, "bold"), fg="#5b21b6").pack(side="right", padx=(10, 4))
        _search_var = tk.StringVar()
        search_ent = ttk.Entry(ctrl, textvariable=_search_var, width=22, font=("Tahoma", 10))
        search_ent.pack(side="right", padx=4)

        tk.Label(ctrl, text="من:", bg="#ede9fe",
                 font=("Tahoma", 10), fg="#5b21b6").pack(side="right", padx=(10, 4))
        _date_from = tk.StringVar()
        ttk.Entry(ctrl, textvariable=_date_from, width=12, font=("Tahoma", 10)).pack(side="right", padx=2)

        tk.Label(ctrl, text="إلى:", bg="#ede9fe",
                 font=("Tahoma", 10), fg="#5b21b6").pack(side="right", padx=(6, 4))
        _date_to = tk.StringVar()
        ttk.Entry(ctrl, textvariable=_date_to, width=12, font=("Tahoma", 10)).pack(side="right", padx=2)

        tk.Button(ctrl, text="🔍 تصفية", bg="#7c3aed", fg="white",
                  font=("Tahoma", 9, "bold"), relief="flat", cursor="hand2",
                  padx=8, command=lambda: _load_sessions()).pack(side="right", padx=8)
        tk.Button(ctrl, text="↺ إعادة تعيين", bg="#e5e7eb", fg="#374151",
                  font=("Tahoma", 9), relief="flat", cursor="hand2",
                  padx=8, command=lambda: [_search_var.set(""),
                                           _date_from.set(""), _date_to.set(""),
                                           _load_sessions()]).pack(side="right", padx=4)

        _count_lbl = tk.Label(ctrl, text="", bg="#ede9fe",
                               font=("Tahoma", 9), fg="#5b21b6")
        _count_lbl.pack(side="left", padx=14)

        # ── الجدول الرئيسي ────────────────────────────────────────
        tbl_fr = tk.Frame(win, bg="white")
        tbl_fr.pack(fill="both", expand=True, padx=16, pady=(8, 0))

        cols = ("id", "date", "student_name", "class_name", "reason", "action_taken")
        tree = ttk.Treeview(tbl_fr, columns=cols, show="headings", height=18,
                            selectmode="browse")

        hdrs = {
            "id":           ("رقم", 50),
            "date":         ("التاريخ", 100),
            "student_name": ("اسم الطالب", 170),
            "class_name":   ("الفصل", 110),
            "reason":       ("موضوع الجلسة", 220),
            "action_taken": ("التوصيات", 250),
        }
        for col, (lbl, w) in hdrs.items():
            tree.heading(col, text=lbl, anchor="center")
            tree.column(col, width=w, anchor="center",
                        stretch=(col in ("reason", "action_taken")))
        tree.column("id", width=0, stretch=False)

        vsb = ttk.Scrollbar(tbl_fr, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(tbl_fr, orient="horizontal",  command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="left",   fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="right", fill="both", expand=True)

        tree.tag_configure("odd",  background="#faf5ff")
        tree.tag_configure("even", background="white")

        # ── تحميل الجلسات ────────────────────────────────────────
        _all_sessions = []

        def _load_sessions():
            nonlocal _all_sessions
            tree.delete(*tree.get_children())
            con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
            cur.execute("SELECT * FROM counselor_sessions ORDER BY date DESC, created_at DESC")
            rows = [dict(r) for r in cur.fetchall()]
            con.close()

            if filter_sid:
                rows = [r for r in rows if str(r.get("student_id","")) == str(filter_sid)]

            q = _search_var.get().strip().lower()
            if q:
                rows = [r for r in rows
                        if q in str(r.get("student_name","")).lower()
                        or q in str(r.get("class_name","")).lower()
                        or q in str(r.get("reason","")).lower()
                        or q in str(r.get("action_taken","")).lower()]

            df = _date_from.get().strip()
            dt = _date_to.get().strip()
            if df: rows = [r for r in rows if str(r.get("date","")) >= df]
            if dt: rows = [r for r in rows if str(r.get("date","")) <= dt]

            _all_sessions.clear()
            _all_sessions.extend(rows)
            _count_lbl.config(text=f"عدد الجلسات: {len(rows)}")

            for i, r in enumerate(rows):
                tag = "odd" if i % 2 == 0 else "even"
                tree.insert("", "end", iid=str(r["id"]),
                            values=(r["id"], r.get("date",""),
                                    r.get("student_name",""),
                                    r.get("class_name",""),
                                    r.get("reason",""),
                                    r.get("action_taken","")),
                            tags=(tag,))

        _load_sessions()
        search_ent.bind("<KeyRelease>", lambda e: _load_sessions())

        # ── لوحة التفاصيل ────────────────────────────────────────
        detail_fr = tk.LabelFrame(win, text=" 📋 تفاصيل الجلسة المحددة ",
                                  font=("Tahoma", 10, "bold"),
                                  fg="#5b21b6", bg="#f0f4f8", padx=10, pady=6)
        detail_fr.pack(fill="x", padx=16, pady=(6, 0))

        _detail_txt = tk.Text(detail_fr, height=5, font=("Tahoma", 10),
                               state="disabled", bg="#faf5ff",
                               relief="flat", wrap="word")
        _detail_txt.pack(fill="x")

        def _on_select(event=None):
            sel = tree.selection()
            if not sel: return
            session = next((r for r in _all_sessions if str(r["id"]) == str(sel[0])), None)
            if not session: return
            notes = session.get("notes", "") or ""
            detail = (
                f"📅 التاريخ: {session.get('date','')}\n"
                f"👤 الطالب: {session.get('student_name','')}  |  الفصل: {session.get('class_name','')}\n"
                f"📌 الموضوع: {session.get('reason','')}\n"
                f"✅ التوصيات: {session.get('action_taken','')}\n"
            )
            if notes:
                detail += f"📝 الملاحظات:\n{notes}"
            _detail_txt.config(state="normal")
            _detail_txt.delete("1.0", "end")
            _detail_txt.insert("1.0", detail)
            _detail_txt.config(state="disabled")

        tree.bind("<<TreeviewSelect>>", _on_select)

        # ── دوال مساعدة ──────────────────────────────────────────
        def _get_sel():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "الرجاء اختيار جلسة أولاً", parent=win)
                return None
            return next((r for r in _all_sessions if str(r["id"]) == str(sel[0])), None)

        def _rebuild(session):
            notes_raw = session.get("notes", "") or ""
            goals, discs, recs, extra = [], [], [], ""
            for line in notes_raw.split("\n"):
                line = line.strip()
                if line.startswith("الأهداف:"):
                    goals = [x.strip() for x in line[len("الأهداف:"):].split(";") if x.strip()]
                elif line.startswith("المداولات:"):
                    discs = [x.strip() for x in line[len("المداولات:"):].split(";") if x.strip()]
                elif line.startswith("التوصيات:"):
                    recs  = [x.strip() for x in line[len("التوصيات:"):].split(";") if x.strip()]
                elif line.startswith("ملاحظات:"):
                    extra = line[len("ملاحظات:"):].strip()
            if not recs:
                action = session.get("action_taken","") or ""
                if action:
                    recs = [x.strip() for x in action.split(";") if x.strip()]
            counselor_col = ""
            for line in notes_raw.split("\n"):
                if "الموجّه" in line or "المرشد" in line:
                    counselor_col = line.strip(); break
            return {
                "student_name":    session.get("student_name",""),
                "class_name":      session.get("class_name",""),
                "date":            session.get("date",""),
                "title":           session.get("reason","الانضباط المدرسي"),
                "goals":           goals or [session.get("reason","")],
                "discussions":     discs,
                "recommendations": recs,
                "notes":           extra,
                "counselor_name":  counselor_col or self._get_active_counselor_name(),
            }

        def _do_send(session, phone, role):
            sd = _rebuild(session)
            try:
                pdf_bytes = generate_session_pdf(sd)
            except Exception as e:
                messagebox.showerror("خطأ PDF", str(e), parent=win); return
            fname   = "جلسة_{}_{}.pdf".format(session.get("student_name",""), session.get("date",""))
            caption = "📋 جلسة إرشادية (أرشيف) — {} — {} | {}".format(
                session.get("student_name",""), session.get("class_name",""), role)
            ok, res = send_whatsapp_pdf(phone, pdf_bytes, fname, caption)
            if ok:
                messagebox.showinfo("✅ تم", f"تم إرسال الجلسة كـ PDF لـ{role}", parent=win)
            else:
                messagebox.showerror("فشل", f"فشل إرسال الجلسة لـ{role}:\n{res}", parent=win)

        # ── أزرار الإجراءات ───────────────────────────────────────
        act_fr = tk.Frame(win, bg="#f0f4f8", pady=10)
        act_fr.pack(fill="x", padx=16, pady=(4, 10))

        def _print_pdf():
            session = _get_sel()
            if not session: return
            sd = _rebuild(session)
            try:
                pdf_bytes = generate_session_pdf(sd)
            except Exception as e:
                messagebox.showerror("خطأ PDF", str(e), parent=win); return
            import tempfile
            fname = "جلسة_{}_{}.pdf".format(
                session.get("student_name","").replace(" ","_"), session.get("date",""))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="darb_")
            tmp.write(pdf_bytes); tmp.close()
            try:
                if os.name == "nt": os.startfile(tmp.name)
                else:
                    import subprocess; subprocess.Popen(["xdg-open", tmp.name])
            except Exception: pass
            messagebox.showinfo("✅ تم", f"تم فتح ملف PDF\n{tmp.name}", parent=win)

        def _save_pdf():
            session = _get_sel()
            if not session: return
            sd = _rebuild(session)
            try:
                pdf_bytes = generate_session_pdf(sd)
            except Exception as e:
                messagebox.showerror("خطأ PDF", str(e), parent=win); return
            default = "جلسة_{}_{}.pdf".format(
                session.get("student_name","").replace(" ","_"), session.get("date",""))
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension=".pdf", initialfile=default,
                filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
            if not path: return
            with open(path, "wb") as f: f.write(pdf_bytes)
            messagebox.showinfo("✅ تم", f"تم حفظ الجلسة:\n{path}", parent=win)

        def _send_principal():
            session = _get_sel()
            if not session: return
            ph = cfg.get("principal_phone","").strip()
            if not ph: messagebox.showerror("خطأ","لم يُسجَّل رقم مدير المدرسة",parent=win); return
            _do_send(session, ph, "مدير المدرسة")

        def _send_deputy():
            session = _get_sel()
            if not session: return
            ph = cfg.get("alert_admin_phone","").strip()
            if not ph: messagebox.showerror("خطأ","لم يُسجَّل رقم وكيل المدرسة",parent=win); return
            _do_send(session, ph, "وكيل المدرسة")

        def _send_counselors():
            session = _get_sel()
            if not session: return
            c1 = cfg.get("counselor1_phone","").strip()
            c2 = cfg.get("counselor2_phone","").strip()
            if not c1 and not c2:
                messagebox.showwarning("تنبيه","لا توجد أرقام موجّهين مسجّلة",parent=win); return
            sd = _rebuild(session)
            try: pdf_bytes = generate_session_pdf(sd)
            except Exception as e: messagebox.showerror("خطأ PDF",str(e),parent=win); return
            fname = "جلسة_{}_{}.pdf".format(session.get("student_name",""),session.get("date",""))
            sent = 0
            for ph in [c1, c2]:
                if ph:
                    caption = "📋 جلسة إرشادية (أرشيف) — {}".format(session.get("student_name",""))
                    ok, _ = send_whatsapp_pdf(ph, pdf_bytes, fname, caption)
                    if ok: sent += 1
            if sent: messagebox.showinfo("✅ تم", f"تم الإرسال لـ {sent} موجّه", parent=win)
            else: messagebox.showerror("فشل","فشل الإرسال — تحقق من الأرقام وحالة الواتساب",parent=win)

        tk.Button(act_fr, text="🖨️ فتح / طباعة PDF",
                  bg="#1565C0", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=6,
                  command=_print_pdf).pack(side="right", padx=6)
        tk.Button(act_fr, text="💾 حفظ PDF",
                  bg="#065f46", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=6,
                  command=_save_pdf).pack(side="right", padx=6)
        tk.Button(act_fr, text="📤 إرسال للمدير",
                  bg="#0369a1", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  command=_send_principal).pack(side="right", padx=6)
        tk.Button(act_fr, text="📤 إرسال للوكيل",
                  bg="#0369a1", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  command=_send_deputy).pack(side="right", padx=6)
        tk.Button(act_fr, text="📤 إرسال للموجّهَين",
                  bg="#7c3aed", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  command=_send_counselors).pack(side="right", padx=6)
        tk.Button(act_fr, text="🔄 تحديث",
                  bg="#e5e7eb", fg="#374151", font=("Tahoma", 9),
                  relief="flat", cursor="hand2", padx=8, pady=6,
                  command=_load_sessions).pack(side="left", padx=6)

        def _delete_session():
            session = _get_sel()
            if not session: return
            confirm = messagebox.askyesno(
                "تأكيد الحذف",
                f"هل أنت متأكد من حذف جلسة الطالب:\n{session.get('student_name','')} — {session.get('date','')}؟\n\nلا يمكن التراجع عن هذا الإجراء.",
                parent=win)
            if not confirm: return
            try:
                con = get_db(); cur = con.cursor()
                cur.execute("DELETE FROM counselor_sessions WHERE id=?", (session["id"],))
                con.commit(); con.close()
                _load_sessions()
                _detail_txt.config(state="normal")
                _detail_txt.delete("1.0", "end")
                _detail_txt.config(state="disabled")
                messagebox.showinfo("✅ تم", "تم حذف الجلسة الإرشادية بنجاح", parent=win)
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل الحذف:\n{e}", parent=win)

        tk.Button(act_fr, text="🗑️ حذف الجلسة",
                  bg="#dc2626", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  command=_delete_session).pack(side="left", padx=6)

    # ══════════════════════════════════════════════════════════
    # العقد السلوكي — نافذة الإدخال
    # ══════════════════════════════════════════════════════════
    def _open_behavioral_contract_dialog(self, sid=None, sname=None, sclass=None):
        """نافذة إنشاء عقد سلوكي وفق نموذج وزارة التعليم."""
        if sid is None:
            sel = self.tree_counselor.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "الرجاء اختيار طالب أولاً")
                return
            vals = self.tree_counselor.item(sel[0], "values")
            sid, sname, sclass = vals[0], vals[1], vals[2]

        cfg    = load_config()
        school = cfg.get("school_name", "المدرسة")

        win = tk.Toplevel(self.root)
        win.title(f"عقد سلوكي — {sname}")
        win.geometry("700x560")
        win.configure(bg="#fffbeb")
        try: win.state("zoomed")
        except: pass
        win.grab_set()

        AMBER   = "#d97706"
        AMBER_D = "#92400e"
        BG_WIN  = "#fffbeb"
        BG_SEC  = "#fef3c7"
        WHITE   = "#ffffff"
        FONT_H  = ("Tahoma", 11, "bold")
        FONT_N  = ("Tahoma", 10)
        FONT_S  = ("Tahoma",  9)

        # ── رأس النافذة ──────────────────────────────────────────
        hdr_fr = tk.Frame(win, bg=AMBER, height=52)
        hdr_fr.pack(fill="x"); hdr_fr.pack_propagate(False)
        tk.Label(hdr_fr, text="📋 عقد سلوكي", bg=AMBER, fg="white",
                 font=("Tahoma", 14, "bold")).pack(side="right", padx=20, pady=12)
        tk.Label(hdr_fr, text=school, bg=AMBER, fg="#fef3c7",
                 font=FONT_S).pack(side="left", padx=16, pady=12)

        # ── منطقة التمرير الرئيسية ───────────────────────────────
        canvas = tk.Canvas(win, bg=BG_WIN, highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        main = tk.Frame(canvas, bg=BG_WIN, padx=20, pady=14)
        canvas_win = canvas.create_window((0, 0), window=main, anchor="nw")

        def _on_frame_conf(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        _rp_last_w = [0]
        def _on_canvas_conf(e):
            w = canvas.winfo_width()
            if w == _rp_last_w[0]: return
            _rp_last_w[0] = w
            canvas.itemconfig(canvas_win, width=w)
        main.bind("<Configure>", _on_frame_conf)
        canvas.bind("<Configure>", _on_canvas_conf)

        # ── بيانات الطالب ────────────────────────────────────────
        info_fr = tk.LabelFrame(main, text=" بيانات الطالب ", font=FONT_H,
                                fg=AMBER_D, bg=BG_WIN, pady=8, padx=10)
        info_fr.pack(fill="x", pady=(0, 10))

        row1 = tk.Frame(info_fr, bg=BG_WIN); row1.pack(fill="x", pady=3)
        tk.Label(row1, text="اسم الطالب:", bg=BG_WIN, font=FONT_N,
                 width=12, anchor="e").pack(side="right")
        tk.Label(row1, text=sname, bg=BG_SEC, font=("Tahoma", 10, "bold"),
                 fg=AMBER_D, relief="groove", padx=10).pack(side="right", padx=6)

        row2 = tk.Frame(info_fr, bg=BG_WIN); row2.pack(fill="x", pady=3)
        tk.Label(row2, text="الفصل الدراسي:", bg=BG_WIN, font=FONT_N,
                 width=12, anchor="e").pack(side="right")
        tk.Label(row2, text=sclass, bg=BG_SEC, font=("Tahoma", 10, "bold"),
                 fg=AMBER_D, relief="groove", padx=10).pack(side="right", padx=6)

        row3 = tk.Frame(info_fr, bg=BG_WIN); row3.pack(fill="x", pady=3)
        tk.Label(row3, text="موضوع العقد:", bg=BG_WIN, font=FONT_N,
                 width=12, anchor="e").pack(side="right")
        subject_var = tk.StringVar(value="الانضباط السلوكي")
        ttk.Entry(row3, textvariable=subject_var, width=30,
                  font=FONT_N).pack(side="right", padx=6)

        # ── الفترة الزمنية ───────────────────────────────────────
        period_fr = tk.LabelFrame(main, text=" الفترة الزمنية للعقد (بالتاريخ الهجري) ",
                                   font=FONT_H, fg=AMBER_D, bg=BG_WIN, pady=8, padx=10)
        period_fr.pack(fill="x", pady=(0, 10))

        today_h = now_riyadh_date()  # ميلادي — يمكن الكتابة يدوياً
        p_row = tk.Frame(period_fr, bg=BG_WIN); p_row.pack(fill="x")
        tk.Label(p_row, text="من:", bg=BG_WIN, font=FONT_N).pack(side="right", padx=(0,4))
        period_from_var = tk.StringVar(value="")
        ttk.Entry(p_row, textvariable=period_from_var, width=16,
                  font=FONT_N).pack(side="right", padx=6)
        tk.Label(p_row, text="إلى:", bg=BG_WIN, font=FONT_N).pack(side="right", padx=(10,4))
        period_to_var = tk.StringVar(value="")
        ttk.Entry(p_row, textvariable=period_to_var, width=16,
                  font=FONT_N).pack(side="right", padx=6)
        tk.Label(p_row, text="(مثال: 01/09/1446)", bg=BG_WIN,
                 font=("Tahoma", 8), fg="#9ca3af").pack(side="right", padx=4)

        # ── التاريخ الميلادي للحفظ ──────────────────────────────
        date_row = tk.Frame(main, bg=BG_WIN); date_row.pack(fill="x", pady=(0,6))
        tk.Label(date_row, text="تاريخ العقد (ميلادي):", bg=BG_WIN, font=FONT_N,
                 width=18, anchor="e").pack(side="right")
        date_var = tk.StringVar(value=today_h)
        ttk.Entry(date_row, textvariable=date_var, width=14,
                  font=FONT_N).pack(side="right", padx=6)

        # ── ملاحظات إضافية ──────────────────────────────────────
        notes_fr = tk.LabelFrame(main, text=" ملاحظات إضافية (اختياري) ",
                                  font=FONT_H, fg=AMBER_D, bg=BG_WIN, pady=6, padx=10)
        notes_fr.pack(fill="x", pady=(0, 10))
        notes_txt = tk.Text(notes_fr, height=4, font=FONT_N, relief="groove", wrap="word")
        notes_txt.pack(fill="x")

        # ── معاينة البنود ────────────────────────────────────────
        preview_fr = tk.LabelFrame(main, text=" بنود العقد (تُطبع تلقائياً) ",
                                    font=FONT_H, fg=AMBER_D, bg=BG_WIN, pady=6, padx=10)
        preview_fr.pack(fill="x", pady=(0, 10))
        preview_txt = tk.Text(preview_fr, height=8, font=("Tahoma", 9),
                               state="disabled", bg=BG_SEC, relief="flat", wrap="word")
        preview_txt.pack(fill="x")
        preview_content = (
            "المسؤوليات على الطالب:\n"
            "  1 - الحضور للمدرسة بانتظام.\n"
            "  2 - القيام بالواجبات المنزلية المُكلَّف بها.\n"
            "  3 - عدم الاعتداء على أي طالب بالمدرسة.\n"
            "  4 - عدم القيام بأي مخالفات داخل المدرسة.\n\n"
            "المزايا والتدعيمات:\n"
            "  1 - سوف يضاف له درجات في السلوك.\n"
            "  2 - سوف يذكر اسمه في الإذاعة المدرسية كطالب متميز.\n"
            "  3 - سوف يسلم شهادة تميز سلوكي.\n"
            "  4 - يُكرَّم في نهاية العام الدراسي.\n"
            "  5 - يتم مساعدته في المواد الدراسية من قبل المعلمين.\n\n"
            "مكافآت إضافية: عند الاستمرار في هذا التميز السلوكي حتى نهاية العام.\n"
            "عقوبات: في حالة عدم الالتزام تُلغى المزايا ويُتخذ الإجراء المناسب."
        )
        preview_txt.config(state="normal")
        preview_txt.insert("1.0", preview_content)
        preview_txt.config(state="disabled")

        # ── أزرار الإجراءات ──────────────────────────────────────
        btn_bot = tk.Frame(win, bg=BG_WIN, pady=10)
        btn_bot.pack(fill="x", padx=20, side="bottom")

        def _get_contract_data():
            return {
                "date":          date_var.get().strip(),
                "student_id":    sid,
                "student_name":  sname,
                "class_name":    sclass,
                "subject":       subject_var.get().strip(),
                "period_from":   period_from_var.get().strip(),
                "period_to":     period_to_var.get().strip(),
                "notes":         notes_txt.get("1.0", "end").strip(),
                "school_name":   school,
                "counselor_name": self._get_active_counselor_name(),
            }

        def save_contract():
            d = _get_contract_data()
            if not d["date"]:
                messagebox.showwarning("تنبيه", "الرجاء إدخال تاريخ العقد", parent=win)
                return
            try:
                con = get_db(); cur = con.cursor()
                cur.execute("""INSERT INTO behavioral_contracts
                    (date, student_id, student_name, class_name, subject,
                     period_from, period_to, notes, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (d["date"], d["student_id"], d["student_name"],
                     d["class_name"], d["subject"], d["period_from"],
                     d["period_to"], d["notes"],
                     datetime.datetime.utcnow().isoformat()))
                con.commit(); con.close()
                messagebox.showinfo("✅ تم", "تم حفظ العقد السلوكي بنجاح", parent=win)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)

        def _open_pdf():
            d = _get_contract_data()
            try:
                pdf_bytes = generate_behavioral_contract_pdf(d)
            except Exception as e:
                messagebox.showerror("خطأ PDF", str(e), parent=win); return
            import tempfile
            fname = "عقد_سلوكي_{}_{}.pdf".format(sname, d["date"])
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="contract_")
            tmp.write(pdf_bytes); tmp.close()
            try:
                if os.name == "nt": os.startfile(tmp.name)
                else: import subprocess; subprocess.Popen(["xdg-open", tmp.name])
            except Exception: pass
            messagebox.showinfo("✅ تم", f"تم فتح ملف PDF\n{tmp.name}", parent=win)

        def _save_pdf():
            d = _get_contract_data()
            try:
                pdf_bytes = generate_behavioral_contract_pdf(d)
            except Exception as e:
                messagebox.showerror("خطأ PDF", str(e), parent=win); return
            default = "عقد_سلوكي_{}_{}.pdf".format(
                sname.replace(" ", "_"), d["date"])
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension=".pdf", initialfile=default,
                filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
            if not path: return
            with open(path, "wb") as f: f.write(pdf_bytes)
            messagebox.showinfo("✅ تم", f"تم حفظ العقد:\n{path}", parent=win)

        def _send_whatsapp(role_key, role_label):
            ph = load_config().get(role_key, "").strip()
            if not ph:
                messagebox.showerror("خطأ", f"لم يُسجَّل رقم {role_label}", parent=win)
                return
            d = _get_contract_data()
            try: pdf_bytes = generate_behavioral_contract_pdf(d)
            except Exception as e: messagebox.showerror("خطأ PDF", str(e), parent=win); return
            fname   = "عقد_سلوكي_{}_{}.pdf".format(sname, d["date"])
            caption = f"📋 عقد سلوكي — {sname} — {sclass} | {role_label}"
            ok, res = send_whatsapp_pdf(ph, pdf_bytes, fname, caption)
            if ok:
                messagebox.showinfo("✅ تم", f"تم إرسال العقد كـ PDF لـ{role_label}", parent=win)
            else:
                messagebox.showerror("فشل", f"فشل الإرسال لـ{role_label}:\n{res}", parent=win)

        def _send_parent():
            store = load_students()
            phone = ""
            for cls in store["list"]:
                for s in cls["students"]:
                    if s["id"] == sid:
                        phone = s.get("phone", "")
                        break
            if not phone:
                messagebox.showerror("خطأ", "رقم ولي الأمر غير مسجل", parent=win); return
            d = _get_contract_data()
            try: pdf_bytes = generate_behavioral_contract_pdf(d)
            except Exception as e: messagebox.showerror("خطأ PDF", str(e), parent=win); return
            fname   = "عقد_سلوكي_{}_{}.pdf".format(sname, d["date"])
            caption = f"📋 عقد سلوكي — {sname} — {sclass} | ولي الأمر"
            ok, res = send_whatsapp_pdf(phone, pdf_bytes, fname, caption)
            if ok:
                messagebox.showinfo("✅ تم", "تم إرسال العقد كـ PDF لولي الأمر", parent=win)
            else:
                messagebox.showerror("فشل", f"فشل الإرسال لولي الأمر:\n{res}", parent=win)

        for txt, bg, cmd in [
            ("💾 حفظ العقد",           "#d97706", save_contract),
            ("🖨️ معاينة / طباعة PDF", "#1565C0", _open_pdf),
            ("💾 تصدير PDF",           "#065f46", _save_pdf),
            ("📤 إرسال للمدير",        "#0369a1", lambda: _send_whatsapp("principal_phone",    "مدير المدرسة")),
            ("📤 إرسال للوكيل",        "#0369a1", lambda: _send_whatsapp("alert_admin_phone",  "وكيل المدرسة")),
            ("📤 إرسال لولي الأمر",    "#7c3aed", _send_parent),
        ]:
            tk.Button(btn_bot, text=txt, bg=bg, fg="white",
                      font=("Tahoma", 10, "bold"), relief="flat",
                      cursor="hand2", padx=10, pady=6,
                      command=cmd).pack(side="right", padx=5)

    # ══════════════════════════════════════════════════════════
    # العقد السلوكي — أرشيف العقود
    # ══════════════════════════════════════════════════════════
    def _open_contracts_archive(self, filter_sid=None, filter_name=None):
        """أرشيف العقود السلوكية — يعرض كل العقود المحفوظة مع إمكانية البحث والطباعة والإرسال والحذف."""
        win = tk.Toplevel(self.root)
        title_txt = f"📄 أرشيف العقود السلوكية — {filter_name}" if filter_name else "📄 أرشيف العقود السلوكية"
        win.title(title_txt)
        win.geometry("1050x680")
        win.configure(bg="#fffbeb")
        try: win.state("zoomed")
        except: pass

        cfg = load_config()

        AMBER   = "#d97706"
        AMBER_D = "#92400e"
        BG_HDR  = "#d97706"
        BG_CTRL = "#fef3c7"
        BG_WIN  = "#fffbeb"

        # ── رأس النافذة ──────────────────────────────────────────
        hdr = tk.Frame(win, bg=BG_HDR, height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📄 أرشيف العقود السلوكية",
                 bg=BG_HDR, fg="white",
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=20, pady=14)
        if filter_name:
            tk.Label(hdr, text=f"طالب: {filter_name}",
                     bg=BG_HDR, fg="#fef3c7",
                     font=("Tahoma", 10)).pack(side="right", padx=10, pady=14)

        # ── شريط البحث والفلترة ──────────────────────────────────
        ctrl = tk.Frame(win, bg=BG_CTRL, pady=8)
        ctrl.pack(fill="x")

        tk.Label(ctrl, text="🔍 بحث:", bg=BG_CTRL,
                 font=("Tahoma", 10, "bold"), fg=AMBER_D).pack(side="right", padx=(10, 4))
        _search_var = tk.StringVar()
        search_ent = ttk.Entry(ctrl, textvariable=_search_var, width=22, font=("Tahoma", 10))
        search_ent.pack(side="right", padx=4)

        tk.Label(ctrl, text="من:", bg=BG_CTRL,
                 font=("Tahoma", 10), fg=AMBER_D).pack(side="right", padx=(10, 4))
        _date_from = tk.StringVar()
        ttk.Entry(ctrl, textvariable=_date_from, width=12, font=("Tahoma", 10)).pack(side="right", padx=2)

        tk.Label(ctrl, text="إلى:", bg=BG_CTRL,
                 font=("Tahoma", 10), fg=AMBER_D).pack(side="right", padx=(6, 4))
        _date_to = tk.StringVar()
        ttk.Entry(ctrl, textvariable=_date_to, width=12, font=("Tahoma", 10)).pack(side="right", padx=2)

        tk.Button(ctrl, text="🔍 تصفية", bg=AMBER, fg="white",
                  font=("Tahoma", 9, "bold"), relief="flat", cursor="hand2",
                  padx=8, command=lambda: _load_contracts()).pack(side="right", padx=8)
        tk.Button(ctrl, text="↺ إعادة تعيين", bg="#e5e7eb", fg="#374151",
                  font=("Tahoma", 9), relief="flat", cursor="hand2",
                  padx=8, command=lambda: [_search_var.set(""),
                                           _date_from.set(""), _date_to.set(""),
                                           _load_contracts()]).pack(side="right", padx=4)

        _count_lbl = tk.Label(ctrl, text="", bg=BG_CTRL,
                               font=("Tahoma", 9), fg=AMBER_D)
        _count_lbl.pack(side="left", padx=14)

        # ── الجدول الرئيسي ────────────────────────────────────────
        tbl_fr = tk.Frame(win, bg="white")
        tbl_fr.pack(fill="both", expand=True, padx=16, pady=(8, 0))

        cols = ("id", "date", "student_name", "class_name", "subject", "period_from", "period_to")
        tree = ttk.Treeview(tbl_fr, columns=cols, show="headings", height=18,
                            selectmode="browse")

        hdrs = {
            "id":           ("رقم",         50),
            "date":         ("التاريخ",      100),
            "student_name": ("اسم الطالب",  170),
            "class_name":   ("الفصل",        110),
            "subject":      ("موضوع العقد",  200),
            "period_from":  ("من",            110),
            "period_to":    ("إلى",           110),
        }
        for col, (lbl, w) in hdrs.items():
            tree.heading(col, text=lbl, anchor="center")
            tree.column(col, width=w, anchor="center",
                        stretch=(col in ("subject",)))
        tree.column("id", width=0, stretch=False)

        vsb = ttk.Scrollbar(tbl_fr, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(tbl_fr, orient="horizontal",  command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="left",   fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="right", fill="both", expand=True)

        tree.tag_configure("odd",  background="#fef9c3")
        tree.tag_configure("even", background="white")

        # ── تحميل العقود ────────────────────────────────────────
        _all_contracts = []

        def _load_contracts():
            nonlocal _all_contracts
            tree.delete(*tree.get_children())
            con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
            cur.execute("SELECT * FROM behavioral_contracts ORDER BY date DESC, created_at DESC")
            rows = [dict(r) for r in cur.fetchall()]
            con.close()

            if filter_sid:
                rows = [r for r in rows if str(r.get("student_id","")) == str(filter_sid)]

            q = _search_var.get().strip().lower()
            if q:
                rows = [r for r in rows
                        if q in str(r.get("student_name","")).lower()
                        or q in str(r.get("class_name","")).lower()
                        or q in str(r.get("subject","")).lower()]

            df = _date_from.get().strip()
            dt = _date_to.get().strip()
            if df: rows = [r for r in rows if str(r.get("date","")) >= df]
            if dt: rows = [r for r in rows if str(r.get("date","")) <= dt]

            _all_contracts.clear()
            _all_contracts.extend(rows)
            _count_lbl.config(text=f"عدد العقود: {len(rows)}")

            for i, r in enumerate(rows):
                tag = "odd" if i % 2 == 0 else "even"
                tree.insert("", "end", iid=str(r["id"]),
                            values=(r["id"], r.get("date",""),
                                    r.get("student_name",""),
                                    r.get("class_name",""),
                                    r.get("subject",""),
                                    r.get("period_from",""),
                                    r.get("period_to","")),
                            tags=(tag,))

        _load_contracts()
        search_ent.bind("<KeyRelease>", lambda e: _load_contracts())

        # ── لوحة التفاصيل ────────────────────────────────────────
        detail_fr = tk.LabelFrame(win, text=" 📋 تفاصيل العقد المحدد ",
                                  font=("Tahoma", 10, "bold"),
                                  fg=AMBER_D, bg=BG_WIN, padx=10, pady=6)
        detail_fr.pack(fill="x", padx=16, pady=(6, 0))

        _detail_txt = tk.Text(detail_fr, height=4, font=("Tahoma", 10),
                               state="disabled", bg=BG_CTRL,
                               relief="flat", wrap="word")
        _detail_txt.pack(fill="x")

        def _on_select(event=None):
            sel = tree.selection()
            if not sel: return
            contract = next((r for r in _all_contracts if str(r["id"]) == str(sel[0])), None)
            if not contract: return
            notes = contract.get("notes", "") or ""
            detail = (
                f"📅 التاريخ: {contract.get('date','')}\n"
                f"👤 الطالب: {contract.get('student_name','')}  |  الفصل: {contract.get('class_name','')}\n"
                f"📌 الموضوع: {contract.get('subject','')}\n"
                f"🗓️ الفترة: من {contract.get('period_from','')} إلى {contract.get('period_to','')}\n"
            )
            if notes:
                detail += f"📝 الملاحظات: {notes}"
            _detail_txt.config(state="normal")
            _detail_txt.delete("1.0", "end")
            _detail_txt.insert("1.0", detail)
            _detail_txt.config(state="disabled")

        tree.bind("<<TreeviewSelect>>", _on_select)

        # ── دوال مساعدة ──────────────────────────────────────────
        def _get_sel():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "الرجاء اختيار عقد أولاً", parent=win)
                return None
            return next((r for r in _all_contracts if str(r["id"]) == str(sel[0])), None)

        def _rebuild_contract(c):
            return {
                "date":          c.get("date",""),
                "student_id":    c.get("student_id",""),
                "student_name":  c.get("student_name",""),
                "class_name":    c.get("class_name",""),
                "subject":       c.get("subject",""),
                "period_from":   c.get("period_from",""),
                "period_to":     c.get("period_to",""),
                "notes":         c.get("notes",""),
                "school_name":   cfg.get("school_name","المدرسة"),
                "counselor_name": self._get_active_counselor_name(),
            }

        # ── أزرار الإجراءات ───────────────────────────────────────
        act_fr = tk.Frame(win, bg=BG_WIN, pady=10)
        act_fr.pack(fill="x", padx=16, pady=(4, 10))

        def _print_pdf():
            contract = _get_sel()
            if not contract: return
            cd = _rebuild_contract(contract)
            try: pdf_bytes = generate_behavioral_contract_pdf(cd)
            except Exception as e: messagebox.showerror("خطأ PDF", str(e), parent=win); return
            import tempfile
            fname = "عقد_سلوكي_{}_{}.pdf".format(
                contract.get("student_name","").replace(" ","_"), contract.get("date",""))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="contract_")
            tmp.write(pdf_bytes); tmp.close()
            try:
                if os.name == "nt": os.startfile(tmp.name)
                else: import subprocess; subprocess.Popen(["xdg-open", tmp.name])
            except Exception: pass
            messagebox.showinfo("✅ تم", f"تم فتح ملف PDF\n{tmp.name}", parent=win)

        def _save_pdf():
            contract = _get_sel()
            if not contract: return
            cd = _rebuild_contract(contract)
            try: pdf_bytes = generate_behavioral_contract_pdf(cd)
            except Exception as e: messagebox.showerror("خطأ PDF", str(e), parent=win); return
            default = "عقد_سلوكي_{}_{}.pdf".format(
                contract.get("student_name","").replace(" ","_"), contract.get("date",""))
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension=".pdf", initialfile=default,
                filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
            if not path: return
            with open(path, "wb") as f: f.write(pdf_bytes)
            messagebox.showinfo("✅ تم", f"تم حفظ العقد:\n{path}", parent=win)

        def _send_role(role_key, role_label):
            contract = _get_sel()
            if not contract: return
            ph = cfg.get(role_key,"").strip()
            if not ph:
                messagebox.showerror("خطأ", f"لم يُسجَّل رقم {role_label}", parent=win); return
            cd = _rebuild_contract(contract)
            try: pdf_bytes = generate_behavioral_contract_pdf(cd)
            except Exception as e: messagebox.showerror("خطأ PDF", str(e), parent=win); return
            fname   = "عقد_سلوكي_{}_{}.pdf".format(contract.get("student_name",""), contract.get("date",""))
            caption = f"📋 عقد سلوكي (أرشيف) — {contract.get('student_name','')} — {contract.get('class_name','')} | {role_label}"
            ok, res = send_whatsapp_pdf(ph, pdf_bytes, fname, caption)
            if ok: messagebox.showinfo("✅ تم", f"تم إرسال العقد كـ PDF لـ{role_label}", parent=win)
            else:  messagebox.showerror("فشل", f"فشل الإرسال:\n{res}", parent=win)

        def _delete_contract():
            contract = _get_sel()
            if not contract: return
            confirm = messagebox.askyesno(
                "تأكيد الحذف",
                f"هل أنت متأكد من حذف عقد الطالب:\n{contract.get('student_name','')} — {contract.get('date','')}؟\n\nلا يمكن التراجع عن هذا الإجراء.",
                parent=win)
            if not confirm: return
            try:
                con = get_db(); cur = con.cursor()
                cur.execute("DELETE FROM behavioral_contracts WHERE id=?", (contract["id"],))
                con.commit(); con.close()
                _load_contracts()
                _detail_txt.config(state="normal")
                _detail_txt.delete("1.0", "end")
                _detail_txt.config(state="disabled")
                messagebox.showinfo("✅ تم", "تم حذف العقد السلوكي بنجاح", parent=win)
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل الحذف:\n{e}", parent=win)

        for txt, bg, cmd in [
            ("🖨️ فتح / طباعة PDF", "#1565C0", _print_pdf),
            ("💾 حفظ PDF",          "#065f46", _save_pdf),
            ("📤 إرسال للمدير",     "#0369a1", lambda: _send_role("principal_phone",   "مدير المدرسة")),
            ("📤 إرسال للوكيل",     "#0369a1", lambda: _send_role("alert_admin_phone", "وكيل المدرسة")),
            ("📤 إرسال للموجّهَين", "#7c3aed", lambda: _send_role("counselor1_phone",  "الموجّه الطلابي")),
        ]:
            tk.Button(act_fr, text=txt, bg=bg, fg="white",
                      font=("Tahoma", 10, "bold"), relief="flat",
                      cursor="hand2", padx=12, pady=6,
                      command=cmd).pack(side="right", padx=6)

        tk.Button(act_fr, text="🗑️ حذف العقد",
                  bg="#dc2626", fg="white", font=("Tahoma", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  command=_delete_contract).pack(side="left", padx=6)
        tk.Button(act_fr, text="🔄 تحديث",
                  bg="#e5e7eb", fg="#374151", font=("Tahoma", 9),
                  relief="flat", cursor="hand2", padx=8, pady=6,
                  command=_load_contracts).pack(side="left", padx=6)

    # ══════════════════════════════════════════════════════════
    # تبويب الاستئذان
    # ══════════════════════════════════════════════════════════
    def _build_permissions_tab(self):
        frame = self.permissions_frame

        hdr = tk.Frame(frame, bg="#0277BD", height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🚪 الاستئذان — موافقة ولي الأمر",
                 bg="#0277BD", fg="white",
                 font=("Tahoma",12,"bold")).pack(side="right", padx=14, pady=12)

        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", padx=8, pady=(6,4))
        ttk.Label(ctrl, text="التاريخ:").pack(side="right", padx=(0,4))
        self.perm_date_var = tk.StringVar(value=now_riyadh_date())
        ttk.Entry(ctrl, textvariable=self.perm_date_var, width=12).pack(side="right", padx=4)
        ttk.Button(ctrl, text="🔍 عرض",
                   command=self._perm_load).pack(side="right", padx=4)
        ttk.Button(ctrl, text="➕ طلب استئذان",
                   command=self._perm_add_dialog).pack(side="right", padx=4)
        ttk.Button(ctrl, text="📲 إعادة إرسال",
                   command=self._perm_resend).pack(side="right", padx=4)
        ttk.Button(ctrl, text="🗑️ حذف",
                   command=self._perm_delete).pack(side="left", padx=4)

        # مؤشر الحالة
        ind = ttk.Frame(frame); ind.pack(fill="x", padx=8, pady=2)
        self.perm_wait_lbl = ttk.Label(ind, text="",
                                        foreground="#E65100", font=("Tahoma",9,"bold"))
        self.perm_wait_lbl.pack(side="right")
        self.perm_ok_lbl = ttk.Label(ind, text="",
                                      foreground="#2E7D32", font=("Tahoma",9,"bold"))
        self.perm_ok_lbl.pack(side="right", padx=12)

        cols = ("id","student_name","class_name","parent_phone",
                "reason","status","approved_by")
        self.tree_perm = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for c,h,w in zip(cols,
            ["ID","اسم الطالب","الفصل","جوال ولي الأمر","السبب","الحالة","الموافق"],
            [35,200,130,120,150,80,120]):
            self.tree_perm.heading(c,text=h)
            self.tree_perm.column(c,width=w,anchor="center")
        self.tree_perm.tag_configure("waiting",  background="#FFF8E1", foreground="#E65100")
        self.tree_perm.tag_configure("approved", background="#E8F5E9", foreground="#2E7D32")
        self.tree_perm.tag_configure("rejected", background="#FFEBEE", foreground="#C62828")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_perm.yview)
        self.tree_perm.configure(yscrollcommand=sb.set)
        self.tree_perm.pack(side="left", fill="both", expand=True, padx=(8,0))
        sb.pack(side="right", fill="y", padx=(0,8))
        self._perm_load()
        self._perm_schedule_refresh()

    def _perm_schedule_refresh(self):
        """تحديث تلقائي كل 5 دقائق — يعمل فقط إذا كان تبويب الاستئذان نشطاً."""
        if hasattr(self, "_current_tab") and self._current_tab.get() == "الاستئذان":
            self._perm_load()
        self.root.after(300_000, self._perm_schedule_refresh)

    def _perm_load(self):
        if not hasattr(self,"tree_perm"): return
        date_f = self.perm_date_var.get().strip() if hasattr(self,"perm_date_var") else now_riyadh_date()
        rows = query_permissions(date_filter=date_f)
        for i in self.tree_perm.get_children(): self.tree_perm.delete(i)
        waiting = approved = 0
        for r in rows:
            s   = r.get("status", PERM_WAITING)
            tag = {"انتظار":"waiting","موافق":"approved","مرفوض":"rejected"}.get(s,"waiting")
            if s == PERM_WAITING:  waiting  += 1
            if s == PERM_APPROVED: approved += 1
            self.tree_perm.insert("","end", iid=str(r["id"]), tags=(tag,),
                values=(r["id"],r["student_name"],r["class_name"],
                        r.get("parent_phone",""),r.get("reason",""),
                        s, r.get("approved_by","")))
        if hasattr(self,"perm_wait_lbl"):
            self.perm_wait_lbl.config(
                text="⏳ انتظار: {}".format(waiting) if waiting else "")
        if hasattr(self,"perm_ok_lbl"):
            self.perm_ok_lbl.config(
                text="✅ وافق وخرج: {}".format(approved) if approved else "")

    def _perm_add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("طلب استئذان جديد")
        win.geometry("480x380")
        win.transient(self.root); win.grab_set()

        ttk.Label(win, text="تسجيل طلب استئذان",
                  font=("Tahoma",12,"bold")).pack(pady=(12,4))
        ttk.Label(win, text="سيُرسَل واتساب لولي الأمر طالباً موافقته",
                  foreground="#5A6A7E").pack(pady=(0,8))

        form = ttk.Frame(win, padding=14); form.pack(fill="both")

        def row(lbl, w_fn):
            f = ttk.Frame(form); f.pack(fill="x", pady=4)
            ttk.Label(f, text=lbl, width=14, anchor="e").pack(side="right")
            w = w_fn(f); w.pack(side="right", fill="x", expand=True, padx=(0,6))
            return w

        date_var = tk.StringVar(value=now_riyadh_date())
        row("التاريخ:", lambda p: ttk.Entry(p, textvariable=date_var, width=14))

        cls_var = tk.StringVar()
        cls_cb  = row("الفصل:", lambda p: ttk.Combobox(
            p, textvariable=cls_var,
            values=[c["name"] for c in self.store["list"]], state="readonly"))

        stu_var = tk.StringVar()
        stu_cb  = row("الطالب:", lambda p: ttk.Combobox(p, textvariable=stu_var, state="readonly"))

        phone_var = tk.StringVar()
        row("جوال ولي الأمر:", lambda p: ttk.Entry(p, textvariable=phone_var, width=16, justify="right"))

        def on_cls(*_):
            cls = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if cls:
                stu_cb["values"] = ["{} ({})".format(s["name"],s["id"])
                                     for s in sorted(cls["students"],key=lambda x:x["name"])]

        def on_stu(*_):
            import re as _re
            m = _re.match(r"^(.+)\(([^)]+)\)$", stu_var.get().strip())
            if not m: return
            sid = m.group(2).strip()
            for cls in self.store["list"]:
                for s in cls["students"]:
                    if s["id"] == sid:
                        phone_var.set(s.get("phone",""))
                        return

        cls_cb.bind("<<ComboboxSelected>>", on_cls)
        stu_cb.bind("<<ComboboxSelected>>", on_stu)

        reason_var = tk.StringVar(value=PERMISSION_REASONS[0])
        row("السبب:", lambda p: ttk.Combobox(p, textvariable=reason_var,
                                               values=PERMISSION_REASONS, state="readonly"))
        approved_var = tk.StringVar(
            value=CURRENT_USER.get("name", CURRENT_USER.get("username","")))
        row("الموافق:", lambda p: ttk.Entry(p, textvariable=approved_var))

        status_lbl = ttk.Label(win, text=""); status_lbl.pack()

        def save():
            import re as _re
            cls_obj = next((c for c in self.store["list"] if c["name"]==cls_var.get()), None)
            if not cls_obj:
                messagebox.showwarning("تنبيه","اختر فصلاً",parent=win); return
            m = _re.match(r"^(.+)\(([^)]+)\)$", stu_var.get().strip())
            if not m:
                messagebox.showwarning("تنبيه","اختر طالباً",parent=win); return
            sname, sid = m.group(1).strip(), m.group(2).strip()
            phone = phone_var.get().strip()

            pid = insert_permission(date_var.get(), sid, sname,
                                    cls_obj["id"], cls_obj["name"],
                                    phone, reason_var.get(), approved_var.get())
            if phone:
                status_lbl.config(text="⏳ جارٍ إرسال واتساب...", foreground="#1565C0")
                win.update_idletasks()
                ok, msg = send_permission_request(pid)
                if ok:
                    status_lbl.config(text="✅ أُرسل — في انتظار رد ولي الأمر",
                                       foreground="green")
                else:
                    status_lbl.config(text="⚠️ لم يُرسَل: {} — الطلب مسجّل".format(msg),
                                       foreground="orange")
            else:
                status_lbl.config(text="⚠️ لا رقم — الطلب مسجّل بدون إرسال",
                                   foreground="orange")
            self._perm_load()
            win.after(1200, win.destroy)

        ttk.Button(win, text="📲 تسجيل وإرسال لولي الأمر",
                   command=save).pack(pady=10)

    def _perm_resend(self):
        sel = self.tree_perm.selection() if hasattr(self,"tree_perm") else []
        if not sel:
            messagebox.showwarning("تنبيه","حدد طلباً أولاً"); return
        pid = int(self.tree_perm.item(sel[0],"values")[0])
        ok, msg = send_permission_request(pid)
        if ok:
            messagebox.showinfo("تم","✅ تم إعادة الإرسال")
        else:
            messagebox.showwarning("فشل","❌ " + msg)

    def _perm_delete(self):
        sel = self.tree_perm.selection() if hasattr(self,"tree_perm") else []
        if not sel:
            messagebox.showwarning("تنبيه","حدد سجلاً"); return
        if not messagebox.askyesno("تأكيد","حذف هذا السجل؟"): return
        delete_permission(int(self.tree_perm.item(sel[0],"values")[0]))
        self._perm_load()


    def _build_term_report_tab(self):
        frame = self.term_report_frame

        hdr = tk.Frame(frame, bg="#4A148C", height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="📊 تقرير نهاية الفصل الدراسي",
                 bg="#4A148C", fg="white",
                 font=("Tahoma",12,"bold")).pack(side="right", padx=14, pady=12)

        body = ttk.Frame(frame); body.pack(fill="both", expand=True, padx=16, pady=12)

        lf = ttk.LabelFrame(body, text=" الفترة الزمنية ", padding=12)
        lf.pack(fill="x", pady=(0,12))

        now2 = datetime.datetime.now()
        r1 = ttk.Frame(lf); r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="من (YYYY-MM):", width=16, anchor="e").pack(side="right")
        self.term_from_var = tk.StringVar(
            value=(now2-datetime.timedelta(days=120)).strftime("%Y-%m"))
        ttk.Entry(r1, textvariable=self.term_from_var, width=12).pack(side="right", padx=4)

        r2 = ttk.Frame(lf); r2.pack(fill="x", pady=4)
        ttk.Label(r2, text="إلى (YYYY-MM):", width=16, anchor="e").pack(side="right")
        self.term_to_var = tk.StringVar(value=now2.strftime("%Y-%m"))
        ttk.Entry(r2, textvariable=self.term_to_var, width=12).pack(side="right", padx=4)

        br = ttk.Frame(lf); br.pack(fill="x", pady=(8,0))
        ttk.Button(br, text="📊 إنشاء التقرير",
                   command=self._generate_term_report).pack(side="right", padx=4)
        ttk.Button(br, text="🖨️ فتح للطباعة",
                   command=self._open_term_report).pack(side="right", padx=4)

        self.term_status = ttk.Label(lf, text="", foreground="#5A6A7E")
        self.term_status.pack(anchor="e", pady=(6,0))

        prev_lf = ttk.LabelFrame(body, text=" معاينة ", padding=4)
        prev_lf.pack(fill="both", expand=True)
        self.term_preview = tk.Text(prev_lf, wrap="word",
                                     font=("Tahoma",9), state="disabled", bg="#FAFAFA")
        sb = ttk.Scrollbar(prev_lf, orient="vertical", command=self.term_preview.yview)
        self.term_preview.configure(yscrollcommand=sb.set)
        self.term_preview.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._term_html = ""

    def _generate_term_report(self):
        mf = self.term_from_var.get().strip() if hasattr(self,"term_from_var") else None
        mt = self.term_to_var.get().strip()   if hasattr(self,"term_to_var")   else None
        if hasattr(self,"term_status"):
            self.term_status.config(text="⏳ جارٍ الإنشاء...")
        self.root.update_idletasks()
        import threading as _th
        def _build():
            try:
                html = generate_term_report_html(mf, mt)
                self._term_html = html
                self.root.after(0, self._show_term_preview)
            except Exception as e:
                self.root.after(0, lambda: self.term_status.config(
                    text="❌ خطأ: {}".format(e), foreground="red"))
        _th.Thread(target=_build, daemon=True).start()

    def _show_term_preview(self):
        import re as _re
        html = self._term_html
        # احذف style وscript كاملاً أولاً
        html = _re.sub(r'<style[^>]*>.*?</style>', '', html, flags=_re.DOTALL)
        html = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL)
        # احذف باقي الـ tags
        text = _re.sub(r'<[^>]+>', ' ', html)
        # نظّف المسافات والأسطر الزائدة
        text = _re.sub(r'[ \t]{2,}', ' ', text)
        text = _re.sub(r'\n{3,}', '\n\n', text).strip()
        if hasattr(self,"term_preview"):
            self.term_preview.config(state="normal")
            self.term_preview.delete("1.0","end")
            self.term_preview.insert("1.0", text)
            self.term_preview.config(state="disabled")
        if hasattr(self,"term_status"):
            self.term_status.config(
                text="✅ جاهز — اضغط 'فتح للطباعة'", foreground="green")
    def _open_term_report(self):
        if not self._term_html:
            self._generate_term_report()
            messagebox.showinfo("تنبيه","انتظر اكتمال التقرير ثم اضغط مجدداً")
            return
        tmp = os.path.join(DATA_DIR, "term_report.html")
        with open(tmp,"w",encoding="utf-8") as f: f.write(self._term_html)
        webbrowser.open("file://{}".format(os.path.abspath(tmp)))


    def _build_results_tab(self):
        frame = self.results_frame

        hdr = tk.Frame(frame, bg="#1A237E", height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🎓 نشر نتائج الطلاب",
                 bg="#1A237E", fg="white",
                 font=("Tahoma",12,"bold")).pack(side="right", padx=14, pady=12)

        body = ttk.Frame(frame); body.pack(fill="both", expand=True, padx=16, pady=12)

        # ─ قسم رفع الملف
        upload_lf = ttk.LabelFrame(body, text=" 📂 رفع ملف النتائج (PDF) ", padding=12)
        upload_lf.pack(fill="x", pady=(0,12))

        r1 = ttk.Frame(upload_lf); r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="ملف PDF:", width=12, anchor="e").pack(side="right")
        self.results_path_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.results_path_var,
                  state="readonly", width=40).pack(side="right", padx=4, fill="x", expand=True)
        ttk.Button(r1, text="📁 اختر الملف",
                   command=self._results_browse).pack(side="right", padx=4)

        r2 = ttk.Frame(upload_lf); r2.pack(fill="x", pady=4)
        ttk.Label(r2, text="العام الدراسي:", width=12, anchor="e").pack(side="right")
        self.results_year_var = tk.StringVar(
            value=str(datetime.date.today().year))
        ttk.Entry(r2, textvariable=self.results_year_var, width=10).pack(side="right", padx=4)

        br = ttk.Frame(upload_lf); br.pack(fill="x", pady=(8,0))
        ttk.Button(br, text="⬆️ استيراد النتائج",
                   command=self._results_import).pack(side="right", padx=4)

        self.results_status = ttk.Label(upload_lf, text="",
                                         font=("Tahoma",9))
        self.results_status.pack(anchor="e", pady=(6,0))

        # ─ قسم الرابط
        link_lf = ttk.LabelFrame(body, text=" 🔗 رابط بوابة النتائج ", padding=12)
        link_lf.pack(fill="x", pady=(0,12))

        base = (STATIC_DOMAIN if STATIC_DOMAIN
                else "http://{}:{}".format(local_ip(), PORT))
        portal_url = "{}/results".format(base)

        ttk.Label(link_lf,
            text=portal_url,
            font=("Tahoma",11,"bold"),
            foreground="#1565C0").pack(anchor="e", pady=(0,8))

        btn_row = ttk.Frame(link_lf); btn_row.pack(fill="x")
        ttk.Button(btn_row, text="📋 نسخ الرابط",
                   command=lambda u=portal_url: (
                       self.root.clipboard_clear(),
                       self.root.clipboard_append(u),
                       messagebox.showinfo("تم","✅ تم نسخ رابط البوابة")
                   )).pack(side="right", padx=4)
        ttk.Button(btn_row, text="🌐 فتح البوابة",
                   command=lambda u=portal_url: webbrowser.open(u)
                   ).pack(side="right", padx=4)

        ttk.Label(link_lf,
            text="شارك هذا الرابط مع الطلاب — كل طالب يدخل رقم هويته ويرى نتيجته فقط",
            foreground="#5A6A7E", font=("Tahoma",8)).pack(anchor="e", pady=(6,0))

        # ─ إحصائيات
        stats_lf = ttk.LabelFrame(body, text=" 📊 إحصائيات النتائج المنشورة ", padding=8)
        stats_lf.pack(fill="x")

        self.results_stats_lbl = ttk.Label(stats_lf, text="",
                                            font=("Tahoma",10))
        self.results_stats_lbl.pack(anchor="e")
        ttk.Button(stats_lf, text="🔄 تحديث الإحصائيات",
                   command=self._results_refresh_stats).pack(side="left", pady=4)

        self._results_refresh_stats()

    def _results_browse(self):
        path = filedialog.askopenfilename(
            title="اختر ملف PDF للنتائج",
            filetypes=[("PDF files","*.pdf")])
        if path:
            self.results_path_var.set(path)

    def _results_import(self):
        path = self.results_path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("تنبيه","اختر ملف PDF أولاً"); return

        self.results_status.config(
            text="⏳ جارٍ فهرسة الشهادات... قد يستغرق دقيقة",
            foreground="#1565C0")
        self.root.update_idletasks()

        import threading as _th
        year = self.results_year_var.get().strip()

        def _run():
            try:
                # نسخ الـ PDF إلى الموقع المشترك مع واجهة الويب
                # حتى يتمكن الطلاب من عرض شهاداتهم عبر الويب أيضاً
                results_dir = os.path.join(DATA_DIR, "results")
                os.makedirs(results_dir, exist_ok=True)
                shared_pdf = os.path.join(results_dir, f"results_{year or 'current'}.pdf")
                try:
                    import shutil as _sh
                    if os.path.abspath(path) != os.path.abspath(shared_pdf):
                        _sh.copy2(path, shared_pdf)
                    parse_path = shared_pdf
                except Exception as _ce:
                    print(f"[RESULTS] تعذّر نسخ PDF للمشاركة: {_ce}")
                    parse_path = path

                students = parse_results_pdf(parse_path)
                inserted, _ = save_results_to_db(students, year)
                def _done():
                    self.results_status.config(
                        text="✅ تم فهرسة {} شهادة — متاحة في التطبيق والويب".format(len(students)),
                        foreground="#2E7D32")
                    self._results_refresh_stats()
                self.root.after(0, _done)
            except Exception as e:
                import traceback
                full_err = traceback.format_exc()
                print("[RESULTS ERROR]", full_err)
                def _err(msg=str(e), tb=full_err):
                    self.results_status.config(
                        text="❌ خطأ: {}".format(msg),
                        foreground="#C62828")
                    # عرض الخطأ الكامل في نافذة منبثقة
                    messagebox.showerror("تفاصيل الخطأ", tb)
                self.root.after(0, _err)

        _th.Thread(target=_run, daemon=True).start()

    def _results_refresh_stats(self):
        if not hasattr(self,"results_stats_lbl"): return
        try:
            con = sqlite3.connect(DB_PATH); cur = con.cursor()
            cur.execute("SELECT COUNT(*) as c, MAX(uploaded_at) as last FROM student_results")
            row = cur.fetchone(); con.close()
            count = row[0] if row else 0
            last  = (row[1] or "")[:16].replace("T"," ") if row and row[1] else "—"
            self.results_stats_lbl.config(
                text="إجمالي الطلاب المنشورة نتائجهم: {}  |  آخر تحديث: {}".format(
                    count, last))
        except Exception as e:
            self.results_stats_lbl.config(text="خطأ: {}".format(e))


    def _build_license_tab(self):
        frame = self.license_frame

        hdr = tk.Frame(frame, bg="#1565C0", height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔐 معلومات الترخيص",
                 bg="#1565C0", fg="white",
                 font=("Tahoma",12,"bold")).pack(side="right", padx=14, pady=12)

        body = ttk.Frame(frame); body.pack(fill="both", expand=True, padx=20, pady=16)

        # ─ حالة الترخيص الحالية
        lf = ttk.LabelFrame(body, text=" حالة الترخيص ", padding=14)
        lf.pack(fill="x", pady=(0,14))

        self.lic_status_lbl = ttk.Label(lf, text="", font=("Tahoma",11,"bold"))
        self.lic_status_lbl.pack(anchor="e", pady=(0,6))
        self.lic_school_lbl = ttk.Label(lf, text="", foreground="#5A6A7E")
        self.lic_school_lbl.pack(anchor="e", pady=(0,4))
        self.lic_expiry_lbl = ttk.Label(lf, text="", foreground="#5A6A7E")
        self.lic_expiry_lbl.pack(anchor="e", pady=(0,4))
        self.lic_machine_lbl = ttk.Label(lf, text="", foreground="#9CA3AF",
                                          font=("Tahoma",8))
        self.lic_machine_lbl.pack(anchor="e")

        self._refresh_license_status()

        ttk.Button(lf, text="🔄 تحديث الحالة",
                   command=self._refresh_license_status).pack(side="left", pady=(8,0))

        # ─ إدخال مفتاح جديد
        renew_lf = ttk.LabelFrame(body, text=" تجديد / تفعيل مفتاح جديد ", padding=14)
        renew_lf.pack(fill="x")

        ttk.Label(renew_lf, text="مفتاح الترخيص:").pack(anchor="e", pady=(0,4))
        self.lic_key_var = tk.StringVar()
        key_entry = ttk.Entry(renew_lf, textvariable=self.lic_key_var,
                               width=36, justify="center",
                               font=("Tahoma",10))
        key_entry.pack(pady=4, ipady=4)

        self.lic_act_status = ttk.Label(renew_lf, text="")
        self.lic_act_status.pack(pady=(4,8))

        def do_activate():
            key = self.lic_key_var.get().strip()
            if not key:
                self.lic_act_status.config(text="أدخل المفتاح أولاً", foreground="#C62828")
                return
            self.lic_act_status.config(text="⏳ جارٍ التفعيل...", foreground="#1565C0")
            frame.update_idletasks()
            import threading as _th
            def _run():
                ok, msg = activate_license(key)
                def _done():
                    if ok:
                        self.lic_act_status.config(text="✅ " + msg, foreground="#2E7D32")
                        self._refresh_license_status()
                    else:
                        self.lic_act_status.config(text="❌ " + msg, foreground="#C62828")
                self.root.after(0, _done)
            _th.Thread(target=_run, daemon=True).start()

        ttk.Button(renew_lf, text="✅ تفعيل / تجديد",
                   command=do_activate).pack()

    def _refresh_license_status(self):
        if not hasattr(self,"lic_status_lbl"): return
        status = check_license()
        if status["valid"]:
            days = status["days_left"]
            color = "#C62828" if days <= 7 else "#2E7D32"
            self.lic_status_lbl.config(
                text="✅ مفعّل — متبقي {} يوم".format(days), foreground=color)
            self.lic_expiry_lbl.config(
                text="تاريخ الانتهاء: {}".format(status.get("expiry","")))
        else:
            self.lic_status_lbl.config(
                text="⛔ " + status["msg"], foreground="#C62828")
            self.lic_expiry_lbl.config(text="")
        self.lic_school_lbl.config(
            text="المدرسة: {}".format(status.get("school","")))
        self.lic_machine_lbl.config(
            text="معرف الجهاز: {}".format(_get_machine_id()[:16]+"..."))


    def _wa_servers_load(self):
        if not hasattr(self, "_tree_wa_servers"): return
        for i in self._tree_wa_servers.get_children():
            self._tree_wa_servers.delete(i)
        cfg     = load_config()
        servers = cfg.get("wa_servers", [])
        # أضف الخادم الافتراضي دائماً
        self._tree_wa_servers.insert("","end", iid="default",
            values=(3000, "الخادم الافتراضي (الرئيسي)"))
        for s in servers:
            if s.get("port", 3000) != 3000:
                self._tree_wa_servers.insert("","end",
                    values=(s["port"], s.get("note","")))

    def _wa_server_add(self, port: int, note: str):
        if port == 3000:
            messagebox.showwarning("تنبيه",
                "المنفذ 3000 هو الافتراضي — أضف منافذ إضافية فقط"); return
        cfg     = load_config()
        servers = cfg.get("wa_servers", [])
        if any(s["port"] == port for s in servers):
            messagebox.showwarning("تنبيه", "هذا المنفذ موجود مسبقاً"); return
        servers.append({"port": port, "note": note})
        cfg["wa_servers"] = servers
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        invalidate_config_cache()
        self._wa_servers_load()
        messagebox.showinfo("تم",
            "✅ تم إضافة المنفذ {}\n"
            "الرسائل ستُوزَّع الآن على {} خوادم".format(
                port, len(servers)+1))

    def _wa_server_del(self):
        if not hasattr(self, "_tree_wa_servers"): return
        sel = self._tree_wa_servers.selection()
        if not sel: return
        iid = sel[0]
        if iid == "default":
            messagebox.showwarning("تنبيه","لا يمكن حذف الخادم الافتراضي"); return
        vals = self._tree_wa_servers.item(iid, "values")
        port = int(vals[0])
        cfg     = load_config()
        servers = [s for s in cfg.get("wa_servers",[]) if s["port"] != port]
        cfg["wa_servers"] = servers
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        invalidate_config_cache()
        self._wa_servers_load()

    def update_all_tabs_after_data_change(self):
        """
        A central function to refresh all relevant UI components after underlying data (students.json) has changed.
        """
        self.store = load_students(force_reload=True)

        # حدّث فقط التبويبات المبنية فعلاً (Lazy Loading)
        if hasattr(self, "tree_dash"):         self.update_dashboard_metrics()
        if hasattr(self, "tree_links"):        self._refresh_links_and_teachers()
        if hasattr(self, "tree_logs"):         self.refresh_logs()
        if hasattr(self, "report_class_combo"):self._refresh_report_options()
        if hasattr(self, "tree_phones"):       self.load_students_to_treeview()
        if hasattr(self, "tree_student_management"): self.load_students_to_management_treeview()
        if hasattr(self, "tree_class_naming"): self.load_class_names_to_treeview()
        if hasattr(self, "msg_canvas"):        self._msg_load_groups()
        if hasattr(self, "schedule_widgets"):
            self._schedule_built_day = None   # إجبار إعادة بناء الجدول بعد تغيير البيانات
            self.populate_schedule_table()
        if hasattr(self, "tree_tard"):         self._tard_load()
        if hasattr(self, "tree_excuses"):      self._exc_load()
        if hasattr(self, "tree_users"):        self._users_load()
        if hasattr(self, "tree_backup"):       self.root.after(100, self._backup_load)
        if hasattr(self, "_term_backup_list"): self._load_term_backups()
        
    def _refresh_report_options(self):
        class_ids = ["(كل الفصول)"] + [c["id"] for c in self.store["list"]]
        self.report_class_combo['values'] = class_ids
        self.report_class_combo.current(0)

    def _build_live_monitor_tab(self):
        frame = self.live_monitor_frame
        links_frame = ttk.LabelFrame(frame, text=" روابط الوصول الخارجي (للمتصفحات الأخرى) ", padding=10)
        links_frame.pack(fill="x", pady=5, padx=5)
        def copy_to_clipboard(text_to_copy):
            self.root.clipboard_clear(); self.root.clipboard_append(text_to_copy); messagebox.showinfo("تم النسخ", "تم نسخ الرابط إلى الحافظة بنجاح!")
        local_frame = ttk.Frame(links_frame); local_frame.pack(fill="x", pady=2)
        monitor_url_local = f"http://{self.ip}:{PORT}/monitor"
        ttk.Label(local_frame, text="الرابط المحلي:", width=12 ).pack(side="right", padx=5)
        local_link_entry = ttk.Entry(local_frame, font=("Segoe UI", 9)); local_link_entry.insert(0, monitor_url_local)
        local_link_entry.config(state="readonly"); local_link_entry.pack(side="right", fill="x", expand=True)
        ttk.Button(local_frame, text="📋 نسخ", width=8, command=lambda: copy_to_clipboard(monitor_url_local)).pack(side="left", padx=5)
        if self.public_url:
            public_frame = ttk.Frame(links_frame); public_frame.pack(fill="x", pady=2)
            monitor_url_public = self.public_url + "/monitor"
            ttk.Label(public_frame, text="الرابط العام:", width=12).pack(side="right", padx=5)
            public_link_entry = ttk.Entry(public_frame, font=("Segoe UI", 9)); public_link_entry.insert(0, monitor_url_public)
            public_link_entry.config(state="readonly"); public_link_entry.pack(side="right", fill="x", expand=True)
            ttk.Button(public_frame, text="📋 نسخ", width=8, command=lambda: copy_to_clipboard(monitor_url_public)).pack(side="left", padx=5)
        browser_frame = ttk.Frame(frame, padding=(0, 10, 0, 0)); browser_frame.pack(fill="both", expand=True)
        live_monitor_browser = HtmlFrame(browser_frame, horizontal_scrollbar="auto", messages_enabled=False); live_monitor_browser.pack(fill="both", expand=True)
        self._live_monitor_active = False  # علم التحكم في حلقة التحديث

        def update_browser_content():
            # ── توقف إذا لم يكن تبويب المراقبة الحية نشطاً ──
            if not self._live_monitor_active:
                return
            if hasattr(self, "_current_tab") and self._current_tab.get() != "المراقبة الحية":
                self.root.after(10_000, update_browser_content)
                return
            # جلب البيانات في خيط خلفي — تحديث الواجهة عبر root.after
            def do_fetch():
                try:
                    today = now_riyadh_date()
                    status_data = get_live_monitor_status(today)
                    html_content = generate_monitor_table_html(status_data)
                    now_str = datetime.datetime.now().strftime('%H:%M:%S')
                    final_html = html_content.replace(
                        '<p id="last-update"></p>',
                        f'<p id="last-update">\u0622\u062e\u0631 \u062a\u062d\u062f\u064a\u062b: {now_str}</p>')
                    self.root.after(0, lambda: live_monitor_browser.load_html(final_html))
                except Exception as e:
                    print(f"Error updating live monitor: {e}")
                self.root.after(0, lambda: self.root.after(60_000, update_browser_content))
            threading.Thread(target=do_fetch, daemon=True).start()

        self._live_monitor_active = True
        self.root.after(500, update_browser_content)

    def reimport_students(self):
        path = filedialog.askopenfilename(
            title="اختر ملف Excel (طلاب)",
            filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: return
        self._preview_import(path)

    def _preview_import(self, xlsx_path: str):
        """معاينة بيانات الاستيراد قبل التطبيق الفعلي."""
        import threading as _th

        win = tk.Toplevel(self.root)
        win.title("معاينة الاستيراد")
        win.geometry("860x560")
        win.transient(self.root)

        loading = ttk.Label(win, text="⏳ جارٍ قراءة الملف...",
                             font=("Tahoma",12))
        loading.pack(expand=True)

        def _load():
            try:
                import pandas as pd
                xls = pd.ExcelFile(xlsx_path)
                REQUIRED = {"رقم الطالب","اسم الطالب","رقم الصف"}
                df = None
                for sname in xls.sheet_names:
                    df_try = pd.read_excel(xlsx_path, sheet_name=sname, dtype=str)
                    if REQUIRED <= set(str(c).strip() for c in df_try.columns):
                        df = df_try; break
                    df0 = pd.read_excel(xlsx_path, sheet_name=sname,
                                        header=None, dtype=str, nrows=30)
                    for i, row in df0.iterrows():
                        if REQUIRED <= set(str(x).strip() for x in row if pd.notna(x)):
                            df = pd.read_excel(xlsx_path, sheet_name=sname,
                                               header=i, dtype=str)
                            break
                    if df is not None: break

                if df is None:
                    win.after(0, lambda: messagebox.showerror(
                        "خطأ","لم أجد أعمدة الطلاب في الملف", parent=win))
                    win.after(0, win.destroy); return

                df.columns = [str(c).strip() for c in df.columns]
                df = df.dropna(subset=["رقم الطالب","اسم الطالب"])
                df = df[df["رقم الطالب"].astype(str).str.lower() != "nan"]

                store       = load_students()
                current_ids = set(s["id"] for cls in store["list"]
                                  for s in cls["students"])
                new_ids     = set(str(r["رقم الطالب"]).strip()
                                  for _,r in df.iterrows())
                added   = new_ids - current_ids
                removed = current_ids - new_ids
                same    = new_ids & current_ids

                win.after(0, lambda: _show(df, added, removed, same, store))
            except Exception as e:
                win.after(0, lambda: messagebox.showerror("خطأ", str(e), parent=win))
                win.after(0, win.destroy)

        def _show(df, added, removed, same, store):
            loading.destroy()

            # رأس
            hdr = tk.Frame(win, bg="#1565C0", height=46)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            tk.Label(hdr,
                text="معاينة الاستيراد — {}".format(
                    os.path.basename(xlsx_path)),
                bg="#1565C0", fg="white",
                font=("Tahoma",11,"bold")).pack(side="right", padx=12, pady=12)

            # بطاقات
            stats = tk.Frame(win, bg="#F5F7FA")
            stats.pack(fill="x", padx=10, pady=6)
            for title, val, color in [
                ("إجمالي في الملف", len(df),      "#1565C0"),
                ("طلاب جدد",        len(added),   "#2E7D32"),
                ("محذوفون",         len(removed), "#C62828"),
                ("موجودون",         len(same),    "#5A6A7E"),
            ]:
                fr = tk.Frame(stats, bg="white", relief="groove", bd=1)
                fr.pack(side="right", padx=5, ipadx=10, ipady=6)
                tk.Label(fr, text=title, bg="white", fg="#5A6A7E",
                         font=("Tahoma",8,"bold")).pack()
                tk.Label(fr, text=str(val), bg="white", fg=color,
                         font=("Tahoma",20,"bold")).pack()

            # أزرار أسفل النافذة أولاً (لضمان ظهورها)
            btns = tk.Frame(win, bg="white"); btns.pack(side="bottom", fill="x", padx=10, pady=8)

            def do_import():
                win.destroy()
                self._do_reimport_students(xlsx_path)

            ttk.Button(btns, text="✅ تأكيد الاستيراد",
                       command=do_import).pack(side="right", padx=4, ipadx=8, ipady=3)
            ttk.Button(btns, text="❌ إلغاء",
                       command=win.destroy).pack(side="right", padx=4, ipadx=8, ipady=3)
            if removed:
                ttk.Label(btns,
                    text="⚠️ {} طالب سيُحذف".format(len(removed)),
                    foreground="#C62828",
                    font=("Tahoma",10,"bold")).pack(side="left", padx=8)

            ttk.Separator(win, orient="horizontal").pack(side="bottom", fill="x")

            # جداول المعاينة
            nb = ttk.Notebook(win)
            nb.pack(fill="both", expand=True, padx=8, pady=4)

            # جدول الجدد
            tab_new = ttk.Frame(nb)
            nb.add(tab_new, text="✅ جدد ({})".format(len(added)))
            tr1 = ttk.Treeview(tab_new,
                columns=("id","name","class"), show="headings", height=12)
            for c,h,w in zip(("id","name","class"),
                             ["رقم الطالب","اسم الطالب","الفصل"],
                             [120,250,150]):
                tr1.heading(c,text=h); tr1.column(c,width=w,anchor="center")
            tr1.tag_configure("new", background="#E8F5E9")
            sb1 = ttk.Scrollbar(tab_new, orient="vertical", command=tr1.yview)
            tr1.configure(yscrollcommand=sb1.set)
            for _,row in df.iterrows():
                sid = str(row.get("رقم الطالب","")).strip()
                if sid in added:
                    tr1.insert("","end", tags=("new",),
                        values=(sid, row.get("اسم الطالب",""),
                                str(row.get("رقم الصف",""))+"_"+str(row.get("الفصل",""))))
            tr1.pack(side="left", fill="both", expand=True)
            sb1.pack(side="right", fill="y")

            # جدول المحذوفين
            tab_del = ttk.Frame(nb)
            nb.add(tab_del, text="🔴 محذوفون ({})".format(len(removed)))
            tr2 = ttk.Treeview(tab_del,
                columns=("id","name","class"), show="headings", height=12)
            for c,h,w in zip(("id","name","class"),
                             ["رقم الطالب","اسم الطالب","الفصل"],
                             [120,250,150]):
                tr2.heading(c,text=h); tr2.column(c,width=w,anchor="center")
            tr2.tag_configure("del", background="#FFEBEE")
            sb2 = ttk.Scrollbar(tab_del, orient="vertical", command=tr2.yview)
            tr2.configure(yscrollcommand=sb2.set)
            for cls in store["list"]:
                for s in cls["students"]:
                    if s["id"] in removed:
                        tr2.insert("","end", tags=("del",),
                            values=(s["id"], s["name"], cls["name"]))
            tr2.pack(side="left", fill="both", expand=True)
            sb2.pack(side="right", fill="y")

        _th.Thread(target=_load, daemon=True).start()

    def _do_reimport_students(self, path: str):
        """ينفّذ الاستيراد الفعلي بعد تأكيد المعاينة."""
        try:
            with open(STUDENTS_JSON, "r", encoding="utf-8") as f:
                current_data = json.load(f)
            custom_names_map = {c['id']: c['name']
                                for c in current_data.get('classes', [])}
        except (FileNotFoundError, json.JSONDecodeError):
            custom_names_map = {}
        try:
            import_students_from_excel_sheet2_format(path)
            if custom_names_map:
                with open(STUDENTS_JSON, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                for c in new_data.get('classes', []):
                    if c['id'] in custom_names_map:
                        c['name'] = custom_names_map[c['id']]
                with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم","تم تحديث الطلاب بنجاح.")
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ في استيراد الطلاب", str(e))


    def reimport_teachers(self):
        path = filedialog.askopenfilename(title="اختر ملف Excel (معلمون)", filetypes=[("Excel files","*.xlsx *.xls")])
        if not path: return
        try:
            import_teachers_from_excel(path)
            self.teachers_data = load_teachers()
            messagebox.showinfo("تم", "تم تحديث المعلمين بنجاح.")
            self._refresh_links_and_teachers()
        except Exception as e:
            messagebox.showerror("خطأ في استيراد المعلمين", str(e))

    def _open_school_settings_tab(self):
        """ينتقل مباشرة إلى تبويب إعدادات المدرسة."""
        if hasattr(self, "_switch_tab") and "إعدادات المدرسة" in self._tab_frames:
            self._switch_tab("إعدادات المدرسة")
        else:
            messagebox.showinfo("تنبيه", "التبويب غير متاح لهذا المستخدم.")

    def open_config_json(self):
        """يفتح نافذة تعديل config.json داخل البرنامج."""
        ensure_dirs()
        if not os.path.exists(CONFIG_JSON):
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)

        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                content_str = f.read()
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر قراءة الملف:\n{e}")
            return

        win = tk.Toplevel(self.root)
        win.title("تعديل ملف الإعدادات — config.json")
        win.geometry("800x600")
        win.transient(self.root)

        # شريط العنوان
        hdr = tk.Frame(win, bg="#1565C0", height=40)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙ تعديل config.json",
                 bg="#1565C0", fg="white",
                 font=("Tahoma", 11, "bold")).pack(side="right", padx=12, pady=8)
        tk.Label(hdr, text=os.path.abspath(CONFIG_JSON),
                 bg="#1565C0", fg="#90CAF9",
                 font=("Courier", 8)).pack(side="left", padx=12, pady=8)

        # منطقة النص
        txt_frame = ttk.Frame(win); txt_frame.pack(fill="both", expand=True, padx=8, pady=6)
        txt = tk.Text(txt_frame, font=("Courier New", 10), wrap="none",
                      undo=True, relief="solid", bd=1)
        vsb = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(txt_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", content_str)

        # أزرار
        btn_frame = ttk.Frame(win); btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        status_lbl = ttk.Label(btn_frame, text="", foreground="green", font=("Tahoma", 9))
        status_lbl.pack(side="right", padx=8)

        def _save():
            raw = txt.get("1.0", "end").strip()
            try:
                parsed = json.loads(raw)  # تحقق من صحة JSON
                with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, ensure_ascii=False, indent=2)
                status_lbl.config(text="✅ تم الحفظ بنجاح", foreground="green")
                win.after(3000, lambda: status_lbl.config(text=""))
            except json.JSONDecodeError as e:
                messagebox.showerror("خطأ JSON", f"الملف يحتوي على خطأ:\n{e}", parent=win)

        def _open_external():
            try:
                os.startfile(os.path.abspath(CONFIG_JSON))
            except Exception:
                webbrowser.open(f"file://{os.path.abspath(CONFIG_JSON)}")

        def _format():
            raw = txt.get("1.0", "end").strip()
            try:
                parsed = json.loads(raw)
                formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
                txt.delete("1.0", "end")
                txt.insert("1.0", formatted)
                status_lbl.config(text="✅ تم التنسيق", foreground="green")
            except json.JSONDecodeError as e:
                messagebox.showerror("خطأ", f"لا يمكن التنسيق:\n{e}", parent=win)

        ttk.Button(btn_frame, text="💾 حفظ", command=_save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="✨ تنسيق JSON", command=_format).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="📂 فتح بالمفكرة", command=_open_external).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="✖ إغلاق", command=win.destroy).pack(side="left", padx=4)

    def _build_schedule_tab(self):
        self.cfg = load_config()
        frame = self.schedule_frame
        self.schedule_widgets = {}
        self.schedule_time_vars = {}

        today_weekday = (datetime.datetime.now().weekday() + 1) % 7
        default_day = today_weekday if today_weekday <= 4 else 0
        self.selected_day_var = tk.IntVar(value=default_day)

        days_frame = ttk.Frame(frame, padding=(10, 5))
        days_frame.pack(fill="x", side="top")
        ttk.Label(days_frame, text="اختر اليوم لعرض/تعديل جدوله:", font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 10))
        
        days_map = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}
        for day_index, day_name in days_map.items():
            rb = ttk.Radiobutton(days_frame, text=day_name, variable=self.selected_day_var, value=day_index, command=self.populate_schedule_table)
            rb.pack(side="right", padx=5)

        main_controls_frame = ttk.Frame(frame, padding=10)
        main_controls_frame.pack(fill="x", side="top")

        buttons_frame = ttk.Frame(main_controls_frame)
        buttons_frame.pack(side="right", fill="y", padx=(10, 0))
        self.start_scheduler_button = ttk.Button(buttons_frame, text="🚀 بدء الإرسال الآلي (لليوم)", command=self.start_scheduler)
        self.start_scheduler_button.pack(fill="x", pady=2)
        self.stop_scheduler_button = ttk.Button(buttons_frame, text="🛑 إيقاف الإرسال", command=self.stop_scheduler, state="disabled")
        self.stop_scheduler_button.pack(fill="x", pady=2)
        ttk.Button(buttons_frame, text="💾 حفظ الجدول والتواقيت", command=self.on_save_schedule_and_times).pack(fill="x", pady=(10, 2))
        ttk.Button(buttons_frame, text="🔄 تحديث الجدول", command=self.populate_schedule_table).pack(fill="x", pady=2)
        self._schedule_last_sync = ttk.Label(buttons_frame, text="", foreground="#888", font=("Tahoma", 8))
        self._schedule_last_sync.pack(fill="x", pady=(0,2))
        
        # --- NEW: Web Editor and Clear Buttons ---
        web_buttons_frame = ttk.Frame(buttons_frame)
        web_buttons_frame.pack(fill="x", pady=(10, 0))
        
        web_menu = tk.Menu(web_buttons_frame, tearoff=0)
        web_menu.add_command(label="فتح الرابط المحلي", command=lambda: self.open_schedule_editor('local'))
        if self.public_url:
            web_menu.add_command(label="فتح الرابط العالمي", command=lambda: self.open_schedule_editor('public'))
        else:
            web_menu.add_command(label="فتح الرابط العالمي (معطل)", state="disabled")

        menubutton = ttk.Menubutton(web_buttons_frame, text="✏️ تعديل الجدول من الويب", menu=web_menu, direction="below")
        menubutton.pack(fill="x", pady=2)

        ttk.Button(web_buttons_frame, text="🗑️ مسح الجدول الحالي", command=self.clear_current_schedule).pack(fill="x", pady=2)
        # --- END NEW ---

        # ─── وقت بداية الدوام (لحساب التأخر) ──────────────────
        start_frame = ttk.LabelFrame(main_controls_frame, text=" 🏫 بداية الدوام ")
        start_frame.pack(side="right", fill="y", padx=(0,6))
        ttk.Label(start_frame, text="وقت بداية الدوام:", font=("Tahoma",10)).pack(pady=(8,2))
        self.school_start_var = tk.StringVar(
            value=self.cfg.get("school_start_time","07:00"))
        start_entry = ttk.Entry(start_frame, textvariable=self.school_start_var,
                                 width=8, justify="center", font=("Courier",12,"bold"))
        start_entry.pack(padx=10, pady=4)
        ttk.Label(start_frame, text="(HH:MM)", foreground="#5A6A7E",
                  font=("Tahoma",8)).pack()
        ttk.Label(start_frame,
                  text="يُستخدم لحساب\ndقائق التأخر",
                  foreground="#5A6A7E", font=("Tahoma",8),
                  justify="center").pack(pady=(4,8))
        # ──────────────────────────────────────────────────────

        times_frame = ttk.LabelFrame(main_controls_frame, text="⏰ توقيت الحصص (HH:MM)")
        times_frame.pack(side="right", fill="y", padx=10)
        
        default_times = self.cfg.get("period_times", ["07:00", "07:50", "08:40", "09:50", "10:40", "11:30", "12:20"])
        for i in range(7):
            period = i + 1
            row = ttk.Frame(times_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"الحصة {period}:").pack(side="right")
            
            time_var = tk.StringVar(value=default_times[i] if i < len(default_times) else "")
            time_entry = ttk.Entry(row, textvariable=time_var, width=7, justify='center')
            time_entry.pack(side="left", padx=5)
            self.schedule_time_vars[period] = time_var

        status_frame = ttk.LabelFrame(main_controls_frame, text="📝 سجل الحالة")
        status_frame.pack(side="left", fill="both", expand=True)
        self.scheduler_log = tk.Text(status_frame, height=8, width=50, state="disabled", wrap="word", font=("Segoe UI", 9))
        log_scroll = ttk.Scrollbar(status_frame, orient="vertical", command=self.scheduler_log.yview)
        self.scheduler_log.config(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.scheduler_log.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        table_container = ttk.Frame(frame)
        table_container.pack(fill="both", expand=True, padx=5, pady=5)

        canvas = tk.Canvas(table_container)
        scrollbar_y = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x = ttk.Scrollbar(table_container, orient="horizontal", command=canvas.xview)
        scrollbar_x.pack(side="bottom", fill="x")
        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        canvas.pack(side="left", fill="both", expand=True)
        self.schedule_table_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=self.schedule_table_frame, anchor="nw")
        def _on_sched_conf(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        self.schedule_table_frame.bind("<Configure>", _on_sched_conf)
        
        self.populate_schedule_table()

        # ── تحديث تلقائي كل 30 ثانية لمزامنة التغييرات من الويب ──
        self._schedule_auto_refresh_active = True
        def _auto_refresh_schedule():
            if not self._schedule_auto_refresh_active:
                return
            if self._current_tab.get() == "جدولة الروابط":
                self.populate_schedule_table()
                if hasattr(self, "_schedule_last_sync"):
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    self._schedule_last_sync.config(text=f"آخر تحديث: {now}")
            frame.after(120_000, _auto_refresh_schedule)
        frame.after(120_000, _auto_refresh_schedule)

    def open_schedule_editor(self, link_type: str):
        if link_type == 'local':
            url = f"http://{self.ip}:{PORT}/schedule/edit"
        elif link_type == 'public':
            if not self.public_url:
                messagebox.showerror("خطأ", "الرابط العالمي غير متاح حاليًا." )
                return
            url = f"{self.public_url}/schedule/edit"
        else:
            return
        webbrowser.open(url)

    def clear_current_schedule(self):
        password = simpledialog.askstring("تأكيد", "للمتابعة، الرجاء إدخال كلمة المرور:", show='*')
        if password != "123":
            messagebox.showerror("خطأ", "كلمة المرور غير صحيحة.")
            return
        
        selected_day = self.selected_day_var.get()
        day_name = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}.get(selected_day, "المحدد")
        
        if not messagebox.askyesno("تأكيد المسح", f"هل أنت متأكد من أنك تريد مسح جميع مدخلات جدول يوم {day_name}؟\nلا يمكن التراجع عن هذا الإجراء."):
            return
            
        try:
            save_schedule(selected_day, []) # Save an empty schedule
            self.populate_schedule_table() # Refresh the UI
            messagebox.showinfo("تم المسح", f"تم مسح جدول يوم {day_name} بنجاح.")
        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ أثناء مسح الجدول: {e}")

    # ══════════════════════════════════════════════════════════
    # إعداد مستلمي رابط التأخر (داخل تبويب جدولة الروابط)
    # ══════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════
    # تبويب مستقل: مستلمو رابط التأخر
    # ══════════════════════════════════════════════════════════
    def _build_tardiness_recipients_tab(self):
        """يبني تبويب إدارة مستلمي رابط التأخر."""
        frame = self.tardiness_recipients_frame

        # عنوان التبويب
        hdr = tk.Frame(frame, bg="#E65100", height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⏱ إعداد إرسال رابط التأخر التلقائي",
                 bg="#E65100", fg="white",
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=16, pady=12)

        tk.Label(frame,
            text="يُرسَل رابط تسجيل التأخر (كل طلاب المدرسة) لجميع المستلمين "
                 "تلقائياً في وقت بداية الدوام يومياً — أو يدوياً بضغطة زر.",
            font=("Tahoma", 10), fg="#444", justify="right",
            wraplength=900
        ).pack(anchor="e", padx=16, pady=(10, 0))

        # ─── مؤشر خادم الواتساب المختصر ─────────────────────────
        wa_mini = ttk.LabelFrame(frame, text=" 🟢 خادم واتساب ", padding=6)
        wa_mini.pack(fill="x", padx=10, pady=(6, 0))
        wa_mini_row = ttk.Frame(wa_mini); wa_mini_row.pack(fill="x")

        self._wa_mini_dot = tk.Label(wa_mini_row, text="⬤", font=("Tahoma", 13), fg="#aaaaaa")
        self._wa_mini_dot.pack(side="right", padx=(0, 4))
        self._wa_mini_text = ttk.Label(wa_mini_row, text="جارٍ التحقق...", font=("Tahoma", 9))
        self._wa_mini_text.pack(side="right", padx=(0, 6))

        def _mini_start_wa():
            if not os.path.isdir(WHATS_PATH):
                messagebox.showerror("خطأ", "مجلد الواتساب غير موجود:\n" + WHATS_PATH)
                return
            try:
                cmd = rf'cmd.exe /k "cd /d {WHATS_PATH} && node server.js"'
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self._wa_mini_text.config(text="جارٍ التشغيل... انتظر 10 ثوانٍ")
                # بعد 11 ث أوقف البوت في خيط خلفي لتجنب تجميد الواجهة
                def _disable_bot_bg():
                    try:
                        import urllib.request as _ur
                        data = json.dumps({"enabled": False}).encode()
                        req = _ur.Request("http://localhost:3000/bot-toggle",
                                          data=data,
                                          headers={"Content-Type": "application/json"},
                                          method="POST")
                        _ur.urlopen(req, timeout=3)
                        print("[WA] البوت مُوقَف تلقائياً عند التشغيل من تبويب التأخر")
                    except Exception:
                        pass
                def _start_disable_thread():
                    threading.Thread(target=_disable_bot_bg, daemon=True).start()
                frame.after(11000, _start_disable_thread)
            except Exception as e:
                messagebox.showerror("خطأ", "تعذّر التشغيل:\n" + str(e))

        def _mini_check():
            self._wa_mini_dot.config(fg="#aaaaaa")
            self._wa_mini_text.config(text="⏳ جارٍ الفحص...", foreground="#555555")
            def _do_check():
                try:
                    import urllib.request, json as _j
                    r = urllib.request.urlopen("http://localhost:3000/status", timeout=2)
                    data = _j.loads(r.read())
                    if data.get("ready"):
                        self.root.after(0, lambda: (
                            self._wa_mini_dot.config(fg="#22c55e"),
                            self._wa_mini_text.config(text="✅ متصل ويعمل", foreground="#166534")))
                    else:
                        self.root.after(0, lambda: (
                            self._wa_mini_dot.config(fg="#f59e0b"),
                            self._wa_mini_text.config(text="⏳ يعمل — امسح QR", foreground="#92400e")))
                except Exception:
                    self.root.after(0, lambda: (
                        self._wa_mini_dot.config(fg="#ef4444"),
                        self._wa_mini_text.config(text="🔴 غير متصل", foreground="#991b1b")))
            threading.Thread(target=_do_check, daemon=True).start()

        ttk.Button(wa_mini_row, text="▶ تشغيل",
                   command=_mini_start_wa).pack(side="left", padx=4)
        ttk.Button(wa_mini_row, text="🔄",
                   command=_mini_check).pack(side="left", padx=2)

        # فحص عند الضغط فقط — لا جدولة تلقائية

        # بناء الواجهة الرئيسية
        self._build_tardiness_recipients_ui(frame)

    def _build_tardiness_recipients_ui(self, parent_frame):
        """يبني واجهة إدارة مستلمي رابط التأخر."""

        lf = ttk.LabelFrame(
            parent_frame,
            text=" 📤 مستلمو رابط التأخر التلقائي ",
            padding=10
        )
        lf.pack(fill="both", expand=True, padx=10, pady=(8,4))

        # رابط التأخر للنسخ — يُحسب دائماً من local_ip الحي
        def get_tard_url():
            base = (STATIC_DOMAIN if STATIC_DOMAIN and not debug_on()
                    else "http://{}:{}".format(local_ip(), PORT))
            return "{}/tardiness".format(base)

        url_row = ttk.Frame(lf); url_row.pack(fill="x", pady=(0,8))
        ttk.Label(url_row, text="رابط التأخر:", font=("Tahoma",9,"bold")).pack(side="right", padx=(0,6))
        self.tard_url_var = tk.StringVar(value=get_tard_url())
        url_entry = ttk.Entry(url_row, textvariable=self.tard_url_var,
                               state="readonly", font=("Courier",9))
        url_entry.pack(side="right", fill="x", expand=True)

        def copy_url():
            url = get_tard_url()
            self.tard_url_var.set(url)   # تحديث فوري
            self.root.clipboard_clear()
            self.root.clipboard_append(url)

        def refresh_url():
            self.tard_url_var.set(get_tard_url())

        btn_frame = ttk.Frame(url_row); btn_frame.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="نسخ",    width=5, command=copy_url).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="تحديث",  width=5, command=refresh_url).pack(side="right", padx=2)

        # تحديث الرابط تلقائياً بعد ثانية (بعد أن يكون الخادم جاهزاً)
        lf.after(1500, refresh_url)

        # أزرار الإرسال اليدوي
        send_row = ttk.Frame(lf); send_row.pack(fill="x", pady=(0,8))
        self.tard_send_btn = ttk.Button(
            send_row, text="📲 إرسال الرابط الآن للجميع",
            command=self._send_tardiness_now)
        self.tard_send_btn.pack(side="right", padx=4)
        self.tard_status_lbl = ttk.Label(
            send_row, text="", foreground="green", font=("Tahoma",9))
        self.tard_status_lbl.pack(side="right", padx=8)

        # ─── الإرسال التلقائي المجدوَل ───────────────────────────
        sched_lf = ttk.LabelFrame(lf, text=" ⏰ الإرسال التلقائي المجدوَل ", padding=8)
        sched_lf.pack(fill="x", pady=(0, 8))

        _cfg_now = load_config()
        self.tard_auto_var = tk.BooleanVar(
            value=_cfg_now.get("tardiness_auto_send_enabled", True))
        ttk.Checkbutton(
            sched_lf,
            text="تفعيل الإرسال التلقائي يومياً (الأحد—الخميس)",
            variable=self.tard_auto_var
        ).pack(anchor="e")

        time_row = ttk.Frame(sched_lf); time_row.pack(fill="x", pady=(6, 0))
        ttk.Label(time_row, text="وقت الإرسال:", font=("Tahoma",10,"bold")).pack(side="right", padx=(0,8))

        _saved_time = _cfg_now.get("tardiness_auto_send_time", "07:00")
        try:
            _sh, _sm = _saved_time.split(":")
        except Exception:
            _sh, _sm = "07", "00"

        self._tard_hour_var   = tk.StringVar(value=_sh)
        self._tard_minute_var = tk.StringVar(value=_sm)

        # إطار داخلي بترتيب يسار←يمين حتى تظهر الساعة قبل الدقيقة (HH:MM)
        _time_inner = ttk.Frame(time_row)
        _time_inner.pack(side="right")
        ttk.Spinbox(_time_inner, from_=0, to=23, width=4, justify="center",
                    textvariable=self._tard_hour_var,
                    format="%02.0f").pack(side="left")
        ttk.Label(_time_inner, text=":", font=("Tahoma",12,"bold")).pack(side="left", padx=2)
        ttk.Spinbox(_time_inner, from_=0, to=59, width=4, justify="center",
                    textvariable=self._tard_minute_var,
                    format="%02.0f").pack(side="left")
        ttk.Label(_time_inner, text=" (HH:MM)", foreground="#888",
                  font=("Tahoma",8)).pack(side="left", padx=(4,0))

        self._tard_sched_status = ttk.Label(sched_lf, text="", foreground="green",
                                             font=("Tahoma",9))
        self._tard_sched_status.pack(anchor="e", pady=(4,0))

        def _save_sched():
            try:
                h = int(self._tard_hour_var.get())
                m = int(self._tard_minute_var.get())
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
            except (ValueError, TypeError):
                self._tard_sched_status.config(
                    text="⚠️ وقت غير صحيح — أدخل ساعة (0-23) ودقيقة (0-59)",
                    foreground="#C62828")
                return
            from config_manager import save_config
            cfg = load_config()
            cfg["tardiness_auto_send_enabled"] = self.tard_auto_var.get()
            cfg["tardiness_auto_send_time"]    = f"{h:02d}:{m:02d}"
            save_config(cfg)
            status = "مفعّل ✅" if self.tard_auto_var.get() else "موقوف ⏸"
            self._tard_sched_status.config(
                text=f"✅ تم الحفظ — الإرسال {status} في {h:02d}:{m:02d}",
                foreground="#166534")

        ttk.Button(sched_lf, text="💾 حفظ الإعداد",
                   command=_save_sched).pack(anchor="w", pady=(6,0))

        ttk.Separator(lf, orient="horizontal").pack(fill="x", pady=6)

        # ─ إضافة مستلم
        add_row = ttk.Frame(lf); add_row.pack(fill="x", pady=(0,6))
        ttk.Label(add_row, text="اسم المستلم:", width=12, anchor="e").pack(side="right")
        self.tard_name_var  = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.tard_name_var,
                  width=20, justify="right").pack(side="right", padx=4)
        ttk.Label(add_row, text="الجوال:", width=7, anchor="e").pack(side="right", padx=(8,0))
        self.tard_phone_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.tard_phone_var,
                  width=14, justify="right").pack(side="right", padx=4)
        ttk.Button(add_row, text="➕ إضافة",
                   command=self._tard_recipient_add).pack(side="right", padx=4)

        # ─ جدول المستلمين
        cols = ("name","phone","role")
        tree_frame = ttk.Frame(lf)
        tree_frame.pack(fill="both", expand=True)
        self.tree_tard_recv = ttk.Treeview(
            tree_frame, columns=cols, show="headings", height=6)
        for col, hdr, w in zip(cols,
            ["الاسم", "رقم الجوال", "الدور/الوظيفة"],
            [200, 140, 160]):
            self.tree_tard_recv.heading(col, text=hdr)
            self.tree_tard_recv.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree_tard_recv.yview)
        self.tree_tard_recv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree_tard_recv.pack(side="left", fill="both", expand=True)

        del_row = ttk.Frame(lf); del_row.pack(fill="x", pady=(6,0))
        ttk.Button(del_row, text="🗑️ حذف المحدد",
                   command=self._tard_recipient_del).pack(side="right", padx=4)
        ttk.Button(del_row, text="👨‍🏫 استيراد من المعلمين",
                   command=self._tard_import_teachers).pack(side="right", padx=4)
        ttk.Button(del_row, text="👤 استيراد من المستخدمين المسجلين",
                   command=self._tard_import_users).pack(side="right", padx=4)

        self._tard_recipients_load()

    def _tard_recipients_load(self):
        if not hasattr(self, "tree_tard_recv"): return
        for i in self.tree_tard_recv.get_children():
            self.tree_tard_recv.delete(i)
        for r in get_tardiness_recipients():
            self.tree_tard_recv.insert("", "end",
                values=(r.get("name",""), r.get("phone",""), r.get("role","")))

    def _tard_recipient_add(self):
        name  = self.tard_name_var.get().strip() if hasattr(self,"tard_name_var") else ""
        phone = self.tard_phone_var.get().strip() if hasattr(self,"tard_phone_var") else ""
        if not name or not phone:
            messagebox.showwarning("تنبيه", "أدخل الاسم ورقم الجوال")
            return
        role = simpledialog.askstring(
            "الدور", "ما دور/وظيفة '"+name+"'؟ (اختياري)",
            parent=self.root) or ""
        recps = get_tardiness_recipients()
        # تجنب التكرار
        if any(r["phone"]==phone for r in recps):
            messagebox.showwarning("تنبيه","رقم الجوال موجود مسبقاً")
            return
        recps.append({"name":name,"phone":phone,"role":role})
        save_tardiness_recipients(recps)
        self.tard_name_var.set("")
        self.tard_phone_var.set("")
        self._tard_recipients_load()

    def _tard_recipient_del(self):
        if not hasattr(self,"tree_tard_recv"): return
        sel = self.tree_tard_recv.selection()
        if not sel:
            messagebox.showwarning("تنبيه","حدد مستلماً أولاً")
            return
        vals  = self.tree_tard_recv.item(sel[0])["values"]
        phone = vals[1]
        if not messagebox.askyesno("تأكيد",f"حذف '{vals[0]}'؟"): return
        recps = [r for r in get_tardiness_recipients() if r.get("phone")!=phone]
        save_tardiness_recipients(recps)
        self._tard_recipients_load()

    def _tard_import_teachers(self):
        """يستورد أرقام المعلمين من قائمة المعلمين الموجودة."""
        teachers_data = load_teachers()
        teachers      = teachers_data.get("teachers", [])
        recps         = get_tardiness_recipients()
        existing_phones = {r["phone"] for r in recps}
        added = 0
        for t in teachers:
            name  = t.get("اسم المعلم","")
            phone = t.get("رقم الجوال","")
            if phone and phone not in existing_phones:
                recps.append({"name":name,"phone":phone,"role":"معلم"})
                existing_phones.add(phone)
                added += 1
        save_tardiness_recipients(recps)
        self._tard_recipients_load()
        messagebox.showinfo("تم",f"تم استيراد {added} معلم من قائمة المعلمين.")

    def _tard_import_users(self):
        """
        يعرض نافذة لاستيراد أرقام المستخدمين المسجلين في البرنامج
        كمستلمين لرابط التأخر.
        """
        from database import get_all_users, save_user_phone
        users = get_all_users()
        if not users:
            messagebox.showinfo("تنبيه", "لا يوجد مستخدمون مسجلون."); return

        win = tk.Toplevel(self.root)
        win.title("استيراد المستخدمين كمستلمين")
        win.geometry("560x420")
        win.transient(self.root); win.grab_set()

        ttk.Label(win,
            text="أدخل رقم جوال لكل مستخدم ثم اختر من تريد استيراده:",
            font=("Tahoma",10)).pack(pady=(12,4), padx=12, anchor="e")

        # جدول
        cols = ("sel","name","username","role","phone")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=10)
        tree.heading("sel",      text="✔")
        tree.heading("name",     text="الاسم")
        tree.heading("username", text="المستخدم")
        tree.heading("role",     text="الدور")
        tree.heading("phone",    text="رقم الجوال")
        tree.column("sel",      width=30,  anchor="center")
        tree.column("name",     width=140, anchor="center")
        tree.column("username", width=100, anchor="center")
        tree.column("role",     width=80,  anchor="center")
        tree.column("phone",    width=120, anchor="center")
        sb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0,4))
        tree.pack(fill="both", expand=True, padx=(12,0), pady=4)

        # تعبئة البيانات
        for u in users:
            iid = tree.insert("", "end", values=(
                "☐",
                u.get("full_name") or u["username"],
                u["username"],
                u.get("role",""),
                u.get("phone","")
            ))
        # تبديل الاختيار بالنقر
        selected = set()
        def _toggle(event):
            row = tree.identify_row(event.y)
            if not row: return
            vals = list(tree.item(row,"values"))
            if row in selected:
                selected.discard(row)
                vals[0] = "☐"
            else:
                selected.add(row)
                vals[0] = "☑"
            tree.item(row, values=vals)
        tree.bind("<Button-1>", _toggle)

        # حقل تعديل جوال
        edit_row = ttk.Frame(win); edit_row.pack(fill="x", padx=12, pady=(0,4))
        ttk.Label(edit_row, text="تعديل جوال المحدد:").pack(side="right", padx=(0,6))
        phone_edit_var = tk.StringVar()
        ttk.Entry(edit_row, textvariable=phone_edit_var, width=18,
                  justify="right").pack(side="right")

        def _apply_phone():
            sel = tree.selection()
            if not sel: return
            row = sel[0]
            vals = list(tree.item(row,"values"))
            vals[4] = phone_edit_var.get().strip()
            tree.item(row, values=vals)
        ttk.Button(edit_row, text="تطبيق", command=_apply_phone).pack(side="right", padx=4)

        def _on_tree_select(e):
            sel = tree.selection()
            if sel:
                phone_edit_var.set(tree.item(sel[0],"values")[4])
        tree.bind("<<TreeviewSelect>>", _on_tree_select)

        status_lbl = ttk.Label(win, text="", foreground="green", font=("Tahoma",9))
        status_lbl.pack(pady=(0,4))

        def _import():
            recps = get_tardiness_recipients()
            existing = {r["phone"] for r in recps}
            added = 0
            for row in tree.get_children():
                vals = tree.item(row,"values")
                if vals[0] == "☑":
                    phone = str(vals[4]).strip()
                    name  = str(vals[1])
                    uname = str(vals[2])
                    role  = str(vals[3])
                    if not phone:
                        continue
                    # احفظ الجوال في جدول المستخدمين
                    save_user_phone(uname, phone)
                    if phone not in existing:
                        recps.append({"name":name,"phone":phone,"role":role})
                        existing.add(phone)
                        added += 1
            save_tardiness_recipients(recps)
            self._tard_recipients_load()
            status_lbl.config(text=f"✅ تم استيراد {added} مستخدم")
            win.after(1200, win.destroy)

        btn_row = ttk.Frame(win); btn_row.pack(pady=(0,10))
        ttk.Button(btn_row, text="✅ استيراد المحددين",
                   command=_import).pack(side="right", padx=6)
        ttk.Button(btn_row, text="إلغاء",
                   command=win.destroy).pack(side="right")

    def _send_tardiness_now(self):
        """يرسل رابط التأخر الآن لجميع المستلمين."""
        if not hasattr(self,"tard_send_btn"): return
        recps = get_tardiness_recipients()
        if not recps:
            messagebox.showwarning("تنبيه","لا يوجد مستلمون. أضف مستلمين أولاً.")
            return
        if not check_whatsapp_server_status():
            messagebox.showerror("خطأ","خادم واتساب غير متاح. شغّله أولاً.")
            return
        self.tard_send_btn.config(state="disabled")
        if hasattr(self,"tard_status_lbl"):
            self.tard_status_lbl.config(
                text=f"⏳ جارٍ الإرسال لـ {len(recps)} مستلم...",
                foreground="blue")
        self.root.update_idletasks()

        def do_send():
            sent, failed, details = send_tardiness_link_to_all()
            detail_txt = "\n".join(details)
            self.root.after(0, lambda: self._after_tardiness_send(
                sent, failed, detail_txt))

        threading.Thread(target=do_send, daemon=True).start()

    def _after_tardiness_send(self, sent, failed, detail_txt):
        if hasattr(self,"tard_send_btn"):
            self.tard_send_btn.config(state="normal")
        if hasattr(self,"tard_status_lbl"):
            color = "green" if failed==0 else ("orange" if sent>0 else "red")
            self.tard_status_lbl.config(
                text=f"✅ {sent} | ❌ {failed}",
                foreground=color)
        messagebox.showinfo(
            "نتيجة الإرسال",
            "تم الإرسال بنجاح: {}\nفشل: {}\n\nالتفاصيل:\n{}".format(
                sent, failed, detail_txt))

    def populate_schedule_table(self):
        selected_day = self.selected_day_var.get()
        saved_schedule = load_schedule(selected_day)
        teachers_data = load_teachers()
        teacher_names = [""] + [t["اسم المعلم"] for t in teachers_data.get("teachers", [])]

        # إذا كان الجدول مبنياً لنفس اليوم → حدّث القيم فقط بدون هدم/إعادة بناء
        if (self.schedule_widgets and
                getattr(self, "_schedule_built_day", None) == selected_day):
            for (class_id, period), combo in self.schedule_widgets.items():
                teacher = saved_schedule.get((class_id, period), "")
                combo.set(teacher if teacher in teacher_names else "")
            return

        # أول مرة أو تغيّر اليوم → أعد البناء
        self._schedule_built_day = selected_day
        for widget in self.schedule_table_frame.winfo_children():
            widget.destroy()
        self.schedule_widgets.clear()

        classes = sorted(self.store["list"], key=lambda c: c['id'])
        max_len = max((len(n) for n in teacher_names), default=15)

        header_font = ("Segoe UI", 10, "bold")
        ttk.Label(self.schedule_table_frame, text="الحصة", font=header_font, borderwidth=1, relief="solid", padding=5).grid(row=0, column=0, sticky="nsew")
        for col_idx, cls in enumerate(classes, 1):
            ttk.Label(self.schedule_table_frame, text=cls['name'], font=header_font, borderwidth=1, relief="solid", padding=5, anchor="center").grid(row=0, column=col_idx, sticky="nsew")

        for period in range(1, 8):
            ttk.Label(self.schedule_table_frame, text=f"الحصة {period}", font=header_font, borderwidth=1, relief="solid", padding=5).grid(row=period, column=0, sticky="nsew")
            for col_idx, cls in enumerate(classes, 1):
                class_id = cls['id']
                combo = ttk.Combobox(self.schedule_table_frame, values=teacher_names, state="readonly", justify='center', width=15)
                combo.bind('<Button-1>', lambda e, c=combo, w=max_len: c.config(width=w))
                combo.grid(row=period, column=col_idx, sticky="nsew", padx=1, pady=1)
                teacher = saved_schedule.get((class_id, period))
                if teacher in teacher_names:
                    combo.set(teacher)
                self.schedule_widgets[(class_id, period)] = combo

    def log_scheduler_message(self, message):
        def _do():
            now = datetime.datetime.now().strftime("%H:%M:%S")
            full_message = f"[{now}] {message}\n"
            try:
                self.scheduler_log.config(state="normal")
                self.scheduler_log.insert("1.0", full_message)
                self.scheduler_log.config(state="disabled")
            except Exception:
                pass
        self.root.after(0, _do)

    def on_save_schedule_and_times(self):
        selected_day = self.selected_day_var.get()
        day_name = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}.get(selected_day, "المحدد")

        schedule_data = []
        for period in range(1, 8):
            for cls in self.store["list"]:
                widget = self.schedule_widgets.get((cls['id'], period))
                if widget:
                    schedule_data.append({"class_id": cls['id'], "period": period, "teacher_name": widget.get()})
        try:
            save_schedule(selected_day, schedule_data)
        except Exception as e:
            messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ جدول يوم {day_name}:\n{e}")
            return

        period_times = [self.schedule_time_vars[p].get() for p in range(1, 8)]
        self.cfg["period_times"] = period_times
        # حفظ وقت بداية الدوام
        if hasattr(self, "school_start_var"):
            self.cfg["school_start_time"] = self.school_start_var.get().strip()
        try:
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("خطأ في الحفظ", f"حدث خطأ أثناء حفظ التواقيت:\n{e}")
            return
            
        messagebox.showinfo("تم الحفظ", f"تم حفظ جدول يوم {day_name} والتواقيت بنجاح.")
        self.log_scheduler_message(f"تم حفظ جدول يوم {day_name}.")


    def start_scheduler(self):
        today = datetime.datetime.now()
        day_of_week = (today.weekday() + 1) % 7 
        
        if day_of_week > 4:
            messagebox.showwarning("يوم عطلة", "لا يمكن بدء المرسل الآلي في يوم عطلة نهاية الأسبوع.")
            self.log_scheduler_message("⚠️ محاولة بدء الإرسال في يوم عطلة. تم الرفض.")
            return

        if self.scheduler_running:
            messagebox.showwarning("قيد التشغيل", "المرسل الآلي يعمل بالفعل.")
            return

        if not messagebox.askyesno("تأكيد البدء", "هل أنت متأكد من أنك تريد بدء الإرسال الآلي لروابط الحصص؟"):
            return

        self.scheduler_running = True
        self.start_scheduler_button.config(state="disabled")
        self.stop_scheduler_button.config(state="normal")
        day_name = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}.get(day_of_week)
        self.log_scheduler_message(f"🚀 تم بدء المرسل الآلي لجدول يوم {day_name}.")

        schedule = load_schedule(day_of_week)
        if not schedule:
            self.log_scheduler_message(f"⚠️ تحذير: جدول يوم {day_name} فارغ. لن يتم إرسال أي شيء.")
            self.stop_scheduler()
            return

        now = datetime.datetime.now()
        base_url = self.public_url or f"http://{self.ip}:{PORT}"
        
        for period in range(1, 8  ):
            time_str = self.schedule_time_vars[period].get()
            try:
                hour, minute = map(int, time_str.split(':'))
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                delay = (target_time - now).total_seconds()
                if delay < 0:
                    self.log_scheduler_message(f"الحصة {period} ({time_str}): الوقت قد فات. تم تخطيها.")
                    continue

                timer = threading.Timer(delay, self.send_links_for_period, args=[period, schedule, base_url])
                self.scheduler_timers.append(timer)
                timer.start()
                self.log_scheduler_message(f"الحصة {period}: تمت جدولتها للإرسال الساعة {time_str}.")

            except (ValueError, AttributeError):
                self.log_scheduler_message(f"الحصة {period}: صيغة الوقت ({time_str}) غير صالحة. تم تخطيها.")
        
        if not self.scheduler_timers:
            self.log_scheduler_message("لم تتم جدولة أي حصص. تأكد من التواقيت.")
            self.stop_scheduler()


    def stop_scheduler(self):
        for timer in self.scheduler_timers:
            timer.cancel()
        
        self.scheduler_timers = []
        self.scheduler_running = False
        self.start_scheduler_button.config(state="normal")
        self.stop_scheduler_button.config(state="disabled")
        self.log_scheduler_message("🛑 تم إيقاف المرسل الآلي.")

    def send_links_for_period(self, period, schedule, base_url):
        self.log_scheduler_message(f"🔔 حان وقت الحصة {period}! جارٍ إرسال الروابط...")
        
        teachers_to_notify = {}
        
        for (class_id, p), teacher_name in schedule.items():
            if p == period and teacher_name:
                class_info = self.store["by_id"].get(class_id)
                if class_info:
                    if teacher_name not in teachers_to_notify:
                        teachers_to_notify[teacher_name] = []
                    teachers_to_notify[teacher_name].append(class_info)

        if not teachers_to_notify:
            self.log_scheduler_message(f"الحصة {period}: لا يوجد معلمون مجدولون لهذه الحصة.")
            return

        all_teachers = {t["اسم المعلم"]: t for t in load_teachers().get("teachers", [])}

        for teacher_name, assigned_classes in teachers_to_notify.items():
            teacher_data = all_teachers.get(teacher_name)
            if not teacher_data or not teacher_data.get("رقم الجوال"):
                self.log_scheduler_message(f"الحصة {period}: فشل إرسال لـ '{teacher_name}' (لا يوجد رقم جوال).")
                continue

            links_text = "\n".join([f"- فصل: {c['name']}\n  الرابط: {base_url}/c/{c['id']}" for c in assigned_classes])
            message_body = (
                f"السلام عليكم أ. {teacher_name},\n"
                f"إليك روابط تسجيل الغياب للحصة {period}:\n\n"
                f"{links_text}\n\n"
                "مع تحيات إدارة المدرسة."
            )
            
            success, msg = send_whatsapp_message(teacher_data["رقم الجوال"], message_body)
            
            if success:
                self.log_scheduler_message(f"✅ تم إرسال روابط الحصة {period} إلى '{teacher_name}'.")
            else:
                self.log_scheduler_message(f"❌ فشل إرسال لـ '{teacher_name}': {msg}")


    def _build_add_student_tab(self):
        frame = self.add_student_frame

    # الحقول
        ttk.Label(frame, text="الاسم الكامل:").grid(row=0, column=1, padx=10, pady=10, sticky="e")
        self.add_name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.add_name_var, width=40).grid(row=0, column=0, padx=10, pady=10, sticky="w")
    
        ttk.Label(frame, text="الرقم الأكاديمي:").grid(row=1, column=1, padx=10, pady=10, sticky="e")
        self.add_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.add_id_var, width=40).grid(row=1, column=0, padx=10, pady=10, sticky="w")
    
        ttk.Label(frame, text="رقم الجوال (اختياري):").grid(row=2, column=1, padx=10, pady=10, sticky="e")
        self.add_phone_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.add_phone_var, width=40).grid(row=2, column=0, padx=10, pady=10, sticky="w")
    
        ttk.Label(frame, text="الفصل:").grid(row=3, column=1, padx=10, pady=10, sticky="e")
        self.add_class_var = tk.StringVar()
        class_names = [c["name"] for c in self.store["list"]]
        self.add_class_combo = ttk.Combobox(frame, textvariable=self.add_class_var, values=class_names, state="readonly", width=37)
        self.add_class_combo.grid(row=3, column=0, padx=10, pady=10, sticky="w")

    # زر الإضافة
        ttk.Button(frame, text="➕ إضافة الطالب", command=self.add_new_student).grid(row=4, column=0, columnspan=2, pady=20)

    # رسالة الحالة
        self.add_status_label = ttk.Label(frame, text="")
        self.add_status_label.grid(row=5, column=0, columnspan=2, pady=10)       

    def add_new_student(self):
        name = self.add_name_var.get().strip()
        student_id = self.add_id_var.get().strip()
        phone = self.add_phone_var.get().strip()
        class_name = self.add_class_var.get().strip()
    
        if not name or not student_id or not class_name:
            messagebox.showwarning("بيانات ناقصة", "الرجاء تعبئة الاسم، الرقم الأكاديمي، والفصل.")
            return
    
        # البحث عن class_id من الاسم
        target_class = None
        for c in self.store["list"]:
            if c["name"] == class_name:
                target_class = c
                break
        if not target_class:
            messagebox.showerror("خطأ", "الفصل المحدد غير موجود.")
            return

    # التحقق من التكرار
        for c in self.store["list"]:
            for s in c["students"]:
                if s.get("id") == student_id:
                    messagebox.showerror("تكرار", f"الرقم الأكاديمي '{student_id}' مستخدم مسبقًا.")
                    return

    # إضافة الطالب
        new_student = {"id": student_id, "name": name, "phone": phone}
        target_class["students"].append(new_student)

    # حفظ
        try:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم", "تمت إضافة الطالب بنجاح!")
            self.add_status_label.config(text="✅ تم الحفظ", foreground="green")
            # مسح الحقول
            self.add_name_var.set("")
            self.add_id_var.set("")
            self.add_phone_var.set("")
            self.add_class_var.set("")
            # تحديث المتجر عالميًا
            global STUDENTS_STORE
            STUDENTS_STORE = None
            self.store = load_students(force_reload=True)
            # تحديث باقي التبويبات
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحفظ:\n{e}")
            
    def delete_selected_student(self):
        if not (selection := self.tree_student_management.selection()):
            messagebox.showwarning("تنبيه", "الرجاء تحديد طالب من القائمة أولاً.")
            return
        values = self.tree_student_management.item(selection[0], "values")
        student_id = values[0]
        student_name = values[1]
        if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف الطالب:\nالاسم: {student_name}\nالرقم: {student_id}\n\nلا يمكن التراجع عن هذا الإجراء!"):
            return

    # ← ابدأ المسافة البادئة هنا (4 مسافات)
        store = load_students(force_reload=True)
        classes = store.get("list", [])
        found = False
        for c in classes:
            for i, s in enumerate(c.get("students", [])):
                if s.get("id") == student_id:
                    del c["students"][i]
                    found = True
                    break
            if found:
                break

        if not found:
            messagebox.showerror("خطأ", "الطالب غير موجود في البيانات!")
            return

        try:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم", "تم حذف الطالب بنجاح.")
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

    def delete_selected_class(self):
        class_names = [c["name"] for c in self.store["list"]]
        class_name = simpledialog.askstring("حذف فصل", "اكتب اسم الفصل الذي تريد حذفه بالضبط:", parent=self.root)
        if not class_name:
            return
        if class_name not in class_names:
            messagebox.showerror("خطأ", "اسم الفصل غير موجود!")
            return
    
        class_id = next(c["id"] for c in self.store["list"] if c["name"] == class_name)
        student_count = len(next(c["students"] for c in self.store["list"] if c["id"] == class_id))
    
        if not messagebox.askyesno("تأكيد الحذف", f"تحذير: سيتم حذف الفصل '{class_name}' وجميع طلابه ({student_count} طالب)!\nهل أنت متأكد؟"):
            return

        new_classes = [c for c in self.store["list"] if c["id"] != class_id]
        try:
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump({"classes": new_classes}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم", f"تم حذف الفصل '{class_name}' بنجاح.")
            self.update_all_tabs_after_data_change()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل الحذف:\n{e}")

# ===================== تبويب تحليل النتائج =====================
# ── ثوابت التقديرات ─────────────────────────────────────────
# grade analysis functions moved to grade_analysis.py
from grade_analysis import *
from grade_analysis import (
    _ga_placeholder_html, _ga_build_html, _ga_build_print_html,
    _ga_export_word, _ga_open_header_editor, _ga_parse_file,
    _ga_parse_excel, _ga_parse_csv, _ga_parse_noor_pdf,
    _ga_is_subject, _ga_grade, _ga_build_cid_map,
)

def _build_grade_analysis_tab_impl(self):
    """
    تبويب تحليل نتائج الطلاب:
    • رفع Excel/PDF/CSV — محلّل ذكي يتعامل مع خطوط PDF المشفرة
    • عرض HTML تفاعلي داخل التطبيق
    • تعديل بيانات الترويسة (مدرسة/فصل/معلم/مدير)
    • تصدير HTML للطباعة كـ PDF
    • تصدير Word .docx
    """
    frame = self.grade_analysis_frame

    # ── شريط العنوان ──
    hdr = tk.Frame(frame, bg="#1A3A5C", height=48)
    hdr.pack(fill="x"); hdr.pack_propagate(False)
    tk.Label(hdr, text="📊 تحليل نتائج الطلاب",
             bg="#1A3A5C", fg="white",
             font=("Tahoma", 13, "bold")).pack(side="right", padx=16, pady=12)
    tk.Label(hdr, text="تقرير تفصيلي بالتقديرات والرسوم البيانية — يدعم Excel / PDF / CSV",
             bg="#1A3A5C", fg="#90CAF9",
             font=("Tahoma", 8)).pack(side="right", pady=12)

    # ── شريط الأدوات ──
    toolbar = tk.Frame(frame, bg="#F0F4F8", pady=7)
    toolbar.pack(fill="x", padx=0)
    tk.Frame(frame, bg="#D0D7E3", height=1).pack(fill="x")

    tb = tk.Frame(toolbar, bg="#F0F4F8")
    tb.pack(fill="x", padx=12)

    self._ga_file_path  = tk.StringVar()
    self._ga_status_var = tk.StringVar(value="لم يتم اختيار ملف")

    tk.Label(tb, text="ملف النتائج:", bg="#F0F4F8", fg="#1A3A5C",
             font=("Tahoma", 9, "bold")).pack(side="right", padx=(0, 5))
    ttk.Entry(tb, textvariable=self._ga_file_path,
              state="readonly", width=34, font=("Tahoma", 9)).pack(side="right", padx=3)

    def _browse():
        p = filedialog.askopenfilename(
            title="اختر ملف النتائج",
            filetypes=[
                ("ملفات مدعومة", "*.xlsx *.xls *.pdf *.csv"),
                ("Excel", "*.xlsx *.xls"),
                ("PDF",   "*.pdf"),
                ("CSV",   "*.csv"),
            ])
        if p:
            self._ga_file_path.set(p)
            self._ga_status_var.set(f"📄 {os.path.basename(p)}")
            status_lbl.config(fg="#E67E22")

    def _analyze():
        path = self._ga_file_path.get()
        if not path:
            messagebox.showwarning("تنبيه", "يُرجى اختيار ملف أولاً", parent=self.root)
            return
        self._ga_status_var.set("⏳ جارٍ تحليل الملف...")
        status_lbl.config(fg="#E67E22")
        frame.update_idletasks()

        def _worker():
            try:
                students = _ga_parse_file(path)
                if not students:
                    self.root.after(0, lambda: (
                        self._ga_status_var.set("❌ لم يُعثر على بيانات طلاب"),
                        status_lbl.config(fg="#E74C3C")
                    ))
                    return
                html = _ga_build_html(students)
                self.root.after(0, lambda h=html, s=students: _show_html(h, s))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: (
                    self._ga_status_var.set(f"❌ {err[:70]}"),
                    status_lbl.config(fg="#E74C3C")
                ))
        threading.Thread(target=_worker, daemon=True).start()

    for txt, col, cmd in [
        ("📁 اختر ملف",    "#2471A3", _browse),
        ("⚡ تحليل",       "#27AE60", _analyze),
    ]:
        tk.Button(tb, text=txt, bg=col, fg="white",
                  font=("Tahoma", 9, "bold"), relief="flat",
                  cursor="hand2", padx=9, pady=4,
                  command=cmd).pack(side="right", padx=3)

    # فاصل
    tk.Frame(tb, bg="#D0D7E3", width=1, height=26).pack(side="right", padx=6)

    # فلاتر
    for lbl_txt, attr in [("الفصل:", "class"), ("المادة:", "subject")]:
        tk.Label(tb, text=lbl_txt, bg="#F0F4F8", fg="#555",
                 font=("Tahoma", 9)).pack(side="right", padx=(6, 3))
        var = tk.StringVar(value="الكل")
        cb  = ttk.Combobox(tb, textvariable=var, state="readonly",
                            width=16, font=("Tahoma", 9))
        cb.pack(side="right", padx=3)
        setattr(self, f"_ga_{attr}_var", var)
        setattr(self, f"_ga_{attr}_cb",  cb)
        cb.bind("<<ComboboxSelected>>", lambda e: _refilter())

    # فاصل
    tk.Frame(tb, bg="#D0D7E3", width=1, height=26).pack(side="right", padx=6)

    # أزرار التصدير
    self._ga_export_html_btn = tk.Button(
        tb, text="📄 تصدير PDF", bg="#E74C3C", fg="white",
        font=("Tahoma", 9, "bold"), relief="flat", cursor="hand2",
        padx=9, pady=4, state="disabled",
        command=lambda: _export_html())
    self._ga_export_html_btn.pack(side="right", padx=3)

    self._ga_export_word_btn = tk.Button(
        tb, text="📝 تصدير Word", bg="#8E44AD", fg="white",
        font=("Tahoma", 9, "bold"), relief="flat", cursor="hand2",
        padx=9, pady=4, state="disabled",
        command=lambda: _export_word())
    self._ga_export_word_btn.pack(side="right", padx=3)

    # زر تعديل الترويسة
    tk.Button(tb, text="✏️ بيانات التقرير", bg="#E67E22", fg="white",
              font=("Tahoma", 9, "bold"), relief="flat", cursor="hand2",
              padx=9, pady=4,
              command=lambda: _ga_open_header_editor(
                  self.root,
                  on_save=lambda: _refilter() if self._ga_all_students else None
              )).pack(side="right", padx=3)

    status_lbl = tk.Label(tb, textvariable=self._ga_status_var,
                           bg="#F0F4F8", fg="#7F8C8D", font=("Tahoma", 9))
    status_lbl.pack(side="left", padx=8)

    tk.Frame(frame, bg="#D0D7E3", height=1).pack(fill="x")

    # ── منطقة المتصفح ──
    browser_frame = tk.Frame(frame, bg="white")
    browser_frame.pack(fill="both", expand=True)

    self._ga_browser = HtmlFrame(browser_frame, horizontal_scrollbar="auto", messages_enabled=False)
    self._ga_browser.pack(fill="both", expand=True)
    self._ga_browser.load_html(_ga_placeholder_html())
    self._ga_all_students = []

    def _show_html(html, students):
        self._ga_all_students = students
        classes  = sorted(set(s.get("class", "") or "غير محدد" for s in students))
        subjects = sorted(set(sub["subject"] for s in students for sub in s.get("subjects", [])))
        self._ga_class_cb["values"]   = ["الكل"] + classes;   self._ga_class_var.set("الكل")
        self._ga_subject_cb["values"] = ["الكل"] + subjects;  self._ga_subject_var.set("الكل")
        self._ga_browser.load_html(html)
        self._ga_status_var.set(f"✅ تم تحليل {len(students)} طالب")
        status_lbl.config(fg="#27AE60")
        self._ga_export_html_btn.config(state="normal")
        self._ga_export_word_btn.config(state="normal")

    def _refilter():
        if not self._ga_all_students:
            return
        sel_class   = self._ga_class_var.get()
        sel_subject = self._ga_subject_var.get()
        filtered = [s for s in self._ga_all_students
                    if sel_class == "الكل" or (s.get("class") or "غير محدد") == sel_class]
        html = _ga_build_html(filtered, sel_subject)
        self._ga_browser.load_html(html)

    def _get_filtered():
        sel_class = self._ga_class_var.get()
        return [s for s in self._ga_all_students
                if sel_class == "الكل" or (s.get("class") or "غير محدد") == sel_class]

    def _export_html():
        if not self._ga_all_students:
            return
        filtered    = _get_filtered()
        sel_subject = self._ga_subject_var.get()
        if not filtered:
            messagebox.showwarning("تنبيه", "لا توجد بيانات للتصدير", parent=self.root)
            return
        today = datetime.date.today().strftime("%Y-%m-%d")
        out = filedialog.asksaveasfilename(
            title="حفظ تقرير PDF", defaultextension=".html",
            initialfile=f"تحليل_نتائج_{today}.html",
            filetypes=[("HTML للطباعة كـ PDF", "*.html")])
        if not out:
            return
        self._ga_status_var.set("⏳ جارٍ إنشاء التقرير...")
        status_lbl.config(fg="#E67E22"); frame.update_idletasks()

        def _do():
            try:
                html = _ga_build_print_html(filtered, sel_subject)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(html)
                self.root.after(0, lambda: _done_html(out))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: (
                    self._ga_status_var.set(f"❌ {err[:60]}"),
                    status_lbl.config(fg="#E74C3C")
                ))
        threading.Thread(target=_do, daemon=True).start()

    def _done_html(path):
        self._ga_status_var.set("✅ تم حفظ التقرير")
        status_lbl.config(fg="#27AE60")
        if messagebox.askyesno("✅ تم",
            f"تم حفظ التقرير:\n{path}\n\nفتحه في المتصفح للطباعة / حفظ PDF؟",
                parent=self.root):
            try:
                webbrowser.open(f"file:///{os.path.abspath(path)}")
            except Exception:
                pass

    def _export_word():
        if not self._ga_all_students:
            return
        filtered    = _get_filtered()
        sel_subject = self._ga_subject_var.get()
        if not filtered:
            messagebox.showwarning("تنبيه", "لا توجد بيانات للتصدير", parent=self.root)
            return
        today = datetime.date.today().strftime("%Y-%m-%d")
        out = filedialog.asksaveasfilename(
            title="حفظ تقرير Word", defaultextension=".docx",
            initialfile=f"تحليل_نتائج_{today}.docx",
            filetypes=[("Word Document", "*.docx")])
        if not out:
            return
        self._ga_status_var.set("⏳ جارٍ إنشاء ملف Word...")
        status_lbl.config(fg="#E67E22"); frame.update_idletasks()

        def _do():
            try:
                _ga_export_word(filtered, out, sel_subject)
                self.root.after(0, lambda: _done_word(out))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: (
                    self._ga_status_var.set(f"❌ {err[:60]}"),
                    status_lbl.config(fg="#E74C3C")
                ))
        threading.Thread(target=_do, daemon=True).start()

    def _done_word(path):
        self._ga_status_var.set("✅ تم حفظ ملف Word")
        status_lbl.config(fg="#27AE60")
        if messagebox.askyesno("✅ تم",
            f"تم حفظ ملف Word:\n{path}\n\nفتحه الآن؟",
                parent=self.root):
            try:
                if sys.platform == "win32":
                    os.startfile(path)
                else:
                    webbrowser.open(f"file:///{os.path.abspath(path)}")
            except Exception:
                pass


# ── ربط الدالة بـ AppGUI ──────────────────────────────────
AppGUI._build_grade_analysis_tab = _build_grade_analysis_tab_impl



