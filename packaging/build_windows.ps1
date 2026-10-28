#Requires -Version 7
# Build the Windows release artifact: dist\cyberdeck-<version>-win64.zip
#   pwsh -File packaging\build_windows.ps1
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "building cyberdeck $version for win64" -ForegroundColor Cyan

if (-not $SkipInstall) {
    uv pip install pyinstaller | Out-Null
}

uv run --no-sync pyinstaller --noconfirm --clean --onefile --name cyberdeck `
    --paths src `
    --collect-all cyberdeck `
    --collect-all textual `
    --collect-data rich `
    packaging/entry.py | Out-Null

if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed with exit code $LASTEXITCODE (is cyberdeck.exe still running?)" }
if (-not (Test-Path "dist\cyberdeck.exe")) { throw "pyinstaller produced no exe" }

$readme = @"
cyberdeck $version - Windows x64
===============================

Double-click cyberdeck.exe, or run it from Windows Terminal:

    .\cyberdeck.exe
    .\cyberdeck.exe --fps 5      # recommended for an always-on dashboard
    .\cyberdeck.exe --still      # frozen Earth, lowest CPU
    .\cyberdeck.exe --city Shanghai

Requirements
  * Windows 10/11 x64, Windows Terminal (or any truecolor terminal)
  * window of at least 110 x 30 cells, a monospace font
    (Cascadia Mono / JetBrains Mono / Consolas)
  * no Python installation needed - this is a self-contained build

Keys
  q quit · r weather · space spin · +/- speed · t theme · 1-8 theme
  up/down select process · s sort · k kill · i info column · e edit

State (config.json / todo.txt / notes.txt / weather cache) lives in
%LOCALAPPDATA%\cyberdeck\. Delete that folder to start from scratch.

First launch may take a few seconds: the executable unpacks itself to a
temporary folder before it starts.

The interface is Chinese; source and docs:
https://github.com/kylechuuuuu/cyberdeck
"@

$stage = "dist\stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item "dist\cyberdeck.exe" $stage
Set-Content -Path (Join-Path $stage "README.txt") -Value $readme -Encoding utf8

$zip = "dist\cyberdeck-$version-win64.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
Remove-Item $stage -Recurse -Force

$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "wrote $zip ($size MB)" -ForegroundColor Green
