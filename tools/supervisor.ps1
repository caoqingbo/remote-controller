# Remote KeyMapper crash supervisor
# Restarts the app if it exits abnormally; a quit.flag written by the GUI means clean exit.
$dir = Split-Path $PSScriptRoot -Parent
$app = Join-Path $dir 'app.py'
$flag = Join-Path $dir 'quit.flag'
Remove-Item $flag -Force -ErrorAction SilentlyContinue

$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $py = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if (-not $py) { Write-Host 'pythonw/py not found'; exit 1 }
    while ($true) {
        $p = Start-Process -FilePath $py -ArgumentList '-w', "`"$app`"" -WorkingDirectory $dir -PassThru
        $p.WaitForExit()
        if (Test-Path $flag) { Remove-Item $flag -Force -ErrorAction SilentlyContinue; exit 0 }
        Start-Sleep 3
    }
}
while ($true) {
    $p = Start-Process -FilePath $pyw -ArgumentList "`"$app`"" -WorkingDirectory $dir -PassThru
    $p.WaitForExit()
    if (Test-Path $flag) { Remove-Item $flag -Force -ErrorAction SilentlyContinue; exit 0 }
    Start-Sleep 3
}
