@echo off
rem Collects everything needed to debug a Streamlate problem into ONE file
rem on your Desktop - send that file to whoever is helping you.
setlocal
set "OUT=%USERPROFILE%\Desktop\streamlate_diagnostics.txt"
set "APP=%LOCALAPPDATA%\Streamlate"
if not exist "%APP%" set "APP=%~dp0"

> "%OUT%" echo === Streamlate diagnostics %date% %time% ===
>> "%OUT%" ver
>> "%OUT%" echo.
>> "%OUT%" echo --- python ---
python --version >> "%OUT%" 2>&1
>> "%OUT%" echo --- app version ---
if exist "%APP%\.version" (type "%APP%\.version" >> "%OUT%") else (echo no .version >> "%OUT%")
>> "%OUT%" echo.
>> "%OUT%" echo --- key packages ---
python -c "import importlib,sys; [print(m, 'OK' if importlib.util.find_spec(m) else 'MISSING') for m in ['sounddevice','faster_whisper','numpy','pystray','PIL','qrcode','pyaudiowpatch','pyttsx3']]" >> "%OUT%" 2>&1
>> "%OUT%" echo.
>> "%OUT%" echo --- gpu ---
nvidia-smi --query-gpu=name,memory.total --format=csv >> "%OUT%" 2>&1
>> "%OUT%" echo.
>> "%OUT%" echo --- ports ---
netstat -ano | findstr ":8765 :8788" >> "%OUT%" 2>&1
>> "%OUT%" echo.
>> "%OUT%" echo ================ subs.log ================
if exist "%APP%\subs.log" (type "%APP%\subs.log" >> "%OUT%") else (echo missing >> "%OUT%")
>> "%OUT%" echo.
>> "%OUT%" echo ============= translator.log =============
if exist "%APP%\translator.log" (type "%APP%\translator.log" >> "%OUT%") else (echo missing >> "%OUT%")
echo.
echo  Done! "streamlate_diagnostics.txt" is on your Desktop.
echo  Send that file to the person helping you.
start "" notepad "%OUT%"
pause
