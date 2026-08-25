"""Read translated chat aloud to the streamer.

Primary: Microsoft neural voices via edge-tts — natural, free, per-language
(needs internet). Playback through Windows' built-in MCI, so no media
player dependencies. Fallback: offline SAPI (pyttsx3) if the neural path
fails. Flood-safe: at most 3 queued lines, oldest dropped."""
import asyncio
import ctypes
import os
import queue
import tempfile
import threading
import time

VOICE_STYLES = {
    "male": {
        "en": "en-US-ChristopherNeural", "pt": "pt-BR-AntonioNeural",
        "es": "es-MX-JorgeNeural", "he": "he-IL-AvriNeural",
        "pl": "pl-PL-MarekNeural", "ja": "ja-JP-KeitaNeural",
        "zh": "zh-CN-YunxiNeural", "ko": "ko-KR-InJoonNeural",
        "fr": "fr-FR-HenriNeural", "de": "de-DE-ConradNeural",
        "ru": "ru-RU-DmitryNeural", "tr": "tr-TR-AhmetNeural",
        "ar": "ar-SA-HamedNeural", "hi": "hi-IN-MadhurNeural",
        "it": "it-IT-DiegoNeural", "nl": "nl-NL-MaartenNeural",
        "uk": "uk-UA-OstapNeural", "vi": "vi-VN-NamMinhNeural",
        "th": "th-TH-NiwatNeural", "id": "id-ID-ArdiNeural",
    },
    "female": {   # the smooth ones
        "en": "en-US-AvaMultilingualNeural", "pt": "pt-BR-ThalitaNeural",
        "es": "es-MX-DaliaNeural", "he": "he-IL-HilaNeural",
        "pl": "pl-PL-ZofiaNeural", "ja": "ja-JP-NanamiNeural",
        "zh": "zh-CN-XiaoxiaoNeural", "ko": "ko-KR-SunHiNeural",
        "fr": "fr-FR-DeniseNeural", "de": "de-DE-KatjaNeural",
        "ru": "ru-RU-SvetlanaNeural", "tr": "tr-TR-EmelNeural",
        "ar": "ar-SA-ZariyahNeural", "hi": "hi-IN-SwaraNeural",
        "it": "it-IT-ElsaNeural", "nl": "nl-NL-FennaNeural",
        "uk": "uk-UA-PolinaNeural", "vi": "vi-VN-HoaiMyNeural",
        "th": "th-TH-PremwadeeNeural", "id": "id-ID-GadisNeural",
    },
    "expressive": {"en": "en-US-AriaNeural"},   # falls back to female map
}


def pick_voice(cfg):
    lang = cfg.get("my_lang", "en")
    style = cfg.get("tts_style", "male")
    for m in (VOICE_STYLES.get(style, {}), VOICE_STYLES["female"],
              VOICE_STYLES["male"]):
        if lang in m:
            return m[lang]
    return VOICE_STYLES["male"]["en"]


def _mci(cmd):
    ctypes.windll.winmm.mciSendStringW(cmd, None, 0, None)


class ChatSpeaker(threading.Thread):
    def __init__(self, cfg, log=print):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.log = log
        self.q = queue.Queue(maxsize=3)
        self.stop_ev = threading.Event()
        self._n = 0

    def say(self, user, text):
        if self.stop_ev.is_set():
            return
        line = f"{user}. {text}"[:220]
        try:
            self.q.put_nowait(line)
        except queue.Full:
            try:  # drop the oldest, keep the newest
                self.q.get_nowait()
                self.q.put_nowait(line)
            except queue.Empty:
                pass

    def stop(self):
        self.stop_ev.set()
        try:
            self.q.put_nowait("")
        except queue.Full:
            pass

    # ---- neural path (edge-tts + MCI playback, zero extra players) ----
    def _speak_natural(self, line):
        import edge_tts
        voice = pick_voice(self.cfg)
        self._n += 1
        tmp = os.path.join(tempfile.gettempdir(),
                           f"streamlate_tts_{os.getpid()}_{self._n}.mp3")
        asyncio.run(edge_tts.Communicate(line, voice,
                                         rate="+12%").save(tmp))
        alias = f"slv{self._n}"
        vol = int(float(self.cfg.get("tts_volume", 0.9)) * 1000)
        _mci(f'open "{tmp}" type mpegvideo alias {alias}')
        _mci(f"setaudio {alias} volume to {vol}")
        _mci(f"play {alias} wait")
        _mci(f"close {alias}")
        try:
            os.remove(tmp)
        except OSError:
            pass

    def run(self):
        natural = self.cfg.get("tts_engine", "natural") == "natural"
        offline = None
        self.log("tts: speaker ready "
                 + ("(neural voices)" if natural else "(offline voice)"))
        while not self.stop_ev.is_set():
            line = self.q.get()
            if not line or self.stop_ev.is_set():
                continue
            if natural:
                try:
                    self._speak_natural(line)
                    continue
                except Exception as e:
                    natural = False
                    self.log(f"tts: neural voice unavailable ({e}) — "
                             "switching to offline voice")
            try:
                if offline is None:
                    import pyttsx3
                    offline = pyttsx3.init()
                    offline.setProperty("rate", 185)
                    offline.setProperty(
                        "volume", float(self.cfg.get("tts_volume", 0.9)))
                offline.say(line)
                offline.runAndWait()
            except Exception as e:
                self.log(f"tts error: {e}")
                time.sleep(1)
