@echo off
rem Standalone captions with their own green tray icon (normally the purple
rem Streamlate icon controls captions too - this is for captions-only use).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_stop.ps1" -Pattern stream_subtitles
start "" pythonw stream_subtitles.py --tray
