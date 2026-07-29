@echo off
setlocal EnableDelayedExpansion
title USB Stream - Setup

:: ============================================================
::  USB Stream - One-click bootstrap
::
::  This is the ONLY file the client needs.
::  It downloads the latest code from GitHub first, then
::  installs all tools and starts the stream server.
::
::  No admin rights required.
::  Install location: %USERPROFILE%\usbstream-tools
:: ============================================================

if "%1"=="--child" goto :RUN
cmd /k ""%~f0" --child"
exit

:RUN
setlocal EnableDelayedExpansion
set "TOOLS_DIR=%USERPROFILE%\usbstream-tools"
set "REPO_DIR=%TOOLS_DIR%\usbstream"
set "ERRORS=0"

if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

:: Add all tool paths up front
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
call :SECTION "Downloading latest code from GitHub"
echo   Fetching https://github.com/sammysam254/usbstream ...
curl.exe -L --silent --show-error -o "%TEMP%\usbstream.zip" "https://github.com/sammysam254/usbstream/archive/refs/heads/main.zip"
if %errorlevel% neq 0 (
    call :ERR "Failed to download from GitHub. Check your internet connection."
    echo.
    echo  Press any key to exit...
    pause >nul
    exit
)
if exist "%REPO_DIR%" rmdir /s /q "%REPO_DIR%"
mkdir "%REPO_DIR%"
powershell -Command "Expand-Archive -Force '%TEMP%\usbstream.zip' '%TEMP%\usbstream_extract'" >nul 2>&1
robocopy "%TEMP%\usbstream_extract\usbstream-main" "%REPO_DIR%" /E /NFL /NDL /NJH /NJS >nul 2>&1
rmdir /s /q "%TEMP%\usbstream_extract" >nul 2>&1
del "%TEMP%\usbstream.zip" >nul 2>&1
call :OK "Code downloaded to %REPO_DIR%"

:: ── STEP 2: Python ───────────────────────────────────────────────────────────
call :SECTION "Python 3"
python --version >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    call :OK "Python !PY_VER! already installed"
    goto :PY_DONE
)
py --version >nul 2>&1
if %errorlevel%==0 ( call :OK "Python found via py launcher" & goto :PY_DONE )
call :WARN "Python not found. Downloading Python 3.11.9..."
set "PY_INSTALLER=%TEMP%\python_installer.exe"
curl.exe -L --progress-bar -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if %errorlevel% neq 0 ( call :ERR "Failed to download Python." & goto :PY_DONE )
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%PY_INSTALLER%" >nul 2>&1
for /f "usebackq tokens=2*" %%A in (
    `reg query "HKCU\Environment" /v PATH 2^>nul`
) do set "PATH=%%B;!PATH!"
call :OK "Python installed"
:PY_DONE

:: ── STEP 3: pip ──────────────────────────────────────────────────────────────
call :SECTION "pip"
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    python -m ensurepip --upgrade >nul 2>&1
    python -m pip install --upgrade pip --quiet >nul 2>&1
    call :OK "pip installed"
) else (
    call :OK "pip already available"
)

:: ── STEP 4: Python packages ──────────────────────────────────────────────────
call :SECTION "Python packages"
pip install websockets aiohttp --quiet >nul 2>&1
if %errorlevel% neq 0 (
    call :ERR "Failed to install Python packages"
) else (
    call :OK "websockets + aiohttp installed"
)

:: ── STEP 5: ADB ──────────────────────────────────────────────────────────────
call :SECTION "ADB (Android Debug Bridge)"
adb version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "ADB not found. Downloading..."
    set "ADB_ZIP=%TEMP%\platform-tools.zip"
    set "ADB_DIR=%TOOLS_DIR%\platform-tools"
    curl.exe -L --progress-bar -o "!ADB_ZIP!" "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    if !errorlevel! neq 0 ( call :ERR "Failed to download ADB." ) else (
        tar.exe -xf "!ADB_ZIP!" -C "%TOOLS_DIR%"
        del "!ADB_ZIP!" >nul 2>&1
        powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';!ADB_DIR!', 'User')"
        set "PATH=%PATH%;!ADB_DIR!"
        call :OK "ADB installed"
    )
) else (
    call :OK "ADB already installed"
)

