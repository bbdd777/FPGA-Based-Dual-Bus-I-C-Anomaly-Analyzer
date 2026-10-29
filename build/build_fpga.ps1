param([int]$Baud=1000000,[string]$VivadoBin=$env:VIVADO_BIN)
& (Join-Path $PSScriptRoot '../src/vivado_prj/scripts/build.ps1') -Baud $Baud -VivadoBin $VivadoBin
if ($LASTEXITCODE -ne 0) { throw 'FPGA build failed' }
