"""Zero-effort OBS linking. OBS stores its websocket settings in a JSON
file; instead of asking the user to open menus and copy passwords, we:
  1. read the password straight from OBS's own config,
  2. flip the enable switch in that file when OBS is closed and it's off,
  3. report a plain status the wizard can show.
The user's only conceivable step: restart OBS once if it was open while
we flipped the switch."""
import json
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000
CFG_PATH = os.path.join(os.environ.get("APPDATA", ""), "obs-studio",
                        "plugin_config", "obs-websocket", "config.json")


def _read_file():
    try:
        with open(CFG_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def file_password():
    d = _read_file()
    return (d or {}).get("server_password", "")


def obs_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW).stdout
        return "obs64.exe" in out
    except Exception:
        return False


def try_connect(password):
    import contextlib
    import io
    try:
        import obsws_python as obs
        with contextlib.redirect_stderr(io.StringIO()):
            cl = obs.ReqClient(host="localhost", port=4455,
                               password=password or "", timeout=3)
            cl.get_version()
        return True
    except Exception:
        return False


def enable_in_file(log=print):
    """Turn the websocket on in OBS's config — only safe while OBS is
    closed (OBS rewrites the file from memory on exit)."""
    d = _read_file()
    if d is None or obs_running():
        return False
    if d.get("server_enabled"):
        return True
    d["server_enabled"] = True
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        log("obs link: websocket enabled in OBS's config")
        return True
    except OSError as e:
        log(f"obs link: could not write OBS config ({e})")
        return False


def effective_password(cfg):
    """Manual override wins; otherwise OBS's own file."""
    return (cfg.get("obs_ws_password") or "").strip() or file_password()


SLOBS_DIR = os.path.join(os.environ.get("APPDATA", ""), "slobs-client")


def status(cfg):
    """('ok'|'waiting'|'restart'|'slobs'|'none', password) for UI display."""
    d = _read_file()
    if d is None:
        if os.path.isdir(SLOBS_DIR):
            return "slobs", ""   # Streamlabs Desktop — manual source, works
        return "none", ""
    pw = effective_password(cfg)
    if try_connect(pw):
        return "ok", pw
    if not d.get("server_enabled"):
        if obs_running():
            return "restart", pw   # flip applies next OBS start
        enable_in_file()
        return "waiting", pw
    return "waiting", pw           # enabled; OBS just isn't running


def autolink(cfg, log=print):
    """Called by the caption service: returns the password to use, after
    silently doing whatever linking is possible right now."""
    pw = effective_password(cfg)
    if try_connect(pw):
        return pw
    d = _read_file()
    if d is not None and not d.get("server_enabled") and not obs_running():
        enable_in_file(log)
    return pw
