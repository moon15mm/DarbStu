@echo off
chcp 65001 > nul
title DarbStu - اداة الاصلاح
color 0A

echo.
echo  =========================================
echo    DarbStu - اداة الاصلاح التلقائي
echo  =========================================
echo.

set CHECK_URL=https://darbte.uk/web/dashboard
set PORT=8000
set FIXED=0

:: ── فحص الموقع ────────────────────────────────────────────────
:CHECK_SITE
echo [1] جاري فحص الموقع darbte.uk ...
curl -s -o nul -w "%%{http_code}" --max-time 8 --insecure %CHECK_URL% > "%TEMP%\darb_code.txt" 2>nul
set /p CODE=<"%TEMP%\darb_code.txt"
del "%TEMP%\darb_code.txt" 2>nul

if "%CODE%"=="200" goto :SITE_OK
if "%CODE%"=="302" goto :SITE_OK
if "%CODE%"=="301" goto :SITE_OK

echo [X] الموقع لا يستجيب (كود: %CODE%)
goto :CHECK_INTERNET

:SITE_OK
echo [OK] الموقع يعمل بشكل صحيح - لا يحتاج اصلاح!
echo.
echo اضغط اي زر للخروج...
pause > nul
exit /b 0

:: ── فحص الانترنت ──────────────────────────────────────────────
:CHECK_INTERNET
echo.
echo [2] فحص الاتصال بالانترنت...
ping -n 1 8.8.8.8 > nul 2>&1
if errorlevel 1 (
    echo [X] لا يوجد اتصال بالانترنت!
    echo     تاكد من الشبكة ثم اعد تشغيل هذا البرنامج.
    goto :END_FAIL
)
echo [OK] الانترنت يعمل

:: ── فحص السيرفر المحلي ────────────────────────────────────────
echo.
echo [3] فحص السيرفر المحلي...
curl -s -o nul --max-time 3 http://127.0.0.1:%PORT%/ 2>nul
if errorlevel 1 (
    echo [X] السيرفر المحلي لا يستجيب
    goto :FIX1
) else (
    echo [OK] السيرفر المحلي يعمل - المشكله في cloudflared
    goto :FIX2
)

:: ══════════════════════════════════════════════════════════════
:: الحل الاول: اعادة تشغيل DarbStu
:: ══════════════════════════════════════════════════════════════
:FIX1
echo.
echo ┌─ الحل 1: اعادة تشغيل DarbStu ─────────────────────────┐

tasklist /FI "IMAGENAME eq DarbStu.exe" 2>nul | find /I "DarbStu.exe" > nul
if not errorlevel 1 (
    echo  [+] ايقاف DarbStu...
    taskkill /F /IM DarbStu.exe > nul 2>&1
    timeout /t 3 /nobreak > nul
)

:: ابحث عن DarbStu.exe
set DARB_PATH=
if exist "%~dp0DarbStu.exe"        set DARB_PATH=%~dp0DarbStu.exe
if exist "%~dp0..\DarbStu.exe"     set DARB_PATH=%~dp0..\DarbStu.exe
if exist "%USERPROFILE%\Desktop\DarbStu\DarbStu.exe" set DARB_PATH=%USERPROFILE%\Desktop\DarbStu\DarbStu.exe

if "%DARB_PATH%"=="" (
    echo  [X] لم يُعثر على DarbStu.exe
    goto :FIX2
)

echo  [+] تشغيل: %DARB_PATH%
start "" "%DARB_PATH%"
echo  [+] انتظار 25 ثانية...
timeout /t 25 /nobreak > nul

goto :CHECK_AFTER_FIX1

