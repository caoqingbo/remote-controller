@echo off
rem Register the T6KeyboardHeal scheduled task (run as Administrator, one time only)
set SCRIPT=%~dp0tools\heal_keyboard.ps1

net session >nul 2>nul
if %errorlevel% neq 0 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b
)

schtasks /create /tn "T6KeyboardHeal" /tr "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%SCRIPT%\"" /sc ONCE /st 00:00 /rl HIGHEST /f
if %errorlevel%==0 (
    echo.
    echo OK - heal task registered.
) else (
    echo Registration failed - send this window to Kimi.
)
pause
