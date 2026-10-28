@echo off
title Bangladesh Law Assistant: setup
rem One command: Python, packages, Ollama + gemma4:e4b, the law index, then start.
rem Safe to run again; finished steps are skipped. Options: see scripts\setup_windows.ps1
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1" %*
echo.
pause
