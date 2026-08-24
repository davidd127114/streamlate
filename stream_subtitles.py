"""Live stream subtitles: your mic (English) → Portuguese captions in OBS.
=========================================================================

Pipeline:  microphone → faster-whisper (local, CPU) → EN→PT translation
           (free Google endpoint) → local web page for an OBS Browser Source.

The captions render INSIDE OBS compositing, so nothing appears on your
desktop and the game's presentation path is untouched.

OBS setup (once):
    Sources → + → Browser
    URL:    http://localhost:8788
    Width:  1400    Height: 300
    Then drag the source anywhere on your canvas — captions hug its bottom
    edge. (Full-canvas size also works: captions sit bottom-center.)

Run:  "Start Stream Subtitles.bat"   (tray icon = green bubble)
Edit subs_config.json to change language, mic device, model, or look.
"""

import json
import os
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(APP_DIR, "subs.log")

# pythonw has no stdout/stderr — give prints (ours and AudioListener's) a home
if sys.stdout is None:
    sys.stdout = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = sys.stdout

from audio_listener import AudioListener  # local copy - mic capture + whisper


class TunedListener(AudioListener):
    """AudioListener with gamer-vocab hotwords and a configurable spoken
    language, so whisper hears slang right in any language."""
    hotwords = None
    language = "en"

    def _transcribe(self, audio):
        try:
            segments, _info = self.model.transcribe(
                audio, language=self.language, beam_size=1, vad_filter=True,
                hotwords=self.hotwords)
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            print("[mic] transcription error: %r" % e)
            return ""


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg), flush=True)


CONFIG_PATH = os.path.join(APP_DIR, "subs_config.json")
DEFAULTS = {
    "port": 8788,
    "spoken_lang": "en",       # what the streamer speaks
    "target_lang": "pt",       # what viewers read
    "model": "small.en",       # whisper size; small.en = sharper, still realtime
    "window_seconds": 2.0,     # caption cadence (lower = snappier, choppier)
    "use_gpu": True,           # 5090 transcribes in ~0.2s; GunZ leaves it idle
    "cpu_threads": 4,
    "pin_efficiency_cores": False,  # Intel hybrid CPUs only: keep off game P-cores
    "mic_device": None,        # sounddevice index, None = system default
    "mic_channel": None,       # 1-based channel, None = auto-pick loudest
    "silence_rms": 0.004,      # speech threshold; low is safe on a clean mic channel
    "show_english": False,     # also show the English line above the PT one
    "font_px": 42,
    "max_age_seconds": 7,      # how long a line stays on screen
    "translator": "ollama",    # "ollama" = local LLM (best quality), "google" = fastest
    "ollama_model": "qwen3.8:27b",
    "engine_url": "http://localhost:11434",
    # vocabulary whisper should be biased to hear correctly (add your own terms)
    "hotwords": "GG, clutch, elo, noob, buff, nerf, lag, spawn, rush, "
                "tryhard, ranked, respawn, loadout, Twitch, clip, chat",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass
    return cfg


def lower_priority():
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = wintypes.HANDLE
            k.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            if not k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000):
                log("priority drop failed")
        except Exception as e:
            log(f"priority drop failed: {e}")


