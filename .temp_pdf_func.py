def generate_academic_inquiry_pdf(inq_data: dict) -> bytes:
    """وينشئ ملف PDF لخطاب الاستفسار الأكاديمي والرد عليه (إذا وجد)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                    Spacer, Table, TableStyle, HRFlowable)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    import io as _io

    # ── تسجيل خط يدعم العربية ──
    _font_name = "Helvetica"
    _font_bold = "Helvetica-Bold"
    _font_candidates = [
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\times.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for _fp in _font_candidates:
        if os.path.exists(_fp):
            try:
                if "DarbFont" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("DarbFont", _fp))
                _font_name = "DarbFont"
                _font_bold = "DarbFont"
                break
            except Exception: pass

    try:
        import arabic_reshaper as _reshaper
        from bidi.algorithm import get_display as _bidi_display
        def _ar(txt):
            if not txt: return ""
            txt = str(txt)
            try: return _bidi_display(_reshaper.reshape(txt))
            except Exception: return txt
    except ImportError:
        def _ar(txt): return str(txt) if txt else ""

    from config_manager import load_config
    import os
    cfg = load_config()
    school = cfg.get("school_name", "المدرسة")
    
    buf = _io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm, title="خطاب استفسار أكاديمي"
    )

    PURPLE = colors.HexColor("#4c1d95")
    BLUE   = colors.HexColor("#1d4ed8")
    LBLUE  = colors.HexColor("#ede9fe")
    GRAY   = colors.HexColor("#6b7280")
    DARK   = colors.HexColor("#1f2937")
    WHITE  = colors.white

    st_school = ParagraphStyle("school", fontName=_font_bold, fontSize=15, alignment=TA_CENTER, textColor=PURPLE, spaceAfter=2)
    st_main   = ParagraphStyle("main", fontName=_font_bold, fontSize=13, alignment=TA_CENTER, textColor=BLUE, spaceAfter=4)
    st_label  = ParagraphStyle("label", fontName=_font_bold, fontSize=11, alignment=TA_RIGHT, textColor=PURPLE, spaceBefore=8, spaceAfter=2)
    st_note   = ParagraphStyle("note", fontName=_font_name, fontSize=10, alignment=TA_RIGHT, textColor=GRAY, leading=16, spaceAfter=4)

    elems = []
    elems.append(Paragraph(_ar("المملكة العربية السعودية"), st_note))
    elems.append(Paragraph(_ar("وزارة التعليم"), st_note))
    elems.append(Spacer(1, 0.2*cm))
    elems.append(Paragraph(_ar(school), st_school))
    elems.append(Paragraph(_ar("خطاب استفسار عن مستوى طالب"), st_main))
    elems.append(HRFlowable(width="100%", thickness=2, color=PURPLE, spaceAfter=10))

    info1 = [
        [_ar(inq_data.get("teacher_name", "")), _ar("المكرم المعلم:")],
        [_ar(inq_data.get("inquiry_date", "")), _ar("تاريخ الخطاب:")],
        [_ar(inq_data.get("subject", "")), _ar("المادة:")],
        [_ar(inq_data.get("student_name", "")), _ar("الطالب:")],
        [_ar(inq_data.get("class_name", "")), _ar("الفصل:")],
    ]
    tbl = Table(info1, colWidths=[12*cm, 4.5*cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0,0),(-1,-1), _font_name),
        ("FONTNAME", (1,0),(1,-1),  _font_bold),
        ("FONTSIZE", (0,0),(-1,-1), 10),
        ("ALIGN",    (0,0),(-1,-1), "RIGHT"),
        ("TEXTCOLOR", (1,0),(1,-1), PURPLE),
        ("TEXTCOLOR", (0,0),(0,-1), DARK),
        ("BACKGROUND", (1,0),(1,-1), LBLUE),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [colors.HexColor("#faf5ff"), WHITE]),
        ("GRID", (0,0),(-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 8),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 0.5*cm))

    # Counselor text
    elems.append(Paragraph(_ar("السلام عليكم ورحمة الله وبركاته،\nنأمل منكم التكرم بإفادتنا بمبررات وأسباب تدني مستوى الطالب المذكور أعلاه في مادتكم، والإجراءات التي اتخذتموها لمعالجة ذلك، وإرفاق ما يثبت ذلك من شواهد إن وجدت."), ParagraphStyle('tx', fontName=_font_name, fontSize=11, alignment=TA_RIGHT, leading=18)))
    elems.append(Spacer(1, 0.5*cm))

    if inq_data.get("status") != "جديد":
        elems.append(Paragraph(_ar("رد المعلم (المبررات والإجراءات المتخذة):"), st_label))
        elems.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#c4b5fd"), spaceAfter=4))
        elems.append(Paragraph(_ar(inq_data.get("reasons", "")), ParagraphStyle('tx2', fontName=_font_name, fontSize=11, alignment=TA_RIGHT, leading=18)))
        elems.append(Spacer(1, 0.5*cm))
        
        elems.append(Paragraph(_ar("الشواهد النصية:"), st_label))
        elems.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#c4b5fd"), spaceAfter=4))
        elems.append(Paragraph(_ar(inq_data.get("evidence_text", "")), ParagraphStyle('tx2', fontName=_font_name, fontSize=11, alignment=TA_RIGHT, leading=18)))
        elems.append(Spacer(1, 0.8*cm))
        
        if inq_data.get("evidence_file"):
            elems.append(Paragraph(_ar("مرفق مع الرد صور/ملفات محفوظة في النظام."), st_note))

    elems.append(Spacer(1, 1.5*cm))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceAfter=8))

    sig_counselor = _ar("الموجه الطلابي") + "\n" + _ar(inq_data.get("counselor_name", ""))
    sig_teacher = _ar("المعلم") + "\n" + _ar(inq_data.get("teacher_name", ""))
    sig_tbl = Table([[sig_counselor, sig_teacher]], colWidths=[8.25*cm, 8.25*cm])
    sig_tbl.setStyle(TableStyle([
        ("FONTNAME", (0,0),(-1,-1), _font_bold),
        ("FONTSIZE", (0,0),(-1,-1), 10),
        ("ALIGN", (0,0),(-1,-1), "CENTER"),
        ("TEXTCOLOR", (0,0),(-1,-1), DARK),
        ("TOPPADDING", (0,0),(-1,-1), 8),
    ]))
    elems.append(sig_tbl)

    doc.build(elems)
    return buf.getvalue()
