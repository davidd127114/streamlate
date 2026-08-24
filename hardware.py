"""Pick the best translation setup for this PC automatically.

The whole point: the user never chooses a model. We look at their GPU and
pick the biggest brain that fits; with no usable GPU we fall back to the
free Google web engine, which needs nothing at all.
"""
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000

# (min VRAM GB, ollama model, approx download, one-line description)
TIERS = [
    (20, "qwen3.8:27b", "17 GB", "best quality — natural gamer speech"),
    (11, "gemma3:12b",  "8 GB",  "great quality"),
    (6,  "gemma3:4b",   "3 GB",  "good quality"),
]


def nvidia_vram_gb():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW)
        vals = [int(v) for v in out.stdout.split() if v.strip().isdigit()]
        return max(vals) / 1024.0 if vals else 0.0
    except Exception:
        return 0.0


def ollama_exe():
    """Path to a working ollama binary — works even right after a silent
    install, before PATH refreshes."""
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Programs", "Ollama", "ollama.exe")
    for cand in ("ollama", local):
        try:
            r = subprocess.run([cand, "--version"], capture_output=True,
                               timeout=10, creationflags=CREATE_NO_WINDOW)
            if r.returncode == 0:
                return cand
        except Exception:
            pass
    return None


def ollama_available():
    return ollama_exe() is not None


def installed_ollama_models():
    exe = ollama_exe()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "list"], capture_output=True, text=True,
                           timeout=15, creationflags=CREATE_NO_WINDOW)
        return [line.split()[0] for line in r.stdout.splitlines()[1:]
                if line.strip()]
    except Exception:
        return []


def pick():
    """Returns a dict describing the best setup for this machine."""
    vram = nvidia_vram_gb()
    has_ollama = ollama_available()
    plan = {
        "vram_gb": round(vram, 1),
        "ollama_installed": has_ollama,
        "whisper_model": "small.en" if vram >= 2 else "base.en",
        "use_gpu": vram >= 2,
        "translator": "google",
        "ollama_model": "",
        "download": "",
        "note": "free Google engine — works on any PC",
    }
    if vram >= 6:
        for min_gb, model, dl, note in TIERS:
            if vram >= min_gb:
                plan.update({"translator": "ollama", "ollama_model": model,
                             "download": dl, "note": note})
                break
    return plan


if __name__ == "__main__":
    import json
    print(json.dumps(pick(), indent=2))
