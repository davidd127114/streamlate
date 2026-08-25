"""One-button stream stack launcher (run with pythonw — no console).
Stops any stale copies, starts the chat overlay + subtitles, and shows a
small confirmation splash."""
import os
import subprocess
import sys
import threading
import time
import tkinter as tk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CREATE_NO_WINDOW = 0x08000000


def splash(lines, accent="#a970ff", ms=4200):
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    bg = "#141417"
    root.configure(bg=bg)
    frame = tk.Frame(root, bg=bg, highlightbackground=accent,
                     highlightthickness=2)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text=lines[0], bg=bg, fg="#ffffff",
             font=("Segoe UI", 14, "bold"), pady=6, padx=24).pack()
    for line in lines[1:]:
        tk.Label(frame, text=line, bg=bg, fg="#c9c9d1",
                 font=("Segoe UI", 11), padx=24).pack(anchor="w")
    tk.Label(frame, text="", bg=bg).pack(pady=3)
    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - w) // 2}+{sh - h - 120}")

    def fade(step=0):
        if step < 8:
            root.after(60, fade, step + 1)
        elif step < 16:
            try:
                root.attributes("-alpha", 1.0 - (step - 8) / 8)
            except tk.TclError:
                pass
            root.after(45, fade, step + 1)
        else:
            root.destroy()

    root.after(ms, fade)
    root.mainloop()


def make_share_qr():
    """QR of the Streamlate download page — drag it into OBS to show viewers
    where to get the tool."""
    path = os.path.join(APP_DIR, "streamlate_link_qr.png")
    if os.path.exists(path):
        return
    try:
        import qrcode
        qrcode.make("https://github.com/davidd127114/streamlate").save(path)
    except Exception:
        pass


