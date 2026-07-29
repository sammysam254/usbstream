@echo off
setlocal EnableDelayedExpansion
title USB Stream - Auto Installer

:: ============================================================
::  USB Stream Auto Installer
::  NO admin rights required - installs to %USERPROFILE%\usbstream-tools
::  Uses curl.exe for fast downloads with progress bar
::  Checks: Python, pip, websockets, ADB, scrcpy, FFmpeg, cloudflared
:: ============================================================

if "%1"=="--child" goto :RUN
cmd /k ""%~f0" --child"
exit

:RUN
set "ERRORS=0"
set "TOOLS_DIR=%USERPROFILE%\usbstream-tools"
set "SCRIPT_DIR=%~dp0"

echo.
echo  ==============================================
echo   USB Stream - Auto Setup
echo   Install dir: %TOOLS_DIR%
echo  ==============================================
echo.

if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

set "PATH=%PATH%;%TOOLS_DIR%"
set "PATH=%PATH%;%TOOLS_DIR%\platform-tools"
set "PATH=%PATH%;%TOOLS_DIR%\scrcpy"
set "PATH=%PATH%;%TOOLS_DIR%\ffmpeg\bin"

:: ── 1. Python ────────────────────────────────────────────────────────────────
call :SECTION "Python 3"
python --version >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    call :OK "Python !PY_VER! already installed"
    goto :PY_DONE
)
py --version >nul 2>&1
if %errorlevel%==0 ( call :OK "Python found via py launcher" & goto :PY_DONE )
python3 --version >nul 2>&1
if %errorlevel%==0 ( call :OK "Python found as python3" & goto :PY_DONE )
call :INSTALL_PYTHON
:PY_DONE

:: ── 2. pip ───────────────────────────────────────────────────────────────────
call :SECTION "pip"
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "pip not found, bootstrapping..."
    python -m ensurepip --upgrade >nul 2>&1
    python -m pip install --upgrade pip --quiet >nul 2>&1
    call :OK "pip installed"
) else (
    call :OK "pip already available"
)

:: ── 3. Python packages ───────────────────────────────────────────────────────
call :SECTION "Python packages (websockets)"
if exist "%SCRIPT_DIR%requirements.txt" (
    pip install -r "%SCRIPT_DIR%requirements.txt" --quiet >nul 2>&1
    if !errorlevel! neq 0 (
        call :ERR "Failed to install Python packages"
    ) else (
        call :OK "Python packages installed"
    )
) else (
    pip install websockets --quiet >nul 2>&1
    call :OK "websockets installed"
)

:: ── 4. ADB ───────────────────────────────────────────────────────────────────
call :SECTION "ADB (Android Debug Bridge)"
adb version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_ADB
) else (
    call :OK "ADB already installed"
)

:: ── 5. scrcpy ────────────────────────────────────────────────────────────────
call :SECTION "scrcpy"
scrcpy --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_SCRCPY
) else (
    call :OK "scrcpy already installed"
)

:: ── 6. FFmpeg ────────────────────────────────────────────────────────────────
call :SECTION "FFmpeg"
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_FFMPEG
) else (
    call :OK "FFmpeg already installed"
)

:: ── 7. cloudflared ───────────────────────────────────────────────────────────
call :SECTION "cloudflared (remote access tunnels)"
cloudflared --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_CLOUDFLARED
) else (
    call :OK "cloudflared already installed"
)

:: ── 8. ADB device check ──────────────────────────────────────────────────────
call :SECTION "ADB device check"
adb version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "ADB still not on PATH - open a new terminal after setup."
) else (
    adb start-server >nul 2>&1
    call :OK "ADB server running"
    echo.
    echo  Connected devices:
    adb devices > "%TEMP%\usbstream_adb.txt" 2>&1
    type "%TEMP%\usbstream_adb.txt"
    del "%TEMP%\usbstream_adb.txt" >nul 2>&1
)

:: ── Summary + launch ─────────────────────────────────────────────────────────
echo.
echo  ==============================================
if %ERRORS% gtr 0 goto :SHOW_ERRORS
goto :START_SERVER

:SHOW_ERRORS
echo   Setup finished with %ERRORS% error(s).
echo   Fix the errors above and re-run install.bat
echo  ==============================================
echo.
echo  Press any key to close...
pause >nul
exit

