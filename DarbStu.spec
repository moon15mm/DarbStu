# -*- mode: python ; coding: utf-8 -*-
# ─── DarbStu.spec — PyInstaller Build Configuration ───────────────────────────
from PyInstaller.utils.hooks import collect_data_files, collect_all
import os

block_cipher = None

# ── جمع ملفات البيانات لكل مكتبة تحتاجها ─────────────────────────────────────
ttkthemes_datas       = collect_data_files('ttkthemes')
tkinterweb_datas      = collect_data_files('tkinterweb')
tkinterweb_tkhtml_datas = collect_data_files('tkinterweb_tkhtml')
arabic_reshaper_datas = collect_data_files('arabic_reshaper')
tkcalendar_datas      = collect_data_files('tkcalendar')

a = Analysis(
    ['DarbStu_v3.py'],
    pathex=['.'],
    binaries=[
        # مكتبة TkHTML الأصلية لـ tkinterweb
        (
            'C:/Users/maher/AppData/Local/Programs/Python/Python311/Lib/site-packages/tkinterweb_tkhtml/tkhtml/libTkhtml3.0.dll',
            'tkinterweb_tkhtml/tkhtml'
        ),
        # مكتبات Tcl/Tk الأساسية
        ('C:/Users/maher/AppData/Local/Programs/Python/Python311/DLLs/_tkinter.pyd', '.'),
        ('C:/Users/maher/AppData/Local/Programs/Python/Python311/DLLs/tcl86t.dll', '.'),
        ('C:/Users/maher/AppData/Local/Programs/Python/Python311/DLLs/tk86t.dll', '.'),
    ],
    datas=[
        ('icon.ico', '.'),
        # مجلدات Tcl/Tk
        ('C:/Users/maher/AppData/Local/Programs/Python/Python311/tcl/tcl8.6', 'tcl/tcl8.6'),
        ('C:/Users/maher/AppData/Local/Programs/Python/Python311/tcl/tk8.6',  'tcl/tk8.6'),
        *ttkthemes_datas,
        *tkinterweb_datas,
        *tkinterweb_tkhtml_datas,
        *arabic_reshaper_datas,
        *tkcalendar_datas,
    ],
    hiddenimports=[
        # ── Tkinter core ──────────────────────────────────────────
        '_tkinter', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
        'tkinter.filedialog', 'tkinter.simpledialog',
        'PIL._tkinter_finder',
        # ── FastAPI / Uvicorn / Starlette ──────────────────────────────
        'uvicorn', 'uvicorn.main', 'uvicorn.config',
        'uvicorn.loops', 'uvicorn.loops.asyncio',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'starlette', 'starlette.routing', 'starlette.responses',
        'starlette.requests', 'starlette.middleware',
        'fastapi', 'fastapi.routing', 'fastapi.responses',
        'anyio', 'anyio._backends', 'anyio._backends._asyncio',
        'anyio._backends._trio',
        'h11',
        # ── Email ──────────────────────────────────────────────────────
        'email.mime', 'email.mime.text', 'email.mime.multipart',
        # ── Data / Excel ───────────────────────────────────────────────
        'pandas', 'pandas.io.formats.excel',
        'openpyxl', 'openpyxl.styles', 'openpyxl.utils',
        'openpyxl.drawing', 'openpyxl.drawing.image',
        # ── Charts ────────────────────────────────────────────────────
        'matplotlib', 'matplotlib.pyplot',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        # ── Arabic text ────────────────────────────────────────────────
        'arabic_reshaper', 'bidi', 'bidi.algorithm',
        # ── UI ────────────────────────────────────────────────────────
        'ttkthemes', 'tkcalendar', 'tkinterweb', 'tkinterweb_tkhtml',
        # ── Images / PDF ───────────────────────────────────────────────
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw',
        'pdf2image',
        'fpdf', 'fpdf2',
        'reportlab', 'reportlab.pdfgen',
        'weasyprint',
        # ── QR / Requests ─────────────────────────────────────────────
        'qrcode', 'qrcode.image.pil',
        'requests', 'urllib3',
        # ── Misc ──────────────────────────────────────────────────────
        'pyngrok',
        'jinja2', 'jinja2.ext',
        'cryptography',
        'typing_extensions',
        'pkg_resources',
        'pkg_resources.py2_compat',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['test', 'tests', 'unittest', 'doctest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DarbStu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # بدون نافذة CMD
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DarbStu',
)
