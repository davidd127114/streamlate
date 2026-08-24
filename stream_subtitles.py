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

try:
    from audio_listener import AudioListener  # local copy - mic capture
except Exception as _e:   # broken pip install etc. — say so in plain words
    print(f"FATAL: audio engine failed to load ({_e!r}). "
          "Re-run install.bat (or StreamlateSetup.exe) to repair packages.")
    raise


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
    # voice-chat translation (Discord etc.) — hears what your PC plays
    "call_translate": False,
    "call_model": "small",       # multilingual whisper for teammates
    "call_device": "",           # part of an output device name; "" = default
    "call_target": "en",         # language YOU read the bubbles in
    "call_show_english": False,
    "call_silence_rms": 0.003,
    "quality": "auto",           # auto | light | tiny | zero — see quality.py
    "speak_to_viewers": True,    # your translated voice as rows in the
                                 # viewer chat feed (no bot login needed)
    "family_filter": False,      # censor profanity on viewer-facing output
    "save_srt": True,            # write session subtitles as .srt for VODs
    "call_on_stream": False,     # caption voice-chat (Discord) on stream too
    "obs_cc": False,             # push native platform captions (CC button)
    "obs_ws_password": "",       # OBS Tools → WebSocket Server Settings
}


# ------------------------------------------- native CC via OBS websocket
CC = {"cl": None, "dead": False}


def send_native_cc(cfg, text):
    """Twitch's player CC button: viewers toggle captions themselves and
    they persist into the VOD. Rides OBS's SendStreamCaption request."""
    if CC["dead"] or not text:
        return
    try:
        if CC["cl"] is None:
            from obs_link import effective_password
            import obsws_python as obs
            CC["cl"] = obs.ReqClient(host="localhost", port=4455,
                                     password=effective_password(cfg),
                                     timeout=5)
            log("native CC: connected to OBS websocket")
        CC["cl"].send_stream_caption(text[:480])
    except Exception as e:
        log(f"native CC unavailable ({e}) — check OBS Tools → WebSocket "
            "Server Settings and the password in Streamlate settings")
        CC["dead"] = True


# ------------------------------------------------------------- SRT session log
SRT = {"t0": None, "rows": [], "base": ""}


def _fmt_srt_time(sec):
    ms = int(sec * 1000)
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"


def srt_log(cfg, original, translated):
    """Append a caption to the session SRT files (original + translated)."""
    if not cfg.get("save_srt", True):
        return
    now = time.time()
    if SRT["t0"] is None:
        SRT["t0"] = now
        os.makedirs(os.path.join(APP_DIR, "subtitles"), exist_ok=True)
        SRT["base"] = os.path.join(
            APP_DIR, "subtitles",
            "stream_" + time.strftime("%Y-%m-%d_%H%M", time.localtime(now)))
    SRT["rows"].append((now - SRT["t0"], original, translated))
    try:
        for idx, lang in ((1, cfg.get("spoken_lang", "en")),
                          (2, cfg["target_lang"])):
            path = f"{SRT['base']}.{lang}{'' if idx == 1 else '.translated'}.srt"
            with open(path, "w", encoding="utf-8") as f:
                for i, (t, en, tr) in enumerate(SRT["rows"], 1):
                    nxt = (SRT["rows"][i][0] if i < len(SRT["rows"])
                           else t + max(2.0, len(en) / 15))
                    end = min(nxt - 0.05, t + 7.0)
                    text = en if idx == 1 else tr
                    f.write(f"{i}\n{_fmt_srt_time(t)} --> "
                            f"{_fmt_srt_time(end)}\n{text}\n\n")
    except OSError as e:
        log(f"srt write failed: {e}")


def inject_streamer_line(text, translated, channel):
    """Push the streamer's translated speech into the viewer chat feed as a
    chat-style row (obs_only: never echoes on the private overlay/phone)."""
    body = json.dumps({"user": "🎤 " + (channel or "streamer"),
                       "color": "#c9a2ff", "text": text, "tr2": translated,
                       "obs_only": True}).encode("utf-8")
    for port in range(8765, 8771):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/inject", data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            continue
    return False


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


