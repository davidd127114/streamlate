"""Streamlabs Desktop auto-setup — same zero-effort story as OBS.

Streamlabs replaced OBS's websocket with its own JSON-RPC API, reachable
locally on the named pipe \\\\.\\pipe\\slobs without a token. We use it to
create the Streamlate browser sources in the active scene. EXPERIMENTAL:
API shapes drift between Streamlabs versions — every call is defensive
and failure falls back to the manual one-source instruction."""
import json
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000
PIPE = r"\\.\pipe\slobs"
SLOBS_DIR = os.path.join(os.environ.get("APPDATA", ""), "slobs-client")


def installed():
    return os.path.isdir(SLOBS_DIR)


def running():
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True,
                             timeout=10,
                             creationflags=CREATE_NO_WINDOW).stdout.lower()
        return "streamlabs" in out
    except Exception:
        return False


class _Pipe:
    def __init__(self):
        self.f = open(PIPE, "r+b", buffering=0)
        self.n = 0

    def call(self, method, resource, args=None):
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method,
               "params": {"resource": resource}}
        if args is not None:
            msg["params"]["args"] = args
        self.f.write((json.dumps(msg) + "\n").encode("utf-8"))
        line = self.f.readline()
        out = json.loads(line.decode("utf-8", "replace"))
        if "error" in out:
            raise RuntimeError(str(out["error"])[:200])
        return out.get("result")

    def close(self):
        try:
            self.f.close()
        except OSError:
            pass


def reachable():
    try:
        p = _Pipe()
        p.close()
        return True
    except OSError:
        return False


def ensure_sources(log=print, chat_feed=False):
    """Create Streamlate's browser sources in Streamlabs' active scene.
    Returns True when sources exist (or were just made)."""
    try:
        p = _Pipe()
    except OSError:
        return False   # Streamlabs not running / pipe unavailable
    try:
        scene = p.call("activeScene", "ScenesService")
        if not isinstance(scene, dict) or "id" not in scene:
            raise RuntimeError("unexpected activeScene shape")
        sid = scene["id"]
        nodes = scene.get("nodes") or []
        names = {n.get("name", "") for n in nodes if isinstance(n, dict)}
        added = []
        if not names & {"Streamlate Captions", "PT Subtitles"}:
            p.call("createAndAddSource", f'Scene["{sid}"]',
                   ["Streamlate Captions", "browser_source",
                    {"url": "http://localhost:8788",
                     "width": 1400, "height": 300}])
            added.append("Captions")
        if chat_feed and "Streamlate Chat" not in names:
            p.call("createAndAddSource", f'Scene["{sid}"]',
                   ["Streamlate Chat", "browser_source",
                    {"url": "http://localhost:8765/obs",
                     "width": 1000, "height": 420}])
            added.append("Chat")
        if added:
            log("Streamlabs sources created automatically: "
                + ", ".join(added))
        return True
    except Exception as e:
        log(f"streamlabs auto-setup failed ({e}) — add the browser source "
            "manually: http://localhost:8788, 1400x300")
        return False
    finally:
        p.close()
