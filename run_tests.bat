@echo off
title Pytest Suite - Business Process Monitor
echo ========================================================
echo Running Automated Test Suite (Pytest)...
echo ========================================================
cd /d "%~dp0"
.\.venv\Scripts\python.exe -m pytest tests/ -v
echo ========================================================
pause
