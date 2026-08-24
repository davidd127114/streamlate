"""First-run setup — one small window, four questions, everything else is
auto-detected. Writes config.json (chat translator) and subs_config.json
(stream subtitles). Run with --auto for a no-questions default setup."""
import json
import os
import subprocess
import sys
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CREATE_NO_WINDOW = 0x08000000

import hardware
from i18n import tr

LANGS = [("English", "en"), ("Portuguese (Brazil)", "pt"), ("Spanish", "es"),
         ("French", "fr"), ("German", "de"), ("Japanese", "ja"),
         ("Korean", "ko"), ("Russian", "ru"), ("Chinese", "zh")]


def _merge_into(path, new_keys):
    """Update a config file without wiping settings the user tuned by hand."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        cur = {}
    cur.update(new_keys)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)


def write_configs(channel, target_lang, mic_device, plan, engine_url,
                  spoken_lang="en"):
    chat = {
        "channel": channel,
        "platform": "auto",
        "translator": plan["translator"],
        "ollama_model": plan["ollama_model"] or "gemma3:4b",
        "engine_url": engine_url,
    }
    whisper_model = plan["whisper_model"]
    if spoken_lang != "en" and whisper_model.endswith(".en"):
        whisper_model = whisper_model[:-3]   # multilingual variant
    subs = {
        "spoken_lang": spoken_lang,
        "target_lang": target_lang,
        "mic_device": mic_device,
        "translator": plan["translator"],
        "ollama_model": plan["ollama_model"] or "gemma3:4b",
        "engine_url": engine_url,
        "model": whisper_model,
        "use_gpu": plan["use_gpu"],
    }
    _merge_into(os.path.join(APP_DIR, "config.json"), chat)
    _merge_into(os.path.join(APP_DIR, "subs_config.json"), subs)


def list_mics():
    try:
        from audio_listener import AudioListener
        return AudioListener.list_input_devices()
    except Exception:
        return []


def main_auto():
    plan = hardware.pick()
    write_configs("", "pt", None, plan, "http://localhost:11434")
    print("auto setup written:", plan)


def main_gui():
    import tkinter as tk
    from tkinter import ttk

    plan = hardware.pick()
    root = tk.Tk()
    root.title(tr("wiz_title"))
    root.configure(bg="#141417")
    root.resizable(False, False)
    FG, BG, ACC = "#e8e8ee", "#141417", "#a970ff"

    def row(label):
        f = tk.Frame(root, bg=BG)
        f.pack(fill="x", padx=24, pady=(10, 0))
        tk.Label(f, text=label, bg=BG, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        return f

    tk.Label(root, text="Streamlate", bg=BG, fg=ACC,
             font=("Segoe UI", 16, "bold"), pady=10).pack()

    r = row(tr("wiz_channel"))
    channel_var = tk.StringVar()
    tk.Entry(r, textvariable=channel_var, width=42,
             font=("Segoe UI", 11)).pack(anchor="w", pady=3)

    r = row(tr("wiz_speak"))
    spoken_var = tk.StringVar(value=LANGS[0][0])
    ttk.Combobox(r, textvariable=spoken_var, state="readonly", width=28,
                 values=[n for n, _ in LANGS]).pack(anchor="w", pady=3)

    r = row(tr("wiz_caption"))
    lang_var = tk.StringVar(value=LANGS[1][0])
    ttk.Combobox(r, textvariable=lang_var, state="readonly", width=28,
                 values=[n for n, _ in LANGS]).pack(anchor="w", pady=3)

    r = row(tr("wiz_mic"))
    mics = list_mics()
    mic_var = tk.StringVar(value=tr("wiz_mic_default"))
    ttk.Combobox(r, textvariable=mic_var, state="readonly", width=48,
                 values=[tr("wiz_mic_default")] + mics).pack(anchor="w", pady=3)

    r = row(tr("wiz_engine"))
    if plan["translator"] == "ollama":
        engine_txt = (f"GPU: {plan['vram_gb']} GB → {plan['ollama_model']} "
                      f"({plan['note']})")
    else:
        engine_txt = (f"GPU: {plan['vram_gb']} GB → {plan['note']}"
                      + ("" if plan["ollama_installed"] or plan["vram_gb"] < 6
                         else "\n" + tr("wiz_engine_tip")))
    tk.Label(r, text=engine_txt, bg=BG, fg="#9adf9e", justify="left",
             font=("Segoe UI", 10)).pack(anchor="w", pady=3)

    r = row(tr("wiz_url"))
    url_var = tk.StringVar(value="http://localhost:11434")
    tk.Entry(r, textvariable=url_var, width=42,
             font=("Segoe UI", 10)).pack(anchor="w", pady=3)

    status = tk.Label(root, text="", bg=BG, fg="#c9a2ff", font=("Segoe UI", 10))
    status.pack(pady=(10, 0))

    def pull_then_save():
        model = plan["ollama_model"]
        need_pull = (plan["translator"] == "ollama"
                     and model not in hardware.installed_ollama_models())
        if need_pull:
            status.config(text=tr("wiz_downloading", model=model,
                                  size=plan["download"]))
            root.update_idletasks()
            try:
                exe = hardware.ollama_exe() or "ollama"
                subprocess.run([exe, "pull", model], timeout=7200,
                               creationflags=CREATE_NO_WINDOW)
            except Exception:
                plan["translator"] = "google"  # still works, just simpler engine
        finish()

    def finish():
        mic = mic_var.get()
        mic_idx = None
        if mic.startswith("["):
            mic_idx = int(mic.split("]")[0][1:])
        lang = dict(LANGS)[lang_var.get()]
        ch = channel_var.get().strip()
        if not (ch.startswith("@") or "/" in ch):   # plain Twitch name
            ch = ch.lstrip("#").lower()
        write_configs(ch, lang, mic_idx, plan, url_var.get().strip(),
                      spoken_lang=dict(LANGS)[spoken_var.get()])
        root.destroy()

    def save():
        if not channel_var.get().strip():
            status.config(text=tr("wiz_need_channel"))
            return
        threading.Thread(target=pull_then_save, daemon=True).start()

    tk.Button(root, text=tr("wiz_save"), command=save, bg=ACC, fg="white",
              font=("Segoe UI", 11, "bold"), bd=0, padx=24,
              pady=8).pack(pady=16)
    root.mainloop()


if __name__ == "__main__":
    if "--auto" in sys.argv:
        main_auto()
    else:
        main_gui()
