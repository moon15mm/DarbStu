@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title DarbStu Build Tool

echo.
echo ======================================================
echo           DarbStu - Preparation and Build
echo ======================================================
echo.

cd /d "%~dp0"

:: 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11.
    pause & exit /b 1
)

:: 2. Check PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INSTALL] Installing PyInstaller...
    pip install pyinstaller --quiet
)

:: 3. Clean previous build
echo [1/7] Cleaning previous build folders...
if exist "dist\DarbStu" rmdir /s /q "dist\DarbStu"
if exist "build"        rmdir /s /q "build"

:: 4. Build EXE
echo [2/7] Building DarbStu.exe... (Please wait 2-5 minutes)
pyinstaller DarbStu.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    pause & exit /b 1
)
echo [OK] DarbStu.exe built successfully.

:: 5. Copy Whatsapp Server
echo [3/7] Copying whatsapp-server files...
if exist "my-whatsapp-server" (
    xcopy "my-whatsapp-server" "dist\DarbStu\my-whatsapp-server\" /E /I /Q /Y /EXCLUDE:build_exclude.txt
)

:: 6. Copy node.exe and cloudflared.exe
echo [4/7] Copying external binaries...
for %%P in (
    "C:\Program Files\nodejs\node.exe"
    "C:\Program Files (x86)\nodejs\node.exe"
    "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    "C:\Program Files\cloudflared\cloudflared.exe"
    "C:\Windows\System32\cloudflared.exe"
) do (
    if exist %%P (
        if "%%~nxP"=="node.exe" copy %%P "dist\DarbStu\node.exe" /Y >nul
        if "%%~nxP"=="cloudflared.exe" copy %%P "dist\DarbStu\cloudflared.exe" /Y >nul
    )
)

:: 7. Copy helper files
echo [5/7] Copying helper files...
if exist "api" xcopy "api" "dist\DarbStu\api\" /E /I /Q /Y >nul
copy "icon.ico" "dist\DarbStu\icon.ico" /Y >nul 2>&1
copy "version.json" "dist\DarbStu\version.json" /Y >nul 2>&1

:: 8. Prepare data folder
echo [6/7] Preparing data folders...
if not exist "dist\DarbStu\data" mkdir "dist\DarbStu\data"
if not exist "dist\DarbStu\data\backups" mkdir "dist\DarbStu\data\backups"
if exist "data\message_template.txt" copy "data\message_template.txt" "dist\DarbStu\data\" /Y >nul

set "BUNDLE_CFG=n"
if exist "data\config.json" (
    echo.
    echo -------------------------------------------------------------
    echo [WAIT] Do you want to bundle your local config.json? (y/n)
    echo (Choose 'n' for a clean setup for others)
    set /p "BUNDLE_CFG=Selection: "
)

if /i "!BUNDLE_CFG!"=="y" (
    copy "data\config.json" "dist\DarbStu\data\" /Y >nul
    echo [OK] config.json bundled.
) else (
    echo [SKIP] Clean setup.
)

:: 9. Build Installer (if Inno Setup exists)
echo [7/7] Checking for Inno Setup...
set "INNO_PATH="
for %%P in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist "%%~P" set "INNO_PATH=%%~P"
)

if not "!INNO_PATH!"=="" (
    echo [INFO] Building Installer...
    "!INNO_PATH!" "installer.iss"
    echo [OK] Setup file created in Output folder.
) else (
    echo [SKIP] Inno Setup not found.
)

echo.
echo ======================================================
echo              BUILD COMPLETE SUCCESSFUL
echo ======================================================
echo  Result: dist\DarbStu\DarbStu.exe
echo ======================================================
echo.
pause
