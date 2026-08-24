@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Streamlate - Installer
echo ==============================================
echo   Streamlate - one-time setup
echo   (installs everything needed automatically)
echo ==============================================
echo.

rem ---------- 1/4 Python ----------
set "PY="
for /f "delims=" %%P in ('where python.exe 2^>nul') do (
  echo %%P | find /i "WindowsApps" >nul || if not defined PY set "PY=%%P"
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY (
  echo [1/4] Downloading Python...
  curl -L --progress-bar -o "%TEMP%\py_setup.exe" https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe
  echo       Installing Python ^(silent^)...
  "%TEMP%\py_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0
  set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
) else (
  echo [1/4] Python found.
)
if not exist "!PY!" (
  echo   Python install failed. Install it manually from python.org and rerun.
  pause
  exit /b 1
)

rem ---------- 2/4 App components ----------
echo [2/4] Installing app components...
"!PY!" -m pip install --user --quiet sounddevice faster-whisper numpy pystray pillow qrcode yt-dlp websocket-client cloudscraper

rem ---------- 3/4 Ollama (AI translation engine) ----------
set "OLLAMA_DIR=%LOCALAPPDATA%\Programs\Ollama"
where ollama >nul 2>&1
if not errorlevel 1 goto ollama_ok
if exist "%OLLAMA_DIR%\ollama.exe" goto ollama_ok
echo [3/4] Downloading the AI engine ^(Ollama, ~700 MB - grab a coffee^)...
curl -L --progress-bar -o "%TEMP%\OllamaSetup.exe" https://ollama.com/download/OllamaSetup.exe
echo       Installing ^(silent^)...
"%TEMP%\OllamaSetup.exe" /VERYSILENT /NORESTART
goto ollama_done
:ollama_ok
echo [3/4] Ollama found.
:ollama_done
if exist "%OLLAMA_DIR%\ollama app.exe" start "" "%OLLAMA_DIR%\ollama app.exe"

rem ---------- 4/4 Desktop icons ----------
echo [4/4] Creating desktop icons...
set "PYW=!PY:python.exe=pythonw.exe!"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $on = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Streamlate.lnk'); $on.TargetPath = '!PYW!'; $on.Arguments = '\"%~dp0stream_mode_launcher.py\"'; $on.WorkingDirectory = '%~dp0'; $on.IconLocation = '%~dp0stream_on.ico,0'; $on.Save(); $off = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Streamlate OFF.lnk'); $off.TargetPath = '!PYW!'; $off.Arguments = '\"%~dp0stream_mode_stop.py\"'; $off.WorkingDirectory = '%~dp0'; $off.IconLocation = '%~dp0stream_off.ico,0'; $off.Save()"

echo.
echo  Done! Opening Streamlate setup...
start "" "!PYW!" "%~dp0stream_mode_launcher.py"
ping -n 4 localhost >nul
