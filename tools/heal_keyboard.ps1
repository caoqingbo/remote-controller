# T6 遥控器键盘自动愈合脚本
# 由计划任务以最高权限调用：重启遥控器的键盘 HID 设备节点，促使其重新枚举
$ErrorActionPreference = 'SilentlyContinue'
$mac = '13D5EF6FCD43'
$log = Join-Path $PSScriptRoot 'heal.log'
function Log($m) { Add-Content -Path $log -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' ' + $m) -Encoding UTF8 }

# 1) 优先：键盘集合节点还在（PnP 显示正常但无输入）→ 禁用再启用
$kbd = Get-PnpDevice | Where-Object { $_.Class -eq 'Keyboard' -and $_.InstanceId -match $mac }
if ($kbd) {
    foreach ($d in $kbd) {
        Log ('disable keyboard node: ' + $d.InstanceId)
        Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
    }
    Start-Sleep 2
    foreach ($d in $kbd) {
        Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
        Log ('enabled keyboard node')
    }
} else {
    # 2) 键盘节点已消失 → 重启整个 BLE HID 父设备（GATT HID 服务重新订阅）
    $parent = Get-PnpDevice | Where-Object { $_.InstanceId -match ('BTHLEDEVICE.*' + $mac) -and $_.InstanceId -match '00001812' }
    if ($parent) {
        foreach ($d in $parent) {
            Log ('restart BLE HID parent: ' + $d.InstanceId)
            Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
        }
        Start-Sleep 3
        foreach ($d in $parent) { Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false }
        Log 'BLE HID parent re-enabled'
    } else {
        Log 'no device node found (remote may be off)'
    }
}
Log 'heal done'
