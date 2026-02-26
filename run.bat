@echo off
title Invoice Manager
echo Starting Invoice Manager...
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Could not start the app.
  echo Make sure Python 3.11 is installed and requirements are installed:
  echo   pip install -r requirements.txt
  pause
)
