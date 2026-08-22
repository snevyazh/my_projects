@echo off
title Google Drive & NAS Transfer Studio
cd /d "%~dp0"
echo ===================================================
echo  Starting Google Drive & NAS Transfer Studio...
echo ===================================================
.venv\Scripts\streamlit.exe run app.py
pause
