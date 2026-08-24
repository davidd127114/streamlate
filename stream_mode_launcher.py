"""One-button stream stack launcher (run with pythonw — no console).
Stops any stale copies, starts the chat overlay + subtitles, and shows a
small confirmation splash."""
import os
import subprocess
import sys
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


def main():
    make_share_qr()
    updated = False
    try:
        from updater import maybe_update
        updated = maybe_update()
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
    from i18n import tr
    lines = [tr("starting")]
    if en_chat:
        lines.append(tr("line_chat"))
    if en_subs:
        lines.append(tr("line_subs"))
    lines.append(tr("line_obs"))
    if updated:
        lines.append(tr("updated"))
    splash(lines)


if __name__ == "__main__":
    main()
