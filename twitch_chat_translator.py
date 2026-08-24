"""Twitch Chat Translator
========================

Reads any Twitch channel's chat anonymously (no login, no API key) and shows
non-English messages translated to English in a small always-on-top window.

Translation uses the free Google Translate web endpoint over HTTPS —
zero GPU / zero local model load, so it never competes with a game.

Usage:
    python twitch_chat_translator.py [channel]
    (first run without an argument asks for the channel and remembers it)

Hotkeys:
    Ctrl + MouseWheel   font size up/down
    Ctrl + T            toggle always-on-top
    Ctrl + O            show/hide the original-language line
    Ctrl + N            switch channel
"""

import difflib
import json
import os
import queue
import random
import re
import socket
import ssl
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tkinter as tk
from tkinter import simpledialog

from i18n import tr

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "translator.log")

DEFAULTS = {
    "channel": "",
    "platform": "auto",   # auto | twitch | youtube | kick (auto sniffs the channel)
    "font_size": 12,
    "opacity": 0.97,
    "topmost": True,
    "show_original": True,
    "geometry": "460x640+60+60",
    "ollama_model": "qwen3.8:27b",
    "engine_url": "http://localhost:11434",
    "pin_efficiency_cores": False,
    "http_port": 8765,
    "overlay_opacity": 0.85,
    "overlay_corner": 1,          # 0=top-left 1=top-right 2=bottom-right 3=bottom-left
    "overlay_size": "420x270",
    "overlay_pos": "",            # custom "+x+y" from Move mode; empty = corner
    "overlay_autohide": False,
    "overlay_ghost": True,    # fade near-invisible when the mouse is over it
    "background_dim": 0.35,   # brightness of the custom background image
    "quality": "auto",        # auto | light | tiny | zero — see quality.py
    "obs_chat_enabled": False,   # translated chat feed for VIEWERS (OBS source)
    "obs_chat_lang": "pt",       # language your audience reads chat in
}

OVERLAY_CORNERS = ["+16+16", "-16+16", "-16-16", "+16-16"]

ENGINE_URL = "http://localhost:11434"  # local Ollama, or a rented GPU box


def find_background(folder):
    """User drops background.png/jpg in the app folder — that's the whole
    feature. Used by both the overlay and the phone page."""
    for name in ("background.png", "background.jpg", "background.jpeg",
                 "background.webp"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return None


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg) + "\n")
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        log(f"config save failed: {e}")


# --------------------------------------------------------------------------
# Translation
# --------------------------------------------------------------------------

