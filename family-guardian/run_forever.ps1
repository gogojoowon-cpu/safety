# Windows supervisor: family-guardian 을 떠나지 않게 무한 재시작.
# PowerShell 정책이 막혀 있으면:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

Set-Location $PSScriptRoot

$activate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "[run_forever] .venv\Scripts\Activate.ps1 not found — please create the virtualenv first."
    exit 1
}
. $activate

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

while ($true) {
    Write-Host ("[run_forever] {0} starting main.py" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
    python main.py
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Write-Host "[run_forever] clean exit — stopping supervisor"
        break
    }
    Write-Host "[run_forever] exited with code $code — restarting in 5s"
    Start-Sleep -Seconds 5
}
