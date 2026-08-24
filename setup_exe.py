"""StreamlateSetup.exe — the one file a new user downloads.

Small GUI installer: fetches Python if missing, the app itself, its
packages, and the Ollama AI engine; creates desktop icons; opens the
setup wizard. Built with PyInstaller (see build_exe.py).

Hidden test flags: --target DIR  --no-shortcuts  --no-ollama  --no-launch
"""
import json
import os
import subprocess
import sys
import threading
import tempfile
import urllib.request
import zipfile

CREATE_NO_WINDOW = 0x08000000
REPO = "davidd127114/streamlate"
PY_URL = "https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe"
OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
DEPS = ["sounddevice", "faster-whisper", "numpy", "pystray", "pillow",
        "qrcode", "yt-dlp", "websocket-client", "cloudscraper",
        "pyaudiowpatch"]

ARGS = sys.argv[1:]
TARGET = None
for i, a in enumerate(ARGS):
    if a == "--target" and i + 1 < len(ARGS):
        TARGET = ARGS[i + 1]
APP = TARGET or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Streamlate")
NO_SHORTCUTS = "--no-shortcuts" in ARGS
NO_OLLAMA = "--no-ollama" in ARGS
NO_LAUNCH = "--no-launch" in ARGS


def find_python():
    cand = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Programs", "Python", "Python313", "python.exe")
    if os.path.exists(cand):
        return cand
    try:
        out = subprocess.run(["where", "python.exe"], capture_output=True,
                             text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW)
        for line in out.stdout.splitlines():
            if line.strip() and "WindowsApps" not in line:
                return line.strip()
    except Exception:
        pass
    return None


def download(url, dest, log, label):
    def hook(n, bs, total):
        if total > 0 and n % 40 == 0:
            log(f"  {label}: {min(100, n * bs * 100 // total)}%", replace=True)
    urllib.request.urlretrieve(url, dest, reporthook=hook)
    log(f"  {label}: 100%", replace=True)


def install(log, done):
    try:
        os.makedirs(APP, exist_ok=True)

        log("1/5  Python…")
        py = find_python()
        if not py:
            exe = os.path.join(tempfile.gettempdir(), "py_setup.exe")
            download(PY_URL, exe, log, "downloading Python")
            log("  installing Python (silent)…")
            subprocess.run([exe, "/quiet", "InstallAllUsers=0",
                            "PrependPath=1", "Include_launcher=0"],
                           timeout=900, creationflags=CREATE_NO_WINDOW)
            py = find_python()
            if not py:
                raise RuntimeError("Python install failed")
        log("  Python OK")

        log("2/5  Streamlate app…")
        z = os.path.join(tempfile.gettempdir(), "streamlate.zip")
        download(f"https://github.com/{REPO}/archive/refs/heads/main.zip",
                 z, log, "downloading app")
        with zipfile.ZipFile(z) as zf:
            names = zf.namelist()
            root = names[0]
            for m in names:
                rel = m[len(root):]
                if not rel or rel.endswith("/"):
                    continue
                dest = os.path.join(APP, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest) or APP, exist_ok=True)
                with zf.open(m) as src, open(dest, "wb") as out:
                    out.write(src.read())
        try:  # stamp version so auto-update starts from here
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/commits/main",
                headers={"User-Agent": "streamlate"})
            with urllib.request.urlopen(req, timeout=10) as r:
                sha = json.load(r)["sha"]
            with open(os.path.join(APP, ".version"), "w") as f:
                f.write(sha)
        except Exception:
            pass
        log("  app OK")

        log("3/5  App packages (a few minutes)…")
        subprocess.run([py, "-m", "pip", "install", "--user", "--quiet"]
                       + DEPS, timeout=1800, creationflags=CREATE_NO_WINDOW)
        log("  packages OK")

        log("4/5  Ollama AI engine…")
        odir = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                            "Programs", "Ollama")
        if NO_OLLAMA:
            log("  skipped (flag)")
        elif os.path.exists(os.path.join(odir, "ollama.exe")):
            log("  Ollama already installed")
        else:
            oexe = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            download(OLLAMA_URL, oexe, log, "downloading Ollama (~700 MB)")
            log("  installing Ollama (silent)…")
            subprocess.run([oexe, "/VERYSILENT", "/NORESTART"], timeout=1200,
                           creationflags=CREATE_NO_WINDOW)
            log("  Ollama OK")
        app_exe = os.path.join(odir, "ollama app.exe")
        if os.path.exists(app_exe) and not NO_OLLAMA:
            subprocess.Popen([app_exe], creationflags=CREATE_NO_WINDOW)

        log("5/5  Desktop icons…")
        pyw = py.replace("python.exe", "pythonw.exe")
        if not NO_SHORTCUTS:
            ps = (
                "$ws = New-Object -ComObject WScript.Shell;"
                "$d = [Environment]::GetFolderPath('Desktop');"
                f"$on = $ws.CreateShortcut($d + '\\Streamlate.lnk');"
                f"$on.TargetPath = '{pyw}';"
                f"$on.Arguments = '\"{APP}\\stream_mode_launcher.py\"';"
                f"$on.WorkingDirectory = '{APP}';"
                f"$on.IconLocation = '{APP}\\stream_on.ico,0'; $on.Save();"
                f"$off = $ws.CreateShortcut($d + '\\Streamlate OFF.lnk');"
                f"$off.TargetPath = '{pyw}';"
                f"$off.Arguments = '\"{APP}\\stream_mode_stop.py\"';"
                f"$off.WorkingDirectory = '{APP}';"
                f"$off.IconLocation = '{APP}\\stream_off.ico,0'; $off.Save()")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           timeout=60, creationflags=CREATE_NO_WINDOW)
            log("  icons OK")
        else:
            log("  skipped (flag)")

        log("")
        log("Done! Opening Streamlate setup…")
        if not NO_LAUNCH:
            subprocess.Popen(
                [pyw, os.path.join(APP, "stream_mode_launcher.py")], cwd=APP,
                creationflags=CREATE_NO_WINDOW)
        done(True)
    except Exception as e:
        log(f"\nERROR: {e}")
        log("Close this window and try again, or grab the ZIP install "
            "from the GitHub page.")
        done(False)


def main():
    import tkinter as tk
    root = tk.Tk()
    root.title("Streamlate Setup")
    root.configure(bg="#141417")
    root.geometry("560x380")
    root.resizable(False, False)
    tk.Label(root, text="Streamlate", bg="#141417", fg="#a970ff",
             font=("Segoe UI", 18, "bold"), pady=8).pack()
    tk.Label(root, text="Installing everything you need — sit back.",
             bg="#141417", fg="#c9c9d1", font=("Segoe UI", 10)).pack()
    box = tk.Text(root, bg="#0e0e10", fg="#d8d8dc", bd=0, padx=10, pady=8,
                  font=("Consolas", 9), state="disabled", height=14)
    box.pack(fill="both", expand=True, padx=16, pady=12)

    def log(msg, replace=False):
        def _do():
            box.configure(state="normal")
            if replace:
                box.delete("end-2l", "end-1l")
            box.insert("end", msg + "\n")
            box.see("end")
            box.configure(state="disabled")
        root.after(0, _do)

    def done(ok):
        if ok:
            root.after(3500, root.destroy)

    threading.Thread(target=install, args=(log, done), daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
