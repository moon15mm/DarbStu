# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import json
from constants import STUDENTS_JSON
from database import load_students

class ClassNamingTabMixin:
    """Mixin: ClassNamingTabMixin for managing school class names."""
    
    def _build_class_naming_tab(self):
        frame = self.class_naming_frame
        
        # Header
        hdr = tk.Frame(frame, bg="#E65100", height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🏫 إدارة وتسمية الفصول", 
                 bg="#E65100", fg="white", 
                 font=("Tahoma", 13, "bold")).pack(side="right", padx=16, pady=12)
        
        # Info label
        tk.Label(frame, 
                 text="هنا يمكنك تعديل أسماء الفصول (مثلاً تغيير 1/1 إلى 'أولى أول'). \nانقر نقراً مزدوجاً فوق اسم الفصل في العمود الأيمن للتعديل.",
                 font=("Tahoma", 10), fg="#444", justify="right").pack(anchor="e", padx=16, pady=10)
        
        # Main container for Treeview
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True, padx=16, pady=5)
        
        cols = ("id", "name", "student_count")
        self.tree_classes = ttk.Treeview(table_frame, columns=cols, show="headings", height=15)
        
        for col, header, width in zip(cols, ["معرّف الفصل (ID)", "اسم الفصل الحالي", "عدد الطلاب"], [150, 300, 150]):
            self.tree_classes.heading(col, text=header)
            self.tree_classes.column(col, width=width, anchor="center")
            
        self.tree_classes.pack(side="right", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree_classes.yview)
        self.tree_classes.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # Control buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", padx=16, pady=10)
        
        ttk.Button(btn_frame, text="💾 حفظ التعديلات", command=self._save_class_renames).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🔄 تحديث القائمة", command=self._refresh_class_list).pack(side="left", padx=5)
        
        # Binding
        self.tree_classes.bind("<Double-1>", self._on_class_name_double_click)
        
        self._refresh_class_list()

    def _refresh_class_list(self):
        """Loads or reloads classes from the store into the treeview."""
        if not hasattr(self, "tree_classes"): return
        
        for item in self.tree_classes.get_children():
            self.tree_classes.delete(item)
            
        # Ensure latest data
        self.store = load_students()
        
        for c in self.store["list"]:
            self.tree_classes.insert("", "end", values=(c["id"], c["name"], len(c["students"])))

    def _on_class_name_double_click(self, event):
        """Allows in-place editing of the class name cell."""
        region = self.tree_classes.identify("region", event.x, event.y)
        if region != "cell" or self.tree_classes.identify_column(event.x) != "#2":
            return
            
        item_id = self.tree_classes.focus()
        if not item_id: return
        
        current_values = list(self.tree_classes.item(item_id, "values"))
        
        # Create an entry widget for editing
        entry = ttk.Entry(self.tree_classes)
        entry.insert(0, current_values[1])
        entry.focus()
        
        bbox = self.tree_classes.bbox(item_id, column="#2")
        if not bbox: return
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        
        def save_edit(e=None):
            new_name = entry.get().strip()
            if new_name:
                current_values[1] = new_name
                self.tree_classes.item(item_id, values=current_values)
            entry.destroy()
            
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def _save_class_renames(self):
        """Persists all current treeview names back to STUDENTS_JSON."""
        changes = {}
        for item in self.tree_classes.get_children():
            vals = self.tree_classes.item(item, "values")
            changes[str(vals[0])] = str(vals[1])
            
        if not changes: return
        
        updated = False
        for c in self.store["list"]:
            cid = str(c["id"])
            if cid in changes and c["name"] != changes[cid]:
                c["name"] = changes[cid]
                updated = True
                
        if updated:
            try:
                with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                    json.dump({"classes": self.store["list"]}, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("نجاح", "تم حفظ أسماء الفصول الجديدة بنجاح.")
                # Force reload store and sync all tabs
                self.store = load_students(force_reload=True)
                if hasattr(self, "update_all_tabs_after_data_change"):
                    self.update_all_tabs_after_data_change()
            except Exception as e:
                messagebox.showerror("خطأ", f"تعذر حفظ التعديلات:\n{e}")
        else:
            messagebox.showinfo("تنبيه", "لم يتم اكتشاف أي تغييرات في الأسماء.")
