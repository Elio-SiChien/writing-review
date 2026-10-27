@echo off
cd /d "%~dp0"
python -X utf8 -m writing_review %*
if errorlevel 1 pause
