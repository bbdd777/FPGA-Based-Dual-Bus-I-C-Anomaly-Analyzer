param([ValidateSet(460800,921600,1000000,2000000)][int]$Baud=1000000,[string]$VivadoBin=$env:VIVADO_BIN)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location $taskRoot
try {
    New-Item -ItemType Directory -Force -Path 'verification' | Out-Null
    $taskInputs = Get-ChildItem -LiteralPath (Join-Path $taskRoot 'rtl'),(Join-Path $taskRoot 'constr') -File | ForEach-Object {
        [PSCustomObject]@{ path=$_.FullName; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    }
    $taskInputs | ConvertTo-Json | Set-Content -LiteralPath 'verification/build_inputs.json' -Encoding utf8
    if (!$VivadoBin) { throw 'Set VIVADO_BIN or pass -VivadoBin with Vivado bin directory' }; New-Item -ItemType Directory -Force -Path 'verification' | Out-Null; & (Join-Path $VivadoBin 'vivado.bat') -mode batch -source scripts/build.tcl -log verification/build.log -journal verification/build.jou -tclargs $Baud
    if ($LASTEXITCODE -ne 0) { throw 'Offline build failed; inspect verification/build.log' }
} finally { Pop-Location }


