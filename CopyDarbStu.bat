@echo off
setlocal

set SOURCE=%~dp0
set DEST=%USERPROFILE%\Desktop\setupDarbStu

echo ================================
echo  DarbStu Setup - Copy Files
echo ================================
echo.

echo [1] Creating setupDarbStu folder...
if not exist "%DEST%" mkdir "%DEST%"
echo     Done.
echo.

echo [2] Copying DarbStu_v3.py...
if exist "%SOURCE%DarbStu_v3.py" (
    copy /y "%SOURCE%DarbStu_v3.py" "%DEST%\" >nul
    echo     Done.
) else (
    echo     WARNING: DarbStu_v3.py not found
)
echo.

echo [3] Copying data folder...
if exist "%SOURCE%data" (
    xcopy /e /i /y "%SOURCE%data" "%DEST%\data" >nul
    echo     Done.
) else (
    echo     WARNING: data folder not found
)
echo.

echo [4] Copying WhatsApp server...
if exist "%SOURCE%my-whatsapp-server" (
    mkdir "%DEST%\my-whatsapp-server" 2>nul
    if exist "%SOURCE%my-whatsapp-server\server.js" (
        copy /y "%SOURCE%my-whatsapp-server\server.js" "%DEST%\my-whatsapp-server\" >nul
        echo     server.js - Done
    )
    if exist "%SOURCE%my-whatsapp-server\package.json" (
        copy /y "%SOURCE%my-whatsapp-server\package.json" "%DEST%\my-whatsapp-server\" >nul
        echo     package.json - Done
    )
    if exist "%SOURCE%my-whatsapp-server\.wwebjs_auth" (
        xcopy /e /i /y "%SOURCE%my-whatsapp-server\.wwebjs_auth" "%DEST%\my-whatsapp-server\.wwebjs_auth" >nul
        echo     WhatsApp session - Done
    ) else (
        echo     WARNING: No WhatsApp session - QR scan needed on new PC
    )
) else (
    echo     WARNING: my-whatsapp-server not found
)
echo.

echo [5] Copying Cloudflare cert.pem...
if exist "%USERPROFILE%\.cloudflared\cert.pem" (
    mkdir "%DEST%\cloudflared" 2>nul
    copy /y "%USERPROFILE%\.cloudflared\cert.pem" "%DEST%\cloudflared\" >nul
    echo     cert.pem - Done
) else (
    echo     WARNING: cert.pem not found
)
echo.

echo [6] Copying license file...
if exist "%SOURCE%.darb_license" (
    copy /y "%SOURCE%.darb_license" "%DEST%\" >nul
    echo     .darb_license - Done
) else (
    echo     NOTE: No license - activation required on first run
)
echo.

echo [7] Creating run.bat...
(
echo @echo off
echo cd /d "%%~dp0"
echo start "WA" /min cmd /c "cd my-whatsapp-server ^&^& node server.js"
echo timeout /t 3 /nobreak ^>nul
echo start "DarbStu" py DarbStu_v3.py
) > "%DEST%\run.bat"
echo     Done.
echo.

echo [8] Creating install.bat...
(
echo @echo off
echo echo Installing Python requirements...
echo py -m pip install fastapi uvicorn requests pyjwt ttkthemes openpyxl pillow
echo echo.
echo echo Installing Node.js packages...
echo cd my-whatsapp-server
echo npm install
echo cd ..
echo echo.
echo echo Copying cert.pem...
echo if exist "cloudflared\cert.pem" ^(
echo     mkdir "%%USERPROFILE%%\.cloudflared" 2^>nul
echo     copy /y "cloudflared\cert.pem" "%%USERPROFILE%%\.cloudflared\" ^>nul
echo     echo cert.pem copied.
echo ^)
echo echo.
echo echo Adding to Windows startup...
echo copy /y "run.bat" "%%APPDATA%%\Microsoft\Windows\Start Menu\Programs\Startup\" ^>nul
echo echo All done - run run.bat to start DarbStu.
echo pause
) > "%DEST%\install.bat"
echo     Done.
echo.

echo ================================
echo  setupDarbStu ready on Desktop
echo ================================
echo.
echo Contents:
dir /b "%DEST%"
echo.
echo Next steps on new PC:
echo 1. Copy setupDarbStu to new PC
echo 2. Run install.bat as Administrator
echo 3. Run run.bat
echo.
pause
endlocal
