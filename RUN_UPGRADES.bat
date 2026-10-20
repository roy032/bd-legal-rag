@echo off
title bd-legal-rag: measure the upgrades
cd /d "%~dp0"
set PYTHONUTF8=1
.venv\Scripts\python -m pip install -q -e ".[serve,embed]"
.venv\Scripts\python -m rag.cli doctor
ollama pull gemma4:e4b
.venv\Scripts\python scripts\measure_upgrades.py %*
echo.
echo Finished. The table is in results\UPGRADES.md
pause
