@echo off
setlocal EnableDelayedExpansion
title Keiko Model & Dataset Dashboard

:: Set current directory to the script location
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Set Python Executable (auto-discover venv)
set "PYTHON_EXE=python"
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%..\venv\Scripts\python.exe"
)

:: Run the premium interactive CLI dashboard helper
"!PYTHON_EXE!" "%SCRIPT_DIR%vision_system\dashboard_helper.py"
if %ERRORLEVEL% neq 0 (
    echo.
    echo Dashboard exited with a status code error.
    pause
)
