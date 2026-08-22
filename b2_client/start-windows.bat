@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "STREAMLIT=%PROJECT_DIR%.venv\Scripts\streamlit.exe"

if not exist "%STREAMLIT%" (
    echo Windows virtual environment not found: "%STREAMLIT%"
    echo Run the Windows setup commands in README.md first.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"
"%STREAMLIT%" run "%PROJECT_DIR%app.py"
