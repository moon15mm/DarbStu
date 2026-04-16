# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import datetime, threading
from typing import List, Dict, Any, Optional

import constants
from gui.lib_loader import Figure, FigureCanvasTkAgg, arabic_reshaper, get_display
from database import get_student_analytics_data

def ar(txt):
    if not txt: return ""
    if arabic_reshaper and get_display:
        return get_display(arabic_reshaper.reshape(str(txt)))
    return str(txt)

class StudentAnalysisTabMixin:
    """Mixin: تبويب تحليل الطالب الشامل"""

    def _build_student_analysis_tab(self):
        frame = self.student_analysis_frame

        # ── (1) شريط العنوان والبحث ──
        header = tk.Frame(frame, bg="#0F172A", height=70)
        header.pack(fill="x"); header.pack_propagate(False)

        tk.Label(header, text="👤 تحليل الطالب الشامل", bg="#0F172A", fg="white",
                 font=("Tahoma", 14, "bold")).pack(side="right", padx=20, pady=20)

        search_f = tk.Frame(header, bg="#1E293B", padx=10, pady=5)
        search_f.pack(side="left", padx=20, pady=15)

        tk.Label(search_f, text="🔍 ابحث عن طالب:", bg="#1E293B", fg="#CBD5E1",
                 font=("Tahoma", 9)).pack(side="right", padx=5)

        self.analysis_search_var = tk.StringVar()
        self.analysis_student_cb = ttk.Combobox(search_f, textvariable=self.analysis_search_var, 
                                                width=40, font=("Tahoma", 10))
        self.analysis_student_cb.pack(side="right", padx=5)
        
        # تعبئة الطلاب
        self.refresh_analysis_students()
        self.analysis_student_cb.bind("<<ComboboxSelected>>", self._on_analysis_student_selected)

        # ── (2) منطقة المحتوى الرئيسية ──
        self.analysis_content = tk.Frame(frame, bg="#F1F5F9")
        self.analysis_content.pack(fill="both", expand=True)

        # ── (3) كروت الإحصائيات (KPIs) ──
        self.analysis_stats_frame = tk.Frame(self.analysis_content, bg="#F1F5F9", pady=15)
        self.analysis_stats_frame.pack(fill="x", padx=20)

        self.analysis_cards = {}
        for i, (title, color, icon) in enumerate([
            ("الغيابات", "#EF4444", "🚩"),
            ("دقائق التأخر", "#F59E0B", "⏱️"),
            ("المخالفات السلوكية", "#6366F1", "⚖️"),
            ("المعدل / التقدير", "#10B981", "🎓")
        ]):
            card = tk.Frame(self.analysis_stats_frame, bg="white", relief="flat", bd=0, padx=15, pady=10)
            card.grid(row=0, column=i, padx=10, sticky="nsew")
            self.analysis_stats_frame.columnconfigure(i, weight=1)
            
            # ظل بسيط (محاكاة)
            card.configure(highlightbackground="#E2E8F0", highlightthickness=1)

            tk.Label(card, text=f"{icon} {title}", bg="white", fg="#64748B", font=("Tahoma", 10)).pack(anchor="e")
            val_lbl = tk.Label(card, text="0", bg="white", fg="#1E293B", font=("Tahoma", 18, "bold"))
            val_lbl.pack(anchor="e", pady=(5,0))
            self.analysis_cards[title] = val_lbl

        # ── (4) منطقة الرسوم البيانية ──
        charts_f = tk.Frame(self.analysis_content, bg="#F1F5F9")
        charts_f.pack(fill="both", expand=True, padx=20, pady=5)
        charts_f.columnconfigure(0, weight=1); charts_f.columnconfigure(1, weight=1)
        charts_f.rowconfigure(0, weight=1)

        # الرسم البياني 1: الغياب الشهري
        abs_lf = tk.LabelFrame(charts_f, text=ar(" اتجاه الغياب الشهري "), bg="white", font=("Tahoma", 9, "bold"), padx=10, pady=10)
        abs_lf.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self.fig_abs = Figure(figsize=(5, 3), dpi=90)
        self.ax_abs  = self.fig_abs.add_subplot(111)
        self.canvas_abs = FigureCanvasTkAgg(self.fig_abs, abs_lf)
        self.canvas_abs.get_tk_widget().pack(fill="both", expand=True)

        # الرسم البياني 2: ملخص الحالات
        cases_lf = tk.LabelFrame(charts_f, text=ar(" توزيع الحالات السلوكية والتأخر "), bg="white", font=("Tahoma", 9, "bold"), padx=10, pady=10)
        cases_lf.grid(row=0, column=0, sticky="nsew")
        self.fig_cases = Figure(figsize=(5, 3), dpi=90)
        self.ax_cases  = self.fig_cases.add_subplot(111)
        self.canvas_cases = FigureCanvasTkAgg(self.fig_cases, cases_lf)
        self.canvas_cases.get_tk_widget().pack(fill="both", expand=True)

        # ── (5) السجل التفصيلي ──
        logs_lf = tk.LabelFrame(self.analysis_content, text=" 🕒 الجدول الزمني لأحدث الإجراءات ", bg="white", font=("Tahoma", 9, "bold"), padx=10, pady=10)
        logs_lf.pack(fill="both", expand=True, padx=30, pady=(10, 20))

        self.analysis_tree = ttk.Treeview(logs_lf, columns=("date", "type", "details", "status"), show="headings", height=5)
        self.analysis_tree.heading("date", text="التاريخ")
        self.analysis_tree.heading("type", text="النوع")
        self.analysis_tree.heading("details", text="التفاصيل")
        self.analysis_tree.heading("status", text="الحالة")
        
        self.analysis_tree.column("date", width=100, anchor="center")
        self.analysis_tree.column("type", width=120, anchor="center")
        self.analysis_tree.column("details", width=400, anchor="e")
        self.analysis_tree.column("status", width=100, anchor="center")
        self.analysis_tree.pack(fill="both", expand=True)

    def refresh_analysis_students(self):
        """تحديث قائمة الطلاب في الـ Combobox من المخزن العام."""
        import constants
        store = constants.STUDENTS_STORE
        if not store or "list" not in store:
            return
            
        student_list = []
        for cls in store["list"]:
            for s in cls.get("students", []):
                sid = s.get("id", "")
                name = s.get("name", "")
                if sid and name:
                    student_list.append(f"{name} - {sid}")
        
        self.analysis_student_cb['values'] = sorted(list(set(student_list)))

    def _on_analysis_student_selected(self, event=None):
        val = self.analysis_search_var.get()
        if " - " in val:
            sid = val.split(" - ")[-1].strip()
            self.load_student_analysis(sid)

    def load_student_analysis(self, student_id: str):
        """
        تُحمل كافة بيانات الطالب وتُحدث الواجهة.
        تُسمى داخلياً أو خارجياً عند الضغط مرتين على اسم طالب أو من تبويب آخر.
        """
        import constants
        store = constants.STUDENTS_STORE
        
        # محاولة إيجاد اسم الطالب لتحديث شريط البحث
        found_name = ""
        if store and "list" in store:
            for cls in store["list"]:
                for s in cls.get("students", []):
                    if str(s.get("id")) == str(student_id):
                        found_name = s.get("name", "")
                        break
                if found_name: break
        
        if found_name:
            self.analysis_search_var.set(f"{found_name} - {student_id}")
        else:
            self.analysis_search_var.set(f"ID: {student_id}")
        
        # جلب البيانات من قاعدة البيانات في thread منفصل
        def _worker():
            try:
                data = get_student_analytics_data(student_id)
                self.root.after(0, lambda d=data: self._update_analysis_ui(d))
            except Exception as e:
                print(f"[ANALYSIS-ERROR] {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _update_analysis_ui(self, data):
        # 1. تحديث الكروت
        abs_count = len(data["absences"])
        tard_mins = sum(r["minutes"] for r in data["tardiness"])
        ref_count = len(data["referrals"])
        gpa_val   = data["results"]["gpa"] if data["results"] else "—"

        self.analysis_cards["الغيابات"].config(text=str(abs_count))
        self.analysis_cards["دقائق التأخر"].config(text=str(tard_mins))
        self.analysis_cards["المخالفات السلوكية"].config(text=str(ref_count))
        self.analysis_cards["المعدل / التقدير"].config(text=str(gpa_val))

        # 2. رسم بياني للغياب (حسب الشهر)
        self._draw_absence_chart(data["absences"])
        
        # 3. رسم بياني ملخص (توزيع المخالفات)
        self._draw_cases_chart(data)

        # 4. تحديث الجدول الزمني
        self.analysis_tree.delete(*self.analysis_tree.get_children())
        combined_logs = []
        for r in data["absences"]: combined_logs.append((r["date"], "غياب", f"الحصة: {r['period']}", "مسجل"))
        for r in data["tardiness"]: combined_logs.append((r["date"], "تأخر", f"مقدر بـ {r['minutes']} دقيقة", "مسجل"))
        for r in data["referrals"]: combined_logs.append((r["date"], f"تحويل {r['type']}", r["violation"], r["status"]))
        for r in data["sessions"]: combined_logs.append((r["date"], "جلسة ارشادية", r["reason"], "منتهية"))
        
        # ترتيب حسب التاريخ تنازلياً
        combined_logs.sort(key=lambda x: x[0], reverse=True)
        for log in combined_logs[:20]: # عرض آخر 20 إجراء فقط
            self.analysis_tree.insert("", "end", values=log)

    def _draw_absence_chart(self, absences):
        self.ax_abs.clear()
        if not absences:
            self.ax_abs.text(0.5, 0.5, ar("لا توجد بيانات غياب"), ha='center', va='center')
        else:
            # تجميع حسب الشهر
            months = {}
            for a in absences:
                m = a["date"][:7] # YYYY-MM
                months[m] = months.get(m, 0) + 1
            
            sorted_months = sorted(months.keys())
            counts = [months[m] for m in sorted_months]
            
            self.ax_abs.bar(sorted_months, counts, color="#6366F1")
            self.ax_abs.set_title(ar("الغيابات المتراكمة شهرياً"), fontsize=10)
            for i, v in enumerate(counts):
                self.ax_abs.text(i, v + 0.1, str(v), ha='center', fontweight='bold')

        self.canvas_abs.draw_idle()

    def _draw_cases_chart(self, data):
        self.ax_cases.clear()
        labels = []
        sizes = []
        
        # بيانات الدائرة: غياب vs تأخر vs مخالفات
        abs_c = len(data["absences"])
        tard_c = len(data["tardiness"])
        ref_c = len(data["referrals"])
        
        vals = [abs_c, tard_c, ref_c]
        labs = [ar("غياب"), ar("تأخر"), ar("سلوك")]
        final_vals = []
        final_labs = []
        for v, l in zip(vals, labs):
            if v > 0:
                final_vals.append(v)
                final_labs.append(l)

        if not final_vals:
            self.ax_cases.text(0.5, 0.5, ar("لا توجد مخالفات مسجلة"), ha='center', va='center')
        else:
            self.ax_cases.pie(final_vals, labels=final_labs, autopct='%1.1f%%', startangle=140, 
                             colors=["#F87171", "#FBBF24", "#818CF8"])
            self.ax_cases.set_title(ar("ميزان الانضباط العام"), fontsize=10)

        self.canvas_cases.draw_idle()
