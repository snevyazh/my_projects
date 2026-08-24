@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "STREAMLIT=%PROJECT_DIR%.venv-windows\Scripts\streamlit.exe"

if not exist "%STREAMLIT%" (
    echo The Windows virtual environment or Streamlit installation was not found.
    echo.
    echo Run this first from PowerShell:
    echo   powershell -ExecutionPolicy Bypass -File "%PROJECT_DIR%setup-windows.ps1"
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"
"%STREAMLIT%" run "%PROJECT_DIR%app.py" --server.address 127.0.0.1

if errorlevel 1 (
    echo.
    echo The PDF to EPUB interface stopped with an error.
    pause
)
