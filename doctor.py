"""Built-in auto-debugging. Three jobs:
  1. missing_deps/repair_deps — detect and reinstall broken packages
     (the #1 cause of 'starting… forever').
  2. last_error — read a service's log and say what killed it, in one line.
  3. write_report — the full diagnostics file, one click, to the Desktop.
The control panel drives all of this; users never open a terminal."""
import importlib.util
import os
import subprocess
import sys
import time

CREATE_NO_WINDOW = 0x08000000

REQUIRED = [
    ("sounddevice", "sounddevice"), ("faster_whisper", "faster-whisper"),
    ("numpy", "numpy"), ("pystray", "pystray"), ("PIL", "pillow"),
    ("qrcode", "qrcode"), ("pyaudiowpatch", "pyaudiowpatch"),
    ("pyttsx3", "pyttsx3"), ("websocket", "websocket-client"),
    ("cloudscraper", "cloudscraper"),
]


def missing_deps():
    out = []
    for module, pip_name in REQUIRED:
        try:
            if importlib.util.find_spec(module) is None:
                out.append(pip_name)
        except Exception:
            out.append(pip_name)
    return out


def repair_deps(names, log=print):
    if not names:
        return True
    log(f"repair: installing {', '.join(names)}")
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                            "--quiet"] + names, timeout=900,
                           creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception as e:
        log(f"repair failed: {e}")
        return False


def last_error(log_path):
    """The most recent fatal-looking line of a service log, or None."""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 16000))
            lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return None
    for ln in reversed(lines):
        low = ln.lower()
        if ("fatal" in low or "traceback" in low or "error:" in low
                or low.endswith("error") or "exception:" in low):
            return ln[:220]
    return None


def diagnose(app_dir):
    """Plain-language findings + which auto-fixes apply.
    Returns (messages, fixes) — fixes ⊆ {'deps'}."""
    msgs, fixes = [], set()
    miss = missing_deps()
    if miss:
        msgs.append(f"Broken installation: missing {', '.join(miss)}")
        fixes.add("deps")
    for name, fname in (("Voice subtitles", "subs.log"),
                        ("Chat translation", "translator.log")):
        err = last_error(os.path.join(app_dir, fname))
        if err:
            msgs.append(f"{name} last error: {err}")
    if not msgs:
        msgs.append("No obvious cause found — use Diagnose and share the file.")
    return msgs, fixes


def write_report(app_dir):
    out = os.path.join(os.path.expanduser("~"), "Desktop",
                       "streamlate_diagnostics.txt")
    parts = [f"=== Streamlate diagnostics {time.strftime('%Y-%m-%d %H:%M')} ===",
             f"python: {sys.version.split()[0]}"]
    try:
        with open(os.path.join(app_dir, ".version")) as f:
            parts.append("app version: " + f.read().strip())
    except OSError:
        parts.append("app version: unknown")
    miss = missing_deps()
    parts.append("packages: " + ("all OK" if not miss
                                 else "MISSING " + ", ".join(miss)))
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                              "--format=csv,noheader"], capture_output=True,
                             text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW).stdout.strip()
        parts.append("gpu: " + (gpu or "none detected"))
    except Exception:
        parts.append("gpu: no nvidia driver")
    for fname in ("subs.log", "translator.log"):
        parts.append(f"\n========== {fname} ==========")
        try:
            with open(os.path.join(app_dir, fname), encoding="utf-8",
                      errors="replace") as f:
                parts.append(f.read()[-30000:])
        except OSError:
            parts.append("(missing)")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out
