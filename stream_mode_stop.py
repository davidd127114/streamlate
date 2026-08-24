"""One-button stream stack stopper (run with pythonw — no console)."""
import os
import subprocess

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CREATE_NO_WINDOW = 0x08000000

try:
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", os.path.join(APP_DIR, "_stop.ps1")],
        creationflags=CREATE_NO_WINDOW, timeout=30)
except Exception:
    pass

from stream_mode_launcher import splash
splash(["Stream Translator — stopped",
        "Chat overlay, phone page and subtitles are off."],
       accent="#8a8a92", ms=2800)
