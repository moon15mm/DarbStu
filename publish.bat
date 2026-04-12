@echo off
chcp 65001 >nul
title DarbStu — نشر تحديث جديد

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║           DarbStu — نشر تحديث على GitHub           ║
echo ╚══════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: ─── التحقق من git ────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    echo [خطأ] git غير مثبت!
    pause & exit /b 1
)

:: ─── التحقق من المستودع ──────────────────────────────────
if not exist ".git" (
    echo [إعداد] تهيئة مستودع git لأول مرة...
    git init
    git remote add origin https://github.com/moon15mm/DarbStu.git
    git branch -M main
    echo.
    echo [تنبيه] سيتم رفع الكود لأول مرة — تأكد من اتصالك بالإنترنت
    echo.
)

:: ─── اقرأ الإصدار الحالي ─────────────────────────────────
for /f "tokens=*" %%v in ('python -c "from constants import APP_VERSION; print(APP_VERSION)"') do (
    set CURRENT_VER=%%v
)
echo الإصدار الحالي: %CURRENT_VER%
echo.

:: ─── اطلب رقم الإصدار الجديد ────────────────────────────
set /p NEW_VER="أدخل رقم الإصدار الجديد (مثال: 2.6.2): "
if "%NEW_VER%"=="" (
    echo [خطأ] يجب إدخال رقم الإصدار
    pause & exit /b 1
)

:: ─── اطلب ملاحظات التحديث ───────────────────────────────
set /p NOTES="أدخل ملاحظات التحديث (مثال: إصلاح عرض الأعذار): "
if "%NOTES%"=="" set NOTES=تحسينات وإصلاح أخطاء

:: ─── تحديث الملفات ───────────────────────────────────────
echo.
echo [1/4] تحديث رقم الإصدار في constants.py و version.json...
python -c "
import re, json, sys

new_ver  = sys.argv[1]
notes    = sys.argv[2]

# constants.py
with open('constants.py', 'r', encoding='utf-8') as f:
    txt = f.read()
txt = re.sub(r\"APP_VERSION\s*=\s*'[^']+'\", f\"APP_VERSION         = '{new_ver}'\", txt)
with open('constants.py', 'w', encoding='utf-8') as f:
    f.write(txt)

# version.json
import datetime
data = {
    'version': new_ver,
    'notes': notes,
    'download_url': 'https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip',
    'release_date': datetime.date.today().isoformat()
}
with open('version.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('OK')
" "%NEW_VER%" "%NOTES%"

if errorlevel 1 (
    echo [خطأ] فشل تحديث الملفات
    pause & exit /b 1
)
echo       ✓ تم تحديث constants.py و version.json

:: ─── إضافة الملفات لـ git ─────────────────────────────────
echo [2/4] إضافة الملفات المعدّلة...
git add -A
if errorlevel 1 (
    echo [خطأ] فشل git add
    pause & exit /b 1
)
echo       ✓ تم

:: ─── Commit ───────────────────────────────────────────────
echo [3/4] حفظ التغييرات (commit)...
git commit -m "release v%NEW_VER%: %NOTES%"
if errorlevel 1 (
    echo [تحذير] لا توجد تغييرات جديدة أو فشل الـ commit
    echo         تحقق من إعداد git (git config user.email / user.name)
    pause & exit /b 1
)
echo       ✓ تم

:: ─── Push ────────────────────────────────────────────────
echo [4/4] رفع التغييرات على GitHub...
git push -u origin main
if errorlevel 1 (
    echo.
    echo [تحذير] فشل الرفع. تحقق من:
    echo   1. اتصالك بالإنترنت
    echo   2. صلاحياتك على المستودع moon15mm/DarbStu
    echo   3. إعداد GitHub token إذا كنت تستخدم HTTPS
    pause & exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║        ✅ تم نشر الإصدار %NEW_VER% بنجاح!          ║
echo ║                                                      ║
echo ║  سيتلقى المستخدمون إشعار التحديث عند تشغيل         ║
echo ║  البرنامج تلقائياً.                                 ║
echo ╚══════════════════════════════════════════════════════╝
echo.
pause
