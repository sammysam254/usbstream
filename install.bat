@echo off
setlocal EnableDelayedExpansion
title USB Stream - Auto Installer

:: ============================================================
::  USB Stream Auto Installer
::  Checks and installs: Python, pip packages, ADB, scrcpy, FFmpeg
::  Run as Administrator for best results
:: ============================================================

set "ERRORS=0"
set "INSTALLED=0"

:: Color codes via ANSI (requires Windows 10+)
echo.
echo  ==============================================
echo   USB Stream - Auto Setup
echo  ==============================================
echo.

:: ── 1. Check for winget ──────────────────────────────────────────────────────
call :CHECK_WINGET
if "%WINGET_OK%"=="0" (
    echo [WARN] winget not found. Some packages will need manual install.
    echo        Get it from: https://aka.ms/getwinget
    echo.
)

:: ── 2. Python ────────────────────────────────────────────────────────────────
call :SECTION "Python 3.11+"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_PYTHON
) else (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    call :OK "Python !PY_VER! already installed"
)

:: ── 3. pip ───────────────────────────────────────────────────────────────────
call :SECTION "pip"
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "pip not found, bootstrapping..."
    python -m ensurepip --upgrade
    python -m pip install --upgrade pip >nul 2>&1
    call :OK "pip installed"
) else (
    call :OK "pip already available"
)

:: ── 4. Python packages (requirements.txt) ────────────────────────────────────
call :SECTION "Python packages (websockets)"
if exist "%~dp0requirements.txt" (
    pip install -r "%~dp0requirements.txt" --quiet
    if !errorlevel! neq 0 (
        call :ERR "Failed to install Python packages"
    ) else (
        call :OK "Python packages installed"
    )
) else (
    call :WARN "requirements.txt not found, installing websockets manually"
    pip install websockets --quiet
    call :OK "websockets installed"
)

:: ── 5. ADB ───────────────────────────────────────────────────────────────────
call :SECTION "ADB (Android Debug Bridge)"
adb version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_ADB
) else (
    for /f "tokens=1,2,3 delims= " %%a in ('adb version 2^>^&1 ^| findstr /i "version"') do (
        call :OK "ADB already installed - %%a %%b %%c"
    )
)

:: ── 6. scrcpy ────────────────────────────────────────────────────────────────
call :SECTION "scrcpy"
scrcpy --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_SCRCPY
) else (
    for /f "tokens=2 delims= " %%v in ('scrcpy --version 2^>^&1 ^| findstr /i "scrcpy"') do (
        call :OK "scrcpy %%v already installed"
    )
)

:: ── 7. FFmpeg ────────────────────────────────────────────────────────────────
call :SECTION "FFmpeg"
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_FFMPEG
) else (
    for /f "tokens=3 delims= " %%v in ('ffmpeg -version 2^>^&1 ^| findstr /i "ffmpeg version"') do (
        call :OK "FFmpeg %%v already installed"
    )
)

:: ── 8. cloudflared ───────────────────────────────────────────────────────────
call :SECTION "cloudflared (remote access tunnels)"
cloudflared --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_CLOUDFLARED
) else (
    for /f "tokens=3 delims= " %%v in ('cloudflared --version 2^>^&1') do (
        call :OK "cloudflared %%v already installed"
    )
)

:: ── 9. Verify ADB detects devices ───────────────────────────────────────────
call :SECTION "ADB device check"
adb devices >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "ADB not responding. Try reconnecting device."
) else (
    adb start-server >nul 2>&1
    call :OK "ADB server running"

    echo.
    echo  Connected devices:
    adb devices -l
)

:: ── Summary ──────────────────────────────────────────────────────────────────
echo.
echo  ==============================================
if %ERRORS%==0 (
    echo   ALL DONE - Setup complete!
    echo.
    echo   To start streaming:
    echo     1. Connect Android device via USB
    echo     2. Enable USB Debugging on device
    echo     3. Run:  python server.py
    echo     4. The remote access link will be printed in the console.
    echo     5. Share that URL to view the stream from anywhere.
    echo.
    echo   Local-only mode (no tunnel):
    echo     python server.py --no-tunnel
    echo     Then open: http://localhost:8080
) else (
    echo   Setup finished with %ERRORS% error(s).
    echo   Check the messages above and resolve manually.
)
echo  ==============================================
echo.
pause
exit /b 0


:: ════════════════════════════════════════════════════════════════
::  SUBROUTINES
:: ════════════════════════════════════════════════════════════════

:SECTION
echo.
echo  ── %~1 ──
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


:: ── winget check ─────────────────────────────────────────────────────────────
:CHECK_WINGET
set "WINGET_OK=0"
winget --version >nul 2>&1
if %errorlevel%==0 set "WINGET_OK=1"
exit /b 0


:: ── Install Python via winget ─────────────────────────────────────────────────
:INSTALL_PYTHON
if "%WINGET_OK%"=="1" (
    call :WARN "Python not found. Installing via winget..."
    winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        call :ERR "Python install failed. Get it from https://python.org/downloads"
    ) else (
        :: Refresh PATH for this session
        for /f "usebackq tokens=2*" %%A in (
            `reg query "HKCU\Environment" /v PATH 2^>nul`
        ) do set "PATH=%%B;!PATH!"
        call :OK "Python installed"
    )
) else (
    call :ERR "Python not found and winget unavailable."
    echo         Download Python manually: https://python.org/downloads
    echo         Make sure to tick 'Add Python to PATH' during install.
)
exit /b 0


