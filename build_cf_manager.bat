@echo off
chcp 65001 > nul
title Build CFManager.exe

pyinstaller --version > nul 2>&1
if errorlevel 1 pip install pyinstaller

if exist "icon.ico" (
    pyinstaller --onefile --noconsole --name CFManager --icon=icon.ico cf_manager.py
) else (
    pyinstaller --onefile --noconsole --name CFManager cf_manager.py
)

if exist "dist\CFManager.exe" (
    copy /Y "dist\CFManager.exe" "CFManager.exe" > nul
    echo [OK] CFManager.exe ready
) else (
    echo [ERROR] Build failed
)
pause
