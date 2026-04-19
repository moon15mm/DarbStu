@echo off
title DarbStu Watchdog - Auto Restart
chcp 65001 > nul

:: ── اعدادات ──────────────────────────────────────────
set DARB_EXE=DarbStu.exe
set CHECK_INTERVAL=30
set RESTART_WAIT=20
set PORT=8000
set LOG=%~dp0watchdog_log.txt

echo [%date% %time%] Watchdog started >> "%LOG%"
echo.
echo  ============================================
echo   DarbStu Watchdog - يراقب ويعيد التشغيل
echo  ============================================
echo   يفحص كل %CHECK_INTERVAL% ثانية
echo   اغلق هذه النافذة لايقاف المراقبة
echo  ============================================
echo.

:LOOP
:: فحص المنفذ 8000
curl -s -o nul --max-time 3 http://127.0.0.1:%PORT%/ 2>nul
if errorlevel 1 (
    echo [%time%] Port %PORT% not responding...

    :: فحص هل DarbStu.exe يعمل
    tasklist /FI "IMAGENAME eq %DARB_EXE%" 2>nul | find /I "%DARB_EXE%" > nul
    if errorlevel 1 (
        echo [%time%] DarbStu.exe is DOWN - restarting...
        echo [%date% %time%] RESTART: DarbStu.exe was down >> "%LOG%"

        :: ابحث عن DarbStu.exe
        set DARB_PATH=
        if exist "%~dp0%DARB_EXE%"                          set DARB_PATH=%~dp0%DARB_EXE%
        if exist "%~dp0..\%DARB_EXE%"                      set DARB_PATH=%~dp0..\%DARB_EXE%
        if exist "%USERPROFILE%\Desktop\DarbStu\%DARB_EXE%" set DARB_PATH=%USERPROFILE%\Desktop\DarbStu\%DARB_EXE%

        if not "%DARB_PATH%"=="" (
            start "" "%DARB_PATH%"
            echo [%time%] Restarted: %DARB_PATH%
            echo [%date% %time%] Started: %DARB_PATH% >> "%LOG%"
            timeout /t %RESTART_WAIT% /nobreak > nul
        ) else (
            echo [%time%] ERROR: Cannot find DarbStu.exe
        )
    ) else (
        echo [%time%] DarbStu.exe is running but port %PORT% is dead - killing and restarting...
        echo [%date% %time%] RESTART: port dead, process alive >> "%LOG%"
        taskkill /F /IM %DARB_EXE% > nul 2>&1
        timeout /t 5 /nobreak > nul

        if not "%DARB_PATH%"=="" (
            start "" "%DARB_PATH%"
        ) else (
            if exist "%~dp0%DARB_EXE%"                          start "" "%~dp0%DARB_EXE%"
            if exist "%USERPROFILE%\Desktop\DarbStu\%DARB_EXE%" start "" "%USERPROFILE%\Desktop\DarbStu\%DARB_EXE%"
        )
        timeout /t %RESTART_WAIT% /nobreak > nul
    )
) else (
    echo [%time%] OK - DarbStu running on port %PORT%
)

timeout /t %CHECK_INTERVAL% /nobreak > nul
goto LOOP
