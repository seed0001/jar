# JARVIS App Installer / Shortcut Creator
$ErrorActionPreference = "Stop"

$rootPath = Resolve-Path "$PSScriptRoot"
$scriptsPath = Join-Path $rootPath "scripts"
$vbsPath = Join-Path $scriptsPath "launch_hidden.vbs"
$iconPath = Join-Path $rootPath "assets\icon_premium.ico"
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "JARVIS.lnk"

Write-Host "Creating JARVIS Desktop Shortcut..." -ForegroundColor Cyan

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$vbsPath`""
$shortcut.WorkingDirectory = $rootPath.Path
$shortcut.IconLocation = $iconPath
$shortcut.Description = "Launch JARVIS Autonomous Assistant"
$shortcut.Save()

Write-Host "Success! You can now launch JARVIS directly from your Desktop." -ForegroundColor Green
Write-Host "The app will open in a standalone window, and services will run in the background." -ForegroundColor Gray
Write-Host "Check 'jarvis_launcher.log' in the project folder if you encounter issues." -ForegroundColor Gray
