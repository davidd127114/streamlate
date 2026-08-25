# Windows built-in OCR bridge for Streamlate VIEWER MODE.
# Uses Windows.Media.Ocr (zero installs). Which languages it can read
# depends on the language packs installed in Windows Settings.
#   -List          print available OCR language tags
#   -Watch         loop: read an image path per stdin line, print the
#                  recognized lines, then "<<<END>>>" (exit on EOF/QUIT)
#   -Path <file>   one-shot OCR of a single image
param([switch]$Watch, [switch]$List, [string]$Path = "", [string]$Lang = "")
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
  Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                 $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
  $t = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
  $t.Wait()
  $t.Result
}

if ($List) {
  [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages |
    ForEach-Object { Write-Output $_.LanguageTag }
  exit 0
}

$engine = $null
if ($Lang) {
  foreach ($l in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
    if ($l.LanguageTag -like "$Lang*") {
      $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($l)
      break
    }
  }
}
if (-not $engine) {
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if (-not $engine) {
  $avail = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
  if ($avail.Count -gt 0) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($avail[0])
  }
}
if (-not $engine) { Write-Output "<<<NOENGINE>>>"; exit 1 }

function OcrFile($p) {
  try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $result.Lines | ForEach-Object { Write-Output $_.Text }
    $stream.Dispose()
    $bmp.Dispose()
  } catch { }
}

if ($Watch) {
  while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line -or $line -eq "QUIT") { break }
    OcrFile $line.Trim()
    Write-Output "<<<END>>>"
    try { [Console]::Out.Flush() } catch { }
  }
} elseif ($Path) {
  OcrFile $Path
  Write-Output "<<<END>>>"
}
