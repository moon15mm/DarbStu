# -*- coding: utf-8 -*-
"""
debug_grades.py — أداة تشخيص إحداثيات أعمدة نور PDF
الاستخدام: python debug_grades.py <path_to_pdf>
"""
import sys, re

try:
    import pdfplumber
except ImportError:
    print("❌ pdfplumber غير مثبّت"); sys.exit(1)

_NOOR_ROW_TOPS = [256, 273, 290, 307, 324, 341, 358, 375, 392]

def debug_pdf(filepath):
    def is_num(s):
        try:
            v = float(str(s).strip())
            return 0 < v <= 200
        except:
            return False

    with pdfplumber.open(filepath) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()  # بدون char_dir='rtl'

        print(f"\n{'='*60}")
        print(f"ملف: {filepath}")
        print(f"عدد الصفحات: {len(pdf.pages)}")
        print(f"{'='*60}\n")

        print("── أرقام في صفوف المواد المتوقعة ──")
        for y_exp in _NOOR_ROW_TOPS:
            row_nums = sorted([
                (w['x0'], float(w['text']))
                for w in words
                if not w['text'].startswith('(cid:')
                and is_num(w['text'])
                and abs(round(w['top']) - y_exp) <= 2
            ])
            if row_nums:
                vals_str = "  |  ".join(f"x={x:.1f} → {v}" for x, v in row_nums)
                print(f"  y≈{y_exp}: {vals_str}")

        print("\n── جميع الأرقام في الصفحة الأولى (x < 150) ──")
        left_nums = sorted([
            (round(w['top']), w['x0'], float(w['text']))
            for w in words
            if not w['text'].startswith('(cid:')
            and is_num(w['text'])
            and w['x0'] < 150
        ])
        for top, x0, val in left_nums:
            mx_mark  = " ← النهاية" if 20 < x0 < 50 else ""
            sc_mark  = " ← المجموع" if 50 < x0 < 90 else ""
            print(f"  top={top:4d}  x0={x0:6.1f}  val={val}{mx_mark}{sc_mark}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("الاستخدام: python debug_grades.py path_to_noor.pdf")
    else:
        debug_pdf(sys.argv[1])
