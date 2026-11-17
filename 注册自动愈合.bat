@echo off
chcp 65001 >nul
rem 注册"键盘自动愈合"计划任务（需要右键 → 以管理员身份运行，仅这一次）
rem 注册后，映射软件检测到遥控器键盘掉线时会自动调用本任务修复，无需再重启电脑。

set SCRIPT=%~dp0tools\heal_keyboard.ps1

net session >nul 2>nul
if %errorlevel% neq 0 (
    echo 请右键本文件，选择"以管理员身份运行"。
    pause
    exit /b
)

schtasks /create /tn "T6KeyboardHeal" /tr "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%SCRIPT%\"" /sc ONCE /st 00:00 /rl HIGHEST /f
if %errorlevel%==0 (
    echo.
    echo 注册成功！之后键盘掉线会自动愈合，无需重启电脑。
    echo 如需立即手动修复一次，运行： schtasks /run /tn T6KeyboardHeal
) else (
    echo 注册失败，请把本窗口内容发给 Kimi。
)
pause
