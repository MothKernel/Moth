@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "from PySide6 import QtWidgets" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)
start "Moth" ".venv\Scripts\pythonw.exe" main.py
exit /b 0
:fail
echo Moth could not start. Install Python 3.11 or newer with the Python launcher, then retry.
pause
exit /b 1
