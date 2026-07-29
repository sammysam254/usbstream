@echo off
setlocal EnableDelayedExpansion
title USB Stream - Auto Installer

:: ============================================================
::  USB Stream Auto Installer
::  NO admin rights required - installs to %USERPROFILE%\usbstream-tools
::  Uses curl.exe for fast downloads with progress bar
::  Checks: Python, pip, websockets, ADB, scrcpy, FFmpeg, cloudflared
:: ============================================================

:: Prevent any accidental early exit from errorlevel cascades
if "%1"=="--child" goto :RUN
cmd /k "%~f0" --child
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

:: Create tools directory
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

:: Add tools dir and sub-paths to PATH for this session
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
if %errorlevel%==0 (
    call :OK "Python found via 'py' launcher"
    goto :PY_DONE
)
python3 --version >nul 2>&1
if %errorlevel%==0 (
    call :OK "Python found as 'python3'"
    goto :PY_DONE
)
call :INSTALL_PYTHON
:PY_DONE

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
if exist "%SCRIPT_DIR%requirements.txt" (
    pip install -r "%SCRIPT_DIR%requirements.txt" --quiet
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
    adb version > "%TEMP%\adbver.txt" 2>&1
    for /f "tokens=1,2,3 delims= " %%a in ('findstr /i "version" "%TEMP%\adbver.txt"') do call :OK "ADB already installed - %%a %%b %%c"
    del "%TEMP%\adbver.txt" >nul 2>&1
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
    adb start-server > "%TEMP%\adb_start.txt" 2>&1
    call :OK "ADB server running"
    echo.
    echo  Connected devices:
    adb devices -l > "%TEMP%\adb_devices.txt" 2>&1
    type "%TEMP%\adb_devices.txt"
    del "%TEMP%\adb_devices.txt" >nul 2>&1
    del "%TEMP%\adb_start.txt" >nul 2>&1
)

:: ── Summary ──────────────────────────────────────────────────────────────────
echo.
echo  ==============================================
if %ERRORS%==0 (
    echo   ALL DONE - Setup complete with no errors!
    echo.
    echo   Starting stream server and opening browser...
    echo  ==============================================
    echo.

    :: Launch server.py in a new visible window
    start "USB Stream Server" cmd /k "cd /d "%SCRIPT_DIR%" && python server.py"

    :: Wait a few seconds for the server to start then open the viewer
    timeout /t 4 /nobreak >nul
    start "" "http://localhost:8080"

    echo   Server window opened. Browser launching at http://localhost:8080
    echo   The cloudflared remote link will appear in the server window.
    echo.
    echo   To stop: close the server window.
) else (
    echo   Setup finished with %ERRORS% error(s).
    echo   Fix the errors above and re-run install.bat
    echo  ==============================================
)
echo.
echo  Press any key to close this setup window...
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


:: ── Python (no admin - per-user silent install) ──────────────────────────────
:INSTALL_PYTHON
call :WARN "Python not found. Downloading Python 3.11 (curl)..."
set "PY_INSTALLER=%TEMP%\python_installer.exe"
curl.exe -L --progress-bar -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if %errorlevel% neq 0 (
    call :ERR "Failed to download Python. Get it from: https://python.org/downloads"
    exit /b 0
)
call :WARN "Running Python installer silently (per-user, no admin needed)..."
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%PY_INSTALLER%" >nul 2>&1
for /f "usebackq tokens=2*" %%A in (
    `reg query "HKCU\Environment" /v PATH 2^>nul`
) do set "PATH=%%B;!PATH!"
call :OK "Python installed (per-user)"
exit /b 0


:: ── ADB (no admin - extract to TOOLS_DIR) ───────────────────────────────────
:INSTALL_ADB
call :WARN "ADB not found. Downloading platform-tools (curl)..."
set "ADB_ZIP=%TEMP%\platform-tools.zip"
set "ADB_DIR=%TOOLS_DIR%\platform-tools"
curl.exe -L --progress-bar -o "%ADB_ZIP%" "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
if %errorlevel% neq 0 (
    call :ERR "Failed to download ADB."
    exit /b 0
)
call :WARN "Extracting ADB..."
tar.exe -xf "%ADB_ZIP%" -C "%TOOLS_DIR%"
del "%ADB_ZIP%" >nul 2>&1
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%ADB_DIR%', 'User')"
set "PATH=%PATH%;%ADB_DIR%"
call :OK "ADB installed to %ADB_DIR%"
exit /b 0


:: ── scrcpy (no admin - extract to TOOLS_DIR) ────────────────────────────────
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
if %errorlevel% neq 0 (
    call :ERR "Failed to download scrcpy."
    exit /b 0
)
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


:: ── FFmpeg (no admin - extract to TOOLS_DIR) ────────────────────────────────
:INSTALL_FFMPEG
call :WARN "FFmpeg not found. Downloading essentials build (curl)..."
set "FF_ZIP=%TEMP%\ffmpeg.zip"
set "FF_DIR=%TOOLS_DIR%\ffmpeg"
set "FF_TMP=%TOOLS_DIR%\ffmpeg_tmp"
curl.exe -L --progress-bar -o "%FF_ZIP%" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if %errorlevel% neq 0 (
    call :ERR "Failed to download FFmpeg."
    exit /b 0
)
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


:: ── cloudflared (no admin - single exe to TOOLS_DIR) ────────────────────────
:INSTALL_CLOUDFLARED
call :WARN "cloudflared not found. Downloading (curl)..."
set "CF_EXE=%TOOLS_DIR%\cloudflared.exe"
curl.exe -L --progress-bar -o "%CF_EXE%" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
if %errorlevel% neq 0 (
    call :ERR "Failed to download cloudflared."
    exit /b 0
)
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH','User') + ';%TOOLS_DIR%', 'User')"
set "PATH=%PATH%;%TOOLS_DIR%"
call :OK "cloudflared installed to %TOOLS_DIR%"
exit /b 0
