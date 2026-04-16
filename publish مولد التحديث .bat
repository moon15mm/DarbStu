@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ======================================================
echo           DarbStu - Publish Update Tool
echo ======================================================
echo.
python DarbPublish.py
if errorlevel 1 (
    echo.
    echo [ERROR] Something went wrong during the publish process.
)
echo.
pause
