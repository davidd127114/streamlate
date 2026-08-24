"""Self-healing fixed ports. Streamlate's pages live on well-known ports
(8765 chat, 8788 captions — OBS sources point at them), so a stale copy
squatting the port must be evicted, not walked around."""
import os
import socket
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000


def busy(port):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def free_port(port, marker, log=print):
    """If `port` is held, kill stale Streamlate processes matching `marker`
    (never ourselves) and wait for the port to clear."""
    if not busy(port):
        return True
    log(f"port {port} busy — clearing stale '{marker}' processes")
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or "
          "Name='python.exe'\" | Where-Object { $_.CommandLine -match "
          f"'{marker}' -and $_.ProcessId -ne {os.getpid()} }} | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=25,
                       creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        log(f"stale clear failed: {e}")
    for _ in range(24):
        if not busy(port):
            log(f"port {port} cleared")
            return True
        time.sleep(0.5)
    log(f"port {port} still busy — another program may be using it")
    return False
