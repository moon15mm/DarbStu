# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os, json, datetime, threading, re, io, csv, base64, time
from constants import now_riyadh_date
from config_manager import ar
from database import query_tardiness
from alerts_service import get_top_absent_students, get_week_comparison, get_absence_by_day_of_week
from report_builder import compute_today_metrics

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:
    Figure = FigureCanvasTkAgg = None

class DashboardTabMixin:
    """Mixin: DashboardTabMixin"""
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


    def _dashboard_tick(self):
        """يُحدَّث كل 30 ث — فقط إذا كان تبويب لوحة المراقبة نشطاً لتجنب اهتزاز التبويبات الأخرى."""
        if hasattr(self, "_current_tab") and self._current_tab.get() == "لوحة المراقبة":
            self.update_dashboard_metrics()
        self.root.after(30000, self._dashboard_tick)

    def update_dashboard_metrics(self):
        date_str = self.dash_date_var.get().strip() or now_riyadh_date()
        try:
            metrics = compute_today_metrics(date_str)
        except Exception as e:
            messagebox.showerror("خطأ", str(e)); return

        t = metrics["totals"]
        pct_absent = round(t["absent"] / max(t["students"],1) * 100, 1)

        # ─ بطاقات الإحصاء
        self.lbl_total.config(text=str(t["students"]))
        self.lbl_present.config(text=str(t["present"]))
        self.lbl_absent.config(text=str(t["absent"]))
        if hasattr(self,"lbl_absent_sub"):
            self.lbl_absent_sub.config(text="{}% من الإجمالي".format(pct_absent))

        # التأخر اليوم
        tard_today = len(query_tardiness(date_filter=date_str))
        if hasattr(self,"lbl_tard"):
            self.lbl_tard.config(text=str(tard_today))

        # مقارنة الأسبوع
        try:
            wk = get_week_comparison()
            if hasattr(self,"lbl_week"):
                self.lbl_week.config(text=str(wk["this_total"]))
            if hasattr(self,"lbl_week_sub"):
                arrow = "▲" if wk["change"]>0 else ("▼" if wk["change"]<0 else "=")
                color  = "#EF4444" if wk["change"]>0 else "#10B981"
                self.lbl_week_sub.config(
                    text="{} {}% عن الأسبوع الماضي".format(
                        arrow, abs(wk["pct"])),
                    foreground=color)
            if hasattr(self,"dash_week_lbl"):
                self.dash_week_lbl.config(
                    text="الأسبوع الماضي: {} غياب".format(wk["last_total"]))
        except Exception as e:
            print("[DASH-WEEK]", e)

        # ─ جدول الفصول
        for i in self.tree_dash.get_children():
            self.tree_dash.delete(i)
        for r in metrics["by_class"]:
            pct = round(r["absent"]/max(r["total"],1)*100, 0)
            tag = "high" if pct >= 20 else "normal"
            self.tree_dash.insert("", "end", tags=(tag,),
                values=(r["class_id"], r["class_name"],
                        r["total"],
                        "🟢 {}".format(r["present"]),
                        "🔴 {}".format(r["absent"]),
                        "{}%".format(int(pct))))

        # ─ أكثر الطلاب غياباً
        if hasattr(self,"tree_top_absent"):
            for i in self.tree_top_absent.get_children():
                self.tree_top_absent.delete(i)
            month = date_str[:7]
            for idx, s in enumerate(get_top_absent_students(month, limit=8)):
                tag = "top1" if idx==0 else ("top3" if idx<3 else "")
                self.tree_top_absent.insert("","end", tags=(tag,),
                    values=(s["name"], s["class_name"],
                            "{} يوم".format(s["days"]), s["last_date"]))

        # ─ رسم الدائرة
        try:
            self.ax_pie.clear()
            sizes  = [t["present"], t["absent"]]
            if sum(sizes) > 0:
                self.ax_pie.pie(
                    sizes,
                    labels=[ar("الحضور"), ar("الغياب")],
                    autopct="%1.1f%%", startangle=90,
                    colors=["#10B981","#EF4444"])
            self.ax_pie.set_title(ar("الحضور/الغياب اليوم"), fontsize=9)
            self.canvas_pie.draw_idle()
        except Exception as e:
            print("[DASH-PIE]", e)

        # ─ رسم مقارنة الأسبوعين
        try:
            self.ax_week.clear()
            wk = get_week_comparison()
            day_names_short = ["أحد","إثنين","ثلاث","أربع","خميس"]
            x = range(5)
            this_vals = [wk["this_daily"].get(
                (datetime.date.fromisoformat(wk["this_week_start"]) +
                 datetime.timedelta(days=i)).isoformat(), 0) for i in range(5)]
            last_vals = [wk["last_daily"].get(
                (datetime.date.fromisoformat(wk["last_week_start"]) +
                 datetime.timedelta(days=i)).isoformat(), 0) for i in range(5)]
            w_bar = 0.35
            self.ax_week.bar([i-w_bar/2 for i in x], last_vals,
                              w_bar, label=ar("الأسبوع الماضي"), color="#93C5FD")
            self.ax_week.bar([i+w_bar/2 for i in x], this_vals,
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
            dow_data = get_absence_by_day_of_week()
            days_ar   = list(dow_data.keys())
            vals      = list(dow_data.values())
            bars = self.ax_dow.bar(
                [ar(d) for d in days_ar], vals,
                color=["#EF4444" if v==max(vals) else "#FCA5A5" for v in vals])
            self.ax_dow.set_title(ar("متوسط الغياب حسب اليوم"), fontsize=9)
            for bar_r, v in zip(bars, vals):
                if v > 0:
                    self.ax_dow.text(bar_r.get_x()+bar_r.get_width()/2,
                                      bar_r.get_height(),
                                      "{:.0f}".format(v),
                                      ha="center", va="bottom", fontsize=7)
            self.canvas_dow.draw_idle()
        except Exception as e:
            print("[DASH-DOW]", e)

