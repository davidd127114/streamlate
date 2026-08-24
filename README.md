# Streamlate

**English** · [Português (Brasil)](README.pt-BR.md) · [Español](README.es.md) · [עברית](README.he.md)

Free, local, live translation for streamers.

- **Your voice → subtitles in another language, on your stream.** Any
  direction: speak English and caption into Portuguese, or speak Portuguese
  (Spanish, French, German, Japanese, Korean, Russian, Chinese…) and caption
  into English — rendered inside OBS a couple of seconds behind your voice.
  Same language both ways = plain closed captions.
- **Your chat → English, for you.** Every non-English chat message translated
  on a click-through in-game overlay and on a phone page you can read from
  your couch. Works with **Twitch, YouTube and Kick** chat — just give it
  your channel name, @handle, or kick.com URL. (Viewer count is
  Twitch-only for now.)
- **No accounts, no API keys, no cloud required.** Everything runs on your PC.
  Anonymous read-only Twitch chat connection — it never touches your account.

## How it adapts to YOUR PC (automatically)

On first run it looks at your GPU and picks the biggest translation model
that fits — you never choose anything:

| Your GPU | Engine it picks | Quality |
|---|---|---|
| 20 GB+ (4090/5090…) | Qwen 27B, local | best — natural gamer speech |
| 11–20 GB | Gemma 12B, local | great |
| 6–11 GB | Gemma 4B, local | good |
| less / none | free Google web engine | fine — and zero GPU use |

Speech recognition (Whisper) runs on GPU when you have one, CPU otherwise.
Every tier works — bigger hardware just sounds more natural.

**Rented GPU instead?** Run [Ollama](https://ollama.com) on any cloud GPU box
(RunPod, Vast.ai…), put its URL in the setup wizard's "Remote engine URL"
field, and your PC does almost nothing. ~$0.25/hr buys you the best tier.

## Install (Windows) — one file, one double-click

### ⬇️ [Download StreamlateSetup.exe](https://github.com/davidd127114/streamlate/releases/latest/download/StreamlateSetup.exe)

Run it. That's the whole install: it fetches everything (Python, the Ollama
AI engine, the app), puts the **Streamlate** icon on your desktop, and opens
the setup wizard — your channel, your language, your mic, done.
*(Windows SmartScreen may warn because the file is new — More info → Run
anyway.)*

<details><summary>Prefer installing from source?</summary>

Download this repo as ZIP (green **Code** button), unzip anywhere, and
double-click `install.bat` — same result.
</details>

## Use

- **`Streamlate`** (purple icon): starts everything — chat overlay,
  phone page, subtitle engine. Tray icons show it's alive.
- In OBS, once: `Sources → + → Browser`, URL `http://localhost:8788`,
  Width `1400`, Height `300`. That gives you a small banner source — **drag
  it anywhere on your canvas like any other source**; captions hug its
  bottom edge. (A full-canvas-sized source also works: captions sit
  bottom-center of the screen.)
- Phone: right-click either tray icon → **Show phone QR code** and scan it
  (same Wi-Fi), or open the URL shown in the tray tooltip.
- Want to tell your viewers about Streamlate? `streamlate_link_qr.png` in
  the app folder is a QR of the download page — drag it into OBS as an
  image source whenever you feel like sharing.
- **`Streamlate OFF`** (gray icon): stops everything.

## Playing something heavy?

Every tray menu has **Translation quality / GPU use** — a four-step dial:
**Best** (the auto-picked tier), **Lighter** (~8 GB), **Tiny** (~3 GB), or
**Zero GPU** (free web engine + CPU speech). Switching evicts the old model
from VRAM immediately, downloads the new tier in the background if you've
never used it (translation keeps working meanwhile), and everything else
stays the same. Pick whatever your game leaves room for; switch back after.

## Discord / voice-chat translation

Teammates speaking another language in Discord (or in-game VC)? Right-click
the **green** tray icon → **Voice-chat translation** — no drivers, no
virtual cables, nothing to configure. Streamlate listens to what your PC is
playing, and translated 🎧 bubbles appear in your chat overlay and phone
page whenever someone speaks a foreign language.

One honest caveat: it hears *everything* your PC plays, so music with vocals
can produce stray bubbles (game sound effects are ignored fine). If you want
surgical isolation, the classic streamer trick works: install the free
[VB-Cable](https://vb-audio.com/Cable/), set Discord's output device to
*CABLE Input*, enable "listen to this device" on *CABLE Output* so you still
hear the call — optional, for purists. Which output device to listen to is
picked in **Change settings → More settings**, no config editing.

**Changing your mind later:** every tray icon has **Change settings** — it
reopens the setup wizard (mic, languages, channel) and restarts Streamlate
with the new choices. Your other tweaks are kept.

## Make it yours

Right-click the purple tray icon → **Change background image…** and pick any
picture (anime wallpaper, your logo…) — the overlay and the phone page both
use it, auto-darkened so chat stays readable. Or just drop a file called
`background.png` into the app folder.

**Moving things around:** tray → **Move mode** unlocks the chat overlay so
you can drag it anywhere (purple border = unlocked), click Move mode again
to lock it back into click-through gaming mode — position is remembered.
Or use **Snap to next corner** for quick corner hopping. The OBS captions
move the OBS way: just drag the browser source in your OBS preview.
Everything else in the tray: text size, auto-hide, show/hide originals —
all without touching the game.

## Tuning (optional — sensible defaults for everything)

`subs_config.json`: caption language, font size, caption window seconds,
mic device/channel, `hotwords` (words Whisper should expect — add your
game's terms!), `show_english`, remote `engine_url`.
`config.json`: chat channel, model, overlay corner/opacity.

## Notes

- Phone page works on your home network (carrier internet blocks incoming
  connections from outside).
- Chat translation falls back Google → nothing breaks if Ollama is off.
- Made by a streamer who wanted his Brazilian chat to understand him.
  MIT licensed — do whatever you want with it.