def pin_to_efficiency_cores():
    """On the 14900K (8P+16E = 32 logical), confine this process to the
    E-cores (logical 16-31) so the game's P-cores are never touched."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        n = os.cpu_count() or 0
        if n != 32:
            log(f"E-core pin skipped: {n} logical CPUs (expected 32)")
            return
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetProcessAffinityMask.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
        if k.SetProcessAffinityMask(k.GetCurrentProcess(), 0xFFFF0000):
            log("pinned to E-cores 16-31")
        else:
            log("E-core pin failed")
    except Exception as e:
        log(f"E-core pin error: {e}")


# ---------------------------------------------------------------- translation

def _clients5(text, source, target):
    url = ("https://clients5.google.com/translate_a/t"
           f"?client=dict-chrome-ex&sl={source}&tl={target}&q="
           + urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    entry = data[0] if data else ""
    return entry[0] if isinstance(entry, list) else str(entry)


def _gtx(text, source, target):
    url = ("https://translate.googleapis.com/translate_a/single"
           f"?client=gtx&sl={source}&tl={target}&dt=t&q="
           + urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])


LANG_NAMES = {"en": "English", "pt": "Brazilian Portuguese", "es": "Spanish",
              "fr": "French", "de": "German", "ja": "Japanese",
              "ko": "Korean", "ru": "Russian", "zh": "Chinese"}

ENGINE_URL = "http://localhost:11434"  # local Ollama, or a rented GPU box

_ollama_state = {"warm": False, "cooldown_until": 0.0}


def _ollama_system(target, source="en"):
    lang = LANG_NAMES.get(target, target)
    src = LANG_NAMES.get(source, source)
    base = (f"You translate live stream captions from {src} to {lang}. "
            f"The streamer is a gamer talking casually to viewers. Write natural, "
            f"colloquial {lang} the way a native gamer actually talks. The text "
            "comes from live speech recognition and may contain small errors - "
            "translate the most likely intended meaning. Do not add words or "
            "excitement that are not in the original. Reply with ONLY the "
            "translation.")
    if target == "pt" and source == "en":
        base += (" Slang guide: bro/dude=mano; man=cara; chat/guys=galera; "
                 "insane/crazy=absurdo ou bizarro; trash=lixo; cracked=monstro; "
                 "throwing=jogando fora; clip it=clipa isso. Keep these in "
                 "English exactly as said: GG, clutch, lag, buff, nerf, elo, "
                 "rank, noob, spawn, rush, tryhard, k-style, slashshot, "
                 "butterfly, reload shot, PPQ. Examples: 'that spray was insane "
                 "bro' -> 'esse spray foi absurdo, mano'; 'chat, we are so "
                 "back' -> 'galera, voltamos com tudo'; 'he is throwing so "
                 "hard' -> 'ele tá jogando fora demais'.")
    return base


def _ollama(text, target, model, timeout=12, source="en"):
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [{"role": "system",
                      "content": _ollama_system(target, source)},
                     {"role": "user", "content": text}],
        "options": {"temperature": 0.2, "num_predict": 150},
        "keep_alive": "2h", "think": False,
    }).encode("utf-8")
    req = urllib.request.Request(ENGINE_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out["message"]["content"].strip().strip('"')


def warm_ollama(cfg):
    """Load the LLM into VRAM in the background; Google covers the gap."""
    try:
        _ollama("Warm up.", cfg["target_lang"], cfg["ollama_model"],
                timeout=300, source=cfg.get("spoken_lang", "en"))
        _ollama_state["warm"] = True
        log(f"ollama {cfg['ollama_model']} warm — best-quality translation active")
    except Exception as e:
        log(f"ollama warmup failed ({e}) — staying on google")


def translate(text, target, cfg=None):
    source = (cfg or {}).get("spoken_lang", "en")
    if cfg and cfg.get("translator") == "ollama" and _ollama_state["warm"]:
        if time.time() >= _ollama_state["cooldown_until"]:
            try:
                return _ollama(text, target, cfg["ollama_model"],
                               source=source)
            except Exception as e:
                log(f"ollama failed ({e}) — google fallback for 60s")
                _ollama_state["cooldown_until"] = time.time() + 60
    try:
        return _clients5(text, source, target)
    except Exception as e:
        log(f"clients5 failed ({e}), trying gtx")
        return _gtx(text, source, target)


# ---------------------------------------------------------------- subtitle feed

class SubtitleStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.lines = deque(maxlen=6)
        self.next_id = 1

    def add(self, en, translated):
        with self.lock:
            self.lines.append({"id": self.next_id, "en": en,
                               "tr": translated, "t": time.time()})
            self.next_id += 1

    def recent(self, max_age):
        now = time.time()
        with self.lock:
            return [{"id": l["id"], "en": l["en"], "tr": l["tr"],
                     "age": round(now - l["t"], 1)}
                    for l in self.lines if now - l["t"] <= max_age]


OBS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>subs</title>
<style>
 * { margin:0; padding:0; }
 body { background:transparent; overflow:hidden;
        font-family:'Segoe UI',system-ui,sans-serif; }
 #wrap { position:fixed; left:50%; bottom:3.5%; transform:translateX(-50%);
         width:72%; text-align:center; }
 .line { display:inline-block; background:rgba(0,0,0,0.55); color:#fff;
         font-size:__FONT__px; line-height:1.35; font-weight:600;
         padding:6px 22px; border-radius:14px; margin-top:8px;
         text-shadow:0 2px 6px rgba(0,0,0,0.9);
         animation:pop 0.18s ease-out; }
 .en { font-size:__FONT_EN__px; opacity:0.75; font-weight:400; }
 @keyframes pop { from { opacity:0; transform:translateY(10px); }
                  to   { opacity:1; transform:none; } }
</style></head>
<body><div id="wrap"></div>
<script>
const MAX_AGE = __MAX_AGE__, SHOW_EN = __SHOW_EN__;
const wrap = document.getElementById('wrap');
let shown = "";
function esc(s){ const d = document.createElement('span'); d.textContent = s; return d.innerHTML; }
async function tick(){
  try {
    const r = await fetch('/subs.json');
    const j = await r.json();
    const lines = j.lines.filter(l => l.age <= MAX_AGE).slice(-2);
    const key = lines.map(l => l.id).join(',');
    if (key !== shown){
      shown = key;
      wrap.innerHTML = lines.map(l =>
        (SHOW_EN ? '<div class="line en">' + esc(l.en) + '</div><br>' : '')
        + '<div class="line">' + esc(l.tr) + '</div><br>').join('');
    }
  } catch (e) {}
  setTimeout(tick, 300);
}
tick();
</script></body></html>"""


