"""Tiny UI localization. Auto-detects the Windows display language;
override with "ui_lang" in config.json ("auto" / "en" / "pt" / "es")."""
import ctypes
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))

STRINGS = {
    "en": {
        "starting": "Streamlate — starting",
        "line_chat": "🟣  Chat overlay + phone page",
        "line_subs": "🟢  Subtitles for OBS",
        "line_obs": "Start OBS and go live — everything else is automatic.",
        "updated": "✓ updated to the latest version",
        "stopped_title": "Streamlate — stopped",
        "stopped_body": "Chat overlay, phone page and subtitles are off.",
        "open_phone": "Open phone page in browser",
        "show_qr": "Show phone QR code",
        "bigger": "Bigger text",
        "smaller": "Smaller text",
        "orig": "Show/hide originals",
        "bg": "Change background image…",
        "bgoff": "Remove background image",
        "movemode": "Move mode (drag the overlay)",
        "corner": "Snap to next corner",
        "autohide": "Auto-hide when chat is quiet",
        "exit": "Exit",
        "drag_hint": "◇ drag me — tray → Move mode again to lock",
        "preview": "Preview captions page",
        "obs_source": "OBS Browser Source",
        "wiz_title": "Streamlate — Setup",
        "wiz_channel": "Your channel  (Twitch name, YouTube @handle, or kick.com URL)",
        "wiz_speak": "You speak…",
        "wiz_caption": "Subtitle your voice into…",
        "wiz_mic": "Microphone",
        "wiz_mic_default": "System default (auto)",
        "wiz_engine": "Translation engine (detected automatically)",
        "wiz_engine_tip": "Tip: install Ollama to unlock AI-quality translation",
        "wiz_url": "Remote engine URL (optional — rented GPU / cloud box)",
        "wiz_save": "Save and finish",
        "wiz_need_channel": "Enter your channel name first",
        "wiz_downloading": "Downloading {model} ({size}) — this can take a while…",
    },
    "pt": {
        "starting": "Streamlate — iniciando",
        "line_chat": "🟣  Overlay do chat + página do celular",
        "line_subs": "🟢  Legendas para o OBS",
        "line_obs": "Abra o OBS e entre ao vivo — o resto é automático.",
        "updated": "✓ atualizado para a versão mais recente",
        "stopped_title": "Streamlate — parado",
        "stopped_body": "Overlay do chat, página do celular e legendas desligados.",
        "open_phone": "Abrir página do celular no navegador",
        "show_qr": "Mostrar QR code do celular",
        "bigger": "Texto maior",
        "smaller": "Texto menor",
        "orig": "Mostrar/ocultar originais",
        "bg": "Trocar imagem de fundo…",
        "bgoff": "Remover imagem de fundo",
        "movemode": "Modo mover (arraste o overlay)",
        "corner": "Pular para o próximo canto",
        "autohide": "Ocultar quando o chat estiver quieto",
        "exit": "Sair",
        "drag_hint": "◇ me arraste — bandeja → Modo mover para travar",
        "preview": "Ver página das legendas",
        "obs_source": "Fonte de Navegador do OBS",
        "wiz_title": "Streamlate — Configuração",
        "wiz_channel": "Seu canal  (nome da Twitch, @handle do YouTube ou URL do kick.com)",
        "wiz_speak": "Você fala…",
        "wiz_caption": "Legendar sua voz em…",
        "wiz_mic": "Microfone",
        "wiz_mic_default": "Padrão do sistema (auto)",
        "wiz_engine": "Motor de tradução (detectado automaticamente)",
        "wiz_engine_tip": "Dica: instale o Ollama para tradução com qualidade de IA",
        "wiz_url": "URL de motor remoto (opcional — GPU alugada / nuvem)",
        "wiz_save": "Salvar e concluir",
        "wiz_need_channel": "Digite o nome do seu canal primeiro",
        "wiz_downloading": "Baixando {model} ({size}) — pode demorar um pouco…",
    },
    "es": {
        "starting": "Streamlate — iniciando",
        "line_chat": "🟣  Overlay del chat + página del celular",
        "line_subs": "🟢  Subtítulos para OBS",
        "line_obs": "Abre OBS y sal en vivo — el resto es automático.",
        "updated": "✓ actualizado a la última versión",
        "stopped_title": "Streamlate — detenido",
        "stopped_body": "Overlay del chat, página del celular y subtítulos apagados.",
        "open_phone": "Abrir página del celular en el navegador",
        "show_qr": "Mostrar código QR del celular",
        "bigger": "Texto más grande",
        "smaller": "Texto más pequeño",
        "orig": "Mostrar/ocultar originales",
        "bg": "Cambiar imagen de fondo…",
        "bgoff": "Quitar imagen de fondo",
        "movemode": "Modo mover (arrastra el overlay)",
        "corner": "Saltar a la siguiente esquina",
        "autohide": "Ocultar cuando el chat esté callado",
        "exit": "Salir",
        "drag_hint": "◇ arrástrame — bandeja → Modo mover para bloquear",
        "preview": "Ver página de subtítulos",
        "obs_source": "Fuente de Navegador de OBS",
        "wiz_title": "Streamlate — Configuración",
        "wiz_channel": "Tu canal  (nombre de Twitch, @handle de YouTube o URL de kick.com)",
        "wiz_speak": "Tú hablas…",
        "wiz_caption": "Subtitular tu voz en…",
        "wiz_mic": "Micrófono",
        "wiz_mic_default": "Predeterminado del sistema (auto)",
        "wiz_engine": "Motor de traducción (detectado automáticamente)",
        "wiz_engine_tip": "Consejo: instala Ollama para traducción con calidad de IA",
        "wiz_url": "URL de motor remoto (opcional — GPU alquilada / nube)",
        "wiz_save": "Guardar y terminar",
        "wiz_need_channel": "Escribe el nombre de tu canal primero",
        "wiz_downloading": "Descargando {model} ({size}) — puede tardar…",
    },
}


def system_lang():
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF
        return {0x16: "pt", 0x0A: "es"}.get(lid, "en")
    except Exception:
        return "en"


def ui_lang():
    try:
        with open(os.path.join(APP_DIR, "config.json"),
                  encoding="utf-8-sig") as f:
            v = json.load(f).get("ui_lang", "auto")
        if v and v != "auto":
            return v if v in STRINGS else "en"
    except (OSError, ValueError):
        pass
    return system_lang()


_LANG = ui_lang()


def tr(key, **kw):
    s = STRINGS.get(_LANG, STRINGS["en"]).get(key) or STRINGS["en"].get(key, key)
    return s.format(**kw) if kw else s
