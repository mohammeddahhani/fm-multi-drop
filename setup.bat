@echo off
REM One-command setup for Windows: checks Python, creates .venv, installs the tool.
setlocal
cd /d "%~dp0"

set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3.9 or newer was not found.
    echo   Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
    echo   or run:  winget install Python.Python.3.12
    exit /b 1
)

%PY% -m venv .venv
if errorlevel 1 (
    echo ERROR: could not create a virtual environment.
    exit /b 1
)
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install --quiet .
if errorlevel 1 exit /b 1
.venv\Scripts\fm-multi-drop.exe --self-test
if errorlevel 1 exit /b 1

echo.
echo Setup complete. Patch a disc image ^(your own copy^) with:
echo.
echo     .venv\Scripts\fm-multi-drop.exe "C:\path\to\YFM MOD KURIBOH.iso" --drops 10
echo.
endlocal