def control_panel(en_chat, en_subs, updated, repaired=None):
    """The window that opens when you click Streamlate: live status of both
    halves + the buttons people actually need. Closing it changes nothing —
    Streamlate keeps running in the tray."""
    import socket
    import subprocess
    import webbrowser
    from i18n import tr

    # single-instance: if a control panel is already open, focus it and exit
    try:
        import ctypes
        u = ctypes.windll.user32
        existing = u.FindWindowW(None, "Streamlate Control")
        if existing:
            u.ShowWindow(existing, 9)          # restore if minimized
            u.SetForegroundWindow(existing)
            return
    except Exception:
        pass

    BG, FG, ACC, DIM = "#141417", "#e8e8ee", "#a970ff", "#8a8a92"
    root = tk.Tk()
    root.title("Streamlate Control")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.after(2500, lambda: root.attributes("-topmost", False))
    try:
        root.iconbitmap(os.path.join(APP_DIR, "stream_on.ico"))
    except tk.TclError:
        pass

    tk.Label(root, text="Streamlate", bg=BG, fg=ACC,
             font=("Segoe UI", 17, "bold")).pack(pady=(14, 2))
    if updated:
        tk.Label(root, text=tr("updated"), bg=BG, fg="#9adf9e",
                 font=("Segoe UI", 9)).pack()
    if repaired:
        tk.Label(root, text=tr("repaired", names=", ".join(repaired)),
                 bg=BG, fg="#9adf9e", font=("Segoe UI", 9)).pack()

    rows = tk.Frame(root, bg=BG)
    rows.pack(pady=8)
    status_lbls = {}
    for key, name, port, enabled in (("chat", tr("p_chat"), 8765, en_chat),
                                     ("subs", tr("p_subs"), 8788, en_subs)):
        f = tk.Frame(rows, bg=BG)
        f.pack(fill="x", padx=26, pady=3)
        tk.Label(f, text=name, bg=BG, fg=FG, width=16, anchor="w",
                 font=("Segoe UI", 11)).pack(side="left")
        lbl = tk.Label(f, text="…", bg=BG, fg=DIM, font=("Segoe UI", 11))
        lbl.pack(side="left")
        status_lbls[key] = (lbl, port, enabled)

    def alive(port):
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            return False

    boot_t = time.time()
    diag_state = {"ran": False, "fixes": set()}
    diag_lbl = tk.Label(root, text="", bg=BG, fg="#ff9d9d",
                        font=("Segoe UI", 9), wraplength=440, justify="left")
    repair_btn_holder = {}

    def run_doctor():
        try:
            import doctor
            msgs, fixes = doctor.diagnose(APP_DIR)
            diag_state["fixes"] = fixes
            def show():
                diag_lbl.config(text="🔍 " + "\n".join(msgs[:3]))
                diag_lbl.pack(pady=(4, 0))
                if repair_btn_holder.get("show"):
                    repair_btn_holder["show"]()
            root.after(0, show)
        except Exception:
            pass

    def refresh():
        stuck = False
        for lbl, port, enabled in status_lbls.values():
            if not enabled:
                lbl.config(text="⚪ " + tr("p_off"), fg=DIM)
            elif alive(port):
                lbl.config(text="🟢 " + tr("p_on"), fg="#9adf9e")
            else:
                lbl.config(text="🕓 " + tr("p_starting"), fg="#e6c07b")
                stuck = True
        # a service that hasn't come up in 30s is dead — auto-diagnose it
        if stuck and not diag_state["ran"] and time.time() - boot_t > 30:
            diag_state["ran"] = True
            threading.Thread(target=run_doctor, daemon=True).start()
        root.after(2000, refresh)

    btns = tk.Frame(root, bg=BG)
    btns.pack(pady=6)

    def mkbtn(col, text, cmd, color="#26262c"):
        tk.Button(btns, text=text, command=cmd, bg=color, fg=FG, bd=0,
                  font=("Segoe UI", 10), padx=14, pady=7,
                  activebackground="#3a3a44",
                  activeforeground=FG).grid(row=0, column=col, padx=4)

    mkbtn(0, tr("p_phone"), lambda: webbrowser.open("http://localhost:8765"))

    def show_qr():
        try:
            os.startfile(os.path.join(APP_DIR, "phone_qr.png"))
        except OSError:
            pass
    mkbtn(1, tr("p_qr"), show_qr)

    def open_settings():
        root.destroy()
        subprocess.run([sys.executable,
                        os.path.join(APP_DIR, "setup_wizard.py")], cwd=APP_DIR)
        subprocess.Popen([sys.executable,
                          os.path.join(APP_DIR, "stream_mode_launcher.py")],
                         cwd=APP_DIR)
    mkbtn(2, tr("p_settings"), open_settings)

    def stop_all():
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", os.path.join(APP_DIR, "_stop.ps1")],
                creationflags=CREATE_NO_WINDOW, timeout=30)
        except Exception:
            pass
        root.destroy()
    mkbtn(3, tr("p_stop"), stop_all, color="#5a2a2a")

    def run_diagnose():
        def work():
            try:
                import doctor
                path = doctor.write_report(APP_DIR)
                os.startfile(path)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()
    mkbtn(4, tr("p_diag"), run_diagnose)

    copyerr_btn = {}

    def copy_errors():
        try:
            import doctor
            snippet = doctor.recent_errors(APP_DIR)
            root.clipboard_clear()
            root.clipboard_append(snippet)
            b = copyerr_btn["b"]
            b.config(text="✓")
            root.after(2000, lambda: b.config(text=tr("p_copyerr")))
        except Exception:
            pass
    copyerr_btn["b"] = tk.Button(btns, text=tr("p_copyerr"),
                                 command=copy_errors, bg="#26262c", fg=FG,
                                 bd=0, font=("Segoe UI", 10), padx=14,
                                 pady=7, activebackground="#3a3a44",
                                 activeforeground=FG)
    copyerr_btn["b"].grid(row=1, column=0, columnspan=5, padx=4,
                          pady=(6, 0))

    def do_repair():
        repair_btn.config(state="disabled", text="…")

        def work():
            try:
                import doctor
                doctor.repair_deps(doctor.missing_deps())
            except Exception:
                pass
            subprocess.Popen(
                [sys.executable,
                 os.path.join(APP_DIR, "stream_mode_launcher.py")],
                cwd=APP_DIR)
            root.after(0, root.destroy)
        threading.Thread(target=work, daemon=True).start()

    repair_btn = tk.Button(root, text="🔧 " + tr("p_repair"),
                           command=do_repair, bg="#3a5f3f", fg=FG, bd=0,
                           font=("Segoe UI", 10, "bold"), padx=16, pady=7)
    repair_btn_holder["btn"] = repair_btn

    def show_repair():
        repair_btn.pack(pady=(4, 2))
    repair_btn_holder["show"] = show_repair

    tk.Label(root, text=tr("p_hint"), bg=BG, fg=DIM,
             font=("Segoe UI", 8), wraplength=430).pack(pady=(6, 12))
    refresh()
    root.mainloop()


def main():
    make_share_qr()
    updated = False
    try:
        from updater import maybe_update
        updated = maybe_update()
    except Exception:
        pass
    repaired = []
    try:   # self-repair broken packages BEFORE anything can crash on them
        import doctor
        miss = doctor.missing_deps()
        if miss and doctor.repair_deps(miss):
            repaired = miss
    except Exception:
        pass
    if not os.path.exists(os.path.join(APP_DIR, "config.json")):
        subprocess.run([sys.executable,
                        os.path.join(APP_DIR, "setup_wizard.py")], cwd=APP_DIR)
        if not os.path.exists(os.path.join(APP_DIR, "config.json")):
            return  # setup cancelled
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", os.path.join(APP_DIR, "_stop.ps1")],
            creationflags=CREATE_NO_WINDOW, timeout=30)
    except Exception:
        pass
    import json
    try:
        with open(os.path.join(APP_DIR, "config.json"),
                  encoding="utf-8-sig") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    en_chat = c.get("enable_chat", True)
    en_subs = c.get("enable_subs", True)
    pyw = sys.executable
    if en_chat:
        subprocess.Popen(
            [pyw, os.path.join(APP_DIR, "twitch_chat_translator.py"),
             "--overlay"],
            cwd=APP_DIR, creationflags=CREATE_NO_WINDOW)
    if en_subs:
        subprocess.Popen(
            [pyw, os.path.join(APP_DIR, "stream_subtitles.py")],
            cwd=APP_DIR, creationflags=CREATE_NO_WINDOW)
    control_panel(en_chat, en_subs, updated, repaired)


if __name__ == "__main__":
    main()
