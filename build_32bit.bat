@echo off
chcp 65001 > nul
title Build DarbStu 32-bit
cd /d "%~dp0"

set PY32=C:\Python310_32\python.exe
set VENV=%~dp0venv32
set OUT=%~dp0dist32

if not exist "%PY32%" (
    echo ERROR: Python 32-bit not found at %PY32%
    pause
    exit /b 1
)

echo [1] Creating virtual environment...
if exist "%VENV%" rmdir /s /q "%VENV%"
"%PY32%" -m venv "%VENV%"

echo [2] Upgrading pip...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [2b] Installing packages (prefer binary wheels)...
"%VENV%\Scripts\pip.exe" install --prefer-binary fastapi uvicorn starlette ttkthemes tkcalendar pillow qrcode pandas openpyxl requests PyJWT python-multipart arabic-reshaper python-bidi matplotlib pyinstaller pyngrok fpdf2 reportlab cryptography python-dateutil tzlocal tabulate --quiet

echo [3] Building EXE...
if exist "%OUT%" rmdir /s /q "%OUT%"
if exist "%~dp0build32" rmdir /s /q "%~dp0build32"

"%VENV%\Scripts\pyinstaller.exe" --onefile --noconsole --name DarbStu_32bit --distpath "%OUT%" --workpath "%~dp0build32" --specpath "%~dp0build32" main.py

if exist "%OUT%\DarbStu_32bit.exe" (
    echo SUCCESS: dist32\DarbStu_32bit.exe is ready
) else (
    echo ERROR: Build failed
)
pause
