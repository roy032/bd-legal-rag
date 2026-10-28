@echo off
title Bangladesh Law Assistant
rem Starts the assistant on this computer only (127.0.0.1) with the local model.
rem Your questions do not leave this computer. Close this window to stop.
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist .venv\Scripts\python.exe (
  echo Not set up yet. Run SETUP_WINDOWS.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python -m rag.cli start %*
pause
