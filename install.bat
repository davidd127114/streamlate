@echo off
cd /d "%~dp0"
echo Installing Python packages (one-time)...
python -m pip install --user sounddevice faster-whisper numpy pystray pillow qrcode
if errorlevel 1 (
  echo.
  echo Python was not found. Install Python 3.11+ from python.org
  echo and tick "Add to PATH", then run this again.
  pause
  exit /b 1
)
echo.
echo Creating desktop shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pyw = (Get-Command pythonw).Source; $ws = New-Object -ComObject WScript.Shell; $on = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Stream Translator.lnk'); $on.TargetPath = $pyw; $on.Arguments = '\"%~dp0stream_mode_launcher.py\"'; $on.WorkingDirectory = '%~dp0'; $on.IconLocation = '%~dp0stream_on.ico,0'; $on.Save(); $off = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Stream Translator OFF.lnk'); $off.TargetPath = $pyw; $off.Arguments = '\"%~dp0stream_mode_stop.py\"'; $off.WorkingDirectory = '%~dp0'; $off.IconLocation = '%~dp0stream_off.ico,0'; $off.Save()"
echo.
echo Done! Double-click "Stream Translator" on your desktop to set up.
echo (For best translation quality, also install Ollama from ollama.com)
pause
