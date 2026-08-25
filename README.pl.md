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

## Tryb widza — oglądaj zagranicznych streamerów

Streamlate działa też w drugą stronę. Otwórz **Streamlate Control** →
**👁 Tryb widza**: zamiast tłumaczyć TWÓJ stream dla widzów, tłumaczy
stream, który TY oglądasz.

- **Napisy głosowe na żywo** — włącz dowolny stream; język streamera jest
  wykrywany automatycznie i tłumaczony na Twój język w przesuwalnej pigułce
  z napisami (prawy przycisk: język, rozmiar, oryginał, źródło dźwięku).
- **Tekst z ekranu (beta)** — prawy przycisk → *Tłumacz tekst z ekranu*,
  przeciągnij ramkę nad ich czatem lub tekstem, a obok pojawi się panel z
  tłumaczeniem na żywo. Dla japońskiego/koreańskiego/chińskiego dodaj ten
  język w Ustawieniach Windows → Język.

Szczera granica: dźwięk streama jest już zmiksowany — nie da się wyizolować
samego mikrofonu streamera, a muzyka z wokalem może dawać zbędne linie.
Jeśli to TWOJA muzyka przeszkadza, odtwarzaj ją na innym urządzeniu i
wybierz urządzenie streama w *Źródło dźwięku*. **🎥 Powrót do trybu
streamera** w tym samym panelu przywraca wszystko.

### Link głosowy — Twoja mowa w języku każdego znajomego

Zasobnik (fioletowy) → **🎤 Link głosowy**: kopiuje publiczną stronę, na
której każdy — bez instalowania czegokolwiek — czyta to, co mówisz,
tłumaczone na żywo na wybrany przez SIEBIE język (30 opcji). Zasilana
transkrypcją TWOJEGO mikrofonu: bez dźwięku gry, muzyki i innych głosów.
Korzysta z tunelu QR widzów, gdy jest włączony.
