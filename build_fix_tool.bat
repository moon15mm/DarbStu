@echo off
chcp 65001 > nul
echo ===================================
echo  بناء DarbFix.exe - اداة الاصلاح
echo ===================================
echo.

pyinstaller --onefile --noconsole --name DarbFix --icon=icon.ico darb_fix.py

echo.
if exist "dist\DarbFix.exe" (
    echo [OK] تم البناء: dist\DarbFix.exe
    copy "dist\DarbFix.exe" "DarbFix.exe" > nul
    echo [OK] تم النسخ بجانب DarbStu.exe
) else (
    echo [خطأ] فشل البناء
)
pause
