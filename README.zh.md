# Streamlate

**中文** · [English](README.md) · [Português](README.pt-BR.md) · [Español](README.es.md) · [עברית](README.he.md) · [Polski](README.pl.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

为主播打造的免费、本地、实时翻译。

- **你的声音 → 直播上的外语字幕。** 任意方向：说中文出英文字幕，或说英文
  出中文字幕 — 在 OBS 内渲染，约慢 2 秒。两边同一语言 = 普通字幕
  （无障碍）。
- **观众的聊天 → 你的语言。** 每条外语消息都会翻译到游戏内透明悬浮窗和
  手机页面上。支持 **Twitch、YouTube、Kick** 聊天。
- **无需账号、无需 API 密钥、无需云端。** 一切都在你的电脑上运行。

## 自动适配你的电脑

| 显卡 | 选用引擎 | 质量 |
|---|---|---|
| 20 GB+ (4090/5090…) | Qwen 27B 本地 | 最佳 |
| 11–20 GB | Gemma 12B 本地 | 很好 |
| 6–11 GB | Gemma 4B 本地 | 良好 |
| 更低 / 无显卡 | 免费 Google 引擎 | 够用 — 零 GPU |

中文语音识别会自动使用更强的模型（medium）。

## 安装（Windows）— 一个文件，双击即可

### ⬇️ [下载 StreamlateSetup.exe](https://github.com/davidd127114/streamlate/releases/latest/download/StreamlateSetup.exe)

运行即可。它会自动安装一切（Python、Ollama AI 引擎、应用本体），在桌面
创建 **Streamlate** 图标并打开设置向导 — 选好频道、语言、麦克风就完成了。

## 使用

- **Streamlate**（紫色图标）：打开控制面板并启动全部功能。OBS 中只需
  添加一次：`来源 → + → 浏览器`，地址 `http://localhost:8788`，宽 `1400`，
  高 `300` — 拖到任意位置。
- 手机：面板 → **二维码** 扫码（同一 Wi-Fi）。
- **Streamlate OFF**（灰色）：全部停止。

托盘菜单：背景图片（动漫壁纸等）、移动模式、翻译质量/GPU 占用、
Discord 语音翻译等。MIT 许可证。
