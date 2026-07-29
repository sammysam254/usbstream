@echo off
setlocal EnableDelayedExpansion
title USB Stream - Setup

if "%1"=="--child" goto :RUN
cmd /k ""%~f0" --child"
exit

:RUN
set "ERRORS=0"
set "TOOLS_DIR=%USERPROFILE%\usbstream-tools"
set "REPO_DIR=%TOOLS_DIR%\usbstream"

if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

set "PATH=%PATH%;%TOOLS_DIR%"
set "PATH=%PATH%;%TOOLS_DIR%\platform-tools"
set "PATH=%PATH%;%TOOLS_DIR%\scrcpy"
set "PATH=%PATH%;%TOOLS_DIR%\ffmpeg\bin"

echo.
echo  ==============================================
echo   USB Stream - Setup
echo   Install dir: %TOOLS_DIR%
echo  ==============================================
echo.

:: ── STEP 1: Download latest code from GitHub ─────────────────────────────────
echo  -- Downloading latest code from GitHub --
echo   Fetching https://github.com/sammysam254/usbstream ...
curl.exe -L --silent --show-error -o "%TEMP%\usbstream.zip" "https://github.com/sammysam254/usbstream/archive/refs/heads/main.zip"
if %errorlevel% neq 0 goto :ERR_DOWNLOAD

if exist "%REPO_DIR%" rmdir /s /q "%REPO_DIR%"
mkdir "%REPO_DIR%"
powershell -Command "Expand-Archive -Force '%TEMP%\usbstream.zip' '%TEMP%\usbstream_ex'" >nul 2>&1
robocopy "%TEMP%\usbstream_ex\usbstream-main" "%REPO_DIR%" /E /NFL /NDL /NJH /NJS >nul 2>&1
rmdir /s /q "%TEMP%\usbstream_ex" >nul 2>&1
del "%TEMP%\usbstream.zip" >nul 2>&1
echo   [OK]   Code ready at %REPO_DIR%
goto :STEP2

:ERR_DOWNLOAD
echo   [FAIL] Could not download from GitHub - check internet connection.
pause
exit

:: ── STEP 2: Python ───────────────────────────────────────────────────────────
:STEP2
echo.
echo  -- Python 3 --
python --version >nul 2>&1
if %errorlevel%==0 goto :PY_OK
py --version >nul 2>&1
if %errorlevel%==0 goto :PY_OK
goto :PY_INSTALL

:PY_OK
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do echo   [OK]   Python %%v already installed
goto :STEP3

:PY_INSTALL
echo   [WARN] Python not found. Downloading Python 3.11.9...
curl.exe -L --progress-bar -o "%TEMP%\py_setup.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if %errorlevel% neq 0 ( echo   [FAIL] Python download failed. & set /a ERRORS+=1 & goto :STEP3 )
"%TEMP%\py_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%TEMP%\py_setup.exe" >nul 2>&1
for /f "usebackq tokens=2*" %%A in (`reg query "HKCU\Environment" /v PATH 2^>nul`) do set "PATH=%%B;!PATH!"
echo   [OK]   Python installed

:: ── STEP 3: pip + packages ───────────────────────────────────────────────────
:STEP3
echo.
echo  -- Python packages --
pip install websockets aiohttp --quiet >nul 2>&1
if %errorlevel% neq 0 ( echo   [FAIL] pip install failed. & set /a ERRORS+=1 ) else ( echo   [OK]   websockets + aiohttp ready )

:: ── STEP 4: ADB ──────────────────────────────────────────────────────────────
:STEP4
echo.
echo  -- ADB --
adb version >nul 2>&1
if %errorlevel%==0 goto :ADB_OK
echo   [WARN] ADB not found. Downloading...
curl.exe -L --progress-bar -o "%TEMP%\pt.zip" "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
if %errorlevel% neq 0 ( echo   [FAIL] ADB download failed. & set /a ERRORS+=1 & goto :STEP5 )
tar.exe -xf "%TEMP%\pt.zip" -C "%TOOLS_DIR%" >nul 2>&1
del "%TEMP%\pt.zip" >nul 2>&1
set "PATH=%PATH%;%TOOLS_DIR%\platform-tools"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH',[Environment]::GetEnvironmentVariable('PATH','User')+';%TOOLS_DIR%\platform-tools','User')" >nul 2>&1
echo   [OK]   ADB installed
goto :STEP5

:ADB_OK
echo   [OK]   ADB already installed

