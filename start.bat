@echo off
rem 🌍 World Intelligence — one-command start (Windows).
rem Double-click this file, or run it from cmd / Git Bash.
setlocal
cd /d "%~dp0backend"

if exist ".venv\Scripts\python.exe" goto :venv_ok
echo 🔧 First run — creating the Python environment (one time)...
python -m venv .venv
if errorlevel 1 (
  echo ❌ Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo    (tick "Add python.exe to PATH" during install), then run this again.
  pause
  exit /b 1
)

:venv_ok
if not exist ".venv\.reqstamp" goto :install
for %%A in (requirements.txt .venv\.reqstamp) do set REQ_TIME=%%~tA
for %%A in (requirements.txt) do set REQ_FILE=%%~tA
if "%REQ_FILE%"=="%REQ_TIME%" goto :run

:install
echo 📦 Installing dependencies (one time)...
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo ❌ Dependency install failed — check your internet connection.
  pause
  exit /b 1
)
echo done> ".venv\.reqstamp"

:run
echo 🌍 World Intelligence ^→ http://localhost:%PORT%
echo    (Ctrl+C to stop)
".venv\Scripts\python.exe" -m app.server
pause
