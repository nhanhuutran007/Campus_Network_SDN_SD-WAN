# Cấu hình hMailServer 5.6.x (32-bit) trên Mail-Server (node 13, Win7, DMZ 10.1.1.11) cho domain campus.internal.
# Cài im lặng (mật khẩu admin hMailServer để trống), rồi chạy script này để đặt mật khẩu mới:
#   c:\campus-setup\hmailserver-5.6.8-x86.exe /verysilent /suppressmsgboxes /norestart
#   powershell -ExecutionPolicy Bypass -File c:\campus-setup\mail-setup.ps1 -NewAdminPassword <mk-hmail> -UserPassword <mk-hop-thu>
# (Nếu đã cài có mật khẩu: thêm -AdminPassword <mk-hien-tai>)
# Đổi domain từ campus.local (bản cũ, xung đột mDNS): chỉ cần -AdminPassword; domain được đổi tên tại chỗ
# (giữ hộp thư + thư cũ) và campus.local thành domain alias để thư gửi tới địa chỉ cũ vẫn nhận được.
# Log: C:\campus-setup\mail-setup.log
param(
    [string]$AdminPassword = '',
    [string]$NewAdminPassword = '',
    [string]$UserPassword = '',
    [string]$Domain = 'campus.internal',
    [string]$OldDomain = 'campus.local'
)
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path C:\campus-setup | Out-Null
Start-Transcript -Path C:\campus-setup\mail-setup.log -Append

# 1. Mạng: IP tĩnh DMZ + DNS nội bộ
$nic = Get-WmiObject Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = true' | Select-Object -First 1
if ($nic.IPAddress -notcontains '10.1.1.11') {
    $nic.EnableStatic(@('10.1.1.11'), @('255.255.255.240')) | Out-Null
    $nic.SetGateways(@('10.1.1.1'), @(1)) | Out-Null
}
$nic.SetDNSServerSearchOrder(@('10.1.90.10')) | Out-Null
$nic.SetDNSDomain($Domain) | Out-Null

# 2. hMailServer: tên máy chủ, domain, cổng submission 587
$app = New-Object -ComObject hMailServer.Application
if (-not $app.Authenticate('Administrator', $AdminPassword)) { Write-Output 'SAI_MAT_KHAU_HMAIL'; Stop-Transcript; exit 1 }
if ($NewAdminPassword) { $app.Settings.SetAdministratorPassword($NewAdminPassword) }
$app.Settings.HostName = "mail.$Domain"

# Lưu ý: PowerShell không phân biệt hoa/thường tên biến => không đặt biến $domain (trùng tham số $Domain)
function Find-Domain($name) {
    for ($i = 0; $i -lt $app.Domains.Count; $i++) {
        if ($app.Domains.Item($i).Name -eq $name) { return $app.Domains.Item($i) }
    }
    return $null
}
$dom = Find-Domain $Domain
$old = Find-Domain $OldDomain
if (-not $dom -and $old) {
    # Đổi tên tại chỗ: hMailServer đổi luôn địa chỉ hộp thư và thư mục dữ liệu
    $old.Name = $Domain
    $old.Save()
    $app.Domains.Refresh()
    $dom = Find-Domain $Domain
    Write-Output "DA_DOI_TEN $OldDomain -> $Domain"
}
if (-not $dom) {
    $dom = $app.Domains.Add()
    $dom.Name = $Domain
    $dom.Active = $true
    $dom.Save()
}
# Phòng khi bản hMailServer không tự đổi địa chỉ hộp thư theo domain
for ($i = 0; $i -lt $dom.Accounts.Count; $i++) {
    $a = $dom.Accounts.Item($i)
    if ($a.Address -like "*@$OldDomain") { $a.Address = $a.Address -replace "@$([regex]::Escape($OldDomain))$", "@$Domain"; $a.Save() }
}
# Alias domain cũ để thư gửi tới @campus.local vẫn vào đúng hộp thư
if ($OldDomain -and -not (Find-Domain $OldDomain)) {
    $hasAlias = $false
    for ($i = 0; $i -lt $dom.DomainAliases.Count; $i++) {
        if ($dom.DomainAliases.Item($i).AliasName -eq $OldDomain) { $hasAlias = $true }
    }
    if (-not $hasAlias) {
        $al = $dom.DomainAliases.Add()
        $al.AliasName = $OldDomain
        $al.Save()
    }
}

$ports = $app.Settings.TCPIPPorts
$has587 = $false
for ($i = 0; $i -lt $ports.Count; $i++) { if ($ports.Item($i).PortNumber -eq 587) { $has587 = $true } }
if (-not $has587) {
    $p = $ports.Add()
    $p.Protocol = 1        # SMTP
    $p.PortNumber = 587
    $p.Save()
}

# 3. Hộp thư mẫu theo phòng ban / chi nhánh (chỉ tạo mới khi có -UserPassword)
$users = 'admin', 'hanhchinh', 'yte', 'taichinh', 'luhanh'
foreach ($u in $users) {
    $addr = "$u@$Domain"
    $exists = $false
    for ($i = 0; $i -lt $dom.Accounts.Count; $i++) { if ($dom.Accounts.Item($i).Address -eq $addr) { $exists = $true } }
    if (-not $exists -and $UserPassword) {
        $a = $dom.Accounts.Add()
        $a.Address = $addr
        $a.Password = $UserPassword
        $a.Active = $true
        $a.MaxSize = 100
        $a.Save()
    }
}

$app.Stop()
$app.Start()

# 4. Windows Firewall: SMTP 25/587, POP3 110, IMAP 143
netsh advfirewall firewall delete rule name="hMailServer campus" | Out-Null
netsh advfirewall firewall add rule name="hMailServer campus" dir=in action=allow protocol=TCP localport=25,110,143,587
netsh advfirewall firewall add rule name="ICMP echo campus" dir=in action=allow protocol=icmpv4:8,any | Out-Null

Write-Output "HostName: $($app.Settings.HostName)"
for ($i = 0; $i -lt $dom.Accounts.Count; $i++) { Write-Output $dom.Accounts.Item($i).Address }
for ($i = 0; $i -lt $dom.DomainAliases.Count; $i++) { Write-Output "alias: $($dom.DomainAliases.Item($i).AliasName)" }
netstat -an | findstr "LISTENING" | findstr ":25 :587 :143 :110"
Write-Output 'MAIL_SETUP_DONE'
Stop-Transcript
