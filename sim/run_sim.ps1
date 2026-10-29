param([string]$VivadoBin=$env:VIVADO_BIN,[string[]]$Tops)
& (Join-Path $PSScriptRoot '../src/vivado_prj/scripts/run_sim.ps1') -VivadoBin $VivadoBin -Tops $Tops
if ($LASTEXITCODE -ne 0) { throw 'RTL checks failed' }
