$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Install Python 3.11 or newer, then rerun setup.ps1.' }
    & $pythonCommand.Source -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'"
    if ($LASTEXITCODE) { throw 'Python version check failed.' }
    & $pythonCommand.Source -m venv --system-site-packages .venv
    if ($LASTEXITCODE) { throw 'Python environment creation failed.' }
}
# Compatible existing packages remain untouched; pip installs only missing/incompatible requirements in .venv.
& $projectPython -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Python dependency setup failed.' }
& $projectPython scripts\resources.py
if ($LASTEXITCODE) { throw 'Resource setup failed.' }
& $projectPython scripts\game_resources.py
if ($LASTEXITCODE) { throw 'GAME resource setup failed.' }
& $projectPython scripts\instrument_resources.py
if ($LASTEXITCODE) { throw 'Instrument resource setup failed.' }
& $projectPython -m pip install -r requirements-texture.txt --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE) { throw 'Accompaniment dependencies failed.' }
& $projectPython scripts\texture_resources.py
if ($LASTEXITCODE) { throw 'Accompaniment resource setup failed.' }
& $projectPython scripts\generate_test_fixtures.py
if ($LASTEXITCODE) { throw 'Test fixture preparation failed.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath 'dist\index.html') -and (Test-Path -LiteralPath 'dist\app-version.json') -and ((Get-Content -LiteralPath 'dist\app-version.json' -Raw | ConvertFrom-Json).version -eq (Get-Content -LiteralPath 'package.json' -Raw | ConvertFrom-Json).version)) {
    Write-Host 'Reuse prebuilt frontend. Node.js is not required for local playback.'
    Write-Host 'Ready. Run .\start.ps1, then open http://127.0.0.1:8765' -ForegroundColor Green
    exit 0
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22.12+ (or use a prebuilt bundle), then rerun setup.ps1.' }
if (-not (Test-Path -LiteralPath 'node_modules\vite\package.json') -or -not (Test-Path -LiteralPath 'node_modules\opensheetmusicdisplay\package.json') -or -not (Test-Path -LiteralPath 'node_modules\tone\package.json')) {
    npm.cmd ci
    if ($LASTEXITCODE) { throw 'Frontend dependencies failed.' }
}
npm.cmd run build
if ($LASTEXITCODE) { throw 'Frontend build failed.' }
Write-Host 'Ready. Run .\start.ps1, then open http://127.0.0.1:8765' -ForegroundColor Green
