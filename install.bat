@echo off
setlocal EnableDelayedExpansion
title USB Stream - Auto Installer

:: ============================================================
::  USB Stream Auto Installer
::  NO admin rights required - installs to %USERPROFILE%\usbstream-tools
::  Checks: Python, pip, websockets, ADB, scrcpy, FFmpeg, cloudflared
:: ============================================================

set "ERRORS=0"
set "TOOLS_DIR=%USERPROFILE%\usbstream-tools"

echo.
echo  ==============================================
echo   USB Stream - Auto Setup
echo   Install dir: %TOOLS_DIR%
echo  ==============================================
echo.

:: Create tools directory
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

:: Add tools dir to PATH for this session immediately
set "PATH=%PATH%;%TOOLS_DIR%"
set "PATH=%PATH%;%TOOLS_DIR%\platform-tools"
set "PATH=%PATH%;%TOOLS_DIR%\scrcpy"
set "PATH=%PATH%;%TOOLS_DIR%\ffmpeg\bin"

:: ── 1. Python ────────────────────────────────────────────────────────────────
call :SECTION "Python 3"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_PYTHON
) else (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    call :OK "Python !PY_VER! already installed"
)

:: ── 2. pip ───────────────────────────────────────────────────────────────────
call :SECTION "pip"
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    call :WARN "pip not found, bootstrapping..."
    python -m ensurepip --upgrade >nul 2>&1
    python -m pip install --upgrade pip --quiet
    call :OK "pip installed"
) else (
    call :OK "pip already available"
)

:: ── 3. Python packages ───────────────────────────────────────────────────────
call :SECTION "Python packages (websockets)"
if exist "%~dp0requirements.txt" (
    pip install -r "%~dp0requirements.txt" --quiet
    if !errorlevel! neq 0 (
        call :ERR "Failed to install Python packages"
    ) else (
        call :OK "Python packages installed"
    )
) else (
    pip install websockets --quiet
    call :OK "websockets installed"
)

:: ── 4. ADB ───────────────────────────────────────────────────────────────────
call :SECTION "ADB (Android Debug Bridge)"
adb version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_ADB
) else (
    for /f "tokens=1,2,3 delims= " %%a in ('adb version 2^>^&1 ^| findstr /i "version"') do (
        call :OK "ADB already installed - %%a %%b %%c"
    )
)

:: ── 5. scrcpy ────────────────────────────────────────────────────────────────
call :SECTION "scrcpy"
scrcpy --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_SCRCPY
) else (
    for /f "tokens=1,2 delims= " %%a in ('scrcpy --version 2^>^&1 ^| findstr /i "scrcpy"') do (
        call :OK "scrcpy already installed - %%a %%b"
    )
)

:: ── 6. FFmpeg ────────────────────────────────────────────────────────────────
call :SECTION "FFmpeg"
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_FFMPEG
) else (
    for /f "tokens=3 delims= " %%v in ('ffmpeg -version 2^>^&1 ^| findstr /i "ffmpeg version"') do (
        call :OK "FFmpeg %%v already installed"
    )
)

:: ── 7. cloudflared ───────────────────────────────────────────────────────────
call :SECTION "cloudflared (remote access tunnels)"
cloudflared --version >nul 2>&1
if %errorlevel% neq 0 (
    call :INSTALL_CLOUDFLARED
) else (
    for /f "tokens=1,2,3 delims= " %%a in ('cloudflared --version 2^>^&1') do (
        call :OK "cloudflared already installed - %%a %%b %%c"
    )
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
    adb devices -l
)

:: ── Summary ──────────────────────────────────────────────────────────────────
echo.
echo  ==============================================
if %ERRORS%==0 (
    echo   ALL DONE - No errors!
    echo.
    echo   NOTE: Open a NEW terminal window before running
    echo         python server.py so the PATH changes take effect.
    echo.
    echo   To start streaming:
    echo     1. Connect Android device via USB
    echo     2. Enable USB Debugging on device
    echo     3. Open a new terminal and run:
    echo           python server.py
    echo     4. The remote cloudflared link prints in the console.
    echo     5. Share that URL to view from anywhere.
    echo.
    echo   Local-only mode (no tunnel):
    echo     python server.py --no-tunnel
) else (
    echo   Setup finished with %ERRORS% error(s).
    echo   Check messages above.
)
echo  ==============================================
echo.
pause
exit /b 0


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

:: ── Python installer (no admin - per-user) ───────────────────────────────────
:INSTALL_PYTHON
call :WARN "Python not found. Downloading Python installer..."
set "PY_INSTALLER=%TEMP%\python_installer.exe"
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%PY_INSTALLER%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download Python."
    echo        Get it from: https://python.org/downloads
    echo        Tick 'Add Python to PATH' during install.
    exit /b 1
)
:: /quiet InstallAllUsers=0 = per-user, no admin needed
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%PY_INSTALLER%" >nul 2>&1
:: Refresh PATH from registry
for /f "usebackq tokens=2*" %%A in (
    `reg query "HKCU\Environment" /v PATH 2^>nul`
) do set "PATH=%%B;!PATH!"
call :OK "Python installed (per-user)"
exit /b 0

