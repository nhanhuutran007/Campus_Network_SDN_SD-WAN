$ErrorActionPreference = "Stop"

& ssh `
    -i "C:\Windows\Temp\codex-campus-eve-ed25519" `
    -o BatchMode=yes `
    root@10.215.28.26 `
    "ssh-copy-id -f -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /tmp/codex-node9-key.pub eve@10.1.99.10"

Write-Host "--- KET QUA SSH-COPY-ID O TREN ---"
Read-Host "Nhan Enter de dong cua so"