class SubsHandler(BaseHTTPRequestHandler):
    store = None
    cfg = None
    protocol_version = "HTTP/1.1"   # keep-alive: OBS reuses one connection

    def log_message(self, *args):
        pass

    def _reply(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == "/" or self.path.startswith("/index"):
                html = (OBS_HTML
                        .replace("__FONT__", str(self.cfg["font_px"]))
                        .replace("__FONT_EN__", str(int(self.cfg["font_px"] * 0.6)))
                        .replace("__MAX_AGE__", str(self.cfg["max_age_seconds"]))
                        .replace("__SHOW_EN__",
                                 "true" if self.cfg["show_english"] else "false"))
                self._reply(html.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path.startswith("/subs.json"):
                body = json.dumps(
                    {"lines": self.store.recent(self.cfg["max_age_seconds"] + 3)}
                ).encode("utf-8")
                self._reply(body, "application/json")
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionError, ValueError):
            pass


def run_tray(cfg):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        log("pystray missing — no tray icon")
        while True:
            time.sleep(3600)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 8, 58, 46), radius=12, fill="#34c98e")
    d.polygon([(18, 44), (34, 44), (18, 60)], fill="#34c98e")
    d.rectangle((16, 22, 48, 26), fill="white")
    d.rectangle((20, 32, 44, 36), fill="white")

    url = f"http://localhost:{cfg['port']}"

    def open_page(icon, item):
        import webbrowser
        webbrowser.open(url)

    def quit_app(icon, item):
        icon.stop()

    icon = pystray.Icon(
        "stream_subtitles", img,
        f"Stream Subtitles → {cfg['target_lang'].upper()} · OBS source: {url}",
        menu=pystray.Menu(
            pystray.MenuItem(f"OBS Browser Source: {url}", None, enabled=False),
            pystray.MenuItem("Preview captions page", open_page),
            pystray.MenuItem("Exit", quit_app),
        ))
    icon.run()
    os._exit(0)


def main():
    global ENGINE_URL
    lower_priority()
    cfg = load_config()
    ENGINE_URL = cfg.get("engine_url") or ENGINE_URL
    if cfg["pin_efficiency_cores"]:
        pin_to_efficiency_cores()
    store = SubtitleStore()

    handler = type("BoundSubs", (SubsHandler,), {"store": store, "cfg": cfg})
    srv = ThreadingHTTPServer(("127.0.0.1", cfg["port"]), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"OBS captions page: http://localhost:{cfg['port']}")

    if cfg["translator"] == "ollama":
        threading.Thread(target=warm_ollama, args=(cfg,), daemon=True).start()

    last_line = ""

    def on_transcript(text):
        nonlocal last_line
        text = text.strip()
        if len(text) < 2 or text == last_line:
            return
        last_line = text
        if cfg.get("spoken_lang", "en") == cfg["target_lang"]:
            store.add(text, text)   # captions-only mode, no translation
            log(f"CAPTION: {text}")
            return
        try:
            translated = translate(text, cfg["target_lang"], cfg)
        except Exception as e:
            log(f"translate failed: {e}")
            return
        store.add(text, translated)
        log(f"EN: {text}  →  {cfg['target_lang'].upper()}: {translated}")

    listener = TunedListener(
        on_transcript=on_transcript,
        model_size=cfg["model"],
        window_seconds=cfg["window_seconds"],
        silence_rms=cfg["silence_rms"],
        device=cfg["mic_device"],
        channel=cfg["mic_channel"],
    )
    listener.hotwords = cfg["hotwords"] or None
    listener.language = cfg.get("spoken_lang", "en")
    if listener.language != "en" and cfg["model"].endswith(".en"):
        # English-only whisper can't hear other languages — use multilingual
        cfg["model"] = cfg["model"][:-3]
        listener.model_size = cfg["model"]
        log(f"non-English speaker: whisper model switched to '{cfg['model']}'")
    if not cfg["use_gpu"]:
        # force CPU so the game's GPU is never touched
        from faster_whisper import WhisperModel
        listener.model = WhisperModel(cfg["model"], device="cpu",
                                      compute_type="int8",
                                      cpu_threads=cfg["cpu_threads"])
        listener.device_used = "cpu"
        log(f"whisper '{cfg['model']}' forced onto CPU (int8, "
            f"{cfg['cpu_threads']} threads)")
    listener.start()
    run_tray(cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
