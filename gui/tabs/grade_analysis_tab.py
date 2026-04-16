# -*- coding: utf-8 -*-
"""
gui/tabs/grade_analysis_tab.py — Mixin لتبويب تحليل النتائج
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os, datetime, threading, webbrowser, sys

# ── تحذير: قد تحتاج لبعض التبعات من app_gui ──
from gui.lib_loader import HtmlFrame
from grade_analysis import (
    _ga_placeholder_html, _ga_build_html, _ga_build_print_html,
    _ga_export_word, _ga_open_header_editor, _ga_parse_file
)

class GradeAnalysisTabMixin:
    """Mixin: تبويب تحليل النتائج"""
    
    def _build_grade_analysis_tab(self):
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
