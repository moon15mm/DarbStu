@echo off
title DarbStu Aggressive Cleanup
echo [DarbStu] Searching for running instances...

:: 1. Try to kill by Port 59124 (The primary lock)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :59124') do (
    echo [DarbStu] Found port lock on PID %%a. Killing...
    taskkill /F /PID %%a 2>nul
)

:: 2. Search for any python process running 'main.py' specifically
echo [DarbStu] Searching for Python processes running main.py...
for /f "tokens=2 delims==" %%a in ('wmic process where "commandline like '%%main.py%%'" get processid /value 2^>nul') do (
    if not "%%a"=="" (
        echo [DarbStu] Found main.py process PID: %%a. Killing...
        taskkill /F /PID %%a 2>nul
    )
)

:: 3. Kill any DarbStu executable
taskkill /F /IM DarbStu.exe /T 2>nul

echo.
echo [DarbStu] Done. If the program still says it's running, please restart your computer or check the Task Manager for any 'python.exe' processes.
pause
