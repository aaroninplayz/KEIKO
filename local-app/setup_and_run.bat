@echo off
:: ============================================================
:: Keiko Local App - Setup & Run Script
:: ============================================================
:: Searches for a virtual environment in this order:
::   1. ./venv       (local venv in project dir)
::   2. ../venv      (parent directory venv)
::   3. System python (fallback)
:: ============================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Find virtual environment
set "PYTHON_EXE="
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
    set "VENV_DIR=%SCRIPT_DIR%venv"
    echo Found local venv.
) else if exist "%SCRIPT_DIR%..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%..\venv\Scripts\python.exe"
    set "VENV_DIR=%SCRIPT_DIR%..\venv"
    echo Found parent venv.
) else (
    echo No virtual environment found. Creating one...
    python -m venv "%SCRIPT_DIR%venv"
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Could not create virtual environment. Is Python installed?
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
    set "VENV_DIR=%SCRIPT_DIR%venv"
    echo Installing dependencies...
    "%SCRIPT_DIR%venv\Scripts\pip.exe" install -r requirements.txt
)

echo.
echo Starting the application...
echo Dashboard:       http://localhost:8000/static/dashboard.html
echo Interview Setup: http://localhost:8000/static/interview-setup.html
echo Admin Panel:     http://localhost:8000/static/admin.html
echo.
"%PYTHON_EXE%" main.py
pause
