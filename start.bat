@echo off
REM ============================================================
REM  iOS Location Simulator - Windows launcher
REM  Keep this file ASCII-only: cmd.exe garbles UTF-8 .bat text.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

REM --- Prefer Python 3.12 when available: the 'lzfse' dependency of
REM     pymobiledevice3 ships prebuilt wheels only up to cp312 ---
set "PY=python"
set "PYARGS="
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 --version >nul 2>nul
  if not errorlevel 1 (
    set "PY=py"
    set "PYARGS=-3.12"
  )
)

echo ============================================================
echo   iOS Location Simulator
echo   Interpreter:
"%PY%" %PYARGS% --version
echo ============================================================
echo.

REM --- Version guard: on 3.13+ pip would try to build lzfse from source ---
"%PY%" %PYARGS% -c "import sys; sys.exit(0 if sys.version_info[:2] <= (3,12) else 1)" 2>nul
if errorlevel 1 (
  echo [!] WARNING: Python 3.12 or older is strongly recommended on Windows.
  echo     The 'lzfse' dependency of pymobiledevice3 ships prebuilt wheels
  echo     only up to cp312. On 3.13+ pip will try to compile it from source
  echo     and fail unless MSVC C++ Build Tools are installed.
  echo     See README.md section "Why Python 3.12".
  echo.
  pause
)

REM --- Skip the network install when pymobiledevice3 is already usable ---
"%PY%" %PYARGS% -c "import pymobiledevice3" 2>nul
if errorlevel 1 (
  echo [1/2] Installing pymobiledevice3 ...
  "%PY%" %PYARGS% -m pip install -U -q pymobiledevice3
  if errorlevel 1 (
    echo.
    echo [!] Install failed. See README.md section "Why Python 3.12".
    pause
    exit /b 1
  )
) else (
  echo [1/2] pymobiledevice3 already installed - skipping download.
)

echo [2/2] Starting local server on http://127.0.0.1:8765/
echo       In the UI: scan device -^> mount image -^> connect.
echo       Keep this window open - closing it restores the real location.
echo.
"%PY%" %PYARGS% server.py
pause
