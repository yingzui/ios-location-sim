@echo off
REM ============================================================
REM  iOS Location Simulator - Windows launcher
REM  Keep this file ASCII-only: cmd.exe garbles UTF-8 .bat text.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

REM --- Interpreter resolution order:
REM     1. %IOSLOC_PYTHON%            explicit override (full path)
REM     2. envs\iosloc312\...\python  project-local 3.12 venv, made by setup-env.bat
REM     3. py -3                      latest 3.x from the Windows launcher
REM     4. python                     whatever is on PATH
REM     Python >= 3.9 is required (pymobiledevice3 constraint).
set "PY="
set "PYARGS="
set "PYSRC="

if not defined IOSLOC_PYTHON goto check_venv
set "PY=%IOSLOC_PYTHON%"
set "PYSRC=IOSLOC_PYTHON env var"
goto have_py

:check_venv
if not exist "envs\iosloc312\Scripts\python.exe" goto check_pylauncher
set "PY=envs\iosloc312\Scripts\python.exe"
set "PYSRC=project venv envs\iosloc312"
goto have_py

:check_pylauncher
where py >nul 2>nul
if errorlevel 1 goto check_path
set "PY=py"
set "PYARGS=-3"
set "PYSRC=py launcher (latest 3.x)"
goto have_py

:check_path
set "PY=python"
set "PYSRC=python on PATH"

:have_py
echo ============================================================
echo   iOS Location Simulator
echo   Interpreter: %PYSRC%
"%PY%" %PYARGS% --version
echo ============================================================
echo.

REM --- Version gate: pymobiledevice3 itself requires Python 3.9+ ---
"%PY%" %PYARGS% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>nul
if errorlevel 1 (
  echo [!] Python 3.9 or newer is required, but none was found.
  echo     Install it from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

REM --- Skip the network install when pymobiledevice3 is already usable ---
"%PY%" %PYARGS% -c "import pymobiledevice3" 2>nul
if errorlevel 1 (
  echo [1/2] Installing pymobiledevice3 ...
  "%PY%" %PYARGS% -m pip install -U -q pymobiledevice3
  if errorlevel 1 (
    echo.
    echo [!] Install failed. Check the network or proxy, then retry.
    echo     Manual command: %PY% %PYARGS% -m pip install -U pymobiledevice3
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
