@echo off
chcp 65001 > nul
title Setup DarbStu Auto-Start

echo.
echo  ================================================
echo   Setup: DarbStu Auto-Start on Windows Startup
echo  ================================================
echo.

:: ── 1: تشغيل DarbStu عند بدء Windows (Startup folder) ──────────
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set DARB_PATH=%USERPROFILE%\Desktop\DarbStu\DarbStu.exe

if not exist "%DARB_PATH%" (
    if exist "%~dp0DarbStu.exe" set DARB_PATH=%~dp0DarbStu.exe
)

echo [1] Adding DarbStu to Windows Startup...
echo start "" "%DARB_PATH%" > "%STARTUP%\DarbStu_autostart.bat"
echo [OK] DarbStu will start automatically on Windows login

:: ── 2: اضافة Watchdog كـ Scheduled Task ──────────────────────────
echo.
echo [2] Setting up Watchdog as Scheduled Task...

set WATCHDOG=%~dp0darb_watchdog.bat
if not exist "%WATCHDOG%" (
    set WATCHDOG=%USERPROFILE%\Desktop\DarbStu\darb_watchdog.bat
)

:: احذف المهمة القديمة ان وجدت
schtasks /Delete /TN "DarbStu_Watchdog" /F > nul 2>&1

:: أضف مهمة جديدة - تشتغل كل 5 دقائق
schtasks /Create /TN "DarbStu_Watchdog" ^
  /TR "\"%WATCHDOG%\"" ^
  /SC MINUTE /MO 5 ^
  /ST 00:00 ^
  /RL HIGHEST ^
  /F > nul 2>&1

if errorlevel 1 (
    echo [!] Scheduled Task needs Admin rights
    echo     Right-click setup_autostart.bat and choose "Run as administrator"
) else (
    echo [OK] Watchdog scheduled every 5 minutes
)

:: ── 3: تشغيل DarbStu الان ────────────────────────────────────────
echo.
echo [3] Starting DarbStu now...
if exist "%DARB_PATH%" (
    taskkill /F /IM DarbStu.exe > nul 2>&1
    timeout /t 2 /nobreak > nul
    start "" "%DARB_PATH%"
    echo [OK] DarbStu started
)

echo.
echo  ================================================
echo   Done! Summary:
echo   - DarbStu starts automatically on Windows login
echo   - Watchdog checks every 5 min and auto-restarts
echo   - Log file: DarbStu folder\watchdog_log.txt
echo  ================================================
echo.
pause
