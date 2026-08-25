"""Voice-chat translation (Discord, in-game VC, anything you can hear).

Captures what your PC is PLAYING via Windows WASAPI loopback — no virtual
cable, no drivers — transcribes it with a multilingual whisper, translates
to your language, and injects speech bubbles into the Streamlate chat
overlay + phone page (speaker shown as 🎧).

Caveat by design: loopback hears everything on that output (game included).
Whisper's voice-activity filter ignores non-speech; music with vocals is the
main source of false captions — mute music or use the optional VB-Cable
isolation setup in the README if that bothers you.
"""
import json
import os
import threading
import time
import urllib.request

import numpy as np

_KEY = {"v": None}


def inject_key():
    """Local secret the chat process demands on /inject (the page may be
    public via the Viewers QR tunnel — only we may write to it)."""
    if _KEY["v"] is None:
        try:
            cfg_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config.json")
            with open(cfg_path, encoding="utf-8-sig") as f:
                _KEY["v"] = json.load(f).get("inject_key", "")
        except (OSError, ValueError):
            _KEY["v"] = ""
    return _KEY["v"]


class CallListener(threading.Thread):
    def __init__(self, cfg, translate_fn, log=print):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.translate = translate_fn        # (text, target, cfg) -> str
        self.log = log
        self.stop_ev = threading.Event()
        self.inject_port = None
        self.caption_cb = None               # optional: captions on stream

    def stop(self):
        self.stop_ev.set()

    # ---- push a bubble into the chat overlay / phone page ----
    def inject(self, text, translation):
        body = json.dumps({"user": "🎧", "color": "#7fd4ff",
                           "text": text, "tr": translation}).encode("utf-8")
        ports = ([self.inject_port] if self.inject_port
                 else list(range(8765, 8771)))
        for port in ports:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/inject", data=body,
                    headers={"Content-Type": "application/json",
                             "X-SL-Key": inject_key()})
                with urllib.request.urlopen(req, timeout=3) as r:
                    if r.status == 200:
                        self.inject_port = port
                        return True
            except Exception:
                continue
        self.inject_port = None
        return False

    def run(self):
        try:
            import pyaudiowpatch as pa
        except ImportError:
            self.log("call translate: pyaudiowpatch missing — pip install pyaudiowpatch")
            return
        from faster_whisper import WhisperModel
        model_name = self.cfg.get("call_model", "small")
        try:
            model = WhisperModel(model_name, device="cuda",
                                 compute_type="float16")
            probe = np.zeros(8000, dtype=np.float32)
            list(model.transcribe(probe, language="en")[0])
            self.log(f"call translate: whisper '{model_name}' on cuda")
        except Exception:
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self.log(f"call translate: whisper '{model_name}' on cpu")

        target = self.cfg.get("call_target", "en")
        show_en = bool(self.cfg.get("call_show_english", False))
        gate = float(self.cfg.get("call_silence_rms", 0.003))
        last_text = ""

        want = (self.cfg.get("call_device") or "").strip().lower()
        while not self.stop_ev.is_set():
            try:
                with pa.PyAudio() as p:
                    lb = None
                    if want:
                        for d in p.get_loopback_device_info_generator():
                            if want in d["name"].lower():
                                lb = d
                                break
                        if lb is None:
                            self.log(f"call translate: no output device "
                                     f"matching '{want}' — using default")
                    if lb is None:
                        lb = p.get_default_wasapi_loopback()
                    rate = int(lb["defaultSampleRate"])
                    ch = max(1, lb["maxInputChannels"])
                    frames = int(rate * 0.25)
                    stream = p.open(format=pa.paFloat32, channels=ch,
                                    rate=rate, input=True,
                                    input_device_index=lb["index"],
                                    frames_per_buffer=frames)
                    self.log(f"call translate: listening to '{lb['name']}'")
                    window = int(rate * 4)
                    buf = np.empty(0, dtype=np.float32)
                    while not self.stop_ev.is_set():
                        raw = stream.read(frames,
                                          exception_on_overflow=False)
                        block = np.frombuffer(raw, dtype=np.float32)
                        if ch > 1:
                            block = block.reshape(-1, ch).mean(axis=1)
                        buf = np.concatenate([buf, block])
                        if len(buf) < window:
                            continue
                        audio, buf = buf[:window], buf[window:]
                        if float(np.sqrt(np.mean(audio ** 2))) < gate:
                            continue
                        # resample to 16 kHz for whisper
                        n16 = int(len(audio) * 16000 / rate)
                        audio16 = np.interp(
                            np.linspace(0, len(audio) - 1, n16),
                            np.arange(len(audio)), audio).astype(np.float32)
                        try:
                            segs, info = model.transcribe(
                                audio16, language=None, beam_size=1,
                                vad_filter=True)
                            text = " ".join(s.text.strip()
                                            for s in segs).strip()
                        except Exception as e:
                            self.log(f"call transcribe error: {e}")
                            continue
                        if len(text) < 3 or text == last_text:
                            continue
                        last_text = text
                        lang = getattr(info, "language", "") or ""
                        if lang == target and not show_en:
                            continue
                        try:
                            translation = self.translate(text, target,
                                                         self.cfg)
                        except Exception:
                            translation = None
                        if translation and translation.strip():
                            self.inject(text, translation.strip())
                            if self.caption_cb:
                                try:
                                    self.caption_cb(text, translation.strip())
                                except Exception:
                                    pass
                    try:
                        stream.close()
                    except Exception:
                        pass
            except Exception as e:
                if self.stop_ev.is_set():
                    return
                self.log(f"call translate reconnect ({e})")
                time.sleep(8)
