# Remote KeyMapper crash supervisor (with logging)
$dir = Split-Path $PSScriptRoot -Parent
$app = Join-Path $dir 'app.py'
$flag = Join-Path $dir 'quit.flag'
$log = Join-Path $dir 'tools\supervisor.log'
Remove-Item $flag -Force -ErrorAction SilentlyContinue

function Log($msg) {
    $line = (Get-Date -Format 'HH:mm:ss') + ' ' + $msg
    Add-Content -Path $log -Value $line -Encoding UTF8
}

# 解析 Python 解释器：优先用户环境里的 pythonw，其次 py -w
$pyw = $null
try { $pyw = (Get-Command pythonw.exe -ErrorAction Stop).Source } catch {}
$py = $null
try { $py = (Get-Command py.exe -ErrorAction Stop).Source } catch {}

Log ('supervisor start; pythonw=' + $pyw + ' py=' + $py)

if (-not $pyw -and -not $py) { Log 'ERROR: no interpreter found'; exit 1 }

while ($true) {
    try {
        if ($pyw) {
            Log ('launch via pythonw: ' + $pyw)
            $p = Start-Process -FilePath $pyw -ArgumentList "`"$app`"" -WorkingDirectory $dir -PassThru
        } else {
            Log ('launch via py -w: ' + $py)
            $p = Start-Process -FilePath $py -ArgumentList '-w', "`"$app`"" -WorkingDirectory $dir -PassThru
        }
        Log ('started PID ' + $p.Id + '; waiting for exit')
        $p.WaitForExit()
        Log ('exited; code=' + $p.ExitCode)
    } catch {
        Log ('LAUNCH ERROR: ' + $_.Exception.Message)
        Start-Sleep 10
        continue
    }
    if (Test-Path $flag) {
        Remove-Item $flag -Force -ErrorAction SilentlyContinue
        Log 'quit.flag found; clean exit'
        exit 0
    }
    Start-Sleep 3
}
