$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$texturePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $texturePython)) { throw 'Run Setup.cmd first.' }
& $texturePython -m pip install -r requirements-texture.txt --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE) { throw 'Accompaniment dependency setup failed.' }
& $texturePython -B -c "from server.emotion_runtime import available; assert all(available(e) for e in ('emo','midi-emotion'))"
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $PSScriptRoot 'scripts\download_emotion_models.ps1')
    & $texturePython -B scripts\prepare_emotion_models.py
}
& $texturePython -B -c "from server.emotion_runtime import verify; [verify(e) for e in ('emo','midi-emotion')]"
if ($LASTEXITCODE) { throw 'Accompaniment resource setup failed.' }
Write-Host 'Accompaniment is ready. Restart Start.cmd.' -ForegroundColor Cyan
