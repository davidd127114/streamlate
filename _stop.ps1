param([string]$Pattern = "twitch_chat_translator|stream_subtitles|viewer_mode")
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe'" |
  Where-Object { $_.CommandLine -match $Pattern } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
