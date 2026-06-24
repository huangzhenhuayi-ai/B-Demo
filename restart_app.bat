@echo off
setlocal
cd /d "%~dp0"

for /f "tokens=2 delims==; " %%P in ('wmic process where "name='python.exe' and commandline like '%%bilibili_keyword_app.py%%'" get ProcessId /value ^| find "="') do (
  taskkill /PID %%P /F >nul 2>nul
)

start "" /min "C:\Users\HUANG ZHEN\AppData\Local\Programs\Python\Python313\python.exe" -u bilibili_keyword_app.py --host 127.0.0.1 --port 8765
echo B站关键词热度排查工具已重启：http://127.0.0.1:8765
pause
