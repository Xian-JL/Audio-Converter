param([Parameter(Mandatory=$true)][string]$PackageDirectory)
$ErrorActionPreference = 'Stop'
$package = [IO.Path]::GetFullPath($PackageDirectory)
$exe = Join-Path $package 'LocalAudio.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'LocalAudio.exe is missing. Build the desktop package first.' }
$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop '声笺.lnk'
$shell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $link) {
    $previous = $shell.CreateShortcut($link)
    if ($previous.TargetPath -ne $exe) { $link = Join-Path $desktop '声笺（Shengjian）.lnk' }
    if ((Test-Path -LiteralPath $link) -and $shell.CreateShortcut($link).TargetPath -ne $exe) { throw 'A different shortcut already uses this name. Choose another shortcut name.' }
}
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $package
$shortcut.IconLocation = (Join-Path $package 'Shengjian.ico') + ',0'
$shortcut.Description = '声笺：旋律转谱、柱式和弦与 EMO 器乐创作'
$shortcut.WindowStyle = 1
$shortcut.Save()
# Migrate only the old shortcut owned by this same installation.
$oldLink = Join-Path $desktop '本地音频.lnk'
if ((Test-Path -LiteralPath $oldLink) -and $shell.CreateShortcut($oldLink).TargetPath -eq $exe) {
    Remove-Item -LiteralPath $oldLink
}
Write-Output $link
