# Streamlate

**Português (Brasil)** · [English](README.md) · [Español](README.es.md)

Tradução ao vivo, gratuita e local, para streamers.

- **Sua voz → legendas em outro idioma, direto na stream.** Em qualquer
  direção: fale português e legende em inglês para alcançar gringos, ou fale
  inglês e legende em português — as legendas aparecem dentro do OBS uns
  2 segundos depois da sua fala. Mesmo idioma nos dois lados = closed
  caption normal (acessibilidade).
- **O chat deles → seu idioma, para você.** Toda mensagem em outra língua é
  traduzida num overlay transparente dentro do jogo e numa página que você
  abre no celular. Funciona com chat da **Twitch, YouTube e Kick** — é só
  informar o nome do canal, @handle ou URL do kick.com.
- **Sem conta, sem chave de API, sem nuvem obrigatória.** Tudo roda no seu
  PC. A leitura do chat é anônima — nunca toca na sua conta.

## Como ele se adapta ao SEU PC (automaticamente)

Na primeira execução ele olha sua GPU e escolhe o maior modelo de tradução
que cabe — você não escolhe nada:

| Sua GPU | Motor escolhido | Qualidade |
|---|---|---|
| 20 GB+ (4090/5090…) | Qwen 27B, local | a melhor — fala de gamer natural |
| 11–20 GB | Gemma 12B, local | ótima |
| 6–11 GB | Gemma 4B, local | boa |
| menos / nenhuma | motor web gratuito do Google | ok — e zero uso de GPU |

O reconhecimento de voz (Whisper) usa a GPU quando existe, senão a CPU.
Todo nível funciona — hardware maior só soa mais natural.

**Prefere GPU alugada?** Rode o [Ollama](https://ollama.com) em qualquer
máquina na nuvem (RunPod, Vast.ai…), cole a URL no campo "Remote engine URL"
do assistente, e seu PC quase não trabalha. ~US$ 0,25/hora compra o nível
máximo.

## Instalação (Windows) — um arquivo faz tudo

1. Baixe esta pasta (botão verde **Code → Download ZIP**, descompacte onde
   quiser).
2. Dê dois cliques em **`install.bat`** uma única vez. Ele instala sozinho o
   Python e o motor de IA Ollama se você não tiver (silencioso, sem telas de
   instalador), configura o app, cria os ícones na área de trabalho e abre o
   assistente — seu canal, seu idioma, seu microfone, pronto.

## Uso

- **`Streamlate`** (ícone roxo): liga tudo — overlay do chat, página do
  celular, motor de legendas. Os ícones na bandeja mostram que está vivo.
- No OBS, uma vez só: `Fontes → + → Navegador`, URL `http://localhost:8788`,
  Largura `1400`, Altura `300`. Isso cria uma faixa pequena — **arraste ela
  para onde quiser na tela, como qualquer fonte**; as legendas ficam na
  borda de baixo dela.
- Celular: abra a URL que aparece na dica do ícone da bandeja (mesmo Wi-Fi),
  ou escaneie o `phone_qr.png`.
- **`Streamlate OFF`** (ícone cinza): desliga tudo.

## Deixe com a sua cara

Clique com o botão direito no ícone roxo da bandeja → **Change background
image…** e escolha qualquer imagem (wallpaper de anime, sua logo…) — o
overlay e a página do celular usam ela, escurecida automaticamente para o
chat continuar legível.

**Movendo as coisas:** bandeja → **Move mode** destrava o overlay para você
arrastar para qualquer lugar (borda roxa = destravado); clique de novo para
travar no modo jogo (os cliques atravessam) — a posição fica salva. As
legendas do OBS se movem do jeito OBS: arraste a fonte de navegador no
preview.

## Ajustes finos (opcional — tudo já vem com bons padrões)

`subs_config.json`: idioma falado e das legendas, tamanho da fonte, janela
de captura, microfone/canal, `hotwords` (palavras que o Whisper deve
esperar — adicione os termos do seu jogo!), `engine_url` remota.
`config.json`: canal do chat, modelo, canto/opacidade do overlay.

## Notas

- A página do celular funciona na sua rede Wi-Fi de casa.
- A tradução do chat cai automaticamente para o Google → nada quebra se o
  Ollama estiver desligado.
- Feito por um streamer que queria que o chat brasileiro entendesse ele.
  Licença MIT — faça o que quiser.