:START_SERVER
echo   ALL DONE - Starting stream server...
echo  ==============================================
echo.

:: Write a small helper that starts the server and captures the tunnel URL
set "SERVER_LOG=%TEMP%\usbstream_server.log"
set "URL_FILE=%TEMP%\usbstream_url.txt"
if exist "%URL_FILE%" del "%URL_FILE%" >nul 2>&1
if exist "%SERVER_LOG%" del "%SERVER_LOG%" >nul 2>&1

:: Launch server in a new visible window, tee output to log file
start "USB Stream Server" cmd /k "cd /d "%SCRIPT_DIR%" && python server.py 2>&1 | tee "%SERVER_LOG%""

echo   Server window opened. Waiting for cloudflared tunnel URL...
echo   (this takes ~10 seconds)
echo.

:: Poll the log file for the trycloudflare URL - wait up to 30 seconds
set "TUNNEL_URL="
set /a WAIT=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
set /a WAIT+=2
:: Search log for trycloudflare.com URL
for /f "tokens=*" %%L in ('findstr /i "trycloudflare.com" "%SERVER_LOG%" 2^>nul') do (
    :: Extract just the https URL from the line
    for /f "tokens=1,2,3,4,5 delims= " %%a in ("%%L") do (
        if not "%%a"=="" echo %%a | findstr /i "https://" >nul 2>&1 && set "TUNNEL_URL=%%a"
        if not "%%b"=="" echo %%b | findstr /i "https://" >nul 2>&1 && set "TUNNEL_URL=%%b"
        if not "%%c"=="" echo %%c | findstr /i "https://" >nul 2>&1 && set "TUNNEL_URL=%%c"
        if not "%%d"=="" echo %%d | findstr /i "https://" >nul 2>&1 && set "TUNNEL_URL=%%d"
        if not "%%e"=="" echo %%e | findstr /i "https://" >nul 2>&1 && set "TUNNEL_URL=%%e"
    )
)
if defined TUNNEL_URL goto :GOT_URL
if %WAIT% lss 30 goto :WAIT_LOOP

:: Timeout — fall back to localhost
echo   [WARN] Tunnel URL not detected in 30s. Opening localhost viewer instead.
set "TUNNEL_URL=http://localhost:8080"

:GOT_URL
echo.
echo  ==============================================
echo   STREAM READY
echo.
echo   Remote access link:
echo   %TUNNEL_URL%
echo.
echo   Opening browser now...
echo  ==============================================
echo.

:: Open the tunnel URL in the default browser
start "" "%TUNNEL_URL%"

echo  Press any key to close this setup window (server keeps running).
pause >nul
exit


:: ════════════════════════════════════════════════════════════════
::  HELPERS
:: ════════════════════════════════════════════════════════════════

:SECTION
echo.
echo  -- %~1 --
exit /b 0

:OK
echo   [OK]   %~1
exit /b 0

:WARN
echo   [WARN] %~1
exit /b 0

:ERR
echo   [FAIL] %~1
set /a ERRORS+=1
exit /b 0


:: ── Python ───────────────────────────────────────────────────────────────────
:INSTALL_PYTHON
call :WARN "Python not found. Downloading Python 3.11 (curl)..."
set "PY_INSTALLER=%TEMP%\python_installer.exe"
curl.exe -L --progress-bar -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if %errorlevel% neq 0 (
    call :ERR "Failed to download Python. Get it from: https://python.org/downloads"
    exit /b 0
)
call :WARN "Running Python installer silently (per-user, no admin)..."
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%PY_INSTALLER%" >nul 2>&1
for /f "usebackq tokens=2*" %%A in (
    `reg query "HKCU\Environment" /v PATH 2^>nul`
) do set "PATH=%%B;!PATH!"
call :OK "Python installed (per-user)"
exit /b 0


:: ── ADB ──────────────────────────────────────────────────────────────────────
:INSTALL_ADB
call :WARN "ADB not found. Downloading platform-tools (curl)..."
set "ADB_ZIP=%TEMP%\platform-tools.zip"
set "ADB_DIR=%TOOLS_DIR%\platform-tools"
curl.exe -L --progress-bar -o "%ADB_ZIP%" "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
if %errorlevel% neq 0 ( call :ERR "Failed to download ADB." & exit /b 0 )
call :WARN "Extracting ADB..."
tar.exe -xf "%ADB_ZIP%" -C "%TOOLS_DIR%"
del "%ADB_ZIP%" >nul 2>&1
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%ADB_DIR%', 'User')"
set "PATH=%PATH%;%ADB_DIR%"
call :OK "ADB installed to %ADB_DIR%"
exit /b 0


