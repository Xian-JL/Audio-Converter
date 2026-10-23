$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
foreach ($required in @($projectPython,'dist\index.html','tools\ffmpeg.exe','tools\ffprobe.exe','models\mdx.onnx','models\mdx-config.json','models\demucs-vocals.onnx','dist\piano\manifest.json','dist\instruments\manifest.json','server\data\basic-harmony.json','vendor\AccoMontage2\LICENSE')) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing $required. Run .\setup.ps1 first." }
}
& $projectPython -c "from server.game import model_directory; model_directory()"
if ($LASTEXITCODE) { throw 'GAME model is missing or unavailable. Run .\setup-game.ps1 first.' }
Write-Host 'Local Audio: http://127.0.0.1:8765 (Ctrl+C stops the local service)' -ForegroundColor Cyan
& $projectPython -m server.app
