@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (goto RUN)
where py >nul 2>nul
if %errorlevel%==0 (goto RUN)
echo 未找到 Python。请先安装 Python 3.10+（安装时勾选 tcl/tk）
pause
exit /b

:RUN
rem 守护模式：软件崩溃会自动重启；正常关闭窗口则完全退出
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\supervisor.ps1"