:: ── scrcpy ───────────────────────────────────────────────────────────────────
:INSTALL_SCRCPY
call :WARN "scrcpy not found. Fetching latest release tag..."
set "SCRCPY_ZIP=%TEMP%\scrcpy.zip"
set "SCRCPY_DIR=%TOOLS_DIR%\scrcpy"
for /f "usebackq delims=" %%T in (
    `powershell -Command "(Invoke-RestMethod 'https://api.github.com/repos/Genymobile/scrcpy/releases/latest').tag_name"`
) do set "SCRCPY_TAG=%%T"
if not defined SCRCPY_TAG set "SCRCPY_TAG=v3.1"
call :WARN "Downloading scrcpy %SCRCPY_TAG% (curl)..."
curl.exe -L --progress-bar -o "%SCRCPY_ZIP%" "https://github.com/Genymobile/scrcpy/releases/download/%SCRCPY_TAG%/scrcpy-win64-%SCRCPY_TAG%.zip"
if %errorlevel% neq 0 ( call :ERR "Failed to download scrcpy." & exit /b 0 )
call :WARN "Extracting scrcpy..."
if exist "%TOOLS_DIR%\scrcpy_tmp" rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp"
mkdir "%TOOLS_DIR%\scrcpy_tmp"
tar.exe -xf "%SCRCPY_ZIP%" -C "%TOOLS_DIR%\scrcpy_tmp"
del "%SCRCPY_ZIP%" >nul 2>&1
if exist "%SCRCPY_DIR%" rmdir /s /q "%SCRCPY_DIR%"
for /d %%d in ("%TOOLS_DIR%\scrcpy_tmp\*") do move "%%d" "%SCRCPY_DIR%" >nul 2>&1
rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp" >nul 2>&1
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%SCRCPY_DIR%', 'User')"
set "PATH=%PATH%;%SCRCPY_DIR%"
call :OK "scrcpy installed to %SCRCPY_DIR%"
exit /b 0


:: ── FFmpeg ───────────────────────────────────────────────────────────────────
:INSTALL_FFMPEG
call :WARN "FFmpeg not found. Downloading essentials build (curl)..."
set "FF_ZIP=%TEMP%\ffmpeg.zip"
set "FF_DIR=%TOOLS_DIR%\ffmpeg"
set "FF_TMP=%TOOLS_DIR%\ffmpeg_tmp"
curl.exe -L --progress-bar -o "%FF_ZIP%" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if %errorlevel% neq 0 ( call :ERR "Failed to download FFmpeg." & exit /b 0 )
call :WARN "Extracting FFmpeg (tar - fast)..."
if exist "%FF_TMP%" rmdir /s /q "%FF_TMP%"
mkdir "%FF_TMP%"
tar.exe -xf "%FF_ZIP%" -C "%FF_TMP%"
del "%FF_ZIP%" >nul 2>&1
if exist "%FF_DIR%" rmdir /s /q "%FF_DIR%"
for /d %%d in ("%FF_TMP%\*") do move "%%d" "%FF_DIR%" >nul 2>&1
rmdir /s /q "%FF_TMP%" >nul 2>&1
set "FF_BIN=%FF_DIR%\bin"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%FF_BIN%', 'User')"
set "PATH=%PATH%;%FF_BIN%"
call :OK "FFmpeg installed to %FF_DIR%"
exit /b 0


:: ── cloudflared ──────────────────────────────────────────────────────────────
:INSTALL_CLOUDFLARED
call :WARN "cloudflared not found. Downloading (curl)..."
set "CF_EXE=%TOOLS_DIR%\cloudflared.exe"
curl.exe -L --progress-bar -o "%CF_EXE%" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
if %errorlevel% neq 0 ( call :ERR "Failed to download cloudflared." & exit /b 0 )
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%TOOLS_DIR%', 'User')"
set "PATH=%PATH%;%TOOLS_DIR%"
call :OK "cloudflared installed to %TOOLS_DIR%"
exit /b 0
