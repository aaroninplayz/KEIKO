@echo off
setlocal EnableDelayedExpansion
title HR Interview Vision AI Panel

:: Get script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Set Python Executable (use parent virtual environment if it exists)
set "PYTHON_EXE=python"
if exist "P:\Dependencies\keiko_venv\Scripts\python.exe" (
    set "PYTHON_EXE=P:\Dependencies\keiko_venv\Scripts\python.exe"
)

:: Verify configuration file exists
if not exist "config.yaml" (
    echo ERROR: config.yaml not found in %SCRIPT_DIR%
    pause
    exit /b 1
)

:MENU
cls
echo ================================================================
echo              HR INTERVIEW VISION AI CONTROL PANEL
echo ================================================================
echo.
echo   Local server: http://127.0.0.1:5000
echo.
echo   [1] Start Live HR Interview Dashboard Server (Web Page)
echo   [2] Collect Labeled Training Data (Webcam Image Grabber)
echo   [3] Train an Independent Vision Classifier (PyTorch + CUDA)
echo   [4] Install / Verify Vision Dependencies (pip)
echo   [5] Reset / Delete Trained Model Weights
echo   [6] Exit Panel
echo.
set "menu_choice="
set /p "menu_choice=Select an option (1-6): "

if "!menu_choice!"=="1" goto LAUNCH_SERVER
if "!menu_choice!"=="2" goto DATA_COLLECT
if "!menu_choice!"=="3" goto TRAIN_MODEL
if "!menu_choice!"=="4" goto INSTALL_DEPS
if "!menu_choice!"=="5" goto RESET_WEIGHTS
if "!menu_choice!"=="6" goto EXIT_APP

echo Invalid option, please try again.
timeout /t 2 >nul
goto MENU


:LAUNCH_SERVER
cls
echo ================================================================
echo                 STARTING VISION DASHBOARD SERVER
echo ================================================================
echo.
echo   1. The local server will boot and open a camera connection.
echo   2. Open your web browser and navigate to: http://127.0.0.1:5000
echo   3. To stop the server and close the camera, press [Ctrl+C]
echo.
echo   Initializing PyTorch CUDA pipeline...
echo.
"!PYTHON_EXE!" "%SCRIPT_DIR%cam_feed.py"
echo.
echo Server stopped.
pause
goto MENU


:DATA_COLLECT
cls
echo ================================================================
echo                 STARTING DATA COLLECTOR UTILITY
echo ================================================================
echo.
"!PYTHON_EXE!" "%SCRIPT_DIR%collect_data.py"
goto MENU


:TRAIN_MODEL
cls
echo ================================================================
echo                 STARTING DETECTOR TRAINER PIPELINE
echo ================================================================
echo.
"!PYTHON_EXE!" "%SCRIPT_DIR%train_detector.py"
goto MENU


:INSTALL_DEPS
cls
echo ================================================================
echo                 VERIFYING VISION DEPENDENCIES
echo ================================================================
echo.
echo   Running pip install for required libraries:
echo   OpenCV, PyYAML, PyTorch, Torchvision, Flask
echo.
"!PYTHON_EXE!" -m pip install -r "%SCRIPT_DIR%requirements.txt"
echo.
echo Dependencies verified.
pause
goto MENU


:RESET_WEIGHTS
cls
echo ================================================================
echo                 RESET / DELETE MODEL WEIGHTS
echo ================================================================
echo.
echo   Select weights to delete:
echo.
echo   [1] Posture Classifier weights
echo   [2] Eye Contact Classifier weights
echo   [3] Attire Classifier weights
echo   [4] Confidence Classifier weights
echo   [5] Emotions Classifier weights
echo   [6] DELETE ALL WEIGHTS
echo   [7] Return to main menu
echo.
set "del_choice="
set /p "del_choice=Selection (1-7): "

if "!del_choice!"=="1" (
    if exist "models\posture.pth" del "models\posture.pth"
    if exist "models\posture_labels.txt" del "models\posture_labels.txt"
    echo Posture weights reset.
)
if "!del_choice!"=="2" (
    if exist "models\eye_contact.pth" del "models\eye_contact.pth"
    if exist "models\eye_contact_labels.txt" del "models\eye_contact_labels.txt"
    echo Eye Contact weights reset.
)
if "!del_choice!"=="3" (
    if exist "models\attire.pth" del "models\attire.pth"
    if exist "models\attire_labels.txt" del "models\attire_labels.txt"
    echo Attire weights reset.
)
if "!del_choice!"=="4" (
    if exist "models\confidence.pth" del "models\confidence.pth"
    if exist "models\confidence_labels.txt" del "models\confidence_labels.txt"
    echo Confidence weights reset.
)
if "!del_choice!"=="5" (
    if exist "models\emotions.pth" del "models\emotions.pth"
    if exist "models\emotions_labels.txt" del "models\emotions_labels.txt"
    echo Emotions weights reset.
)
if "!del_choice!"=="6" (
    if exist "models" rmdir /s /q "models"
    mkdir "models"
    echo All weights deleted successfully.
)
if "!del_choice!"=="7" goto MENU

echo.
pause
goto MENU


:EXIT_APP
echo.
echo Goodbye!
endlocal
exit /b 0