# Common BR-Portuguese chat abbreviations expanded before translating so the
# translator actually understands them. Applied on standalone words only.
SLANG = {
    "vc": "você", "vcs": "vocês", "tb": "também", "tbm": "também",
    "pq": "porque", "q": "que", "n": "não", "nn": "não", "naum": "não",
    "mt": "muito", "mto": "muito", "mta": "muita", "blz": "beleza",
    "vlw": "valeu", "flw": "falou", "cmg": "comigo", "ctg": "contigo",
    "hj": "hoje", "dps": "depois", "agr": "agora", "msm": "mesmo",
    "tmj": "tamo junto", "sla": "sei lá", "mds": "meu Deus",
    "pfv": "por favor", "obg": "obrigado", "oq": "o que", "td": "tudo",
    "tds": "todos", "qnd": "quando", "ngm": "ninguém", "nd": "nada",
    "gnt": "gente", "dnv": "de novo", "sdds": "saudades", "aki": "aqui",
    "eh": "é", "neh": "né", "vdd": "verdade", "pdp": "pode pá",
    "tlgd": "tá ligado", "slc": "se lascou", "fzr": "fazer", "fla": "fala",
    # Spanish
    "xq": "porque", "tmb": "también", "bn": "bien", "xfa": "por favor",
    "ntp": "no te preocupes", "nmms": "no manches", "kiubo": "qué hubo",
    "tqm": "te quiero mucho", "grax": "gracias", "salu2": "saludos",
    # French
    "mdr": "mort de rire", "ptdr": "pété de rire", "bcp": "beaucoup",
    "slt": "salut", "jsp": "je sais pas", "jpp": "j'en peux plus",
    "pk": "pourquoi", "qqn": "quelqu'un", "stp": "s'il te plaît",
    # German
    "vlt": "vielleicht", "kp": "kein Plan", "ka": "keine Ahnung",
    "hdl": "hab dich lieb", "gn8": "gute Nacht",
    # Polish
    "nwm": "nie wiem", "wgl": "w ogóle", "spk": "spoko", "cb": "ciebie",
    "sb": "sobie", "zw": "zaraz wracam", "jj": "już jestem",
    "nara": "na razie", "pzdr": "pozdrawiam", "wgle": "w ogóle",
}
_slang_re = re.compile(
    r"\b(" + "|".join(sorted(SLANG, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Laughter/emote-spam in any language needs no translation:
# kkkk jajaja jsjsjs rsrs hahaha hehe huehue xaxaxa xD lol lmao kekw
# wwww(JP) 草(JP) ㅋㅋ/ㅎㅎ(KR) хахах/ахах(RU) חחחח(HE)
LAUGH_RE = re.compile(
    r"(?i)^\W*(?:"
    r"k{2,}|(?:ja){2,}j*|(?:js){2,}s*|(?:rs){2,}|(?:ha){2,}h*|(?:he){2,}h*|"
    r"(?:hue){2,}|(?:xa){2,}x*|x+d+|l+o+l+|lmf?ao+|kek(?:w|a)?|omegalul|lul+|"
    r"w{3,}|ｗ{2,}|草+|笑+|哈{2,}|嘿{2,}|ㅋ{2,}|ㅎ{2,}|"
    r"(?:ах){2,}х*|(?:ха){2,}х*|(?:хе){2,}х*|ח{2,}|(?:xd){2,}"
    r")\W*$"
)

URL_RE = re.compile(r"^https?://\S+$")


def normalize_slang(text):
    return _slang_re.sub(lambda m: SLANG[m.group(1).lower()], text)


def translate_clients5(text):
    """Google's dict-chrome-ex endpoint. Returns (translation, detected_lang).
    Separate rate-limit bucket from the gtx endpoint — survives CGNAT."""
    url = (
        "https://clients5.google.com/translate_a/t"
        "?client=dict-chrome-ex&sl=auto&tl=en&q=" + urllib.parse.quote(text)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    entry = data[0] if data else ""
    if isinstance(entry, list):
        translation = entry[0] if entry else ""
        detected = entry[1] if len(entry) > 1 else ""
    else:
        translation, detected = str(entry), ""
    return translation, detected


def translate_gtx(text):
    """Free Google Translate web endpoint. Returns (translation, detected_lang)."""
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=auto&tl=en&dt=t&q=" + urllib.parse.quote(text)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    translation = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])
    detected = data[2] if len(data) > 2 and data[2] else ""
    return translation, detected


OLLAMA_SYSTEM = (
    "You translate live Twitch chat messages into English. If a message is "
    "already entirely English, reply with exactly SKIP. Otherwise reply with "
    "ONLY the English translation - no quotes, no notes. Messages can be in "
    "any language; Brazilian Portuguese gamer slang is the most common - "
    "translate slang naturally (mano=bro, cara=dude, mds=omg, tmj=we're "
    "together, monstro=beast/cracked). Keep emote words, usernames, kkkk "
    "laughter and game terms (KEKW, slashshot, gg) unchanged. Examples: "
    "'mano esse jogo eh mt bom kkkk' -> 'bro this game is so good kkkk'; "
    "'o cara é monstro demais' -> 'the guy is such a beast'."
)

_ollama_chat = {"warm": False}

CHAT_LANG_NAMES = {"en": "English", "pt": "Brazilian Portuguese",
                   "es": "Spanish", "fr": "French", "de": "German",
                   "ja": "Japanese", "ko": "Korean", "ru": "Russian",
                   "zh": "Chinese", "he": "Hebrew", "pl": "Polish"}


def translate_ollama_to(text, model, target, timeout=12):
    """LLM translation of a chat message into ANY language (viewer feed).
    Same quality rules as the streamer's own translation."""
    lang = CHAT_LANG_NAMES.get(target, target)
    system = (
        f"You translate live stream chat messages into {lang}. If a message "
        f"is already entirely in {lang}, reply with exactly SKIP. Otherwise "
        f"reply with ONLY the {lang} translation - no quotes, no notes. "
        "Translate slang naturally for a gamer audience. Keep emote words, "
        "usernames, kkkk laughter and gaming terms (GG, clutch, lag, skin, "
        "buff, nerf, elo) unchanged."
    )
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}],
        "options": {"temperature": 0.2, "num_predict": 150},
        "keep_alive": "2h", "think": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENGINE_URL + "/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    result = out["message"]["content"].strip().strip('"')
    return None if result == "SKIP" else result


def warm_chat_ollama(cfg):
    """Load the chat LLM in the background; Google covers until it's warm."""
    if cfg.get("quality") == "zero":
        log("zero-GPU tier: chat stays on google, LLM never loaded")
        return
    try:
        translate_ollama("Aquecendo o modelo.", cfg["ollama_model"], timeout=300)
        _ollama_chat["warm"] = True
        log(f"chat ollama {cfg['ollama_model']} warm — best-quality chat translation")
    except Exception as e:
        log(f"chat ollama warmup failed ({e}) — staying on google")


def translate_ollama(text, model, timeout=12):
    """Local LLM translation — best slang handling, no rate limits.
    Returns (translation, detected_lang)."""
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [
            {"role": "system", "content": OLLAMA_SYSTEM},
            {"role": "user", "content": text},
        ],
        "options": {"temperature": 0.2, "num_predict": 150},
        "keep_alive": "2h", "think": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENGINE_URL + "/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    translation = out["message"]["content"].strip().strip('"')
    if translation == "SKIP":
        return "", "en"
    return translation, ""


ENGINES = [
    ("local", lambda text, cfg: translate_ollama(text, cfg["ollama_model"])),
    ("google", lambda text, cfg: translate_clients5(text)),
    ("google2", lambda text, cfg: translate_gtx(text)),
]


class TranslateWorker(threading.Thread):
    """Takes raw chat messages, decides whether translation is needed, emits
    (user, color, text, translation_or_None) to the UI queue."""

    def __init__(self, in_q, out_q, cfg, history=None):
        super().__init__(daemon=True)
        self.in_q = in_q
        self.out_q = out_q
        self.cfg = cfg
        self.history = history
        self.cache = OrderedDict()
        self.cooldown = {}          # engine name -> retry-after timestamp
        self.active_engine = None

    def run(self):
        while True:
            item = self.in_q.get()
            if item is None:
                return
            user, color, text = item
            try:
                translation = self.decide(text)
            except Exception as e:  # never die on one bad message
                log(f"translate worker error: {e}")
                translation = None
            tr2 = None
            if self.cfg.get("obs_chat_enabled"):
                try:
                    tr2 = self.viewer_translate(text)
                except Exception:
                    tr2 = None
            if self.history is not None:
                self.history.add(user, display_color(user, color), text,
                                 translation, tr2)
            self.out_q.put(("chat", user, color, text, translation))

    def viewer_translate(self, text):
        """Second direction: the whole chat into the AUDIENCE's language,
        for the on-stream feed. Same engine priority as everything else:
        local LLM first, free web engine as fallback."""
        t = text.strip()
        if len(t) < 2 or LAUGH_RE.match(t) or URL_RE.match(t):
            return None
        lang = self.cfg.get("obs_chat_lang", "pt")
        key = "v:" + t.lower()
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key][0]
        if (_ollama_chat["warm"] and self.cfg.get("quality") != "zero"
                and self.in_q.qsize() <= 5
                and time.time() >= self.cooldown.get("local", 0)):
            try:
                tr2 = translate_ollama_to(normalize_slang(t),
                                          self.cfg["ollama_model"], lang)
                if tr2 and difflib.SequenceMatcher(
                        None, tr2.lower(), t.lower()).ratio() > 0.92:
                    tr2 = None
                self.cache[key] = (tr2, "")
                if len(self.cache) > 800:
                    self.cache.popitem(last=False)
                return tr2
            except Exception as e:
                log(f"viewer llm failed ({e}) — google fallback")
        try:
            url = ("https://clients5.google.com/translate_a/t"
                   f"?client=dict-chrome-ex&sl=auto&tl={lang}&q="
                   + urllib.parse.quote(normalize_slang(t)))
            req = urllib.request.Request(url,
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
            entry = data[0] if data else ""
            tr2, detected = ((entry[0], entry[1] if len(entry) > 1 else "")
                             if isinstance(entry, list) else (str(entry), ""))
            if detected == lang or not tr2:
                tr2 = None
        except Exception:
            return None
        self.cache[key] = (tr2, "")
        if len(self.cache) > 800:
            self.cache.popitem(last=False)
        return tr2

    def translate_any(self, text):
        last_err = None
        for name, fn in ENGINES:
            if name == "local" and (self.cfg.get("quality") == "zero"
                                    or not _ollama_chat["warm"]
                                    or self.in_q.qsize() > 5):
                continue  # zero tier, not loaded, or flooding — use google
            if time.time() < self.cooldown.get(name, 0):
                continue
            try:
                result = fn(text, self.cfg)
            except Exception as e:
                last_err = e
                log(f"engine {name.strip()} failed: {e}")
                self.cooldown[name] = time.time() + 90
                continue
            if self.active_engine != name:
                self.active_engine = name
                self.out_q.put(("status_hint", f"translation engine: {name.strip()}"))
            return result
        raise last_err or RuntimeError("all translation engines on cooldown")

    def decide(self, text):
        t = text.strip()
        if len(t) < 2 or LAUGH_RE.match(t) or URL_RE.match(t):
            return None
        norm = normalize_slang(t)
        key = norm.lower()
        if key in self.cache:
            self.cache.move_to_end(key)
            translation, detected = self.cache[key]
        else:
            try:
                translation, detected = self.translate_any(norm)
            except Exception:
                self.out_q.put(("status_hint", "translation offline — showing originals"))
                return None
            self.cache[key] = (translation, detected)
            if len(self.cache) > 800:
                self.cache.popitem(last=False)
        if detected == "en" or not translation:
            return None
        if difflib.SequenceMatcher(None, translation.lower(), t.lower()).ratio() > 0.92:
            return None
        return translation


# --------------------------------------------------------------------------
# Twitch IRC (anonymous, read-only)
# --------------------------------------------------------------------------

TAG_UNESCAPE = {r"\s": " ", r"\:": ";", r"\\": "\\", r"\r": "\r", r"\n": "\n"}


def unescape_tag(v):
    out, i = [], 0
    while i < len(v):
        if v[i] == "\\" and i + 1 < len(v):
            out.append(TAG_UNESCAPE.get(v[i : i + 2], v[i + 1]))
            i += 2
        else:
            out.append(v[i])
            i += 1
    return "".join(out)


def parse_privmsg(line):
    tags = {}
    if line.startswith("@"):
        raw_tags, _, line = line[1:].partition(" ")
        for kv in raw_tags.split(";"):
            k, _, v = kv.partition("=")
            tags[k] = v
    if not line.startswith(":"):
        return None
    prefix, _, rest = line[1:].partition(" ")
    parts = rest.split(" ", 2)
    if len(parts) < 3 or parts[0] != "PRIVMSG":
        return None
    text = parts[2]
    if text.startswith(":"):
        text = text[1:]
    if text.startswith("\x01ACTION"):
        text = text[8:].rstrip("\x01").strip()
    user = unescape_tag(tags.get("display-name", "")) or prefix.split("!", 1)[0]
    color = tags.get("color", "")
    return user, color, text


class IrcReader(threading.Thread):
    def __init__(self, channel, out_q, ui_q):
        super().__init__(daemon=True)
        self.channel = channel.lower().lstrip("#@ ")
        self.out_q = out_q
        self.ui_q = ui_q
        self.stop_ev = threading.Event()
        self.sock = None

    def stop(self):
        self.stop_ev.set()
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass

    def _send(self, s):
        self.sock.sendall((s + "\r\n").encode("utf-8"))

    def run(self):
        delay = 2
        while not self.stop_ev.is_set():
            try:
                self.ui_q.put(("status", f"connecting to #{self.channel}…"))
                ctx = ssl.create_default_context()
                raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=15)
                self.sock = ctx.wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
                self.sock.settimeout(400)  # Twitch pings ~every 5 min
                self._send("CAP REQ :twitch.tv/tags")
                self._send(f"NICK justinfan{random.randint(10000, 99999)}")
                self._send(f"JOIN #{self.channel}")
                buf = b""
                delay = 2
                while not self.stop_ev.is_set():
                    data = self.sock.recv(4096)
                    if not data:
                        raise ConnectionError("server closed connection")
                    buf += data
                    while b"\r\n" in buf:
                        raw_line, buf = buf.split(b"\r\n", 1)
                        line = raw_line.decode("utf-8", "replace")
                        if line.startswith("PING"):
                            self._send("PONG :tmi.twitch.tv")
                            continue
                        if " 366 " in line:  # end of JOIN
                            self.ui_q.put(("status", f"connected — #{self.channel}"))
                            continue
                        msg = parse_privmsg(line)
                        if msg:
                            self.out_q.put(msg)
            except Exception as e:
                if self.stop_ev.is_set():
                    return
                log(f"irc reconnect ({e})")
                self.ui_q.put(("status", f"disconnected — retrying in {delay}s"))
                time.sleep(delay)
                delay = min(delay * 2, 60)
            finally:
                try:
                    if self.sock:
                        self.sock.close()
                except OSError:
                    pass


# --------------------------------------------------------------------------
# Phone access — tiny LAN web server, phone browser polls for new messages
# --------------------------------------------------------------------------

class ChatHistory:
    """Thread-safe ring buffer of processed messages for the phone page."""

    def __init__(self, maxlen=300):
        self.lock = threading.Lock()
        self.items = deque(maxlen=maxlen)
        self.next_id = 1
        self.viewers = None          # live viewer count, None = offline/unknown

    def add(self, user, color, text, translation, tr2=None):
        with self.lock:
            self.items.append({
                "id": self.next_id, "ts": time.strftime("%H:%M"),
                "user": user, "color": color, "text": text, "tr": translation,
                "tr2": tr2,
            })
            self.next_id += 1

    def since(self, last_id):
        with self.lock:
            return [m for m in self.items if m["id"] > last_id], self.next_id - 1

    def clear(self):
        with self.lock:
            self.items.clear()


PHONE_HTML = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Streamlate</title>
<style>
 :root { --fs: 16px; }
 * { margin:0; padding:0; box-sizing:border-box; }
 body { background:#0e0e10 url('/bg') center/cover fixed no-repeat;
        color:#d8d8dc;
        font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; }
 #log .m { text-shadow:0 1px 4px rgba(0,0,0,0.9); }
 #scrim { position:fixed; inset:0; background:rgba(10,10,14,0.45);
          z-index:-1; }
 #bar { position:fixed; top:0; left:0; right:0; background:#18181bee;
        backdrop-filter:blur(6px); display:flex; align-items:center; gap:8px;
        padding:10px 12px; padding-top:calc(10px + env(safe-area-inset-top)); z-index:10; }
 #chan { font-weight:700; color:#a970ff; flex:1; font-size:15px;
         overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
 button { background:#26262c; color:#d8d8dc; border:0; border-radius:8px;
          padding:8px 12px; font-size:14px; }
 button.on { background:#3a5f3f; }
 #log { padding:64px 12px 24px; padding-bottom:calc(24px + env(safe-area-inset-bottom));
        font-size:var(--fs); line-height:1.45; overflow-wrap:break-word; }
 .m { margin-bottom:6px; }
 .u { font-weight:700; }
 .tr { color:#a8e6b0; }
 .orig { color:#77777f; font-size:0.82em; display:block; padding-left:14px; }
 body.hideorig .orig { display:none; }
 .t { color:#55555c; font-size:0.75em; margin-right:4px; }
 #down { position:fixed; bottom:18px; left:50%; transform:translateX(-50%);
         background:#a970ff; color:#fff; border-radius:20px; padding:10px 18px;
         display:none; z-index:10; }
</style></head>
<body>
<div id="scrim"></div>
<div id="bar"><span id="chan">connecting…</span>
 <button id="orig" class="on">PT</button>
 <button id="minus">A−</button><button id="plus">A+</button></div>
<div id="log"></div>
<button id="down">▼ new messages</button>
<script>
let last = 0, fs = 16;
const log = document.getElementById('log'), down = document.getElementById('down');
function esc(s){ const d = document.createElement('span'); d.textContent = s; return d.innerHTML; }
function atBottom(){ return innerHeight + scrollY >= document.body.scrollHeight - 60; }
async function tick(){
  try {
    const r = await fetch('/msgs?since=' + last);
    const j = await r.json();
    document.getElementById('chan').textContent = '#' + j.channel
      + (j.viewers != null ? '  ·  👁 ' + j.viewers : '');
    if (j.msgs.length){
      const stick = atBottom();
      for (const m of j.msgs){
        const div = document.createElement('div'); div.className = 'm';
        let h = '<span class="t">' + m.ts + '</span>'
              + '<span class="u" style="color:' + m.color + '">' + esc(m.user) + '</span>: ';
        if (m.tr){
          h += '<span class="tr" dir="auto">' + esc(m.tr) + '</span>'
             + '<span class="orig" dir="auto">⤷ ' + esc(m.text) + '</span>';
        } else { h += '<span dir="auto">' + esc(m.text) + '</span>'; }
        div.innerHTML = h; log.appendChild(div);
      }
      while (log.children.length > 400) log.removeChild(log.firstChild);
      last = j.latest;
      if (stick) scrollTo(0, document.body.scrollHeight);
      else down.style.display = 'block';
    }
  } catch (e) {}
  setTimeout(tick, 1200);
}
addEventListener('scroll', () => { if (atBottom()) down.style.display = 'none'; });
down.onclick = () => { scrollTo(0, document.body.scrollHeight); down.style.display = 'none'; };
document.getElementById('plus').onclick = () => {
  fs = Math.min(26, fs + 2); document.documentElement.style.setProperty('--fs', fs + 'px'); };
document.getElementById('minus').onclick = () => {
  fs = Math.max(11, fs - 2); document.documentElement.style.setProperty('--fs', fs + 'px'); };
document.getElementById('orig').onclick = (e) => {
  document.body.classList.toggle('hideorig'); e.target.classList.toggle('on'); };
tick();
</script>
</body></html>"""


OBS_CHAT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Streamlate chat</title>
<style>
 * { margin:0; padding:0; box-sizing:border-box; }
 body { background:transparent; overflow:hidden;
        font-family:'Segoe UI',system-ui,sans-serif; }
 #feed { position:fixed; left:0; right:0; bottom:0; padding:10px 14px;
         display:flex; flex-direction:column; justify-content:flex-end; }
 .m { font-size:26px; line-height:1.35; margin-top:5px; color:#fff;
      text-shadow:0 2px 6px rgba(0,0,0,.95), 0 0 2px rgba(0,0,0,.9);
      unicode-bidi:plaintext; animation:in .18s ease-out;
      overflow-wrap:anywhere; }
 .u { font-weight:700; }
 @keyframes in { from { opacity:0; transform:translateY(8px); }
                 to { opacity:1; transform:none; } }
</style></head>
<body><div id="feed"></div>
<script>
let last = 0;
const feed = document.getElementById('feed');
function esc(s){ const d = document.createElement('span'); d.textContent = s; return d.innerHTML; }
async function tick(){
  try {
    const r = await fetch('/msgs?since=' + last);
    const j = await r.json();
    for (const m of j.msgs){
      const div = document.createElement('div'); div.className = 'm';
      const body = m.tr2 || m.text;
      div.innerHTML = '<span class="u" style="color:' + m.color + '">'
        + esc(m.user) + '</span>: ' + esc(body);
      feed.appendChild(div);
    }
    if (j.msgs.length) last = j.latest;
    while (feed.children.length > 9) feed.removeChild(feed.firstChild);
  } catch (e) {}
  setTimeout(tick, 900);
}
tick();
</script></body></html>"""


class PhoneHandler(BaseHTTPRequestHandler):
    history = None   # set via subclass in start_phone_server
    app_cfg = None
    ui_q = None      # when set, injected messages also reach the overlay
    protocol_version = "HTTP/1.1"   # keep-alive: one connection per client

    def log_message(self, *args):
        pass

    def do_POST(self):
        """Localhost-only /inject: voice-chat translator pushes bubbles here."""
        try:
            if (self.client_address[0] not in ("127.0.0.1", "::1")
                    or not self.path.startswith("/inject")):
                self.send_error(403)
                return
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= 8192:
                self.send_error(400)
                return
            d = json.loads(self.rfile.read(n))
            user = str(d.get("user", "🎧"))[:40]
            color = str(d.get("color", "#7fd4ff"))[:9]
            text = str(d.get("text", ""))[:500]
            tr_ = d.get("tr")
            tr_ = str(tr_)[:500] if tr_ else None
            if not text.strip():
                self.send_error(400)
                return
            self.history.add(user, color, text, tr_)
            if self.ui_q is not None:
                self.ui_q.put(("chat", user, color, text, tr_))
            self._reply(b'{"ok":true}', "application/json")
        except (BrokenPipeError, ConnectionError, ValueError):
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
                self._reply(PHONE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path.startswith("/obs"):
                self._reply(OBS_CHAT_HTML.encode("utf-8"),
                            "text/html; charset=utf-8")
            elif self.path.startswith("/bg"):
                bg = find_background(APP_DIR)
                if not bg:
                    self.send_error(404)
                    return
                with open(bg, "rb") as f:
                    data = f.read()
                ctype = "image/png" if bg.endswith(".png") else "image/jpeg"
                self._reply(data, ctype)
            elif self.path.startswith("/msgs"):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                since = int((qs.get("since", ["0"])[0] or "0"))
                msgs, latest = self.history.since(since)
                body = json.dumps({
                    "channel": self.app_cfg.get("channel", ""),
                    "viewers": self.history.viewers,
                    "latest": latest, "msgs": msgs,
                }).encode("utf-8")
                self._reply(body, "application/json")
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionError, ValueError):
            pass


class ExclusiveHTTPServer(ThreadingHTTPServer):
    # Windows: reuse_address lets two instances silently share one port —
    # then requests land on a random one. Demand exclusive ownership so a
    # second instance moves to the next port instead.
    allow_reuse_address = False


def start_phone_server(history, cfg, ui_q=None):
    """Serve the phone page on the LAN. Returns (port, server) or (None, None)."""
    base = int(cfg.get("http_port", 8765))
    for port in range(base, base + 6):
        try:
            handler = type("BoundHandler", (PhoneHandler,),
                           {"history": history, "app_cfg": cfg, "ui_q": ui_q})
            srv = ExclusiveHTTPServer(("0.0.0.0", port), handler)
        except OSError:
            continue
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return port, srv
    log("phone server: no free port")
    return None, None


def make_phone_qr(url):
    """Refresh phone_qr.png for the current LAN address."""
    try:
        import qrcode
        qrcode.make(url).save(os.path.join(APP_DIR, "phone_qr.png"))
    except Exception as e:
        log(f"qr generation failed: {e}")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


TWITCH_WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Twitch's own public web client


def fetch_viewers(channel):
    """Live viewer count via Twitch's public GraphQL (no login). None = offline."""
    body = json.dumps({
        "query": '{user(login:"%s"){stream{viewersCount}}}' % channel,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://gql.twitch.tv/gql", data=body,
        headers={"Client-ID": TWITCH_WEB_CLIENT_ID,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    user = (data.get("data") or {}).get("user")
    if not user or not user.get("stream"):
        return None
    return user["stream"].get("viewersCount")


def start_viewer_poller(history, cfg):
    def loop():
        from chat_sources import detect_platform
        while True:
            try:
                if detect_platform(cfg.get("channel", ""),
                                   cfg.get("platform", "auto")) == "twitch":
                    history.viewers = fetch_viewers(cfg["channel"])
                else:
                    history.viewers = None   # viewer count is Twitch-only for now
            except Exception as e:
                log(f"viewer count failed: {e}")
                history.viewers = None
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()


def make_reader(cfg, raw_q, ui_q):
    """Chat reader for whichever platform the channel points at."""
    from chat_sources import detect_platform, YouTubeReader, KickReader
    platform = detect_platform(cfg.get("channel", ""),
                               cfg.get("platform", "auto"))
    if platform == "youtube":
        return YouTubeReader(cfg["channel"], raw_q, ui_q, log)
    if platform == "kick":
        return KickReader(cfg["channel"], raw_q, ui_q, log)
    return IrcReader(cfg["channel"], raw_q, ui_q)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

BG = "#0e0e10"
FG_PLAIN = "#d8d8dc"
FG_TRANS = "#a8e6b0"
FG_DIM = "#77777f"
FG_TIME = "#55555c"
FALLBACK_COLORS = [
    "#ff7f7f", "#7fbfff", "#8fe388", "#ffb86c", "#d0a9ff",
    "#ff9edb", "#7fe0d6", "#f2e178", "#9db8ff", "#ffa9a0",
]


def display_color(user, color):
    """Twitch user color made readable on the dark background."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
        color = FALLBACK_COLORS[hash(user.lower()) % len(FALLBACK_COLORS)]
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    if 0.299 * r + 0.587 * g + 0.114 * b < 80:
        r, g, b = (min(255, c + 100) for c in (r, g, b))
        color = f"#{r:02x}{g:02x}{b:02x}"
    return color


class App(tk.Tk):
    def __init__(self, cfg, overlay=False):
        super().__init__()
        self.cfg = cfg
        self.overlay = overlay
        self.raw_q = queue.Queue()   # irc -> translator
        self.ui_q = queue.Queue()    # translator/irc -> ui
        self.irc = None
        self.known_color_tags = set()
        self.last_msg_time = time.time()
        self._status_refresh = 0.0

        self.title("Streamlate")
        self.configure(bg=BG)
        if overlay:
            self.overrideredirect(True)
            self.overlay_locked = True
            pos = cfg.get("overlay_pos") or OVERLAY_CORNERS[
                cfg["overlay_corner"] % 4]
            self.geometry(cfg["overlay_size"] + pos)
            self.attributes("-topmost", True)
            alpha = cfg["overlay_opacity"]
        else:
            try:
                self.geometry(cfg["geometry"])
            except tk.TclError:
                pass
            self.attributes("-topmost", cfg["topmost"])
            alpha = cfg["opacity"]
        try:
            self.attributes("-alpha", alpha)
        except tk.TclError:
            pass

        if overlay:
            self.viewer_label = tk.Label(self, text="", anchor="e", bg=BG,
                                         fg=FG_DIM, padx=8, font=("Segoe UI", 9))
            self.viewer_label.pack(side="top", fill="x")
            self.canvas = tk.Canvas(self, bg=BG, bd=0, highlightthickness=0)
            self.canvas.pack(fill="both", expand=True)
            self.overlay_msgs = deque(maxlen=10)
            self._bg_photo = None
            self.after(350, self._load_overlay_bg)
        else:
            self.text = tk.Text(
                self, bg=BG, fg=FG_PLAIN, bd=0, padx=10, pady=8,
                wrap="word", cursor="arrow", state="disabled",
                insertbackground=BG, selectbackground="#3a3a44",
            )
            sb = tk.Scrollbar(self, command=self.text.yview,
                              troughcolor=BG, bg="#26262c", bd=0)
            self.text.configure(yscrollcommand=sb.set)
            self.status = tk.Label(
                self, text="starting…", anchor="w", bg="#18181b", fg=FG_DIM,
                padx=8, pady=3, font=("Segoe UI", 9),
            )
            self.status.pack(side="bottom", fill="x")
            sb.pack(side="right", fill="y")
            self.text.pack(side="left", fill="both", expand=True)

        self.apply_fonts()

        if not overlay:
            self.bind("<Control-MouseWheel>", self.on_font_wheel)
            self.bind("<Control-t>", self.toggle_topmost)
            self.bind("<Control-o>", self.toggle_original)
            self.bind("<Control-n>", self.switch_channel)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.history = ChatHistory()
        self.worker = TranslateWorker(self.raw_q, self.ui_q, self.cfg, self.history)
        self.worker.start()

        port, self.http_srv = start_phone_server(self.history, self.cfg,
                                                 self.ui_q)
        self.phone_url = f"http://{lan_ip()}:{port}" if port else ""
        if self.phone_url:
            threading.Thread(target=make_phone_qr, args=(self.phone_url,),
                             daemon=True).start()
        start_viewer_poller(self.history, self.cfg)
        threading.Thread(target=warm_chat_ollama, args=(self.cfg,),
                         daemon=True).start()
        self.base_status = "starting…"
        self.set_status(self.base_status)

        if overlay:
            self._ghost_alpha = alpha
            self.after(300, self._apply_overlay_styles)
            self.after(500, self._ghost_tick)
            threading.Thread(target=self._overlay_tray, daemon=True).start()

        self.after(80, self.poll)

    # ---- overlay: click-through window that can never eat game input ----

    def _apply_overlay_styles(self, clickthrough=True):
        """WS_EX_TRANSPARENT (clicks pass through to the game) +
        WS_EX_NOACTIVATE (never steals focus) + TOOLWINDOW (no alt-tab entry).
        Move mode drops TRANSPARENT/NOACTIVATE so the window can be dragged."""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            u.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int,
                                            ctypes.c_ssize_t)
            u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            self.update_idletasks()
            hwnd = int(self.wm_frame(), 16)
            GWL_EXSTYLE = -20
            cur = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            new = cur | 0x00080000 | 0x00000080         # LAYERED | TOOLWINDOW
            passthru = 0x00000020 | 0x08000000          # TRANSPARENT | NOACTIVATE
            new = (new | passthru) if clickthrough else (new & ~passthru)
            u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)
            log(f"overlay styles applied: 0x{new:x} (clickthrough={clickthrough})")
        except Exception as e:
            log(f"overlay styles failed: {e}")

    def _ghost_tick(self):
        """Fade the overlay way down whenever the mouse is on/near it, so
        buttons behind it (browser controls etc.) stay visible. Clicks
        already pass through — this makes SEEING pass through too."""
        try:
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            m = 16
            inside = (self.winfo_x() - m <= pt.x
                      <= self.winfo_x() + self.winfo_width() + m
                      and self.winfo_y() - m <= pt.y
                      <= self.winfo_y() + self.winfo_height() + m)
            want = (0.06 if (inside and self.overlay_locked
                             and self.cfg.get("overlay_ghost", True))
                    else float(self.cfg["overlay_opacity"]))
            cur = self._ghost_alpha
            step = 0.30 if want < cur else 0.10   # vanish fast, return soft
            new = cur + max(min(want - cur, step), -step)
            if abs(new - cur) > 0.004:
                self._ghost_alpha = new
                self.attributes("-alpha", new)
        except Exception:
            pass
        self.after(60, self._ghost_tick)

    # ---- Move mode: unlock, drag anywhere, lock back ----

    def _drag_start(self, e):
        self._drag_off = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._drag_off[0]}"
                      f"+{e.y_root - self._drag_off[1]}")

    def _toggle_move_mode(self):
        self.overlay_locked = not self.overlay_locked
        if not self.overlay_locked:
            self._apply_overlay_styles(clickthrough=False)
            self.canvas.configure(highlightthickness=2,
                                  highlightbackground="#a970ff")
            for w in (self.canvas, self.viewer_label):
                w.bind("<Button-1>", self._drag_start)
                w.bind("<B1-Motion>", self._drag_move)
            self.viewer_label.configure(text=tr("drag_hint"))
        else:
            for w in (self.canvas, self.viewer_label):
                w.unbind("<Button-1>")
                w.unbind("<B1-Motion>")
            self.canvas.configure(highlightthickness=0)
            self.cfg["overlay_pos"] = f"+{self.winfo_x()}+{self.winfo_y()}"
            save_config(self.cfg)
            self._apply_overlay_styles()
            self._refresh_viewers()

    def _overlay_show(self):
        self.deiconify()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.after(150, self._apply_overlay_styles)

    def _do_cmd(self, cmd):
        if cmd == "font+":
            self.cfg["font_size"] = min(28, self.cfg["font_size"] + 1)
            self.apply_fonts()
        elif cmd == "font-":
            self.cfg["font_size"] = max(7, self.cfg["font_size"] - 1)
            self.apply_fonts()
        elif cmd == "orig":
            self.cfg["show_original"] = not self.cfg["show_original"]
            if self.overlay:
                self._redraw_overlay()
        elif cmd == "bg":
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Pick a background image",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")])
            if path:
                try:
                    from PIL import Image
                    Image.open(path).convert("RGB").save(
                        os.path.join(APP_DIR, "background.png"))
                    for old in ("background.jpg", "background.jpeg",
                                "background.webp"):
                        try:
                            os.remove(os.path.join(APP_DIR, old))
                        except OSError:
                            pass
                    self._load_overlay_bg()
                except Exception as e:
                    log(f"background change failed: {e}")
        elif cmd == "bgoff":
            for name in ("background.png", "background.jpg",
                         "background.jpeg", "background.webp"):
                try:
                    os.remove(os.path.join(APP_DIR, name))
                except OSError:
                    pass
            self._load_overlay_bg()
        elif cmd == "movemode":
            self._toggle_move_mode()
        elif cmd == "corner":
            self.cfg["overlay_pos"] = ""
            self.cfg["overlay_corner"] = (self.cfg["overlay_corner"] + 1) % 4
            self.geometry(self.cfg["overlay_size"]
                          + OVERLAY_CORNERS[self.cfg["overlay_corner"]])
        elif cmd == "autohide":
            self.cfg["overlay_autohide"] = not self.cfg["overlay_autohide"]
            if not self.cfg["overlay_autohide"]:
                self._overlay_show()
        elif cmd == "ghost":
            self.cfg["overlay_ghost"] = not self.cfg.get("overlay_ghost", True)
            save_config(self.cfg)
        elif cmd == "exit":
            self.on_close()
            os._exit(0)

    def _overlay_tray(self):
        try:
            import pystray
        except ImportError:
            log("pystray missing — overlay has no tray menu")
            return

        def put(c):
            return lambda icon, item: self.ui_q.put(("cmd", c))

        def open_page(icon, item):
            import webbrowser
            webbrowser.open(self.phone_url)

        def show_qr(icon, item):
            try:
                os.startfile(os.path.join(APP_DIR, "phone_qr.png"))
            except OSError:
                pass

        menu = pystray.Menu(
            pystray.MenuItem(f"#{self.cfg['channel']} — {self.phone_url}",
                             None, enabled=False),
            pystray.MenuItem(tr("open_phone"), open_page),
            pystray.MenuItem(tr("show_qr"), show_qr),
            pystray.MenuItem(tr("bigger"), put("font+")),
            pystray.MenuItem(tr("smaller"), put("font-")),
            pystray.MenuItem(tr("orig"), put("orig")),
            pystray.MenuItem(tr("bg"), put("bg")),
            pystray.MenuItem(tr("bgoff"), put("bgoff")),
            pystray.MenuItem(tr("movemode"), put("movemode"),
                             checked=lambda item: not self.overlay_locked),
            pystray.MenuItem(tr("corner"), put("corner")),
            pystray.MenuItem(tr("autohide"), put("autohide"),
                             checked=lambda item: bool(self.cfg["overlay_autohide"])),
            pystray.MenuItem(tr("ghost"), put("ghost"),
                             checked=lambda item: bool(self.cfg.get("overlay_ghost", True))),
            pystray.MenuItem(tr("q_menu"), quality_submenu(self.cfg, pystray)),
            pystray.MenuItem(tr("settings"),
                             lambda icon, item: open_settings_and_restart()),
            pystray.MenuItem(tr("exit"), put("exit")),
        )
        self._tray_icon = pystray.Icon(
            "streamlate_overlay", _tray_image(),
            f"Streamlate — #{self.cfg['channel']}", menu=menu)
        self._tray_icon.run()

    # ---- fonts / tags ----

    def apply_fonts(self):
        import tkinter.font as tkfont
        size = self.cfg["font_size"]
        self.f_user = tkfont.Font(family="Segoe UI", size=size, weight="bold")
        self.f_msg = tkfont.Font(family="Segoe UI", size=size)
        self.f_orig = tkfont.Font(family="Segoe UI", size=max(size - 2, 7))
        if self.overlay:
            self._redraw_overlay()
            return
        self.text.configure(font=("Segoe UI", size))
        self.text.tag_configure("time", foreground=FG_TIME,
                                font=("Consolas", max(size - 3, 7)))
        self.text.tag_configure("plain", foreground=FG_PLAIN,
                                font=("Segoe UI", size))
        self.text.tag_configure("trans", foreground=FG_TRANS,
                                font=("Segoe UI", size))
        self.text.tag_configure("orig", foreground=FG_DIM,
                                font=("Segoe UI", max(size - 2, 7)))
        for tag in self.known_color_tags:
            self.text.tag_configure(tag, font=("Segoe UI", size, "bold"))

    def user_tag(self, user, color):
        color = display_color(user, color)
        tag = "u" + color
        if tag not in self.known_color_tags:
            self.text.tag_configure(tag, foreground=color,
                                    font=("Segoe UI", self.cfg["font_size"], "bold"))
            self.known_color_tags.add(tag)
        return tag

    # ---- message flow ----

    def poll(self):
        try:
            while True:
                item = self.ui_q.get_nowait()
                if item[0] == "chat":
                    _, user, color, text, translation = item
                    self.add_message(user, color, text, translation)
                elif item[0] == "status":
                    self.set_status(item[1])
                elif item[0] == "status_hint":
                    self.set_status(item[1], transient=True)
                elif item[0] == "cmd":
                    self._do_cmd(item[1])
        except queue.Empty:
            pass
        now = time.time()
        if now - self._status_refresh > 10:
            self._status_refresh = now
            self._refresh_viewers()
        if (self.overlay and self.cfg["overlay_autohide"]
                and self.overlay_locked
                and self.state() != "withdrawn"
                and now - self.last_msg_time > 8):
            self.withdraw()
        self.after(80, self.poll)

    def _refresh_viewers(self):
        v = self.history.viewers
        if self.overlay:
            live = f"👁 {v}" if v is not None else "offline"
            self.viewer_label.configure(text=f"#{self.cfg['channel']}  ·  {live}")
        else:
            self.status.configure(text=self.base_status + self._suffix())

    def _suffix(self):
        v = self.history.viewers
        viewers = f"  ·  👁 {v}" if v is not None else ""
        phone = f"  ·  phone: {self.phone_url}" if self.phone_url else ""
        return viewers + phone + "  ·  Ctrl+Wheel/T/O/N"

    def set_status(self, msg, transient=False):
        if self.overlay:
            log("status: " + msg)
            return
        self.status.configure(text=msg + self._suffix())
        if transient:
            self.after(6000, lambda: self.status.configure(
                text=self.base_status + self._suffix()))
        else:
            self.base_status = msg

    def _insert(self, pos, s, tag):
        try:
            self.text.insert(pos, s, tag)
        except tk.TclError:
            # Tk build that can't take astral-plane chars (rare on 3.13)
            safe = "".join(c if ord(c) <= 0xFFFF else "□" for c in s)
            self.text.insert(pos, safe, tag)

    # ---- overlay canvas rendering (supports background images) ----

    def _load_overlay_bg(self):
        path = find_background(APP_DIR)
        if not path:
            self.canvas.delete("bg")
            self._bg_photo = None
            return
        try:
            from PIL import Image, ImageEnhance, ImageTk
            self.update_idletasks()
            w = max(self.canvas.winfo_width(), 50)
            h = max(self.canvas.winfo_height(), 50)
            img = Image.open(path).convert("RGB")
            scale = max(w / img.width, h / img.height)
            img = img.resize((int(img.width * scale) + 1,
                              int(img.height * scale) + 1))
            img = img.crop((0, 0, w, h))
            img = ImageEnhance.Brightness(img).enhance(
                float(self.cfg.get("background_dim", 0.35)))
            self._bg_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("bg")
            self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo,
                                     tags="bg")
            self.canvas.tag_lower("bg")
            log(f"overlay background: {os.path.basename(path)}")
        except Exception as e:
            log(f"overlay background failed: {e}")

    def _overlay_add(self, user, color, text, translation):
        self.overlay_msgs.append(
            (user, display_color(user, color), text, translation))
        self._redraw_overlay()

    def _redraw_overlay(self):
        if not hasattr(self, "canvas"):
            return
        c = self.canvas
        c.delete("msg")
        W = c.winfo_width() or 400
        H = c.winfo_height() or 250
        pad = 10

        def put(x, yy, s, font, fill):
            c.create_text(x + 1, yy + 1, text=s, font=font, fill="#000000",
                          anchor="nw", width=W - x - pad, tags="msg")
            return c.create_text(x, yy, text=s, font=font, fill=fill,
                                 anchor="nw", width=W - x - pad, tags="msg")

        y = pad
        for user, ucolor, text, translation in self.overlay_msgs:
            uid = put(pad, y, user + ":", self.f_user, ucolor)
            ux = c.bbox(uid)[2] + 6
            body = translation if translation else text
            bid = put(min(ux, W - 60), y, body, self.f_msg,
                      FG_TRANS if translation else FG_PLAIN)
            y = c.bbox(bid)[3] + 2
            if translation and self.cfg["show_original"]:
                oid = put(pad + 18, y, "⤷ " + text, self.f_orig, FG_DIM)
                y = c.bbox(oid)[3] + 2
            y += 3
        overflow = y - H + pad
        if overflow > 0:
            c.move("msg", 0, -overflow)

    def add_message(self, user, color, text, translation):
        if self.overlay:
            self.last_msg_time = time.time()
            if self.state() == "withdrawn":
                self._overlay_show()
            self._overlay_add(user, color, text, translation)
            return
        at_bottom = self.text.yview()[1] > 0.985
        self.text.configure(state="normal")
        ts = time.strftime("%H:%M ")
        self._insert("end", ts, "time")
        self._insert("end", user, self.user_tag(user, color))
        if translation:
            self._insert("end", ": ", "plain")
            self._insert("end", translation + "\n", "trans")
            if self.cfg["show_original"]:
                self._insert("end", " " * 8 + "⤷ " + text + "\n", "orig")
        else:
            self._insert("end", ": " + text + "\n", "plain")
        # keep the widget light
        if int(self.text.index("end-1c").split(".")[0]) > 900:
            self.text.delete("1.0", "120.0")
        self.text.configure(state="disabled")
        if at_bottom:
            self.text.see("end")

    # ---- hotkeys ----

    def on_font_wheel(self, ev):
        self.cfg["font_size"] = max(7, min(28, self.cfg["font_size"]
                                           + (1 if ev.delta > 0 else -1)))
        self.apply_fonts()
        return "break"

    def toggle_topmost(self, _ev=None):
        self.cfg["topmost"] = not self.cfg["topmost"]
        self.attributes("-topmost", self.cfg["topmost"])
        self.set_status(("always-on-top ON" if self.cfg["topmost"]
                         else "always-on-top OFF"), transient=True)

    def toggle_original(self, _ev=None):
        self.cfg["show_original"] = not self.cfg["show_original"]
        self.set_status(("originals shown" if self.cfg["show_original"]
                         else "originals hidden"), transient=True)

    def switch_channel(self, _ev=None):
        ch = simpledialog.askstring("Switch channel", "Twitch channel name:",
                                    parent=self)
        if ch and ch.strip():
            self.start_irc(ch.strip())

    # ---- lifecycle ----

    def start_irc(self, channel):
        if self.irc:
            self.irc.stop()
        from chat_sources import detect_platform, display_name
        platform = detect_platform(channel, self.cfg.get("platform", "auto"))
        if platform == "twitch":
            channel = channel.strip().lower().lstrip("#@ ")
        else:
            channel = channel.strip()
        if self.cfg["channel"] and channel != self.cfg["channel"]:
            self.history.clear()
        self.cfg["channel"] = channel
        prefix = "#" if platform == "twitch" else ""
        self.title(f"Streamlate — {prefix}{display_name(channel)}")
        self.irc = make_reader(self.cfg, self.raw_q, self.ui_q)
        self.irc.start()

    def on_close(self):
        if not self.overlay:
            self.cfg["geometry"] = self.geometry()
        save_config(self.cfg)
        if self.irc:
            self.irc.stop()
        self.destroy()


def lower_priority():
    """Below-normal CPU priority so the translator never competes with a game."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = wintypes.HANDLE
            k.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            if not k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000):
                log("priority drop failed: SetPriorityClass returned 0")
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


def _drain_ui_queue(ui_q):
    while True:  # history already holds the messages; just log status changes
        item = ui_q.get()
        if item[0] == "status":
            log("status: " + item[1])


def quality_submenu(cfg, pystray):
    """Shared quality-tier radio submenu for the tray menus."""
    from quality import set_quality

    def pick(tier):
        return lambda icon, item: set_quality(
            tier, APP_DIR, cfg.get("engine_url") or ENGINE_URL, log)

    def chk(tier):
        return lambda item: cfg.get("quality", "auto") == tier

    return pystray.Menu(
        pystray.MenuItem(tr("q_auto"), pick("auto"), radio=True,
                         checked=chk("auto")),
        pystray.MenuItem(tr("q_light"), pick("light"), radio=True,
                         checked=chk("light")),
        pystray.MenuItem(tr("q_tiny"), pick("tiny"), radio=True,
                         checked=chk("tiny")),
        pystray.MenuItem(tr("q_zero"), pick("zero"), radio=True,
                         checked=chk("zero")),
    )


def open_settings_and_restart():
    """Re-run the setup wizard, then relaunch the whole stack so every
    change (mic, language, channel) takes effect. Wizard merges configs,
    so tuned settings survive."""
    import subprocess
    try:
        subprocess.run([sys.executable,
                        os.path.join(APP_DIR, "setup_wizard.py")],
                       cwd=APP_DIR)
        subprocess.Popen([sys.executable,
                          os.path.join(APP_DIR, "stream_mode_launcher.py")],
                         cwd=APP_DIR)
    except Exception as e:
        log(f"settings relaunch failed: {e}")


def _tray_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 8, 58, 46), radius=12, fill="#a970ff")
    d.polygon([(18, 44), (34, 44), (18, 60)], fill="#a970ff")
    d.ellipse((16, 22, 24, 30), fill="white")
    d.ellipse((28, 22, 36, 30), fill="white")
    d.ellipse((40, 22, 48, 30), fill="white")
    return img


def _run_tray(cfg, url):
    """System-tray icon so phone-only mode is visible without any window.
    A tray icon never overlaps the game, so it costs zero input latency."""
    try:
        import pystray
    except ImportError:
        log("pystray/PIL missing — running with no tray icon")
        while True:
            time.sleep(3600)

    img = _tray_image()

    def open_page(icon, item):
        import webbrowser
        webbrowser.open(url)

    def show_qr(icon, item):
        os.startfile(os.path.join(APP_DIR, "phone_qr.png"))

    def quit_app(icon, item):
        icon.stop()

    icon = pystray.Icon(
        "streamlate", img,
        f"Streamlate — #{cfg['channel']} · {url}",
        menu=pystray.Menu(
            pystray.MenuItem(f"#{cfg['channel']} — {url}", None, enabled=False),
            pystray.MenuItem(tr("open_phone"), open_page, default=True),
            pystray.MenuItem(tr("show_qr"), show_qr),
            pystray.MenuItem(tr("q_menu"), quality_submenu(cfg, pystray)),
            pystray.MenuItem(tr("settings"),
                             lambda icon, item: open_settings_and_restart()),
            pystray.MenuItem(tr("exit"), quit_app),
        ),
    )
    icon.run()
    os._exit(0)


def run_headless(cfg):
    """Phone-only mode: no window, just IRC + translation + phone page + a
    tray icon by the clock. Zero impact on game presentation latency."""
    if not cfg["channel"]:
        log("headless mode needs a channel (run windowed once, or pass it as an argument)")
        return
    history = ChatHistory()
    raw_q, ui_q = queue.Queue(), queue.Queue()
    TranslateWorker(raw_q, ui_q, cfg, history).start()
    port, _srv = start_phone_server(history, cfg)
    start_viewer_poller(history, cfg)
    threading.Thread(target=warm_chat_ollama, args=(cfg,), daemon=True).start()
    url = f"http://{lan_ip()}:{port}"
    log(f"headless: #{cfg['channel']} → {url}")
    make_phone_qr(url)   # refresh in case the PC's LAN IP changed
    make_reader(cfg, raw_q, ui_q).start()
    threading.Thread(target=_drain_ui_queue, args=(ui_q,), daemon=True).start()
    _run_tray(cfg, url)


def main():
    global ENGINE_URL
    lower_priority()
    from quality import apply_quality
    cfg = apply_quality(load_config())
    ENGINE_URL = cfg.get("engine_url") or ENGINE_URL
    if cfg.get("pin_efficiency_cores"):
        pin_to_efficiency_cores()
    args = [a for a in sys.argv[1:] if a.strip()]
    headless = any(a.lower() in ("--headless", "--phone-only") for a in args)
    overlay = any(a.lower() == "--overlay" for a in args)
    channels = [a for a in args if not a.startswith("-")]
    if channels:
        cfg["channel"] = channels[0].strip()
    if headless:
        save_config(cfg)
        run_headless(cfg)
        return
    app = App(cfg, overlay=overlay)
    if not cfg["channel"]:
        ch = simpledialog.askstring(
            "Twitch Chat Translator",
            "Which Twitch channel should I watch?\n(your own channel name)",
            parent=app,
        )
        if not ch or not ch.strip():
            app.destroy()
            return
        cfg["channel"] = ch.strip().lower().lstrip("#@")
    save_config(cfg)
    app.start_irc(cfg["channel"])
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        raise
