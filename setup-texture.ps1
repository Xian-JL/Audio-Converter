$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$texturePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $texturePython)) { throw 'Run Setup.cmd first.' }
& $texturePython -m pip install -r requirements-texture.txt --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE) { throw 'Accompaniment dependency setup failed.' }
& $texturePython scripts\texture_resources.py
if ($LASTEXITCODE) { throw 'Accompaniment resource setup failed.' }
Write-Host 'Accompaniment is ready. Restart Start.cmd.' -ForegroundColor Cyan
