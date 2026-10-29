param([string]$Uv4Path=$env:KEIL_UV4,[string]$FromElfPath=$env:FROMELF_EXE,[string]$PythonExe='python')
& (Join-Path $PSScriptRoot '../src/mcu/scripts/build.ps1') -Uv4Path $Uv4Path -FromElfPath $FromElfPath -PythonExe $PythonExe
if ($LASTEXITCODE -ne 0) { throw 'MCU build failed' }
