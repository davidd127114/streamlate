# Streamlate

**Español** · [English](README.md) · [Português (Brasil)](README.pt-BR.md) · [עברית](README.he.md)

Traducción en vivo, gratuita y local, para streamers.

- **Tu voz → subtítulos en otro idioma, en tu stream.** En cualquier
  dirección: habla español y subtitula en inglés, o habla inglés y subtitula
  en español — renderizado dentro de OBS un par de segundos después de tu
  voz. Mismo idioma en ambos lados = subtítulos normales (accesibilidad).
- **Su chat → tu idioma, para ti.** Cada mensaje en otro idioma se traduce
  en un overlay transparente dentro del juego y en una página para tu
  celular. Funciona con chat de **Twitch, YouTube y Kick** — solo pon el
  nombre del canal, @handle o URL de kick.com.
- **Sin cuentas, sin claves de API, sin nube obligatoria.** Todo corre en tu
  PC. La lectura del chat es anónima — nunca toca tu cuenta.

## Cómo se adapta a TU PC (automáticamente)

En el primer arranque mira tu GPU y elige el mejor modelo de traducción que
quepa — tú no eliges nada:

| Tu GPU | Motor elegido | Calidad |
|---|---|---|
| 20 GB+ (4090/5090…) | Qwen 27B, local | la mejor — habla gamer natural |
| 11–20 GB | Gemma 12B, local | excelente |
| 6–11 GB | Gemma 4B, local | buena |
| menos / ninguna | motor web gratuito de Google | bien — y cero uso de GPU |

El reconocimiento de voz (Whisper) usa la GPU si existe, si no la CPU.
Todos los niveles funcionan — mejor hardware solo suena más natural.

**¿GPU alquilada?** Corre [Ollama](https://ollama.com) en cualquier máquina
en la nube (RunPod, Vast.ai…), pega su URL en "Remote engine URL" del
asistente, y tu PC casi no trabaja. ~US$ 0.25/hora compra el nivel máximo.

## Instalación (Windows) — un archivo lo hace todo

1. Descarga esta carpeta (botón verde **Code → Download ZIP**, descomprime
   donde quieras).
2. Doble clic en **`install.bat`** una sola vez. Instala solo el Python y el
   motor de IA Ollama si no los tienes (silencioso, sin pantallas de
   instalador), configura la app, crea los íconos del escritorio y abre el
   asistente — tu canal, tu idioma, tu micrófono, listo.

## Uso

- **`Streamlate`** (ícono morado): arranca todo — overlay del chat, página
  del celular, motor de subtítulos. Los íconos de la bandeja muestran que
  está vivo.
- En OBS, una sola vez: `Fuentes → + → Navegador`, URL
  `http://localhost:8788`, Ancho `1400`, Alto `300`. Eso crea una franja
  pequeña — **arrástrala a donde quieras como cualquier fuente**; los
  subtítulos se pegan a su borde inferior.
- Celular: abre la URL del tooltip del ícono de bandeja (mismo Wi-Fi), o
  escanea `phone_qr.png`.
- **`Streamlate OFF`** (ícono gris): apaga todo.

## Hazlo tuyo

Clic derecho en el ícono morado → **Change background image…** y elige
cualquier imagen (wallpaper de anime, tu logo…) — el overlay y la página del
celular la usan, oscurecida automáticamente para que el chat siga legible.

**Mover cosas:** bandeja → **Move mode** desbloquea el overlay para
arrastrarlo a donde sea (borde morado = desbloqueado); clic de nuevo para
bloquearlo en modo juego (los clics lo atraviesan) — la posición se guarda.
Los subtítulos de OBS se mueven a la manera OBS: arrastra la fuente de
navegador en el preview.

## Ajustes (opcional — todo trae buenos valores por defecto)

`subs_config.json`: idioma hablado y de subtítulos, tamaño de fuente,
ventana de captura, micrófono/canal, `hotwords` (palabras que Whisper debe
esperar — ¡agrega los términos de tu juego!), `engine_url` remota.
`config.json`: canal del chat, modelo, esquina/opacidad del overlay.

## Notas

- La página del celular funciona en tu red Wi-Fi de casa.
- La traducción del chat cae automáticamente a Google → nada se rompe si
  Ollama está apagado.
- Hecho por un streamer que quería que su chat brasileño lo entendiera.
  Licencia MIT — haz lo que quieras.