:: ── STEP 6: scrcpy ───────────────────────────────────────────────────────────
call :SECTION "scrcpy"
scrcpy --version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "scrcpy not found. Downloading..."
    set "SCRCPY_ZIP=%TEMP%\scrcpy.zip"
    set "SCRCPY_DIR=%TOOLS_DIR%\scrcpy"
    for /f "usebackq delims=" %%T in (
        `powershell -Command "(Invoke-RestMethod 'https://api.github.com/repos/Genymobile/scrcpy/releases/latest').tag_name"`
    ) do set "SCRCPY_TAG=%%T"
    if not defined SCRCPY_TAG set "SCRCPY_TAG=v3.1"
    curl.exe -L --progress-bar -o "!SCRCPY_ZIP!" "https://github.com/Genymobile/scrcpy/releases/download/!SCRCPY_TAG!/scrcpy-win64-!SCRCPY_TAG!.zip"
    if !errorlevel! neq 0 ( call :ERR "Failed to download scrcpy." ) else (
        if exist "%TOOLS_DIR%\scrcpy_tmp" rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp"
        mkdir "%TOOLS_DIR%\scrcpy_tmp"
        tar.exe -xf "!SCRCPY_ZIP!" -C "%TOOLS_DIR%\scrcpy_tmp"
        del "!SCRCPY_ZIP!" >nul 2>&1
        if exist "!SCRCPY_DIR!" rmdir /s /q "!SCRCPY_DIR!"
        for /d %%d in ("%TOOLS_DIR%\scrcpy_tmp\*") do move "%%d" "!SCRCPY_DIR!" >nul 2>&1
        rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp" >nul 2>&1
        powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';!SCRCPY_DIR!', 'User')"
        set "PATH=%PATH%;!SCRCPY_DIR!"
        call :OK "scrcpy installed"
    )
) else (
    call :OK "scrcpy already installed"
)

:: ── STEP 7: FFmpeg ───────────────────────────────────────────────────────────
call :SECTION "FFmpeg"
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "FFmpeg not found. Downloading..."
    set "FF_ZIP=%TEMP%\ffmpeg.zip"
    set "FF_DIR=%TOOLS_DIR%\ffmpeg"
    set "FF_TMP=%TOOLS_DIR%\ffmpeg_tmp"
    curl.exe -L --progress-bar -o "!FF_ZIP!" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    if !errorlevel! neq 0 ( call :ERR "Failed to download FFmpeg." ) else (
        if exist "!FF_TMP!" rmdir /s /q "!FF_TMP!"
        mkdir "!FF_TMP!"
        tar.exe -xf "!FF_ZIP!" -C "!FF_TMP!"
        del "!FF_ZIP!" >nul 2>&1
        if exist "!FF_DIR!" rmdir /s /q "!FF_DIR!"
        for /d %%d in ("!FF_TMP!\*") do move "%%d" "!FF_DIR!" >nul 2>&1
        rmdir /s /q "!FF_TMP!" >nul 2>&1
        set "FF_BIN=!FF_DIR!\bin"
        powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';!FF_BIN!', 'User')"
        set "PATH=%PATH%;!FF_BIN!"
        call :OK "FFmpeg installed"
    )
) else (
    call :OK "FFmpeg already installed"
)

:: ── STEP 8: cloudflared ──────────────────────────────────────────────────────
call :SECTION "cloudflared (remote access tunnels)"
cloudflared --version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "cloudflared not found. Downloading..."
    set "CF_EXE=%TOOLS_DIR%\cloudflared.exe"
    curl.exe -L --progress-bar -o "!CF_EXE!" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if !errorlevel! neq 0 ( call :ERR "Failed to download cloudflared." ) else (
        powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%TOOLS_DIR%', 'User')"
        call :OK "cloudflared installed"
    )
) else (
    call :OK "cloudflared already installed"
)

:: ── STEP 9: ADB device check ─────────────────────────────────────────────────
call :SECTION "ADB device check"
adb version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "ADB not on PATH. Reconnect a terminal and retry."
) else (
    adb start-server >nul 2>&1
    call :OK "ADB server running"
    echo.
    echo  Connected devices:
    adb devices
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo  ==============================================
if %ERRORS% gtr 0 (
    echo   Setup finished with %ERRORS% error(s).
    echo   Fix the errors above and re-run this script.
    echo  ==============================================
    echo.
    pause
    exit
)

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
