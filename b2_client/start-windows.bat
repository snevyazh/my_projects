@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Windows virtual environment not found: "%PYTHON%"
    echo Run the Windows setup commands in README.md first.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"

cd /d "%PROJECT_DIR%"
"%PYTHON%" -m streamlit run "%PROJECT_DIR%app.py"
