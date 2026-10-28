#Requires -Version 7
# Launch the cyberdeck dashboard.
#   .\run.ps1            normal start
#   .\run.ps1 -Loop      kiosk mode: restart automatically if the app crashes
param(
    [switch]$Loop,
    [int]$Delay = 5
)

Set-Location $PSScriptRoot

if (-not $Loop) {
    uv run cyberdeck @args
    exit $LASTEXITCODE
}

while ($true) {
    uv run cyberdeck @args
    $code = $LASTEXITCODE
    # 0 = quit with q, 130 / -1073741510 = ctrl+c: honour it instead of restarting
    if ($code -eq 0 -or $code -eq 130 -or $code -eq -1073741510) { break }
    Write-Host "[cyberdeck] exited with code $code, restarting in ${Delay}s (ctrl+c to stop)" -ForegroundColor DarkYellow
    Start-Sleep -Seconds $Delay
}
