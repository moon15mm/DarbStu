@echo off
chcp 65001 > nul
title Build DarbFix.exe

echo.
echo ===================================
echo   Building DarbFix.exe
echo ===================================
echo.

:: Check pyinstaller
pyinstaller --version > nul 2>&1
if errorlevel 1 (
    echo [!] pyinstaller not found - installing...
    pip install pyinstaller
)

:: Build command - with icon if exists, without if not
if exist "icon.ico" (
    echo [+] Building with icon...
    pyinstaller --onefile --noconsole --name DarbFix --icon=icon.ico darb_fix.py
) else (
    echo [+] Building without icon...
    pyinstaller --onefile --noconsole --name DarbFix darb_fix.py
)

echo.
if exist "dist\DarbFix.exe" (
    echo [OK] Build successful: dist\DarbFix.exe
    copy /Y "dist\DarbFix.exe" "DarbFix.exe" > nul
    echo [OK] Copied to: DarbFix.exe
) else (
    echo [ERROR] Build failed - check output above
)

echo.
pause
