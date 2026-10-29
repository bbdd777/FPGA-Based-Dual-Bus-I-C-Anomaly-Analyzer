param([string]$PythonExe='python')
if ($PythonExe.Contains('/') -or $PythonExe.Contains('\')) { $PythonExe=[System.IO.Path]::GetFullPath($PythonExe) }
Push-Location (Join-Path $PSScriptRoot '../src/pc')
try { & $PythonExe app.py } finally { Pop-Location }
