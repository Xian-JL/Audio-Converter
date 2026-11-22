$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$instrumentPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $instrumentPython)) { throw 'Run Setup.cmd first.' }
& $instrumentPython -m pip install -r requirements-instrument.txt --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE) { throw 'Instrument inference dependencies failed.' }
& $instrumentPython -B scripts/transcription_resources.py
if ($LASTEXITCODE) { throw 'Instrument resources failed. Existing downloads can be resumed.' }
& $instrumentPython -B -c "import torchaudio; from server.instrument_runtime import verify; verify('transkun'); verify('basic-pitch')"
if ($LASTEXITCODE) { throw 'Instrument resource verification failed.' }
Write-Host 'Piano and guzheng resources are ready.'
