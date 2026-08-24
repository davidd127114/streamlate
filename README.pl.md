# Streamlate

**Polski** · [English](README.md) · [Português](README.pt-BR.md) · [Español](README.es.md) · [עברית](README.he.md) · [日本語](README.ja.md) · [中文](README.zh.md) · [한국어](README.ko.md)

Darmowe, lokalne tłumaczenie na żywo dla streamerów.

- **Twój głos → napisy w innym języku, prosto na streamie.** W dowolną
  stronę: mów po polsku, a widzowie czytają po angielsku — albo odwrotnie.
  Napisy pojawiają się w OBS około 2 sekundy po twoich słowach. Ten sam
  język po obu stronach = zwykłe napisy (dostępność).
- **Ich czat → twój język, dla ciebie.** Każda obca wiadomość jest
  tłumaczona na przezroczystej nakładce w grze i na stronie, którą
  otwierasz na telefonie. Działa z czatem **Twitch, YouTube i Kick**.
- **Bez kont, bez kluczy API, bez chmury.** Wszystko działa na twoim PC.

## Jak dopasowuje się do TWOJEGO komputera (automatycznie)

| Twoja karta graficzna | Wybrany silnik | Jakość |
|---|---|---|
| 20 GB+ (4090/5090…) | Qwen 27B, lokalnie | najlepsza |
| 11–20 GB | Gemma 12B, lokalnie | świetna |
| 6–11 GB | Gemma 4B, lokalnie | dobra |
| mniej / brak | darmowy silnik Google | w porządku — zero GPU |

Dla polskiej mowy program automatycznie wybiera mocniejszy model
rozpoznawania (medium).

## Instalacja (Windows) — jeden plik, jedno kliknięcie

### ⬇️ [Pobierz StreamlateSetup.exe](https://github.com/davidd127114/streamlate/releases/latest/download/StreamlateSetup.exe)

Uruchom go. To cała instalacja: pobiera wszystko (Python, silnik AI Ollama,
aplikację), tworzy ikonę **Streamlate** na pulpicie i otwiera kreatora —
twój kanał, język, mikrofon, gotowe.

## Użycie

- Ikona **Streamlate** (fioletowa): otwiera panel sterowania i uruchamia
  wszystko. W OBS raz dodaj: `Źródła → + → Przeglądarka`, adres
  `http://localhost:8788`, szer. `1400`, wys. `300` — i przeciągnij gdzie
  chcesz.
- Telefon: panel → **Kod QR** i zeskanuj (to samo Wi-Fi).
- **Streamlate OFF** (szara): wyłącza wszystko.

Menu zasobnika: tło (np. tapeta anime), tryb przesuwania, jakość
tłumaczenia / użycie GPU, tłumaczenie rozmów z Discorda i więcej.
Licencja MIT.
