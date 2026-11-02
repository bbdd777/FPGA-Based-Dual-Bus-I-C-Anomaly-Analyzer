@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch_pc.ps1"
if errorlevel 1 (
    echo.
    echo 启动未完成，请查看上方提示。
    pause
    exit /b 1
)
endlocal
