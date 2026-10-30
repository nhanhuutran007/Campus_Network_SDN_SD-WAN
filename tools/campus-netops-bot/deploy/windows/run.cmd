@echo off
rem Run by Task Scheduler (SYSTEM). If the bot exits or crashes, wait 30 s and start it again.
cd /d "%~dp0app"
:loop
echo [%date% %time%] start telegram_bot.py>> "%~dp0logs\bot.log"
"%~dp0python\python.exe" telegram_bot.py >> "%~dp0logs\bot.log" 2>&1
echo [%date% %time%] bot exited code %errorlevel%>> "%~dp0logs\bot.log"
timeout /t 30 /nobreak >nul
goto loop
