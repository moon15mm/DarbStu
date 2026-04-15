@echo off
chcp 65001 >nul
title DarbStu — Build

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║          DarbStu — بناء نسخة التنصيب               ║
echo ╚══════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: ─── 1. التحقق من Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [خطأ] Python غير مثبت. الرجاء تثبيت Python 3.11 أولاً.
    pause & exit /b 1
)

:: ─── 2. التحقق من PyInstaller ────────────────────────────────────────────────
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [تثبيت] تثبيت PyInstaller...
    pip install pyinstaller --quiet
)

:: ─── 3. تنظيف البناء السابق ──────────────────────────────────────────────────
echo [1/7] تنظيف البناء السابق...
if exist "dist\DarbStu" rmdir /s /q "dist\DarbStu"
if exist "build"        rmdir /s /q "build"

:: ─── 4. بناء الـ EXE ─────────────────────────────────────────────────────────
echo [2/7] بناء DarbStu.exe ... (قد يأخذ 2-5 دقائق)
pyinstaller DarbStu.spec --noconfirm
if errorlevel 1 (
    echo [خطأ] فشل PyInstaller. راجع الأخطاء أعلاه.
    pause & exit /b 1
)
echo       ✓ تم بناء DarbStu.exe

:: ─── 5. نسخ ملفات واتساب سيرفر ──────────────────────────────────────────────
echo [3/7] نسخ ملفات واتساب سيرفر...
if exist "my-whatsapp-server" (
    xcopy "my-whatsapp-server" "dist\DarbStu\my-whatsapp-server\" /E /I /Q /Y /EXCLUDE:build_exclude.txt
    echo       ✓ تم نسخ my-whatsapp-server
) else (
    echo       [تحذير] مجلد my-whatsapp-server غير موجود
)

:: ─── 6. نسخ node.exe ─────────────────────────────────────────────────────────
echo [4/7] نسخ node.exe...
set NODE_FOUND=0
for %%P in (
    "C:\Program Files\nodejs\node.exe"
    "C:\Program Files (x86)\nodejs\node.exe"
) do (
    if exist %%P (
        copy %%P "dist\DarbStu\node.exe" /Y >nul
        echo       ✓ تم نسخ node.exe من %%P
        set NODE_FOUND=1
        goto :node_done
    )
)
:node_done
if "%NODE_FOUND%"=="0" (
    echo       [تحذير] لم يتم العثور على node.exe
    echo       الرجاء نسخ node.exe يدوياً إلى dist\DarbStu\
)

:: ─── 7. نسخ cloudflared.exe ──────────────────────────────────────────────────
echo [5/7] نسخ cloudflared.exe...
set CF_FOUND=0
for %%P in (
    "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    "C:\Program Files\cloudflared\cloudflared.exe"
    "C:\Windows\System32\cloudflared.exe"
) do (
    if exist %%P (
        copy %%P "dist\DarbStu\cloudflared.exe" /Y >nul
        echo       ✓ تم نسخ cloudflared.exe من %%P
        set CF_FOUND=1
        goto :cf_done
    )
)
:cf_done
if "%CF_FOUND%"=="0" (
    echo       [تحذير] cloudflared.exe غير موجود على هذا الجهاز
    echo       حمّله من: https://github.com/cloudflare/cloudflared/releases
    echo       ثم ضعه في dist\DarbStu\cloudflared.exe
)

:: ─── 8. نسخ الملفات المساعدة ─────────────────────────────────────────────────
echo [6/7] نسخ الملفات المساعدة (api, icons, version)...
if exist "api" (
    xcopy "api" "dist\DarbStu\api\" /E /I /Q /Y >nul
    echo       ✓ تم نسخ مجلد api
)
copy "icon.ico" "dist\DarbStu\icon.ico" /Y >nul 2>&1
copy "version.json" "dist\DarbStu\version.json" /Y >nul 2>&1

:: إنشاء مجلد data الافتراضي مع القوالب
if not exist "dist\DarbStu\data" mkdir "dist\DarbStu\data"
if not exist "dist\DarbStu\data\backups" mkdir "dist\DarbStu\data\backups"
if not exist "dist\DarbStu\data\backups\terms" mkdir "dist\DarbStu\data\backups\terms"

:: نسخ القوالب الافتراضية إن وجدت
if exist "data\message_template.txt" (
    copy "data\message_template.txt" "dist\DarbStu\data\message_template.txt" /Y >nul
)
if exist "data\config.json" (
    copy "data\config.json" "dist\DarbStu\data\config.json" /Y >nul
)

echo       ✓ تم إعداد كافة الملفات المساعدة

:: ─── 9. بناء الإنستولر ───────────────────────────────────────────────────────
echo [7/7] بناء الإنستولر...
set INNO=""
for %%P in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist %%P set INNO=%%P
)

if not %INNO%=="" (
    %INNO% "installer.iss"
    if errorlevel 1 (
        echo [تحذير] فشل بناء الإنستولر. يمكنك استخدام dist\DarbStu مباشرة.
    ) else (
        echo       ✓ تم إنشاء ملف الإنستولر في مجلد Output\
    )
) else (
    echo       [تحذير] Inno Setup غير مثبت.
    echo       يمكن تنزيله من: https://jrsoftware.org/isdl.php
    echo       أو استخدام مجلد dist\DarbStu\ مباشرة.
)

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║                   اكتمل البناء ✓                   ║
echo ║                                                      ║
echo ║  النتيجة: dist\DarbStu\DarbStu.exe                 ║
echo ║  الإنستولر (إن وُجد): Output\DarbStu_Setup.exe     ║
echo ╚══════════════════════════════════════════════════════╝
echo.
pause
