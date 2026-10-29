param([string]$PythonExe = '')

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$packageRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $packageRoot '.venv/Scripts/python.exe'
$requirementsFile = Join-Path $packageRoot 'src/pc/requirements-lock.txt'
$applicationFile = Join-Path $packageRoot 'src/pc/app.py'

function Find-TaskPython {
    # 优先选择已验证的3.12/3.10，避免系统默认Python过新或过旧导致依赖无法安装。
    $candidates = @()
    if ($PythonExe) { $candidates += @{ Command = $PythonExe; Prefix = @() } }
    $candidates += @(
        @{ Command = 'py.exe'; Prefix = @('-3.12') },
        @{ Command = 'py.exe'; Prefix = @('-3.10') },
        @{ Command = 'python.exe'; Prefix = @() },
        @{ Command = 'py.exe'; Prefix = @('-3.11') }
    )
    $probe = 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)'
    foreach ($candidate in $candidates) {
        if (!(Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
        try {
            $prefix = $candidate.Prefix
            & $candidate.Command @prefix -c $probe *> $null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {
            # py启动器存在但未装对应版本时，继续检查下一个候选。
        }
    }
    throw '没有找到Python 3.10～3.12。请先安装Python 3.12（包含pip和Tkinter），再双击启动上位机.bat。'
}

try {
    foreach ($path in @($requirementsFile, $applicationFile)) {
        if (!(Test-Path -LiteralPath $path)) {
            throw '缺少上位机文件。请先将整个ZIP解压，再运行包根目录的启动上位机.bat。'
        }
    }
    if (!(Test-Path -LiteralPath $taskPython)) {
        Write-Host '[1/3] 首次运行，正在建立本包专用Python环境……'
        $candidate = Find-TaskPython
        $prefix = $candidate.Prefix
        & $candidate.Command @prefix -m venv (Join-Path $packageRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python环境创建失败，请查看上方错误。' }
    }
    & $taskPython -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw '包内.venv不可用或Python版本不支持，请使用Python 3.10～3.12建立环境。' }

    # 已安装依赖时直接启动；不会每次联网安装，也不改变系统Python的依赖。
    $dependenciesReady = $false
    try {
        & $taskPython -c 'import tkinter, serial, matplotlib, numpy; from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg' *> $null
        $dependenciesReady = ($LASTEXITCODE -eq 0)
    } catch { $dependenciesReady = $false }
    if (!$dependenciesReady) {
        Write-Host '[2/3] 正在安装上位机依赖，首次安装需要联网，请等待……'
        & $taskPython -m pip install --disable-pip-version-check -r $requirementsFile
        if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。请检查网络和上方错误，再重新双击启动。' }
    }
    Write-Host '[3/3] 正在启动上位机。打开后选择串口、1000000波特率，再点击“连接监测”。'
    Push-Location (Join-Path $packageRoot 'src/pc')
    try {
        & $taskPython $applicationFile
        if ($LASTEXITCODE -ne 0) { throw '上位机运行失败，请查看上方错误。' }
    } finally { Pop-Location }
    exit 0
} catch {
    Write-Host ''
    Write-Host ('启动失败：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
