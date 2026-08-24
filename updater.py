"""Auto-update from GitHub on launch. Zero clicks: compares the repo's
latest commit to the local .version, downloads the zip when newer, and
refreshes code files — never the user's settings, backgrounds, or logs.
Set "auto_update": false in config.json to opt out."""
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = "davidd127114/streamlate"
VFILE = os.path.join(APP_DIR, ".version")
KEEP = {"config.json", "subs_config.json", ".version"}


def _remote_sha(timeout=5):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/commits/main",
        headers={"User-Agent": "streamlate",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["sha"]


def maybe_update(log=print):
    """Returns True if an update was applied."""
    try:
        try:
            with open(os.path.join(APP_DIR, "config.json"),
                      encoding="utf-8-sig") as f:
                if json.load(f).get("auto_update") is False:
                    return False
        except (OSError, ValueError):
            pass
        remote = _remote_sha()
        local = ""
        try:
            with open(VFILE) as f:
                local = f.read().strip()
        except OSError:
            pass
        if not local:
            with open(VFILE, "w") as f:
                f.write(remote)     # fresh install: call it current
            return False
        if local == remote:
            return False
        log(f"streamlate update: {local[:7]} -> {remote[:7]}")
        zpath = os.path.join(tempfile.gettempdir(), "streamlate_update.zip")
        urllib.request.urlretrieve(
            f"https://github.com/{REPO}/archive/refs/heads/main.zip", zpath)
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            root = names[0]
            for m in names:
                rel = m[len(root):]
                if not rel or rel.endswith("/"):
                    continue
                base = os.path.basename(rel)
                if base in KEEP or base.startswith("background.") \
                        or base.endswith(".log"):
                    continue
                dest = os.path.join(APP_DIR, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest) or APP_DIR, exist_ok=True)
                with z.open(m) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
        os.remove(zpath)
        with open(VFILE, "w") as f:
            f.write(remote)
        return True
    except Exception as e:
        log(f"update check skipped: {e}")
        return False


if __name__ == "__main__":
    print("updated" if maybe_update() else "no update")
