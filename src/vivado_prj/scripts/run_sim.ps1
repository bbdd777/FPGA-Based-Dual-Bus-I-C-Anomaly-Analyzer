param([string[]]$Tops,[string]$VivadoBin=$env:VIVADO_BIN)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (!$VivadoBin) { throw 'Set VIVADO_BIN or pass -VivadoBin' }; $taskBin = $VivadoBin
$taskVerify = Join-Path $taskRoot 'verification/sim'
New-Item -ItemType Directory -Force -Path $taskVerify | Out-Null
$taskSources = Get-ChildItem -LiteralPath (Join-Path $taskRoot 'rtl') -Filter *.v | ForEach-Object { $_.FullName }
$taskSources += Get-ChildItem -LiteralPath (Join-Path $taskRoot 'sim') -Filter *.v | ForEach-Object { $_.FullName }
if (!$Tops) { $Tops = @('tb_capture_ring','tb_failover_rules','tb_uart_1m','tb_pressure','tb_stream_1m','tb_live_busy','tb_bad_reads','tb_analyzer_core') }
Push-Location $taskVerify
try {
    & (Join-Path $taskBin 'xvlog.bat') --work xil_defaultlib @taskSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilog compilation failed' }
    foreach ($taskTop in $Tops) {
        & (Join-Path $taskBin 'xelab.bat') ('xil_defaultlib.'+$taskTop) -s $taskTop --debug typical
        if ($LASTEXITCODE -ne 0) { throw ('Elaboration failed: '+$taskTop) }
        & (Join-Path $taskBin 'xsim.bat') $taskTop -runall -log ($taskTop+'.log')
        if ($LASTEXITCODE -ne 0) { throw ('Simulation failed: '+$taskTop) }
        $taskLog = Get-Content -LiteralPath ($taskTop+'.log') -Raw
        if ($taskLog -notmatch ('PASS ALL '+$taskTop) -or $taskLog -match '(?im)^Fatal:|\$fatal') {
            throw ('Self-check failed: '+$taskTop)
        }
    }
} finally { Pop-Location }

