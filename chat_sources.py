"""Chat readers for platforms beyond Twitch. Each reader is a daemon thread
that emits (username, color, text) tuples into raw_q and status strings into
ui_q — the same contract as the Twitch IrcReader, so everything downstream
(translation, overlay, phone page) is platform-blind.

    YouTube: via chat-downloader — no API key needed.
    Kick:    experimental — public Pusher websocket, Cloudflare-tolerant.
"""
import json
import re
import threading
import time

_KICK_EMOTE = re.compile(r"\[emote:\d+:([^\]]*)\]")


def detect_platform(channel, configured="auto"):
    if configured and configured != "auto":
        return configured
    c = (channel or "").lower()
    if "youtube.com" in c or "youtu.be" in c or c.startswith("@"):
        return "youtube"
    if "kick.com" in c:
        return "kick"
    return "twitch"   # includes pasted twitch.tv URLs (normalize_channel strips them)


def normalize_channel(channel, platform=None):
    """People paste full URLs — make them work. A Twitch URL (or #name /
    @name / trailing junk) collapses to the bare lowercase channel name;
    YouTube and Kick forms pass through for their own readers."""
    c = (channel or "").strip()
    p = platform or detect_platform(c)
    if p == "twitch":
        low = c.lower()
        for sep in ("twitch.tv/",):
            if sep in low:
                c = c[low.find(sep) + len(sep):]
                break
        c = (c.split("/")[0].split("?")[0].strip().lstrip("#@ ").lower())
    return c


def display_name(channel):
    """Short channel name for titles, whatever form the user typed."""
    c = channel.rstrip("/")
    for sep in ("kick.com/", "youtube.com/", "youtu.be/"):
        if sep in c:
            c = c.split(sep, 1)[1]
    return c.split("/")[0].lstrip("@#")


def _find_key(o, key):
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None


def _parse_yt_line(line):
    try:
        d = json.loads(line)
    except ValueError:
        return None
    r = _find_key(d, "liveChatTextMessageRenderer")
    if not r:
        return None
    author = (r.get("authorName") or {}).get("simpleText") or "viewer"
    runs = (r.get("message") or {}).get("runs", [])
    text = "".join(
        x.get("text", "")
        or (x.get("emoji", {}).get("shortcuts") or [""])[0]
        for x in runs).strip()
    if not text:
        return None
    return (author.lstrip("@"), "", text)


class YouTubeReader(threading.Thread):
    """YouTube live chat via yt-dlp's live_chat stream — yt-dlp is the most
    actively maintained YouTube client there is, so this keeps working when
    scraper libraries break."""

    def __init__(self, channel, out_q, ui_q, log=print):
        super().__init__(daemon=True)
        self.channel = channel
        self.out_q = out_q
        self.ui_q = ui_q
        self.log = log
        self.stop_ev = threading.Event()
        self.proc = None

    def stop(self):
        self.stop_ev.set()
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass

    def _url(self):
        c = self.channel
        if c.startswith("http"):
            return c
        if not c.startswith("@"):
            c = "@" + c
        return f"https://www.youtube.com/{c}/live"

    def run(self):
        import glob
        import os
        import subprocess
        import tempfile
        name = display_name(self.channel)
        delay = 5
        while not self.stop_ev.is_set():
            tmp = os.path.join(tempfile.gettempdir(),
                               f"streamlate_yt_{os.getpid()}_{int(time.time())}")
            try:
                self.ui_q.put(("status", f"connecting to YouTube {name}…"))
                self.proc = subprocess.Popen(
                    ["yt-dlp", "--skip-download", "--write-subs",
                     "--sub-langs", "live_chat", "-o", tmp, self._url()],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=0x08000000)
                part = tmp + ".live_chat.json.part"
                final = tmp + ".live_chat.json"
                for _ in range(60):
                    if self.stop_ev.is_set():
                        return
                    if os.path.exists(part) or os.path.exists(final):
                        break
                    if self.proc.poll() is not None:
                        raise RuntimeError("yt-dlp exited — channel offline?")
                    time.sleep(1)
                else:
                    raise RuntimeError("no live chat appeared — offline?")
                self.ui_q.put(("status", f"connected — YouTube {name}"))
                delay = 5
                path = part if os.path.exists(part) else final
                offset = 0
                buf = ""
                while not self.stop_ev.is_set():
                    if self.proc.poll() is not None:
                        raise RuntimeError("yt-dlp ended — stream over?")
                    try:
                        size = os.path.getsize(path)
                    except OSError:
                        time.sleep(1)
                        continue
                    if size < offset:
                        offset = 0
                    if size > offset:
                        with open(path, "r", encoding="utf-8",
                                  errors="replace") as f:
                            f.seek(offset)
                            buf += f.read()
                            offset = f.tell()
                        *complete, buf = buf.split("\n")
                        for line in complete:
                            m = _parse_yt_line(line)
                            if m:
                                self.out_q.put(m)
                    time.sleep(1.0)
            except Exception as e:
                if self.stop_ev.is_set():
                    return
                self.log(f"youtube chat reconnect ({e})")
                self.ui_q.put(("status", f"YouTube retry in {delay}s"))
                time.sleep(delay)
                delay = min(delay * 2, 60)
            finally:
                try:
                    if self.proc:
                        self.proc.terminate()
                except Exception:
                    pass
                for g in glob.glob(tmp + "*"):
                    try:
                        os.remove(g)
                    except OSError:
                        pass


