"""VIEWER MODE — watch any foreign stream with live translation.

The flip side of Streamlate: instead of translating YOUR stream for
viewers, translate SOMEONE ELSE'S stream for you. Two tools:

  1. Voice captions — whatever the PC is playing (any stream, any site)
     is transcribed with language auto-detect and translated to your
     language in a draggable caption pill. Reuses the WASAPI-loopback
     listener from voice-chat translation — no virtual cables.
  2. Screen text (beta) — drag a box over on-screen text (their chat,
     their overlay) and it is OCR'd with Windows' built-in engine and
     translated live in a panel next to it.

No servers, no OBS, no chat login — this mode touches nothing of the
streamer setup. Toggle back in the Streamlate Control panel.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "viewer.log")
ALIVE_PATH = os.path.join(APP_DIR, "viewer.alive")
CREATE_NO_WINDOW = 0x08000000

BG, FG, ACC, DIM = "#141417", "#e8e8ee", "#a970ff", "#8a8a92"

LANG_NAMES = {"en": "English", "pt": "Português", "es": "Español",
              "fr": "Français", "de": "Deutsch", "ja": "日本語",
              "ko": "한국어", "ru": "Русский", "zh": "中文",
              "he": "עברית", "pl": "Polski", "ar": "العربية",
              "it": "Italiano", "nl": "Nederlands", "tr": "Türkçe",
              "hi": "हिन्दी", "id": "Indonesia", "vi": "Tiếng Việt",
              "th": "ไทย", "uk": "Українська", "cs": "Čeština",
              "sv": "Svenska", "ro": "Română", "el": "Ελληνικά",
              "hu": "Magyar", "da": "Dansk", "fi": "Suomi",
              "no": "Norsk", "bg": "Български", "ms": "Melayu"}

# (original font, translation font, wraplength)
SIZES = {"s": (10, 14, 480), "m": (11, 18, 600), "l": (14, 23, 720)}


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(**kv):
    """Read-modify-write so we never clobber keys other tools own."""
    cfg = load_config()
    cfg.update(kv)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------- translation
# Google web chain only: viewer mode must stay near-zero footprint (the
# viewer may be gaming while watching) and the source language is unknown.

def _clients5(text, target):
    url = ("https://clients5.google.com/translate_a/t"
           f"?client=dict-chrome-ex&sl=auto&tl={target}&q="
           + urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    entry = data[0] if data else ""
    return entry[0] if isinstance(entry, list) else str(entry)


def _gtx(text, target):
    url = ("https://translate.googleapis.com/translate_a/single"
           f"?client=gtx&sl=auto&tl={target}&dt=t&q="
           + urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])


def translate(text, target, _cfg=None):
    try:
        return _clients5(text, target)
    except Exception:
        return _gtx(text, target)


def pick_whisper_model():
    try:
        import hardware
        vram = hardware.nvidia_vram_gb()
    except Exception:
        vram = 0.0
    if vram >= 16:
        return "medium"     # best multilingual ears, still light on a big GPU
    if vram >= 6:
        return "small"
    return "base"           # CPU fallback


# ---------------------------------------------------------------- OCR (beta)

class OcrWorker:
    """Grabs a screen region every couple of seconds, OCRs it with the
    long-running PowerShell bridge, and hands changed text to a callback."""

    def __init__(self, bbox, target, on_text, on_status):
        self.bbox = bbox
        self.target = target
        self.on_text = on_text
        self.on_status = on_status
        self.stop_ev = threading.Event()
        self.proc = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_ev.set()
        try:
            if self.proc:
                self.proc.stdin.write("QUIT\n")
                self.proc.stdin.flush()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass

    def _run(self):
        from PIL import ImageGrab
        try:
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", os.path.join(APP_DIR, "ocr_win.ps1"), "-Watch"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", bufsize=1,
                creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            log(f"ocr: could not start bridge ({e})")
            return
        frames = [os.path.join(tempfile.gettempdir(),
                               f"streamlate_ocr_{i}.png") for i in (0, 1)]
        last, tick, empties, ever = "", 0, 0, False
        while not self.stop_ev.is_set():
            path = frames[tick % 2]
            tick += 1
            try:
                ImageGrab.grab(bbox=self.bbox).save(path)
                self.proc.stdin.write(path + "\n")
                self.proc.stdin.flush()
                lines = []
                while True:
                    ln = self.proc.stdout.readline()
                    if not ln or ln.strip() in ("<<<END>>>", "<<<NOENGINE>>>"):
                        break
                    if ln.strip():
                        lines.append(ln.strip())
            except Exception as e:
                log(f"ocr tick failed ({e})")
                break
            text = " ".join(lines).strip()
            norm = " ".join(text.lower().split())
            if not text:
                empties += 1
                if empties >= 5 and not ever:
                    self.on_status("nohit")
            elif norm != last:
                last, empties, ever = norm, 0, True
                try:
                    tr_text = translate(text[:600], self.target)
                except Exception:
                    tr_text = ""
                if tr_text.strip():
                    self.on_text(tr_text.strip())
            for _ in range(10):
                if self.stop_ev.is_set():
                    break
                time.sleep(0.25)
        for path in frames:
            try:
                os.remove(path)
            except OSError:
                pass


# ---------------------------------------------------------------- the app

class ViewerApp:
    def __init__(self):
        from i18n import tr
        self.tr = tr
        cfg = load_config()
        self.target = cfg.get("viewer_target") or cfg.get("my_lang") or "en"
        self.show_orig = bool(cfg.get("viewer_show_orig", True))
        self.size = cfg.get("viewer_size", "m")
        if self.size not in SIZES:
            self.size = "m"
        self.device = cfg.get("viewer_device", "")
        self._device_cache = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg=BG)
        self.frame = tk.Frame(self.root, bg=BG, highlightbackground=ACC,
                              highlightthickness=2, padx=16, pady=10)
        self.frame.pack(fill="both", expand=True)
        self.lbl_orig = tk.Label(self.frame, text="", bg=BG, fg=DIM,
                                 justify="left", anchor="w")
        self.lbl_main = tk.Label(self.frame, text=tr("v_listening"), bg=BG,
                                 fg=FG, justify="left", anchor="w")
        self.lbl_main.pack(anchor="w")
        self._apply_size()

        pos = cfg.get("viewer_pos", "")
        try:
            x, y = (int(v) for v in pos.split(","))
            self.root.geometry(f"+{x}+{y}")
        except (ValueError, AttributeError):
            self.root.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"+{(sw - 640) // 2}+{sh - 220}")
        self.root.deiconify()

        for w in (self.root, self.frame, self.lbl_main, self.lbl_orig):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Button-3>", self._menu)

        self.listener = None
        self.ocr = None
        self.ocr_panel = None
        self.last_caption_t = 0.0
        self._start_listener()
        self._tick()

    # ---- caption pill ----
    def _apply_size(self):
        fo, fm, wrap = SIZES[self.size]
        self.lbl_orig.config(font=("Segoe UI", fo), wraplength=wrap)
        self.lbl_main.config(font=("Segoe UI", fm, "bold"), wraplength=wrap)

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root, e.y_root
        self._wx, self._wy = self.root.winfo_x(), self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{self._wx + e.x_root - self._dx}"
                           f"+{self._wy + e.y_root - self._dy}")

    def _drag_end(self, _e):
        save_config(viewer_pos=f"{self.root.winfo_x()},{self.root.winfo_y()}")

    def _caption(self, text, translated):
        def show():
            self.last_caption_t = time.time()
            self.lbl_main.config(text=translated, fg=FG)
            if self.show_orig:
                self.lbl_orig.config(text=text, fg=DIM)
                self.lbl_orig.pack(anchor="w", before=self.lbl_main)
            else:
                self.lbl_orig.pack_forget()
        self.root.after(0, show)

    def _tick(self):
        try:
            with open(ALIVE_PATH, "w") as f:
                f.write(str(time.time()))
        except OSError:
            pass
        # dim a caption nobody has replaced in a while
        if self.last_caption_t and time.time() - self.last_caption_t > 14:
            self.lbl_main.config(fg=DIM)
        self.root.after(2000, self._tick)

    # ---- audio listener ----
    def _start_listener(self):
        from call_audio import CallListener
        if self.listener:
            self.listener.stop()
        vcfg = {"call_model": pick_whisper_model(), "call_target": self.target,
                "call_show_english": False, "call_silence_rms": 0.0035,
                "call_device": self.device}
        self.listener = CallListener(vcfg, translate, log)
        self.listener.inject = lambda *a, **k: False   # no chat overlay here
        self.listener.caption_cb = self._caption
        self.listener.start()
        log(f"viewer mode: listening, target={self.target}, "
            f"whisper={vcfg['call_model']}")

    def _loopback_devices(self):
        """Output devices we can listen to — so the viewer can keep their
        own music on one device and the stream on another."""
        if self._device_cache is None:
            names = []
            try:
                import pyaudiowpatch as pa
                with pa.PyAudio() as p:
                    for d in p.get_loopback_device_info_generator():
                        n = d["name"].replace(" [Loopback]", "").strip()
                        if n and n not in names:
                            names.append(n)
            except Exception:
                pass
            self._device_cache = names
        return self._device_cache

    def _set_device(self, name):
        self.device = name
        save_config(viewer_device=name)
        self.lbl_main.config(text=self.tr("v_listening"), fg=FG)
        self.lbl_orig.pack_forget()
        self._start_listener()

    def _set_target(self, code):
        self.target = code
        save_config(viewer_target=code)
        self.lbl_main.config(text=self.tr("v_listening"), fg=FG)
        self.lbl_orig.pack_forget()
        self._start_listener()          # listener reads target once at start
        if self.ocr:
            self.ocr.target = code

    def _menu(self, e):
        tr = self.tr
        m = tk.Menu(self.root, tearoff=0, bg="#1e1e24", fg=FG,
                    activebackground=ACC, activeforeground="#ffffff")
        lang = tk.Menu(m, tearoff=0, bg="#1e1e24", fg=FG,
                       activebackground=ACC, activeforeground="#ffffff")
        for code, name in LANG_NAMES.items():
            lang.add_radiobutton(
                label=name, value=code,
                variable=tk.StringVar(value=self.target),
                command=lambda c=code: self._set_target(c))
        m.add_cascade(label=f"🌐 {tr('v_lang')}  ({self.target})", menu=lang)
        m.add_checkbutton(label=tr("v_showorig"),
                          onvalue=True, offvalue=False,
                          variable=tk.BooleanVar(value=self.show_orig),
                          command=self._toggle_orig)
        size = tk.Menu(m, tearoff=0, bg="#1e1e24", fg=FG,
                       activebackground=ACC, activeforeground="#ffffff")
        for key, label in (("s", tr("v_size_s")), ("m", tr("v_size_m")),
                           ("l", tr("v_size_l"))):
            size.add_radiobutton(label=label, value=key,
                                 variable=tk.StringVar(value=self.size),
                                 command=lambda k=key: self._set_size(k))
        m.add_cascade(label=f"🔠 {tr('v_size')}", menu=size)
        dev = tk.Menu(m, tearoff=0, bg="#1e1e24", fg=FG,
                      activebackground=ACC, activeforeground="#ffffff")
        dev.add_radiobutton(label=tr("v_device_default"), value="",
                            variable=tk.StringVar(value=self.device),
                            command=lambda: self._set_device(""))
        for name in self._loopback_devices():
            dev.add_radiobutton(label=name[:48], value=name,
                                variable=tk.StringVar(value=self.device),
                                command=lambda n=name: self._set_device(n))
        m.add_cascade(label=f"🔈 {tr('v_device')}", menu=dev)
        m.add_separator()
        m.add_command(label=("🛑 " + tr("v_ocr_off")) if self.ocr
                      else ("📖 " + tr("v_ocr_on")),
                      command=self._toggle_ocr)
        m.add_separator()
        m.add_command(label="✖ " + tr("v_quit"), command=self._quit)
        m.tk_popup(e.x_root, e.y_root)

    def _toggle_orig(self):
        self.show_orig = not self.show_orig
        save_config(viewer_show_orig=self.show_orig)
        if not self.show_orig:
            self.lbl_orig.pack_forget()

    def _set_size(self, key):
        self.size = key
        save_config(viewer_size=key)
        self._apply_size()

    # ---- screen-text OCR (beta) ----
    def _toggle_ocr(self):
        if self.ocr:
            self._stop_ocr()
            return
        self._select_region()

    def _select_region(self):
        tr = self.tr
        sel = tk.Toplevel(self.root)
        sel.attributes("-fullscreen", True)
        sel.attributes("-topmost", True)
        sel.attributes("-alpha", 0.25)
        sel.configure(bg="black", cursor="crosshair")
        cv = tk.Canvas(sel, bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(sel.winfo_screenwidth() // 2, 60,
                       text=tr("v_ocr_hint"), fill="#ffffff",
                       font=("Segoe UI", 16, "bold"))
        state = {"x": 0, "y": 0, "rect": None}

        def down(e):
            state["x"], state["y"] = e.x, e.y
            state["rect"] = cv.create_rectangle(e.x, e.y, e.x, e.y,
                                                outline=ACC, width=3)

        def move(e):
            if state["rect"]:
                cv.coords(state["rect"], state["x"], state["y"], e.x, e.y)

        def up(e):
            x1 = min(state["x"], e.x)
            y1 = min(state["y"], e.y)
            x2 = max(state["x"], e.x)
            y2 = max(state["y"], e.y)
            sel.destroy()
            if x2 - x1 > 40 and y2 - y1 > 15:
                self._start_ocr((x1, y1, x2, y2))

        cv.bind("<Button-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        sel.bind("<Escape>", lambda _e: sel.destroy())
        sel.focus_force()

    def _start_ocr(self, bbox):
        tr = self.tr
        panel = tk.Toplevel(self.root)
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.attributes("-alpha", 0.93)
        panel.configure(bg=BG)
        pf = tk.Frame(panel, bg=BG, highlightbackground="#3fbf6f",
                      highlightthickness=2, padx=12, pady=8)
        pf.pack(fill="both", expand=True)
        width = max(280, min(900, bbox[2] - bbox[0]))
        lbl = tk.Label(pf, text="📖 …", bg=BG, fg=FG, justify="left",
                       anchor="w", font=("Segoe UI", 12),
                       wraplength=width - 40)
        lbl.pack(side="left", fill="both", expand=True)
        tk.Button(pf, text="✕", command=self._stop_ocr, bg=BG, fg=DIM,
                  bd=0, font=("Segoe UI", 10),
                  activebackground=BG, activeforeground=FG).pack(
                      side="right", anchor="n")
        y = bbox[3] + 8
        if y + 120 > panel.winfo_screenheight():
            y = max(0, bbox[1] - 120)
        panel.geometry(f"+{bbox[0]}+{y}")
        drag = {}

        def pdown(e):
            drag["dx"], drag["dy"] = e.x_root, e.y_root
            drag["wx"], drag["wy"] = panel.winfo_x(), panel.winfo_y()

        def pmove(e):
            panel.geometry(f"+{drag['wx'] + e.x_root - drag['dx']}"
                           f"+{drag['wy'] + e.y_root - drag['dy']}")
        for w in (panel, pf, lbl):
            w.bind("<Button-1>", pdown)
            w.bind("<B1-Motion>", pmove)
        self.ocr_panel = (panel, lbl)

        def on_text(text):
            self.root.after(0, lambda: lbl.config(text=text))

        def on_status(kind):
            if kind == "nohit":
                self.root.after(0, lambda: lbl.config(
                    text=tr("v_ocr_nohit"), fg="#e6c07b"))
        self.ocr = OcrWorker(bbox, self.target, on_text, on_status)

    def _stop_ocr(self):
        if self.ocr:
            self.ocr.stop()
            self.ocr = None
        if self.ocr_panel:
            try:
                self.ocr_panel[0].destroy()
            except tk.TclError:
                pass
            self.ocr_panel = None

    def _quit(self):
        self._stop_ocr()
        if self.listener:
            self.listener.stop()
        try:
            os.remove(ALIVE_PATH)
        except OSError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    # single instance
    try:
        import ctypes
        ctypes.windll.kernel32.CreateMutexW(None, False, "StreamlateViewerMode")
        if ctypes.windll.kernel32.GetLastError() == 183:   # already exists
            return
        try:   # crisp coords on scaled displays (OCR region must be exact)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    except Exception:
        pass
    log("viewer mode starting")
    ViewerApp().run()


if __name__ == "__main__":
    main()