:: ── STEP 5: scrcpy ───────────────────────────────────────────────────────────
:STEP5
echo.
echo  -- scrcpy --
scrcpy --version >nul 2>&1
if %errorlevel%==0 goto :SCRCPY_OK
echo   [WARN] scrcpy not found. Downloading...
set "SCRCPY_TAG=v3.1"
for /f "usebackq delims=" %%T in (`powershell -Command "(Invoke-RestMethod 'https://api.github.com/repos/Genymobile/scrcpy/releases/latest').tag_name" 2^>nul`) do set "SCRCPY_TAG=%%T"
curl.exe -L --progress-bar -o "%TEMP%\scrcpy.zip" "https://github.com/Genymobile/scrcpy/releases/download/%SCRCPY_TAG%/scrcpy-win64-%SCRCPY_TAG%.zip"
if %errorlevel% neq 0 ( echo   [FAIL] scrcpy download failed. & set /a ERRORS+=1 & goto :STEP6 )
if exist "%TOOLS_DIR%\scrcpy_tmp" rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp"
mkdir "%TOOLS_DIR%\scrcpy_tmp"
tar.exe -xf "%TEMP%\scrcpy.zip" -C "%TOOLS_DIR%\scrcpy_tmp" >nul 2>&1
del "%TEMP%\scrcpy.zip" >nul 2>&1
if exist "%TOOLS_DIR%\scrcpy" rmdir /s /q "%TOOLS_DIR%\scrcpy"
for /d %%d in ("%TOOLS_DIR%\scrcpy_tmp\*") do move "%%d" "%TOOLS_DIR%\scrcpy" >nul 2>&1
rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp" >nul 2>&1
set "PATH=%PATH%;%TOOLS_DIR%\scrcpy"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH',[Environment]::GetEnvironmentVariable('PATH','User')+';%TOOLS_DIR%\scrcpy','User')" >nul 2>&1
echo   [OK]   scrcpy installed
goto :STEP6

:SCRCPY_OK
echo   [OK]   scrcpy already installed

:: ── STEP 6: FFmpeg ───────────────────────────────────────────────────────────
:STEP6
echo.
echo  -- FFmpeg --
ffmpeg -version >nul 2>&1
if %errorlevel%==0 goto :FF_OK
echo   [WARN] FFmpeg not found. Downloading...
curl.exe -L --progress-bar -o "%TEMP%\ffmpeg.zip" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if %errorlevel% neq 0 ( echo   [FAIL] FFmpeg download failed. & set /a ERRORS+=1 & goto :STEP7 )
if exist "%TOOLS_DIR%\ffmpeg_tmp" rmdir /s /q "%TOOLS_DIR%\ffmpeg_tmp"
mkdir "%TOOLS_DIR%\ffmpeg_tmp"
tar.exe -xf "%TEMP%\ffmpeg.zip" -C "%TOOLS_DIR%\ffmpeg_tmp" >nul 2>&1
del "%TEMP%\ffmpeg.zip" >nul 2>&1
if exist "%TOOLS_DIR%\ffmpeg" rmdir /s /q "%TOOLS_DIR%\ffmpeg"
for /d %%d in ("%TOOLS_DIR%\ffmpeg_tmp\*") do move "%%d" "%TOOLS_DIR%\ffmpeg" >nul 2>&1
rmdir /s /q "%TOOLS_DIR%\ffmpeg_tmp" >nul 2>&1
set "PATH=%PATH%;%TOOLS_DIR%\ffmpeg\bin"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH',[Environment]::GetEnvironmentVariable('PATH','User')+';%TOOLS_DIR%\ffmpeg\bin','User')" >nul 2>&1
echo   [OK]   FFmpeg installed
goto :STEP7

:FF_OK
echo   [OK]   FFmpeg already installed

:: ── STEP 7: cloudflared ──────────────────────────────────────────────────────
:STEP7
echo.
echo  -- cloudflared --
cloudflared --version >nul 2>&1
if %errorlevel%==0 goto :CF_OK
echo   [WARN] cloudflared not found. Downloading...
curl.exe -L --progress-bar -o "%TOOLS_DIR%\cloudflared.exe" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
if %errorlevel% neq 0 ( echo   [FAIL] cloudflared download failed. & set /a ERRORS+=1 & goto :STEP8 )
powershell -Command "[Environment]::SetEnvironmentVariable('PATH',[Environment]::GetEnvironmentVariable('PATH','User')+';%TOOLS_DIR%','User')" >nul 2>&1
echo   [OK]   cloudflared installed
goto :STEP8

:CF_OK
echo   [OK]   cloudflared already installed

:: ── STEP 8: ADB device check ─────────────────────────────────────────────────
:STEP8
echo.
echo  -- ADB device check --
adb version >nul 2>&1
if %errorlevel% neq 0 goto :NO_ADB
adb start-server >nul 2>&1
echo   [OK]   ADB server running
echo.
echo  Connected devices:
adb devices
goto :LAUNCH

:NO_ADB
echo   [WARN] ADB not on PATH yet - reconnect a terminal and retry.

:: ── Launch ────────────────────────────────────────────────────────────────────
:LAUNCH
echo.
echo  ==============================================
if %ERRORS% gtr 0 goto :SHOW_ERRORS
echo   ALL DONE - Starting stream server...
echo  ==============================================
echo.
echo   The cloudflared tunnel URL will appear below.
echo   Open that URL in your browser to view the stream.
echo.
echo   Press Ctrl+C to stop.
echo  ==============================================
echo.
timeout /t 2 /nobreak >nul
cd /d "%REPO_DIR%"
python server.py
goto :EOF

:SHOW_ERRORS
echo   Setup finished with %ERRORS% error(s).
echo   Fix the errors above and re-run this script.
echo  ==============================================
echo.
pause
