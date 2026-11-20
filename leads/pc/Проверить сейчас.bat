@echo off
chcp 65001 >nul
cd /d "%~dp0"
python chats.py --now
echo.
type log.txt 2>nul
pause
