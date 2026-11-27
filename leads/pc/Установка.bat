@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Ставлю библиотеки...
python -m pip install -q -r requirements.txt || (echo Не получилось. Проверь, что установлен Python. & pause & exit /b 1)
if not exist .env copy .env.example .env >nul
echo.
echo Добавляю проверку раз в час в Планировщик заданий Windows...
for /f "delims=" %%p in ('where pythonw') do set PYW=%%p& goto found
:found
schtasks /Create /F /SC HOURLY /MO 1 /ST 08:23 /TN "Hazzer - заявки из чатов" /TR "\"%PYW%\" \"%~dp0chats.py\"" >nul && echo Готово: проверка каждый час (с 8 до 23 по Москве).
rem Зависшую проверку Windows снимет через 20 минут (а не через 3 дня), пропущенную запустит при включении ПК, на батарее тоже работает.
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew; Set-ScheduledTask -TaskName 'Hazzer - заявки из чатов' -Settings $s" >nul
echo.
echo Дальше: заполни файл .env и запусти «Вход в Telegram.bat».
pause
