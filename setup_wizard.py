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
         ("Hebrew — עברית", "he"), ("Polish — Polski", "pl"),
         ("French", "fr"), ("German", "de"), ("Japanese — 日本語", "ja"),
         ("Korean — 한국어", "ko"), ("Russian", "ru"),
         ("Chinese — 中文", "zh"), ("Arabic — العربية", "ar"),
         ("Italian", "it"), ("Dutch", "nl"), ("Turkish — Türkçe", "tr"),
         ("Hindi — हिन्दी", "hi"), ("Indonesian", "id"),
         ("Vietnamese — Tiếng Việt", "vi"), ("Thai — ไทย", "th"),
         ("Ukrainian — Українська", "uk"), ("Czech — Čeština", "cs"),
         ("Swedish", "sv"), ("Romanian", "ro"), ("Greek — Ελληνικά", "el"),
         ("Hungarian", "hu"), ("Danish", "da"), ("Finnish", "fi"),
         ("Norwegian", "no"), ("Bulgarian", "bg"), ("Malay", "ms")]

SPOKEN_LANGS = [("Auto — I mix languages (detect)", "auto")] + LANGS

HARD_SPEECH = {"he", "ja", "ko", "zh", "ru", "pl", "ar", "hi", "th",
               "vi", "uk", "el", "bg", "auto"}


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


