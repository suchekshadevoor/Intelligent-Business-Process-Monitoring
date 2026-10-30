@echo off
title Business Process Monitor
echo ========================================================
echo Starting Intelligent Business Process Monitoring System...
echo ========================================================
cd /d "%~dp0"
.\.venv\Scripts\streamlit.exe run app.py
pause
