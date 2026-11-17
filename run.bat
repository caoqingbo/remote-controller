@echo off
chcp 65001 >nul
set LOG=%~dp0tools\run.log
echo ===== %DATE% %TIME% run.bat clicked ===== >> "%LOG%"
cd /d "%~dp0"
echo cwd=%CD% >> "%LOG%"
where pythonw >nul 2>nul
echo where pythonw exit=%errorlevel% >> "%LOG%"
where py >nul 2>nul
echo where py exit=%errorlevel% >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\supervisor.ps1" >> "%LOG%" 2>&1
echo powershell exit=%errorlevel% >> "%LOG%"