def read_config(name):
    try:
        with open(os.path.join(APP_DIR, name), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_configs(channel, target_lang, mic_device, plan, engine_url,
                  spoken_lang="en", extra_chat=None, extra_subs=None):
    # A quality tier the user picked by hand is sacred: never let a
    # settings visit re-run auto-detect over it.
    keep_engine = read_config("config.json").get("quality",
                                                 "auto") not in ("", "auto")
    chat = {
        "channel": channel,
        "platform": "auto",
        "engine_url": engine_url,
    }
    if not keep_engine:
        chat.update({"translator": plan["translator"],
                     "ollama_model": plan["ollama_model"] or "gemma3:4b"})
    chat.update(extra_chat or {})
    whisper_model = plan["whisper_model"]
    if spoken_lang != "en" and whisper_model.endswith(".en"):
        whisper_model = whisper_model[:-3]   # multilingual variant
    if spoken_lang in HARD_SPEECH and plan["use_gpu"]:
        whisper_model = "medium"             # better ears for these languages
    subs = {
        "spoken_lang": spoken_lang,
        "target_lang": target_lang,
        "mic_device": mic_device,
        "engine_url": engine_url,
    }
    if not keep_engine:
        subs.update({"translator": plan["translator"],
                     "ollama_model": plan["ollama_model"] or "gemma3:4b",
                     "model": whisper_model,
                     "use_gpu": plan["use_gpu"]})
    subs.update(extra_subs or {})
    _merge_into(os.path.join(APP_DIR, "config.json"), chat)
    _merge_into(os.path.join(APP_DIR, "subs_config.json"), subs)


def list_outputs():
    """Loopback-capturable output devices for voice-chat translation."""
    try:
        import pyaudiowpatch as pa
        with pa.PyAudio() as p:
            return [d["name"].replace(" [Loopback]", "")
                    for d in p.get_loopback_device_info_generator()]
    except Exception:
        return []


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
    chat_cfg = read_config("config.json")
    subs_cfg = read_config("subs_config.json")
    code2name = {c: n for n, c in LANGS}

    root = tk.Tk()
    root.title(tr("wiz_title"))
    root.configure(bg="#141417")
    root.resizable(False, False)
    FG, BG, ACC = "#e8e8ee", "#141417", "#a970ff"

    def row(label, parent=None):
        f = tk.Frame(parent or root, bg=BG)
        f.pack(fill="x", padx=24, pady=(8, 0))
        tk.Label(f, text=label, bg=BG, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        return f

    tk.Label(root, text="Streamlate", bg=BG, fg=ACC,
             font=("Segoe UI", 16, "bold"), pady=8).pack()

    r = row(tr("wiz_channel"))
    channel_var = tk.StringVar(value=chat_cfg.get("channel", ""))
    tk.Entry(r, textvariable=channel_var, width=42,
             font=("Segoe UI", 11)).pack(anchor="w", pady=3)

    r = row(tr("wiz_speak"))
    spoken2name = {c: n for n, c in SPOKEN_LANGS}
    spoken_var = tk.StringVar(
        value=spoken2name.get(subs_cfg.get("spoken_lang", "en"),
                              SPOKEN_LANGS[1][0]))
    spoken_cb = ttk.Combobox(r, textvariable=spoken_var, state="readonly",
                             width=30, values=[n for n, _ in SPOKEN_LANGS])
    spoken_cb.pack(anchor="w", pady=3)

    def _audience_defaults(_ev=None):
        # growth logic: non-English streamer → viewer-facing stuff defaults
        # to English (the bridge language); English streamer → Portuguese.
        default = ("English" if dict(SPOKEN_LANGS)[spoken_var.get()] != "en"
                   else "Portuguese (Brazil)")
        lang_var.set(default)
        obslang_var.set(default)
    spoken_cb.bind("<<ComboboxSelected>>", _audience_defaults)

    r = row(tr("wiz_caption"))
    lang_var = tk.StringVar(
        value=code2name.get(subs_cfg.get("target_lang", "pt"), LANGS[1][0]))
    ttk.Combobox(r, textvariable=lang_var, state="readonly", width=28,
                 values=[n for n, _ in LANGS]).pack(anchor="w", pady=3)

    r = row(tr("wiz_mic"))
    mics = list_mics()
    mic_default = tr("wiz_mic_default")
    cur_mic = subs_cfg.get("mic_device")
    mic_init = mic_default
    if cur_mic is not None:
        for m in mics:
            if m.startswith(f"[{cur_mic}]"):
                mic_init = m
                break
    mic_var = tk.StringVar(value=mic_init)
    ttk.Combobox(r, textvariable=mic_var, state="readonly", width=48,
                 values=[mic_default] + mics).pack(anchor="w", pady=3)

    r = row("")
    en_chat_var = tk.BooleanVar(value=chat_cfg.get("enable_chat", True))
    en_subs_var = tk.BooleanVar(value=chat_cfg.get("enable_subs", True))
    for var, key in ((en_chat_var, "wiz_enable_chat"),
                     (en_subs_var, "wiz_enable_subs")):
        tk.Checkbutton(r, text=tr(key), variable=var, bg=BG, fg=FG,
                       selectcolor="#26262c", activebackground=BG,
                       activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w")

    r = row("OBS")
    obs_lbl = tk.Label(r, text="…", bg=BG, fg="#8a8a92", justify="left",
                       font=("Segoe UI", 10))
    obs_lbl.pack(anchor="w", pady=2)

    def _obs_status():
        try:
            from obs_link import status
            state, _pw = status(chat_cfg)
            txt, col = {
                "ok": (tr("wiz_obs_ok"), "#9adf9e"),
                "waiting": (tr("wiz_obs_wait"), "#e6c07b"),
                "restart": (tr("wiz_obs_restart"), "#e6c07b"),
                "none": (tr("wiz_obs_none"), "#8a8a92"),
            }[state]
            root.after(0, lambda: obs_lbl.config(text=txt, fg=col))
        except Exception:
            pass
    threading.Thread(target=_obs_status, daemon=True).start()

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

    # ---------------- advanced (folded away for first-time users) ----------
    adv = tk.Frame(root, bg=BG)
    adv_open = tk.BooleanVar(value=False)

    def toggle_adv():
        if adv_open.get():
            adv.pack_forget()
            adv_open.set(False)
            adv_btn.config(text="⚙  " + tr("wiz_more") + "  ▸")
        else:
            adv.pack(fill="x", before=status)
            adv_open.set(True)
            adv_btn.config(text="⚙  " + tr("wiz_more") + "  ▾")

    adv_btn = tk.Button(root, text="", command=toggle_adv, bg="#26262c",
                        fg=FG, bd=0, font=("Segoe UI", 10), padx=14, pady=5)
    adv_btn.pack(pady=(12, 0))

    r = row(tr("wiz_calltr"), adv)
    call_var = tk.BooleanVar(value=bool(subs_cfg.get("call_translate")))
    tk.Checkbutton(r, text=tr("wiz_call_on"), variable=call_var, bg=BG,
                   fg=FG, selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")
    outs = list_outputs()
    call_dev_default = tr("wiz_out_default")
    cur_dev = (subs_cfg.get("call_device") or "").strip()
    dev_init = call_dev_default
    for o in outs:
        if cur_dev and cur_dev.lower() in o.lower():
            dev_init = o
            break
    call_dev_var = tk.StringVar(value=dev_init)
    ttk.Combobox(r, textvariable=call_dev_var, state="readonly", width=48,
                 values=[call_dev_default] + outs).pack(anchor="w", pady=3)
    call_lang_var = tk.StringVar(
        value=code2name.get(subs_cfg.get("call_target", "en"), LANGS[0][0]))
    f2 = tk.Frame(r, bg=BG)
    f2.pack(anchor="w", pady=(2, 0))
    tk.Label(f2, text=tr("wiz_call_lang"), bg=BG, fg=FG,
             font=("Segoe UI", 10)).pack(side="left")
    ttk.Combobox(f2, textvariable=call_lang_var, state="readonly", width=22,
                 values=[n for n, _ in LANGS]).pack(side="left", padx=6)
    callstream_var = tk.BooleanVar(value=bool(subs_cfg.get("call_on_stream")))
    tk.Checkbutton(r, text=tr("wiz_callstream"), variable=callstream_var,
                   bg=BG, fg=FG, selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")

    r = row(tr("wiz_cc_sec"), adv)
    cc_var = tk.BooleanVar(value=bool(subs_cfg.get("obs_cc")))
    tk.Checkbutton(r, text=tr("wiz_cc"), variable=cc_var, bg=BG, fg=FG,
                   selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")
    f_cc = tk.Frame(r, bg=BG)
    f_cc.pack(anchor="w", pady=(2, 0))
    tk.Label(f_cc, text=tr("wiz_cc_pw"), bg=BG, fg=FG,
             font=("Segoe UI", 10)).pack(side="left")
    ccpw_var = tk.StringVar(value=subs_cfg.get("obs_ws_password", ""))
    tk.Entry(f_cc, textvariable=ccpw_var, width=24, show="•",
             font=("Segoe UI", 10)).pack(side="left", padx=6)

    r = row(tr("wiz_obschat"), adv)
    obschat_var = tk.BooleanVar(value=bool(chat_cfg.get("obs_chat_enabled")))
    tk.Checkbutton(r, text=tr("wiz_obschat_on"), variable=obschat_var, bg=BG,
                   fg=FG, selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")
    f_oc = tk.Frame(r, bg=BG)
    f_oc.pack(anchor="w", pady=(2, 0))
    tk.Label(f_oc, text=tr("wiz_obschat_lang"), bg=BG, fg=FG,
             font=("Segoe UI", 10)).pack(side="left")
    obslang_var = tk.StringVar(
        value=code2name.get(chat_cfg.get("obs_chat_lang", "pt"), LANGS[1][0]))
    ttk.Combobox(f_oc, textvariable=obslang_var, state="readonly", width=22,
                 values=[n for n, _ in LANGS]).pack(side="left", padx=6)
    speakfeed_var = tk.BooleanVar(
        value=subs_cfg.get("speak_to_viewers", True))
    tk.Checkbutton(r, text=tr("wiz_speakfeed"), variable=speakfeed_var,
                   bg=BG, fg=FG, selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")
    tk.Label(r, text="OBS: http://localhost:8765/obs  (1000×420)", bg=BG,
             fg="#9adf9e", font=("Segoe UI", 9)).pack(anchor="w")

    family_var = tk.BooleanVar(value=bool(chat_cfg.get("family_filter")))
    tk.Checkbutton(r, text=tr("wiz_family"), variable=family_var, bg=BG,
                   fg=FG, selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")

    r = row(tr("wiz_tts_sec"), adv)
    tts_var = tk.BooleanVar(value=bool(chat_cfg.get("tts_enabled")))
    tk.Checkbutton(r, text=tr("wiz_tts"), variable=tts_var, bg=BG, fg=FG,
                   selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")

    r = row(tr("wiz_look"), adv)
    f3 = tk.Frame(r, bg=BG)
    f3.pack(anchor="w", pady=2)
    tk.Label(f3, text=tr("wiz_font"), bg=BG, fg=FG,
             font=("Segoe UI", 10)).pack(side="left")
    font_var = tk.IntVar(value=int(subs_cfg.get("font_px", 64)))
    tk.Spinbox(f3, from_=24, to=110, increment=4, textvariable=font_var,
               width=5, font=("Segoe UI", 10)).pack(side="left", padx=6)
    showen_var = tk.BooleanVar(value=bool(subs_cfg.get("show_english")))
    tk.Checkbutton(r, text=tr("wiz_show_both"), variable=showen_var, bg=BG,
                   fg=FG, selectcolor="#26262c", activebackground=BG,
                   activeforeground=FG,
                   font=("Segoe UI", 10)).pack(anchor="w")

    r = row(tr("wiz_hotwords"), adv)
    hot_var = tk.StringVar(value=subs_cfg.get("hotwords", ""))
    tk.Entry(r, textvariable=hot_var, width=58,
             font=("Segoe UI", 9)).pack(anchor="w", pady=3)

    r = row(tr("wiz_ui_lang"), adv)
    UI_LANGS = [("Auto", "auto"), ("English", "en"), ("Português", "pt"),
                ("Español", "es"), ("עברית", "he"), ("Polski", "pl"),
                ("日本語", "ja"), ("中文", "zh"), ("한국어", "ko")]
    ui2name = {c: n for n, c in UI_LANGS}
    ui_var = tk.StringVar(
        value=ui2name.get(chat_cfg.get("ui_lang", "auto"), "Auto"))
    ttk.Combobox(r, textvariable=ui_var, state="readonly", width=18,
                 values=[n for n, _ in UI_LANGS]).pack(anchor="w", pady=3)

    r = row(tr("wiz_url"), adv)
    url_var = tk.StringVar(
        value=chat_cfg.get("engine_url", "http://localhost:11434"))
    tk.Entry(r, textvariable=url_var, width=42,
             font=("Segoe UI", 10)).pack(anchor="w", pady=3)

    status = tk.Label(root, text="", bg=BG, fg="#c9a2ff", font=("Segoe UI", 10))
    status.pack(pady=(8, 0))
    toggle_adv(), toggle_adv()   # initialize button label (ends closed)

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
        from chat_sources import detect_platform, normalize_channel
        ch = channel_var.get().strip()
        ch = normalize_channel(ch, detect_platform(ch))
        spoken_code = dict(SPOKEN_LANGS)[spoken_var.get()]
        dev = call_dev_var.get()
        extra_subs = {
            "family_filter": bool(family_var.get()),
            "speak_to_viewers": bool(speakfeed_var.get()),
            "call_on_stream": bool(callstream_var.get()),
            "obs_cc": bool(cc_var.get()),
            "obs_ws_password": ccpw_var.get().strip(),
            "call_translate": bool(call_var.get()),
            "call_device": "" if dev == call_dev_default else dev,
            "call_target": dict(LANGS)[call_lang_var.get()],
            "font_px": int(font_var.get()),
            "show_english": bool(showen_var.get()),
        }
        if hot_var.get().strip():
            extra_subs["hotwords"] = hot_var.get().strip()
        extra_chat = {"ui_lang": dict(UI_LANGS)[ui_var.get()],
                      "my_lang": ("en" if spoken_code == "auto"
                                  else spoken_code),
                      "tts_enabled": bool(tts_var.get()),
                      "family_filter": bool(family_var.get()),
                      "enable_chat": bool(en_chat_var.get()),
                      "enable_subs": bool(en_subs_var.get()),
                      "obs_chat_enabled": bool(obschat_var.get()),
                      "obs_chat_lang": dict(LANGS)[obslang_var.get()]}
        write_configs(ch, lang, mic_idx, plan, url_var.get().strip(),
                      spoken_lang=spoken_code,
                      extra_chat=extra_chat, extra_subs=extra_subs)
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
