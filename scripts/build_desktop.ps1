param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (-not (Test-Path -LiteralPath $destination -PathType Container)) { throw 'Build the portable runtime directory first.' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'The Windows .NET Framework C# compiler is unavailable.' }
$iconDirectory = Join-Path $projectRoot 'desktop'
$iconPath = Join-Path $iconDirectory 'branding\Shengjian-line.ico'
if (-not (Test-Path -LiteralPath $iconPath)) { throw 'The approved Shengjian icon is missing.' }
$executable = Join-Path $destination 'LocalAudio.exe'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$executable" "/win32icon:$iconPath" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll (Join-Path $iconDirectory 'Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Desktop launcher compilation failed.' }
Copy-Item -LiteralPath $iconPath -Destination (Join-Path $destination 'Shengjian.ico')
Write-Host "Desktop launcher built: $executable"