:CHECK_AFTER_FIX1
curl -s -o nul -w "%%{http_code}" --max-time 8 --insecure %CHECK_URL% > "%TEMP%\darb_code.txt" 2>nul
set /p CODE=<"%TEMP%\darb_code.txt"
del "%TEMP%\darb_code.txt" 2>nul
if "%CODE%"=="200" ( echo └─ [OK] تم الاصلاح بالحل 1! & goto :END_OK )
if "%CODE%"=="302" ( echo └─ [OK] تم الاصلاح بالحل 1! & goto :END_OK )
echo └─ لم يُحل - جاري الانتقال للحل 2...

:: ══════════════════════════════════════════════════════════════
:: الحل الثاني: اعادة تشغيل cloudflared
:: ══════════════════════════════════════════════════════════════
:FIX2
echo.
echo ┌─ الحل 2: اعادة تشغيل cloudflared ─────────────────────┐

echo  [+] ايقاف cloudflared...
taskkill /F /IM cloudflared.exe > nul 2>&1
timeout /t 3 /nobreak > nul

:: ابحث عن cloudflared.exe
set CF_PATH=
if exist "%~dp0cloudflared.exe"    set CF_PATH=%~dp0cloudflared.exe
if exist "%~dp0..\cloudflared.exe" set CF_PATH=%~dp0..\cloudflared.exe
if exist "C:\Program Files\cloudflared\cloudflared.exe" set CF_PATH=C:\Program Files\cloudflared\cloudflared.exe
if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" set CF_PATH=C:\Program Files (x86)\cloudflared\cloudflared.exe

if "%CF_PATH%"=="" (
    echo  [X] لم يُعثر على cloudflared.exe
    goto :FIX3
)

echo  [+] تشغيل cloudflared: %CF_PATH%
start "" /B "%CF_PATH%" tunnel --url http://localhost:%PORT% --no-autoupdate
echo  [+] انتظار 25 ثانية...
timeout /t 25 /nobreak > nul

curl -s -o nul -w "%%{http_code}" --max-time 8 --insecure %CHECK_URL% > "%TEMP%\darb_code.txt" 2>nul
set /p CODE=<"%TEMP%\darb_code.txt"
del "%TEMP%\darb_code.txt" 2>nul
if "%CODE%"=="200" ( echo └─ [OK] تم الاصلاح بالحل 2! & goto :END_OK )
if "%CODE%"=="302" ( echo └─ [OK] تم الاصلاح بالحل 2! & goto :END_OK )
echo └─ لم يُحل - جاري الانتقال للحل 3...

:: ══════════════════════════════════════════════════════════════
:: الحل الثالث: اغلاق كامل واعادة تشغيل كل شيء
:: ══════════════════════════════════════════════════════════════
:FIX3
echo.
echo ┌─ الحل 3: اعادة تشغيل كامل ────────────────────────────┐

echo  [+] ايقاف كل العمليات...
taskkill /F /IM DarbStu.exe > nul 2>&1
taskkill /F /IM cloudflared.exe > nul 2>&1
timeout /t 5 /nobreak > nul

if not "%DARB_PATH%"=="" (
    echo  [+] تشغيل DarbStu من الصفر...
    start "" "%DARB_PATH%"
    echo  [+] انتظار 40 ثانية للتهيئة الكاملة...
    timeout /t 40 /nobreak > nul

    curl -s -o nul -w "%%{http_code}" --max-time 10 --insecure %CHECK_URL% > "%TEMP%\darb_code.txt" 2>nul
    set /p CODE=<"%TEMP%\darb_code.txt"
    del "%TEMP%\darb_code.txt" 2>nul
    if "%CODE%"=="200" ( echo └─ [OK] تم الاصلاح بالحل 3! & goto :END_OK )
    if "%CODE%"=="302" ( echo └─ [OK] تم الاصلاح بالحل 3! & goto :END_OK )
    echo └─ لم يُحل
)

:: ══════════════════════════════════════════════════════════════
:: الحل الرابع: مسح اعدادات cloudflared الفاسدة
:: ══════════════════════════════════════════════════════════════
:FIX4
echo.
echo ┌─ الحل 4: مسح اعدادات cloudflared الفاسدة ─────────────┐

