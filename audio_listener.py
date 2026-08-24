"""Microphone capture + near-real-time transcription via faster-whisper.

Captures the default input device with sounddevice in rolling ~5s windows.
Loud-enough windows are transcribed and emitted via on_transcript(text).
Quiet windows accumulate into silence and are emitted via on_silence(seconds)
so the chat engine can let chat get bored.

GPU is attempted once; any CUDA problem silently falls back to CPU int8
(base/small models are fast enough on CPU for 5s windows).
"""

import queue
import threading
import time

import numpy as np
import sounddevice as sd

SAMPLERATE = 16000


class AudioListener:
    def __init__(self, on_transcript, on_silence=None, model_size="base",
                 window_seconds=5.0, silence_rms=0.006,
                 device=None, channel=None):
        """device: sounddevice input index (None = system default).
        channel: 1-based channel on that device (None = auto-pick loudest —
        multi-channel interfaces like the UA Twin often carry the mic on a
        higher channel while ch1 is dead silent)."""
        self.on_transcript = on_transcript
        self.on_silence = on_silence or (lambda s: None)
        self.model_size = model_size
        self.window_seconds = window_seconds
        self.silence_rms = silence_rms
        self.device = device
        self.channel = channel          # 1-based, resolved in start()
        self._ch_idx = 0
        self._n_ch = 1
        self.model = None
        self.device_used = None
        self._q = queue.Queue()
        self._running = False
        self._stream = None

    @staticmethod
    def list_input_devices():
        default_in = sd.default.device[0]
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                api = sd.query_hostapis(d["hostapi"])["name"]
                out.append("[%d] %s (api=%s, ch=%d)%s" % (
                    i, d["name"], api, d["max_input_channels"],
                    "  <-- default" if i == default_in else ""))
        return out

    def _pick_channel(self):
        """Record 2s across all channels, pick the loudest one."""
        info = sd.query_devices(
            self.device if self.device is not None else sd.default.device[0])
        n_ch = info["max_input_channels"]
        self._n_ch = n_ch
        if self.channel is not None:
            self._ch_idx = self.channel - 1
            print("[mic] using channel %d (manual)" % self.channel)
            return
        if n_ch == 1:
            self._ch_idx = 0
            return
        print("[mic] auto-detecting live channel on '%s' (%d channels)..."
              % (info["name"], n_ch))
        rec = sd.rec(int(2 * SAMPLERATE), samplerate=SAMPLERATE,
                     channels=n_ch, dtype="float32", device=self.device)
        sd.wait()
        rms = np.sqrt(np.mean(rec.astype(np.float64) ** 2, axis=0))
        self._ch_idx = int(np.argmax(rms))
        best = float(rms[self._ch_idx])
        print("[mic] picked channel %d (rms=%.5f)" % (self._ch_idx + 1, best))
        if best < 0.00005:
            print("[mic] WARNING: every channel is near-silent. Check your "
                  "interface's routing/gain (e.g. UA Console) or run with "
                  "--list-devices and pass --device N.")

    # ------------------------------------------------------------------ model

    def load_model(self):
        from faster_whisper import WhisperModel
        try:
            model = WhisperModel(self.model_size, device="cuda",
                                 compute_type="float16")
            # force real initialization; fall back on any CUDA problem
            probe = np.zeros(int(SAMPLERATE * 0.5), dtype=np.float32)
            list(model.transcribe(probe, language="en")[0])
            self.device_used = "cuda"
        except Exception:
            model = WhisperModel(self.model_size, device="cpu",
                                 compute_type="int8")
            self.device_used = "cpu"
        self.model = model
        print("[mic] faster-whisper '%s' loaded on %s"
              % (self.model_size, self.device_used))

    # -------------------------------------------------------------- lifecycle

    def start(self):
        if self.model is None:
            self.load_model()
        self._pick_channel()
        self._running = True
        self._stream = sd.InputStream(
            samplerate=SAMPLERATE, channels=self._n_ch, dtype="float32",
            device=self.device,
            blocksize=int(SAMPLERATE * 0.25), callback=self._callback)
        self._stream.start()
        worker = threading.Thread(target=self._worker, daemon=True,
                                  name="audio-worker")
        worker.start()
        print("[mic] listening (channel %d, %.0fs windows, ctrl+c to stop)"
              % (self._ch_idx + 1, self.window_seconds))

    def stop(self):
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass

    # -------------------------------------------------------------- internals

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass  # over/underruns are fine for this use case
        self._q.put(indata[:, self._ch_idx:self._ch_idx + 1].copy())

    def _worker(self):
        window_samples = int(SAMPLERATE * self.window_seconds)
        chunks = []
        total = 0
        silence_accum = 0.0
        while self._running:
            try:
                chunk = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total < window_samples:
                continue
            audio = np.concatenate(chunks)[:, 0]
            chunks, total = [], 0

            rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
            bar = "#" * min(int(rms / 0.05 * 10), 10)
            print("[mic] level [%-10s] rms=%.4f %s"
                  % (bar, rms, "SPEECH" if rms >= self.silence_rms else "quiet"))
            if rms < self.silence_rms:
                silence_accum += self.window_seconds
                try:
                    self.on_silence(silence_accum)
                except Exception as e:
                    print("[mic] on_silence error: %r" % e)
                continue

            text = self._transcribe(audio)
            if text:
                silence_accum = 0.0
                try:
                    self.on_transcript(text)
                except Exception as e:
                    print("[mic] on_transcript error: %r" % e)
            else:
                silence_accum += self.window_seconds

    def _transcribe(self, audio):
        try:
            segments, _info = self.model.transcribe(
                audio, language="en", beam_size=1, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            print("[mic] transcription error: %r" % e)
            return ""


if __name__ == "__main__":
    # quick standalone check: prints whatever it hears
    listener = AudioListener(on_transcript=lambda t: print("[you] " + t),
                             on_silence=lambda s: print("[mic] silence %.0fs" % s))
    listener.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()
