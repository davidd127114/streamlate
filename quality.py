"""Translation quality tiers — trade VRAM for quality with one tray click.

auto  = the tier the wizard picked for this GPU (best it can hold)
light = gemma3:12b (~8 GB) — great quality, roughly half the VRAM
tiny  = gemma3:4b  (~3 GB) — good quality, laptop-friendly
zero  = free web engine + CPU whisper — the GPU is not touched at all
"""
import json
import os
import subprocess
import sys
import urllib.request

CREATE_NO_WINDOW = 0x08000000
TIER_MODELS = {"light": "gemma3:12b", "tiny": "gemma3:4b"}
KNOWN_MODELS = {"qwen3.8:27b", "gemma3:27b", "gemma3:12b", "gemma3:4b"}


def apply_quality(cfg, for_subs=False):
    """Rewrite a loaded config in-place according to the chosen tier."""
    q = cfg.get("quality") or ("zero" if cfg.get("game_mode") else "auto")
    cfg["quality"] = q
    if q == "zero":
        cfg["translator"] = "google"
        if for_subs:
            cfg["use_gpu"] = False
            cfg["model"] = ("base.en" if cfg.get("spoken_lang", "en") == "en"
                            else "base")
            cfg["call_model"] = "base"
    elif q in TIER_MODELS:
        cfg["translator"] = "ollama"
        cfg["ollama_model"] = TIER_MODELS[q]
    return cfg


def unload_models(engine_url, keep=""):
    """Evict every known LLM from VRAM except `keep` (keep_alive 0)."""
    for m in KNOWN_MODELS - {keep}:
        try:
            body = json.dumps({"model": m, "keep_alive": 0}).encode()
            req = urllib.request.Request(
                engine_url + "/api/generate", data=body,
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass


def set_quality(tier, app_dir, engine_url, log=print):
    """Write the tier to both configs, free VRAM, fetch the model if new,
    and relaunch the stack. Called from the tray menus."""
    for name in ("config.json", "subs_config.json"):
        path = os.path.join(app_dir, name)
        try:
            with open(path, encoding="utf-8-sig") as f:
                c = json.load(f)
        except (OSError, ValueError):
            c = {}
        c["quality"] = tier
        c.pop("game_mode", None)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(c, f, indent=2)
        except OSError as e:
            log(f"quality write failed: {e}")
    target = TIER_MODELS.get(tier, "")
    unload_models(engine_url, keep=target)
    if target:
        # no-op if present; downloads in the background if not (google covers)
        try:
            exe = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                               "Programs", "Ollama", "ollama.exe")
            subprocess.Popen([exe if os.path.exists(exe) else "ollama",
                              "pull", target],
                             creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass
    subprocess.Popen([sys.executable,
                      os.path.join(app_dir, "stream_mode_launcher.py")],
                     cwd=app_dir)
