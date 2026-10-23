$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' scripts\game_resources.py
if ($LASTEXITCODE) { throw 'GAME resource setup failed.' }
