@echo off
set "VENV_DIR=P:\Dependencies\keiko_venv"
set "PYTHON_BASE=P:\Dependencies\Python313\python.exe"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment in %VENV_DIR%...
    if not exist "%PYTHON_BASE%" (
        echo ERROR: Base Python not found at %PYTHON_BASE%
        pause
        exit /b 1
    )
    "%PYTHON_BASE%" -m venv "%VENV_DIR%"
    echo Installing dependencies...
    "%VENV_DIR%\Scripts\pip.exe" install -r requirements.txt
) else (
    echo Virtual environment found.
)

echo Starting the application...
echo Home Page: http://localhost:8000/static/index.html
echo Interview Panel: http://localhost:8000/static/interview.html
echo Admin Menu: http://localhost:8000/static/admin.html
"%VENV_DIR%\Scripts\python.exe" main.py
pause
