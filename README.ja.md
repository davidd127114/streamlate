# Streamlate

**日本語** · [English](README.md) · [Português](README.pt-BR.md) · [Español](README.es.md) · [עברית](README.he.md) · [Polski](README.pl.md) · [中文](README.zh.md) · [한국어](README.ko.md)

配信者のための無料・ローカル・リアルタイム翻訳。

- **あなたの声 → 別言語の字幕として配信に表示。** どの方向でもOK:
  日本語で話して英語字幕、英語で話して日本語字幕。OBS内に約2秒遅れで
  表示されます。同じ言語同士なら普通のクローズドキャプションに。
- **視聴者のチャット → あなたの言語に。** 外国語のコメントをゲーム内の
  透過オーバーレイとスマホページに翻訳表示。**Twitch・YouTube・Kick**
  のチャットに対応。
- **アカウント不要、APIキー不要、クラウド不要。** すべてあなたのPCで
  動作します。

## あなたのPCに自動で最適化

| GPU | 選ばれるエンジン | 品質 |
|---|---|---|
| 20 GB以上 (4090/5090…) | Qwen 27B ローカル | 最高 |
| 11–20 GB | Gemma 12B ローカル | とても良い |
| 6–11 GB | Gemma 4B ローカル | 良い |
| それ以下 / なし | 無料Googleエンジン | 十分 — GPU不使用 |

日本語の音声認識には自動的に強力なモデル（medium）が使われます。

## インストール（Windows）— 1ファイル、ダブルクリックだけ

### ⬇️ [StreamlateSetup.exe をダウンロード](https://github.com/davidd127114/streamlate/releases/latest/download/StreamlateSetup.exe)

実行するだけ。Python・Ollama AIエンジン・アプリを自動で導入し、
デスクトップに **Streamlate** アイコンを作り、セットアップを開きます —
チャンネル、言語、マイクを選んで完了。

## 使い方

- **Streamlate**（紫アイコン）: コントロールパネルが開き、すべて起動。
  OBSに一度だけ: `ソース → + → ブラウザ`、URL `http://localhost:8788`、
  幅 `1400`、高さ `300` — 好きな場所にドラッグ。
- スマホ: パネル → **QRコード** をスキャン（同じWi-Fi）。
- **Streamlate OFF**(灰色): すべて停止。

トレイメニュー: 背景画像（アニメ壁紙など）、移動モード、翻訳品質/GPU、
Discord通話の翻訳など。MITライセンス。
