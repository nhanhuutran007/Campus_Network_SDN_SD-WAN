$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$remoteScript = Join-Path $PSScriptRoot "check_ovs_live_temp.sh"
$output = Join-Path $PSScriptRoot "check_ovs_live_temp.log"

Get-Content -Raw -Encoding UTF8 $remoteScript |
    & ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@10.215.28.26 "bash -s" 2>&1 |
    Tee-Object -FilePath $output

Write-Host "--- DA LUU KET QUA VAO $output ---"
Read-Host "Nhan Enter de dong cua so"
