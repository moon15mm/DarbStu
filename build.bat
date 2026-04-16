@echo off
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
echo       [OK] DarbStu.exe built successfully.

:: 5. Copy Whatsapp Server
echo [3/7] Copying whatsapp-server files...
if exist "my-whatsapp-server" (
    xcopy "my-whatsapp-server" "dist\DarbStu\my-whatsapp-server\" /E /I /Q /Y /EXCLUDE:build_exclude.txt
)

:: 6. Copy node.exe
echo [4/7] Copying node.exe...
set NODE_FOUND=0
for %%P in (
    "C:\Program Files\nodejs\node.exe"
    "C:\Program Files (x86)\nodejs\node.exe"
) do (
    if exist %%P (
        copy %%P "dist\DarbStu\node.exe" /Y >nul
        set NODE_FOUND=1
    )
)

:: 7. Copy cloudflared.exe
echo [5/7] Copying cloudflared.exe...
for %%P in (
    "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    "C:\Program Files\cloudflared\cloudflared.exe"
    "C:\Windows\System32\cloudflared.exe"
) do (
    if exist %%P (
        copy %%P "dist\DarbStu\cloudflared.exe" /Y >nul
    )
)

:: 8. Copy helper files
echo [6/7] Copying helper files (api, icons, version)...
if exist "api" xcopy "api" "dist\DarbStu\api\" /E /I /Q /Y >nul
copy "icon.ico" "dist\DarbStu\icon.ico" /Y >nul 2>&1
copy "version.json" "dist\DarbStu\version.json" /Y >nul 2>&1

if not exist "dist\DarbStu\data" mkdir "dist\DarbStu\data"
if not exist "dist\DarbStu\data\backups" mkdir "dist\DarbStu\data\backups"

if exist "data\message_template.txt" copy "data\message_template.txt" "dist\DarbStu\data\" /Y >nul
if exist "data\config.json" copy "data\config.json" "dist\DarbStu\data\" /Y >nul

:: 9. Build Installer (if Inno Setup exists)
echo [7/7] Checking for Inno Setup...
set INNO=""
for %%P in ("C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "C:\Program Files\Inno Setup 6\ISCC.exe") do (
    if exist %%P set INNO=%%P
)

if not %INNO%=="" (
    echo [INFO] Building Installer...
    %INNO% "installer.iss"
    echo       [OK] Setup file created in Output folder.
) else (
    echo [SKIP] Inno Setup not found. You can use dist\DarbStu folder directly.
)

echo.
echo ======================================================
echo              BUILD COMPLETE SUCCESSFUL
echo ======================================================
echo  Result: dist\DarbStu\DarbStu.exe
echo ======================================================
echo.
pause
