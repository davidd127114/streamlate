"""Read translated chat aloud to the streamer — offline Windows voices,
zero external services. Flood-safe: keeps at most 3 queued lines and
drops the oldest, so a raid never builds a backlog of speech."""
import queue
import threading


class ChatSpeaker(threading.Thread):
    def __init__(self, cfg, log=print):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.log = log
        self.q = queue.Queue(maxsize=3)
        self.stop_ev = threading.Event()

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

    def run(self):
        try:
            import pyttsx3
        except ImportError:
            self.log("tts: pyttsx3 missing — pip install pyttsx3")
            return
        engine = pyttsx3.init()
        engine.setProperty("rate", 185)
        engine.setProperty("volume", float(self.cfg.get("tts_volume", 0.9)))
        # prefer a voice matching the language the streamer reads in
        want = {"en": "english", "pt": "portug", "es": "spanish",
                "pl": "polish", "he": "hebrew", "ja": "japanese",
                "zh": "chinese", "ko": "korean", "fr": "french",
                "de": "german", "ru": "russian"}.get(
                    self.cfg.get("my_lang", "en"), "english")
        for v in engine.getProperty("voices"):
            blob = (v.name + " " + (v.id or "")).lower()
            if want in blob:
                engine.setProperty("voice", v.id)
                break
        self.log("tts: speaker ready")
        while not self.stop_ev.is_set():
            line = self.q.get()
            if not line or self.stop_ev.is_set():
                continue
            try:
                engine.say(line)
                engine.runAndWait()
            except Exception as e:
                self.log(f"tts error: {e}")