if not "%CF_PATH%"=="" (
    "%CF_PATH%" --version > nul 2>&1
    if errorlevel 1 (
        echo  [X] ملف cloudflared.exe معطوب - سيتم التنزيل
        goto :FIX5
    )
    echo  [OK] ملف cloudflared.exe سليم - المشكله في الاعدادات
)

taskkill /F /IM cloudflared.exe > nul 2>&1
timeout /t 2 /nobreak > nul

if exist "%USERPROFILE%\.cloudflared" (
    rmdir /S /Q "%USERPROFILE%\.cloudflared" 2>nul
    echo  [OK] تم مسح الاعدادات القديمة
) else (
    echo  [!] لا يوجد مجلد اعدادات
)

if not "%CF_PATH%"=="" (
    echo  [+] تشغيل Quick Tunnel بدون اعداد...
    start "" /B "%CF_PATH%" tunnel --url http://localhost:%PORT% --no-autoupdate
    timeout /t 25 /nobreak > nul
    curl -s -o nul -w "%%{http_code}" --max-time 8 --insecure %CHECK_URL% > "%TEMP%\darb_code.txt" 2>nul
    set /p CODE=<"%TEMP%\darb_code.txt"
    del "%TEMP%\darb_code.txt" 2>nul
    if "%CODE%"=="200" ( echo └─ [OK] تم الاصلاح بالحل 4! & goto :END_OK )
    if "%CODE%"=="302" ( echo └─ [OK] تم الاصلاح بالحل 4! & goto :END_OK )
    echo └─ لم يُحل - جاري الانتقال للحل 5...
)

:: ══════════════════════════════════════════════════════════════
:: الحل الخامس: تنزيل cloudflared جديد
:: ══════════════════════════════════════════════════════════════
:FIX5
echo.
echo ┌─ الحل 5: تنزيل cloudflared.exe جديد ──────────────────┐

set CF_DL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
set CF_SAVE=%~dp0cloudflared.exe

echo  [+] جاري التنزيل من GitHub (قد يستغرق دقيقة)...
taskkill /F /IM cloudflared.exe > nul 2>&1
if exist "%CF_SAVE%" del /F "%CF_SAVE%" 2>nul

curl -L --insecure --max-time 120 -o "%CF_SAVE%" "%CF_DL%"
if not exist "%CF_SAVE%" (
    echo  [X] فشل التنزيل
    goto :END_FAIL
)

echo  [OK] تم تنزيل cloudflared الجديد
start "" /B "%CF_SAVE%" tunnel --url http://localhost:%PORT% --no-autoupdate
timeout /t 30 /nobreak > nul

curl -s -o nul -w "%%{http_code}" --max-time 8 --insecure %CHECK_URL% > "%TEMP%\darb_code.txt" 2>nul
set /p CODE=<"%TEMP%\darb_code.txt"
del "%TEMP%\darb_code.txt" 2>nul
if "%CODE%"=="200" ( echo └─ [OK] تم الاصلاح بالحل 5! & goto :END_OK )
if "%CODE%"=="302" ( echo └─ [OK] تم الاصلاح بالحل 5! & goto :END_OK )
echo └─ جميع الحلول استُنفدت

goto :END_FAIL

:: ══════════════════════════════════════════════════════════════
:END_OK
echo.
echo  =========================================
echo    تم الاصلاح بنجاح! الموقع يعمل الان
echo  =========================================
echo.
pause
exit /b 0

:END_FAIL
echo.
echo  =========================================
echo    [X] تعذر الاصلاح التلقائي
echo  =========================================
echo.
echo  الخطوات اليدوية:
echo  1. اغلق نافذة DarbStu
echo  2. افتح DarbStu مرة اخرى
echo  3. انتظر دقيقة ثم اعد فتح الموقع
echo.
pause
exit /b 1
