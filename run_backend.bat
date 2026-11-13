@echo off
cd /d "%~dp0"
uvicorn backend.app.main:app --reload --port 8000
