"""Viewers QR — a public, scan-anytime link to the live translated-chat
page. A free Cloudflare quick tunnel exposes the local page; the QR image
regenerates whenever the tunnel URL changes and feeds an OBS image source
("Streamlate Viewers QR") the streamer can drag anywhere. Read-only by
design: the inject endpoint requires a local secret key."""
import os
import re
import subprocess
import threading
import time
import urllib.request

CREATE_NO_WINDOW = 0x08000000
CF_URL = ("https://github.com/cloudflare/cloudflared/releases/latest/"
          "download/cloudflared-windows-amd64.exe")


class ViewerTunnel:
    def __init__(self, app_dir, port, log=print):
        self.app_dir = app_dir
        self.port = port
        self.log = log
        self.url = None
        self.proc = None
        self.stop_ev = threading.Event()

    def _exe(self):
        path = os.path.join(self.app_dir, "cloudflared.exe")
        if not os.path.exists(path):
            self.log("viewers qr: downloading cloudflared (~40 MB, once)…")
            urllib.request.urlretrieve(CF_URL, path)
            self.log("viewers qr: cloudflared ready")
        return path

    def _make_qr(self):
        import qrcode
        from PIL import Image, ImageDraw, ImageFont
        qr = qrcode.make(self.url).convert("RGB")
        qr = qr.resize((360, 360))
        card = Image.new("RGB", (400, 470), "#ffffff")
        card.paste(qr, (20, 20))
        d = ImageDraw.Draw(card)
        try:
            f1 = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 30)
            f2 = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 19)
        except OSError:
            f1 = f2 = None
        d.text((200, 398), "READ MY CHAT", font=f1, fill="#7b2fbf",
               anchor="mm")
        d.text((200, 434), "translated live — scan me", font=f2,
               fill="#555555", anchor="mm")
        out = os.path.join(self.app_dir, "viewers_qr.png")
        card.save(out)
        return out

    def _obs_source(self, png):
        try:
            import contextlib
            import io
            from obs_link import effective_password
            import obsws_python as obs
            with contextlib.redirect_stderr(io.StringIO()):
                cl = obs.ReqClient(host="localhost", port=4455,
                                   password=effective_password({}),
                                   timeout=4)
            scene = cl.get_current_program_scene().current_program_scene_name
            names = [i["sourceName"]
                     for i in cl.get_scene_item_list(scene).scene_items]
            if "Streamlate Viewers QR" not in names:
                cl.create_input(scene, "Streamlate Viewers QR",
                                "image_source", {"file": png}, True)
                self.log("viewers qr: OBS source created — drag it anywhere")
            else:   # refresh the image after a URL change
                cl.set_input_settings("Streamlate Viewers QR",
                                      {"file": png}, True)
        except Exception:
            pass   # OBS closed — the PNG still exists for manual use

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            exe = self._exe()
        except Exception as e:
            self.log(f"viewers qr: cloudflared download failed ({e})")
            return
        while not self.stop_ev.is_set():
            try:
                self.proc = subprocess.Popen(
                    [exe, "tunnel", "--url",
                     f"http://localhost:{self.port}", "--no-autoupdate"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, creationflags=CREATE_NO_WINDOW)
                for line in self.proc.stderr:
                    if self.stop_ev.is_set():
                        return
                    m = re.search(
                        r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                    if m and m.group(0) != self.url:
                        self.url = m.group(0)
                        self.log(f"viewers qr: public link live — {self.url}")
                        try:
                            png = self._make_qr()
                            self._obs_source(png)
                        except Exception as e:
                            self.log(f"viewers qr: qr build failed ({e})")
            except Exception as e:
                self.log(f"viewers qr: tunnel error ({e})")
            if not self.stop_ev.is_set():
                time.sleep(10)   # tunnel dropped — reconnect

    def stop(self):
        self.stop_ev.set()
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass
