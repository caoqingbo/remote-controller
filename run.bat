@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (start "" pythonw app.py & exit /b)
where py >nul 2>nul
if %errorlevel%==0 (start "" /min py -w app.py & exit /b)
echo 未找到 Python。请先安装 Python 3.10+（安装时勾选 tcl/tk）
pause