_CHANNEL = {"name": ""}


def _channel_name():
    if not _CHANNEL["name"]:
        try:
            with open(os.path.join(APP_DIR, "config.json"),
                      encoding="utf-8-sig") as f:
                ch = json.load(f).get("channel", "")
            _CHANNEL["name"] = ch.rstrip("/").split("/")[-1].lstrip("@#") \
                or "streamer"
        except (OSError, ValueError):
            _CHANNEL["name"] = "streamer"
    return _CHANNEL["name"]


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
              "ko": "Korean", "ru": "Russian", "zh": "Chinese",
              "he": "Hebrew", "pl": "Polish", "ar": "Arabic",
              "it": "Italian", "nl": "Dutch", "tr": "Turkish",
              "hi": "Hindi", "id": "Indonesian", "vi": "Vietnamese",
              "th": "Thai", "uk": "Ukrainian", "cs": "Czech",
              "sv": "Swedish", "ro": "Romanian", "el": "Greek",
              "hu": "Hungarian", "da": "Danish", "fi": "Finnish",
              "no": "Norwegian", "bg": "Bulgarian", "ms": "Malay"}

# languages where whisper's 'small' struggles — bump to 'medium' on GPU
HARD_SPEECH = {"he", "ja", "ko", "zh", "ru", "pl", "ar", "hi", "th",
               "vi", "uk", "el", "bg", "auto"}

ENGINE_URL = "http://localhost:11434"  # local Ollama, or a rented GPU box

_ollama_state = {"warm": False, "cooldown_until": 0.0}


def _ollama_system(target, source="en"):
    lang = LANG_NAMES.get(target, target)
    if source in (None, "", "auto"):
        return (f"You translate live gaming voice-chat lines into {lang}. "
                "The speakers are gamers talking casually. The text comes "
                "from speech recognition and may contain small errors - "
                "translate the most likely intended meaning naturally. "
                "Reply with ONLY the translation.")
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


def call_translate(text, target, cfg):
    """Auto-source translation for voice-chat lines (language unknown)."""
    if cfg.get("translator") == "ollama" and _ollama_state["warm"]:
        if time.time() >= _ollama_state["cooldown_until"]:
            try:
                return _ollama(text, target, cfg["ollama_model"],
                               source="auto")
            except Exception as e:
                log(f"call ollama failed ({e}) — google fallback")
                _ollama_state["cooldown_until"] = time.time() + 60
    try:
        return _clients5(text, "auto", target)
    except Exception:
        return _gtx(text, "auto", target)


CALL = {"listener": None}


def start_call(cfg, caption_cb=None):
    from call_audio import CallListener
    if CALL["listener"]:
        return
    CALL["listener"] = CallListener(cfg, call_translate, log)
    CALL["listener"].caption_cb = caption_cb or CALL.get("cb")
    CALL["listener"].start()


def stop_call():
    if CALL["listener"]:
        CALL["listener"].stop()
        CALL["listener"] = None


