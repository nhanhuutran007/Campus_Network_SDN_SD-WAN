# Cài Campus NetOps Bot lên DHCP-Server (node 72, Windows Server 2012 R2) — chạy MỘT lần, quyền Administrator:
#   powershell -ExecutionPolicy Bypass -File C:\netops\install.ps1
# Bộ cài offline (Python 3.11 embeddable + UCRT app-local + thư viện) đã nằm sẵn trong C:\netops.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root "python\python.exe"
New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null

Write-Host "== Python"
& $py -c "import sys, ssl; print(sys.version); print(ssl.OPENSSL_VERSION)"

Write-Host "== Khoá thư mục bí mật (chỉ SYSTEM + Administrators)"
$sec = Join-Path $root "secrets"
icacls $sec /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null
icacls (Join-Path $root "app\.env") /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" | Out-Null

Write-Host "== Unit test offline"
# PowerShell 4 + ErrorActionPreference=Stop coi stderr của chương trình ngoài (unittest in ra stderr) là lỗi
# và dừng script → chạy qua cmd, ghi log, chỉ in dòng tổng kết.
Push-Location (Join-Path $root "app")
cmd /c "`"$py`" -m unittest discover -s tests > `"$root\logs\unittest.txt`" 2>&1"
Get-Content (Join-Path $root "logs\unittest.txt") | Select-Object -Last 3
Pop-Location

Write-Host "== Đăng ký task NetOps-Bot (khởi động cùng máy, chạy bằng SYSTEM, tự chạy lại khi dừng)"
schtasks /Create /TN "NetOps-Bot" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "`"$root\run.cmd`"" /F | Out-Null
schtasks /Run /TN "NetOps-Bot" | Out-Null

Write-Host "== Selftest (DNS, HTTPS qua FW, SSH thiết bị, Ryu, vManage)"
Push-Location (Join-Path $root "app")
& $py scripts\selftest.py
Pop-Location
