param([string]$PythonExe='python',[switch]$UnitOnly)
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
if ($PythonExe.Contains('/') -or $PythonExe.Contains('\')) { $PythonExe=[System.IO.Path]::GetFullPath($PythonExe) }
$pcRoot=Join-Path $PSScriptRoot '../src/pc'
if (!$UnitOnly) {
    $simRoot=Join-Path $PSScriptRoot '../src/vivado_prj/verification/sim'
    foreach ($name in @('core_stream.hex','stream_1m.hex','stream_1m_serial.hex','busy_stream.hex','bad_reads_stream.hex')) {
        if (!(Test-Path -LiteralPath (Join-Path $simRoot $name))) {
            throw 'Run sim/run_sim.ps1 -VivadoBin <Vivado bin> first, or use -UnitOnly.'
        }
    }
}
Push-Location $pcRoot
try {
    $checks=@('run_tests.py')
    if (!$UnitOnly) { $checks+=@('check_replay.py','check_gui.py','check_scroll_layout.py','check_transport.py') }
    foreach ($file in $checks) { & $PythonExe $file; if ($LASTEXITCODE -ne 0) { throw ('PC check failed: '+$file) } }
} finally { Pop-Location }