def translate(text, target, cfg=None):
    source = (cfg or {}).get("spoken_lang", "en")
    if source == "auto":
        return call_translate(text, target, cfg or {})
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
 .line { display:inline-block; unicode-bidi:plaintext;
         background:rgba(0,0,0,0.55); color:#fff;
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


def ensure_obs_sources(cfg):
    """If OBS is running and its websocket is reachable, create Streamlate's
    browser sources automatically (sized to the actual canvas, captions
    placed bottom-center). Existing sources are never touched — dragging
    stays sacred. Silently skips when OBS is closed or websocket is off."""
    import contextlib
    import io as _io
    try:
        from obs_link import autolink
        import obsws_python as obs
        with contextlib.redirect_stderr(_io.StringIO()):
            cl = obs.ReqClient(host="localhost", port=4455,
                               password=autolink(cfg, log), timeout=4)
    except Exception:
        return False   # OBS closed / websocket off — manual setup still works
    try:
        scene = cl.get_current_program_scene().current_program_scene_name
        names = [i["sourceName"]
                 for i in cl.get_scene_item_list(scene).scene_items]
        v = cl.get_video_settings()
        W, H = int(v.base_width), int(v.base_height)
        added = []
        has_caps = any(n in ("Streamlate Captions", "PT Subtitles")
                       for n in names)
        if not has_caps:
            w = min(1400, W)
            cl.create_input(scene, "Streamlate Captions", "browser_source",
                            {"url": "http://localhost:8788",
                             "width": w, "height": 300}, True)
            try:
                iid = [i["sceneItemId"] for i in
                       cl.get_scene_item_list(scene).scene_items
                       if i["sourceName"] == "Streamlate Captions"][0]
                cl.set_scene_item_transform(
                    scene, iid, {"positionX": (W - w) / 2,
                                 "positionY": H - 330})
            except Exception:
                pass
            added.append("Captions")
        if cfg.get("obs_chat_enabled") and "Streamlate Chat" not in names:
            cl.create_input(scene, "Streamlate Chat", "browser_source",
                            {"url": "http://localhost:8765/obs",
                             "width": 1000, "height": 420}, True)
            added.append("Chat")
        if added:
            log("OBS sources created automatically: " + ", ".join(added))
        return True    # done — sources exist (or just made); stop retrying
    except Exception as e:
        log(f"obs auto-setup skipped ({e})")
        return False


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

    from i18n import tr

    from quality import set_quality

    def pick_quality(tier):
        return lambda icon, item: set_quality(tier, APP_DIR, ENGINE_URL, log)

    def q_checked(tier):
        return lambda item: cfg.get("quality", "auto") == tier

    quality_menu = pystray.Menu(
        pystray.MenuItem(tr("q_auto"), pick_quality("auto"),
                         radio=True, checked=q_checked("auto")),
        pystray.MenuItem(tr("q_light"), pick_quality("light"),
                         radio=True, checked=q_checked("light")),
        pystray.MenuItem(tr("q_tiny"), pick_quality("tiny"),
                         radio=True, checked=q_checked("tiny")),
        pystray.MenuItem(tr("q_zero"), pick_quality("zero"),
                         radio=True, checked=q_checked("zero")),
    )

    def open_settings(icon, item):
        import subprocess
        subprocess.run([sys.executable,
                        os.path.join(APP_DIR, "setup_wizard.py")], cwd=APP_DIR)
        subprocess.Popen([sys.executable,
                          os.path.join(APP_DIR, "stream_mode_launcher.py")],
                         cwd=APP_DIR)

    def toggle_call(icon, item):
        cfg["call_translate"] = not cfg.get("call_translate")
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except OSError:
            pass
        if cfg["call_translate"]:
            start_call(cfg)
        else:
            stop_call()

    icon = pystray.Icon(
        "streamlate_subs", img,
        f"Streamlate → {cfg['target_lang'].upper()} · OBS: {url}",
        menu=pystray.Menu(
            pystray.MenuItem(f"{tr('obs_source')}: {url}", None, enabled=False),
            pystray.MenuItem(tr("preview"), open_page),
            pystray.MenuItem(tr("calltr"), toggle_call,
                             checked=lambda item: bool(cfg.get("call_translate"))),
            pystray.MenuItem(tr("q_menu"), quality_menu),
            pystray.MenuItem(tr("settings"), open_settings),
            pystray.MenuItem(tr("exit"), quit_app),
        ))
    icon.run()
    os._exit(0)


def main():
    global ENGINE_URL
    lower_priority()
    from quality import apply_quality
    cfg = apply_quality(load_config(), for_subs=True)
    if cfg["quality"] != "auto":
        log(f"quality tier: {cfg['quality']}")
    ENGINE_URL = cfg.get("engine_url") or ENGINE_URL
    if cfg["pin_efficiency_cores"]:
        pin_to_efficiency_cores()
    store = SubtitleStore()

    class ExclusiveServer(ThreadingHTTPServer):
        allow_reuse_address = False   # never share a port with another copy

    from port_guard import free_port
    free_port(int(cfg["port"]), "stream_subtitles", log)
    handler = type("BoundSubs", (SubsHandler,), {"store": store, "cfg": cfg})
    srv = None
    for attempt in range(3):
        try:
            srv = ExclusiveServer(("127.0.0.1", cfg["port"]), handler)
            break
        except OSError as e:
            log(f"caption port bind failed ({e}) — retry {attempt + 1}/3")
            time.sleep(4)
    if srv is None:
        log("FATAL: caption port unavailable — is another app on 8788?")
        raise SystemExit(1)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"OBS captions page: http://localhost:{cfg['port']}")

    if cfg["translator"] == "ollama":
        threading.Thread(target=warm_ollama, args=(cfg,), daemon=True).start()

    def obs_setup_loop():
        # OBS may start after Streamlate — keep offering for a while
        for _ in range(30):
            if ensure_obs_sources(cfg):
                return
            time.sleep(20)
    threading.Thread(target=obs_setup_loop, daemon=True).start()

    last_line = ""

    def on_transcript(text):
        nonlocal last_line
        text = text.strip()
        if len(text) < 2 or text == last_line:
            return
        last_line = text
        if cfg.get("spoken_lang", "en") == cfg["target_lang"]:
            shown = text
            if cfg.get("family_filter"):
                from profanity import censor
                shown = censor(text, APP_DIR)
            store.add(shown, shown)   # captions-only mode, no translation
            srt_log(cfg, shown, shown)
            if cfg.get("obs_cc"):
                send_native_cc(cfg, shown)
            log(f"CAPTION: {shown}")
            return
        try:
            translated = translate(text, cfg["target_lang"], cfg)
        except Exception as e:
            log(f"translate failed: {e}")
            return
        shown_orig, shown_tr = text, translated
        if cfg.get("family_filter"):
            from profanity import censor
            shown_orig = censor(text, APP_DIR)
            shown_tr = censor(translated, APP_DIR)
        store.add(shown_orig, shown_tr)
        srt_log(cfg, shown_orig, shown_tr)
        if cfg.get("obs_cc"):
            send_native_cc(cfg, shown_tr)
        log(f"EN: {text}  →  {cfg['target_lang'].upper()}: {translated}")
        if cfg.get("speak_to_viewers") and len(text) >= 12:
            try:
                inject_streamer_line(shown_orig, shown_tr, _channel_name())
            except Exception:
                pass

    listener = TunedListener(
        on_transcript=on_transcript,
        model_size=cfg["model"],
        window_seconds=cfg["window_seconds"],
        silence_rms=cfg["silence_rms"],
        device=cfg["mic_device"],
        channel=cfg["mic_channel"],
    )
    listener.hotwords = cfg["hotwords"] or None
    spoken = cfg.get("spoken_lang", "en")
    listener.language = None if spoken == "auto" else spoken
    if spoken != "en" and cfg["model"].endswith(".en"):
        # English-only whisper can't hear other languages — use multilingual
        cfg["model"] = cfg["model"][:-3]
        listener.model_size = cfg["model"]
        log(f"non-English speaker: whisper model switched to '{cfg['model']}'")
    if (spoken in HARD_SPEECH and cfg["use_gpu"]
            and cfg["model"] in ("base", "small")):
        cfg["model"] = "medium"   # noticeably better for these languages
        listener.model_size = "medium"
        log(f"'{spoken}' speech: whisper bumped to 'medium'")
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

    def call_caption(text, translated):
        """Teammate voices captioned on stream, labeled — no tool on the
        market does this (deaf/HoH collab requests go unanswered)."""
        if not cfg.get("call_on_stream"):
            return
        line_o, line_t = "🎧 " + text, "🎧 " + translated
        if cfg.get("family_filter"):
            from profanity import censor
            line_o = censor(line_o, APP_DIR)
            line_t = censor(line_t, APP_DIR)
        store.add(line_o, line_t)
        srt_log(cfg, line_o, line_t)
        if cfg.get("obs_cc"):
            send_native_cc(cfg, line_t)

    CALL["cb"] = call_caption
    if cfg.get("call_translate"):
        start_call(cfg, call_caption)
    run_tray(cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