class KickReader(threading.Thread):
    """EXPERIMENTAL. Kick's chat rides on a public Pusher websocket; the
    chatroom id comes from their API (Cloudflare-guarded, hence cloudscraper)."""

    PUSHER = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
              "?protocol=7&client=js&version=8.4.0-rc2&flash=false")

    def __init__(self, channel, out_q, ui_q, log=print):
        super().__init__(daemon=True)
        self.channel = display_name(channel)
        self.out_q = out_q
        self.ui_q = ui_q
        self.log = log
        self.stop_ev = threading.Event()
        self.ws = None

    def stop(self):
        self.stop_ev.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def _chatroom_id(self):
        import cloudscraper
        s = cloudscraper.create_scraper()
        r = s.get(f"https://kick.com/api/v2/channels/{self.channel}",
                  timeout=15)
        r.raise_for_status()
        return r.json()["chatroom"]["id"]

    def run(self):
        import websocket
        delay = 5
        while not self.stop_ev.is_set():
            try:
                self.ui_q.put(("status", f"connecting to Kick {self.channel}…"))
                cid = self._chatroom_id()
                self.ws = websocket.create_connection(self.PUSHER, timeout=15)
                self.ws.send(json.dumps({
                    "event": "pusher:subscribe",
                    "data": {"auth": "", "channel": f"chatrooms.{cid}.v2"},
                }))
                self.ui_q.put(("status", f"connected — Kick {self.channel}"))
                self.ws.settimeout(400)
                delay = 5
                while not self.stop_ev.is_set():
                    frame = json.loads(self.ws.recv())
                    ev = frame.get("event", "")
                    if ev == "pusher:ping":
                        self.ws.send(json.dumps({"event": "pusher:pong",
                                                 "data": {}}))
                        continue
                    if ev.endswith("ChatMessageEvent"):
                        data = json.loads(frame.get("data", "{}"))
                        user = (data.get("sender") or {}).get("username",
                                                              "viewer")
                        color = ((data.get("sender") or {}).get("identity")
                                 or {}).get("color", "")
                        text = _KICK_EMOTE.sub(r"\1", data.get("content") or "")
                        if text.strip():
                            self.out_q.put((user, color or "", text.strip()))
            except Exception as e:
                if self.stop_ev.is_set():
                    return
                self.log(f"kick chat reconnect ({e})")
                self.ui_q.put(("status", f"Kick retry in {delay}s"))
                time.sleep(delay)
                delay = min(delay * 2, 60)
            finally:
                try:
                    if self.ws:
                        self.ws.close()
                except Exception:
                    pass
