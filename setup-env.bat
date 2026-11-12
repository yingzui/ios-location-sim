@echo off
REM ============================================================
REM  iOS Location Simulator - create the project-local venv
REM  Keep this file ASCII-only: cmd.exe garbles UTF-8 .bat text.
REM
REM  Usage:
REM    setup-env.bat                      use Python 3.12 from the py launcher
REM    setup-env.bat "C:\Python312\python.exe"   use an explicit interpreter
REM
REM  Result: envs\iosloc312\  (git-ignored). start.bat picks it up
REM  automatically, so dependencies stay out of your global site-packages.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "VENV=envs\iosloc312"

if exist "%VENV%\Scripts\python.exe" (
  echo [!] %VENV% already exists.
  echo     Delete that folder first if you want to rebuild it.
  echo.
  pause
  exit /b 1
)

if not "%~1"=="" goto use_arg

py -3.12 --version >nul 2>nul
if errorlevel 1 goto no_py312

echo Creating %VENV% with: py -3.12
py -3.12 -m venv "%VENV%"
goto created

:use_arg
echo Creating %VENV% with: %~1
"%~1" -m venv "%VENV%"
goto created

:no_py312
echo [!] Python 3.12 was not found by the py launcher.
echo.
echo     Pass the interpreter path as the first argument, for example:
echo       setup-env.bat "C:\Python312\python.exe"
echo.
echo     Any Python 3.9+ also works, but 3.12 is the version this
echo     project is tested against.
echo.
pause
exit /b 1

:created
if not exist "%VENV%\Scripts\python.exe" (
  echo [!] venv creation failed.
  pause
  exit /b 1
)

echo [1/2] Upgrading pip ...
"%VENV%\Scripts\python.exe" -m pip install -q -U pip

echo [2/2] Installing requirements ...
"%VENV%\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [!] Dependency install failed. Check the network or proxy, then retry.
  pause
  exit /b 1
)

echo.
echo Done: %VENV%
"%VENV%\Scripts\python.exe" --version
echo Double-click start.bat from now on - it will use this environment.
pause