:: ── Install ADB ──────────────────────────────────────────────────────────────
:INSTALL_ADB
if "%WINGET_OK%"=="1" (
    call :WARN "ADB not found. Installing Android Platform Tools via winget..."
    winget install --id Google.PlatformTools --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        call :INSTALL_ADB_MANUAL
    ) else (
        :: Refresh PATH
        for /f "usebackq tokens=2*" %%A in (
            `reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul`
        ) do set "PATH=%%B;!PATH!"
        call :OK "ADB installed via winget"
    )
) else (
    call :INSTALL_ADB_MANUAL
)
exit /b 0

:INSTALL_ADB_MANUAL
:: Fallback: download platform-tools zip directly
call :WARN "Downloading ADB platform-tools manually..."
set "ADB_ZIP=%TEMP%\platform-tools.zip"
set "ADB_DIR=%ProgramFiles%\platform-tools"
powershell -Command "Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile '%ADB_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download ADB. Get it from: https://developer.android.com/tools/releases/platform-tools"
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%ADB_ZIP%' -DestinationPath '%ProgramFiles%' -Force"
del "%ADB_ZIP%" >nul 2>&1
:: Add to user PATH
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%ADB_DIR%', 'User')"
set "PATH=%PATH%;%ADB_DIR%"
call :OK "ADB installed to %ADB_DIR% — PATH updated"
exit /b 0


:: ── Install scrcpy ───────────────────────────────────────────────────────────
:INSTALL_SCRCPY
if "%WINGET_OK%"=="1" (
    call :WARN "scrcpy not found. Installing via winget..."
    winget install --id Genymobile.scrcpy --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        call :INSTALL_SCRCPY_MANUAL
    ) else (
        call :OK "scrcpy installed via winget"
    )
) else (
    call :INSTALL_SCRCPY_MANUAL
)
exit /b 0

:INSTALL_SCRCPY_MANUAL
call :WARN "Downloading scrcpy manually..."
set "SCRCPY_ZIP=%TEMP%\scrcpy.zip"
set "SCRCPY_DIR=%ProgramFiles%\scrcpy"
:: Get latest release zip (v3.1 as of build date — update version as needed)
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/Genymobile/scrcpy/releases/download/v3.1/scrcpy-win64-v3.1.zip' -OutFile '%SCRCPY_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download scrcpy. Get it from: https://github.com/Genymobile/scrcpy/releases"
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%SCRCPY_ZIP%' -DestinationPath '%ProgramFiles%\scrcpy' -Force"
del "%SCRCPY_ZIP%" >nul 2>&1
:: scrcpy extracts into a subfolder — find it
for /d %%d in ("%ProgramFiles%\scrcpy\*") do set "SCRCPY_BIN=%%d"
if not defined SCRCPY_BIN set "SCRCPY_BIN=%ProgramFiles%\scrcpy"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%SCRCPY_BIN%', 'User')"
set "PATH=%PATH%;%SCRCPY_BIN%"
call :OK "scrcpy installed — PATH updated"
exit /b 0


:: ── Install FFmpeg ───────────────────────────────────────────────────────────
:INSTALL_FFMPEG
if "%WINGET_OK%"=="1" (
    call :WARN "FFmpeg not found. Installing via winget..."
    winget install --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        call :INSTALL_FFMPEG_MANUAL
    ) else (
        call :OK "FFmpeg installed via winget"
    )
) else (
    call :INSTALL_FFMPEG_MANUAL
)
exit /b 0

:INSTALL_FFMPEG_MANUAL
call :WARN "Downloading FFmpeg manually (essentials build)..."
set "FF_ZIP=%TEMP%\ffmpeg.zip"
set "FF_DIR=%ProgramFiles%\ffmpeg"
powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%FF_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download FFmpeg. Get it from: https://ffmpeg.org/download.html"
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%FF_ZIP%' -DestinationPath '%ProgramFiles%\ffmpeg' -Force"
del "%FF_ZIP%" >nul 2>&1
:: FFmpeg extracts into a versioned subfolder — grab the bin path
for /d %%d in ("%ProgramFiles%\ffmpeg\*") do set "FF_BIN=%%d\bin"
if not defined FF_BIN set "FF_BIN=%ProgramFiles%\ffmpeg\bin"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%FF_BIN%', 'User')"
set "PATH=%PATH%;%FF_BIN%"
call :OK "FFmpeg installed — PATH updated"
exit /b 0


:: ── Install cloudflared ──────────────────────────────────────────────────────
:INSTALL_CLOUDFLARED
if "%WINGET_OK%"=="1" (
    call :WARN "cloudflared not found. Installing via winget..."
    winget install --id Cloudflare.cloudflared --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        call :INSTALL_CLOUDFLARED_MANUAL
    ) else (
        :: Refresh system PATH so cloudflared is immediately usable
        for /f "usebackq tokens=2*" %%A in (
            `reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul`
        ) do set "PATH=%%B;!PATH!"
        call :OK "cloudflared installed via winget"
    )
) else (
    call :INSTALL_CLOUDFLARED_MANUAL
)
exit /b 0

:INSTALL_CLOUDFLARED_MANUAL
:: Download the official Windows AMD64 binary directly from Cloudflare
call :WARN "Downloading cloudflared binary manually..."
set "CF_DIR=%ProgramFiles%\cloudflared"
set "CF_EXE=%CF_DIR%\cloudflared.exe"

if not exist "%CF_DIR%" (
    powershell -Command "New-Item -ItemType Directory -Path '%CF_DIR%' -Force" >nul
)

powershell -Command ^
    "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CF_EXE%' -UseBasicParsing"

if %errorlevel% neq 0 (
    call :ERR "Failed to download cloudflared."
    echo         Get it manually from: https://github.com/cloudflare/cloudflared/releases
    exit /b 1
)

:: Add to user PATH permanently
powershell -Command ^
    "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%CF_DIR%', 'User')"
set "PATH=%PATH%;%CF_DIR%"

call :OK "cloudflared installed to %CF_DIR% — PATH updated"
exit /b 0
