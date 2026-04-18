# -*- mode: python ; coding: utf-8 -*-
# ─── DarbStu.spec — PyInstaller Build Configuration ───────────────────────────
from PyInstaller.utils.hooks import collect_data_files, collect_all
import sys, os

block_cipher = None

# ── مسار Python الحالي (يعمل على أي جهاز) ────────────────────────────────────
PY = sys.prefix          # مثال: C:\Python311
DLL_DIR  = os.path.join(PY, 'DLLs')
TCL_DIR  = os.path.join(PY, 'tcl')

# ── مسار tkinterweb_tkhtml (يُبحث عنه تلقائياً) ──────────────────────────────
try:
    import tkinterweb_tkhtml
    _twt_base = os.path.dirname(tkinterweb_tkhtml.__file__)
    _tkhtml_dll = os.path.join(_twt_base, 'tkhtml', 'libTkhtml3.0.dll')
    tkhtml_bin = [(_tkhtml_dll, 'tkinterweb_tkhtml/tkhtml')] if os.path.exists(_tkhtml_dll) else []
except ImportError:
    tkhtml_bin = []

# ── جمع ملفات البيانات ────────────────────────────────────────────────────────
ttkthemes_datas       = collect_data_files('ttkthemes')
tkinterweb_datas      = collect_data_files('tkinterweb')
arabic_reshaper_datas = collect_data_files('arabic_reshaper')
tkcalendar_datas      = collect_data_files('tkcalendar')
try:
    matplotlib_datas, matplotlib_bins, matplotlib_hidden = collect_all('matplotlib')
except Exception:
    matplotlib_datas = []; matplotlib_bins = []; matplotlib_hidden = []

try:
    numpy_datas, numpy_bins, numpy_hidden = collect_all('numpy')
except Exception:
    numpy_datas = []; numpy_bins = []; numpy_hidden = []

try:
    tkinterweb_tkhtml_datas = collect_data_files('tkinterweb_tkhtml')
except Exception:
    tkinterweb_tkhtml_datas = []

# ── تحديد مسارات DLL الأساسية لـ Tcl/Tk ─────────────────────────────────────
tk_bins = []
for dll in ['_tkinter.pyd', 'tcl86t.dll', 'tk86t.dll']:
    p = os.path.join(DLL_DIR, dll)
    if os.path.exists(p):
        tk_bins.append((p, '.'))

# ── بيانات Tcl/Tk ─────────────────────────────────────────────────────────────
tk_datas = []
for d in ['tcl8.6', 'tk8.6']:
    p = os.path.join(TCL_DIR, d)
    if os.path.exists(p):
        tk_datas.append((p, f'tcl/{d}'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=tk_bins + tkhtml_bin + matplotlib_bins + numpy_bins,
    datas=[
        ('icon.ico', '.'),
        ('api', 'api'),
        *tk_datas,
        *ttkthemes_datas,
        *matplotlib_datas,
        *numpy_datas,
        *tkinterweb_datas,
        *tkinterweb_tkhtml_datas,
        *arabic_reshaper_datas,
        *tkcalendar_datas,
    ],
    hiddenimports=[
        # ── Tkinter ───────────────────────────────────────────────
        '_tkinter', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
        'tkinter.filedialog', 'tkinter.simpledialog',
        'PIL._tkinter_finder',
        # ── FastAPI / Uvicorn ─────────────────────────────────────
        'uvicorn', 'uvicorn.main', 'uvicorn.config', 'uvicorn.server',
        'uvicorn.loops', 'uvicorn.loops.asyncio', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
        'uvicorn.middleware', 'uvicorn.middleware.proxy_headers',
        'uvicorn.middleware.message_logger',
        'uvicorn._types', 'uvicorn.importer', 'uvicorn.logging',
        'starlette', 'starlette.routing', 'starlette.responses',
        'starlette.requests', 'starlette.middleware',
        'starlette.middleware.cors', 'starlette.middleware.base',
        'starlette.staticfiles', 'starlette.exceptions',
        'starlette.background', 'starlette.concurrency',
        'fastapi', 'fastapi.routing', 'fastapi.responses', 'multipart',
        'fastapi.middleware', 'fastapi.middleware.cors',
        'fastapi.security', 'fastapi.staticfiles',
        'anyio', 'anyio._backends', 'anyio._backends._asyncio',
        'anyio._backends._trio', 'anyio.from_thread',
        'h11', 'h11._connection', 'h11._events',
        'multiprocessing', 'multiprocessing.popen_spawn_win32',
        # ── Cloud & Security ─────────────────────────────────────
        'secrets', 'cryptography', 'cryptography.hazmat.backends.openssl',
        'requests', 'urllib3', 'cloudflare_tunnel',
        # ── Email ─────────────────────────────────────────────────
        'email.mime', 'email.mime.text', 'email.mime.multipart',
        # ── Excel / Data ──────────────────────────────────────────
        'pandas', 'pandas.io.formats.excel',
        'openpyxl', 'openpyxl.styles', 'openpyxl.utils',
        'openpyxl.drawing', 'openpyxl.drawing.image',
        # ── Charts ────────────────────────────────────────────────
        'matplotlib', 'matplotlib.pyplot',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        # ── Arabic ────────────────────────────────────────────────
        'arabic_reshaper', 'bidi', 'bidi.algorithm',
        # ── UI ────────────────────────────────────────────────────
        'ttkthemes', 'tkcalendar', 'tkinterweb', 'tkinterweb_tkhtml',
        # ── Images / PDF ──────────────────────────────────────────
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw',
        'reportlab', 'reportlab.pdfgen', 'reportlab.lib',
        'reportlab.platypus', 'qrcode', 'qrcode.image.pil',
        'fpdf2',
        # ── Misc ──────────────────────────────────────────────────
        'jinja2', 'jinja2.ext',
        'typing_extensions',
        'pkg_resources',
        'sqlite3',
        'zipfile', 'hashlib', 'hmac',
        *matplotlib_hidden,
        *numpy_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['test', 'tests', 'unittest', 'doctest', 'pyngrok', 'playwright'],
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
    console=False,
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
