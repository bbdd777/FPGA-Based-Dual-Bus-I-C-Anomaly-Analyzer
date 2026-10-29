param([string]$Uv4Path=$env:KEIL_UV4,[string]$FromElfPath=$env:FROMELF_EXE,[string]$PythonExe='python')
$ErrorActionPreference='Stop'
if (!$Uv4Path -or !$FromElfPath) { throw 'Pass -Uv4Path and -FromElfPath or set KEIL_UV4/FROMELF_EXE' }
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskProject=Join-Path $taskRoot 'project.uvprojx'
New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot 'verification'),(Join-Path $taskRoot 'objects'),(Join-Path $taskRoot 'listings') | Out-Null
$taskLog=Join-Path $taskRoot 'verification/keil_build.log'
$taskProcess=Start-Process -FilePath $Uv4Path -ArgumentList @('-r',('"'+$taskProject+'"'),'-t','Failover400','-o',('"'+$taskLog+'"')) -WindowStyle Hidden -PassThru -Wait
Get-Content -LiteralPath $taskLog
if ($taskProcess.ExitCode -ne 0) { throw ('Build exit '+$taskProcess.ExitCode) }
if ((Get-Content -LiteralPath $taskLog -Raw) -notmatch '0 Error\(s\), 0 Warning\(s\)') { throw 'Build not clean' }
$taskAsm=Join-Path $taskRoot 'verification/disassembly.txt'
& $FromElfPath --text -c -s --output $taskAsm (Join-Path $taskRoot 'objects/mcu4_400.axf')
if ($LASTEXITCODE -ne 0) { throw 'fromelf failed' }
& $PythonExe (Join-Path $PSScriptRoot 'check_arm_timing.py')
if ($LASTEXITCODE -ne 0) { throw 'ARM timing check failed' }