:: ── ADB installer (no admin - extract to TOOLS_DIR) ─────────────────────────
:INSTALL_ADB
call :WARN "ADB not found. Downloading platform-tools..."
set "ADB_ZIP=%TEMP%\platform-tools.zip"
set "ADB_DIR=%TOOLS_DIR%\platform-tools"
powershell -Command "Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile '%ADB_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download ADB."
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%ADB_ZIP%' -DestinationPath '%TOOLS_DIR%' -Force"
del "%ADB_ZIP%" >nul 2>&1
:: platform-tools.zip extracts to a folder called platform-tools inside TOOLS_DIR
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%ADB_DIR%', 'User')"
set "PATH=%PATH%;%ADB_DIR%"
call :OK "ADB installed to %ADB_DIR%"
exit /b 0

:: ── scrcpy installer (no admin - extract to TOOLS_DIR) ──────────────────────
:INSTALL_SCRCPY
call :WARN "scrcpy not found. Downloading..."
set "SCRCPY_ZIP=%TEMP%\scrcpy.zip"
set "SCRCPY_DIR=%TOOLS_DIR%\scrcpy"

:: Fetch the latest release tag from GitHub
for /f "usebackq delims=" %%T in (
    `powershell -Command "(Invoke-RestMethod 'https://api.github.com/repos/Genymobile/scrcpy/releases/latest').tag_name"`
) do set "SCRCPY_TAG=%%T"

if not defined SCRCPY_TAG set "SCRCPY_TAG=v3.1"
call :OK "Latest scrcpy tag: %SCRCPY_TAG%"

powershell -Command "Invoke-WebRequest -Uri 'https://github.com/Genymobile/scrcpy/releases/download/%SCRCPY_TAG%/scrcpy-win64-%SCRCPY_TAG%.zip' -OutFile '%SCRCPY_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download scrcpy."
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%SCRCPY_ZIP%' -DestinationPath '%TOOLS_DIR%\scrcpy_tmp' -Force"
del "%SCRCPY_ZIP%" >nul 2>&1
:: Move the inner folder to a clean path
if exist "%SCRCPY_DIR%" rmdir /s /q "%SCRCPY_DIR%"
for /d %%d in ("%TOOLS_DIR%\scrcpy_tmp\*") do (
    move "%%d" "%SCRCPY_DIR%" >nul 2>&1
)
rmdir /s /q "%TOOLS_DIR%\scrcpy_tmp" >nul 2>&1
if not exist "%SCRCPY_DIR%" set "SCRCPY_DIR=%TOOLS_DIR%\scrcpy_tmp"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%SCRCPY_DIR%', 'User')"
set "PATH=%PATH%;%SCRCPY_DIR%"
call :OK "scrcpy installed to %SCRCPY_DIR%"
exit /b 0

:: ── FFmpeg installer (no admin - extract to TOOLS_DIR) ──────────────────────
:INSTALL_FFMPEG
call :WARN "FFmpeg not found. Downloading essentials build..."
set "FF_ZIP=%TEMP%\ffmpeg.zip"
set "FF_DIR=%TOOLS_DIR%\ffmpeg"
powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%FF_ZIP%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download FFmpeg."
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%FF_ZIP%' -DestinationPath '%TOOLS_DIR%\ffmpeg_tmp' -Force"
del "%FF_ZIP%" >nul 2>&1
if exist "%FF_DIR%" rmdir /s /q "%FF_DIR%"
for /d %%d in ("%TOOLS_DIR%\ffmpeg_tmp\*") do (
    move "%%d" "%FF_DIR%" >nul 2>&1
)
rmdir /s /q "%TOOLS_DIR%\ffmpeg_tmp" >nul 2>&1
set "FF_BIN=%FF_DIR%\bin"
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%FF_BIN%', 'User')"
set "PATH=%PATH%;%FF_BIN%"
call :OK "FFmpeg installed to %FF_DIR%"
exit /b 0

:: ── cloudflared installer (no admin - single exe to TOOLS_DIR) ───────────────
:INSTALL_CLOUDFLARED
call :WARN "cloudflared not found. Downloading..."
set "CF_EXE=%TOOLS_DIR%\cloudflared.exe"
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CF_EXE%' -UseBasicParsing"
if %errorlevel% neq 0 (
    call :ERR "Failed to download cloudflared."
    exit /b 1
)
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%TOOLS_DIR%', 'User')"
set "PATH=%PATH%;%TOOLS_DIR%"
call :OK "cloudflared installed to %TOOLS_DIR%"
exit /b 0
