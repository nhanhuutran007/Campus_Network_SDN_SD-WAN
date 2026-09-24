# DNS nội bộ campus.internal trên DHCP-Server (node 72, Windows Server 2012 R2, 10.1.90.10)
# Chạy một lần bằng Administrator: powershell -ExecutionPolicy Bypass -File C:\campus-setup\dns-setup.ps1
# Log: C:\campus-setup\dns-setup.log
# .internal = TLD ICANN dành cho mạng riêng (2024). Zone cũ campus.local (xung đột mDNS) giữ tạm
# để chuyển tiếp, xoá sau: Remove-DnsServerZone campus.local -Force
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path C:\campus-setup | Out-Null
Start-Transcript -Path C:\campus-setup\dns-setup.log -Append

Install-WindowsFeature DNS -IncludeManagementTools
Import-Module DnsServer

$zone = 'campus.internal'
if (-not (Get-DnsServerZone -Name $zone -ErrorAction SilentlyContinue)) {
    Add-DnsServerPrimaryZone -Name $zone -ZoneFile "$zone.dns"
}
$records = @{ 'www' = '10.1.1.10'; 'web' = '10.1.1.10'; 'mail' = '10.1.1.11';
              'dns' = '10.1.90.10'; 'dhcp' = '10.1.90.10'; 'syslog' = '10.1.90.11' }
foreach ($name in $records.Keys) {
    if (-not (Get-DnsServerResourceRecord -ZoneName $zone -Name $name -RRType A -ErrorAction SilentlyContinue)) {
        Add-DnsServerResourceRecordA -ZoneName $zone -Name $name -IPv4Address $records[$name]
    }
}
if (-not (Get-DnsServerResourceRecord -ZoneName $zone -RRType MX -ErrorAction SilentlyContinue)) {
    Add-DnsServerResourceRecordMX -ZoneName $zone -Name '.' -MailExchange "mail.$zone" -Preference 10
}

# Reverse zone cho DMZ (PTR www / mail)
$rev = '1.1.10.in-addr.arpa'
if (-not (Get-DnsServerZone -Name $rev -ErrorAction SilentlyContinue)) {
    Add-DnsServerPrimaryZone -Name $rev -ZoneFile "$rev.dns"
}
foreach ($ptr in @{ '10' = "www.$zone."; '11' = "mail.$zone." }.GetEnumerator()) {
    $cur = Get-DnsServerResourceRecord -ZoneName $rev -Name $ptr.Key -RRType Ptr -ErrorAction SilentlyContinue
    if ($cur -and $cur.RecordData.PtrDomainName -ne $ptr.Value) {
        Remove-DnsServerResourceRecord -ZoneName $rev -Name $ptr.Key -RRType Ptr -Force
        $cur = $null
    }
    if (-not $cur) { Add-DnsServerResourceRecordPtr -ZoneName $rev -Name $ptr.Key -PtrDomainName $ptr.Value }
}

# DHCP Site 100: phát DNS nội bộ + domain cho mọi scope
Import-Module DhcpServer -ErrorAction SilentlyContinue
Set-DhcpServerv4OptionValue -DnsServer 10.1.90.10 -DnsDomain $zone -Force
Get-DhcpServerv4Scope | ForEach-Object {
    Set-DhcpServerv4OptionValue -ScopeId $_.ScopeId -DnsServer 10.1.90.10 -DnsDomain $zone -Force
}

Get-DnsServerResourceRecord -ZoneName $zone | Format-Table -AutoSize | Out-String -Width 200
Resolve-DnsName "www.$zone" -Server 127.0.0.1 -ErrorAction SilentlyContinue | Format-Table | Out-String
Get-DhcpServerv4OptionValue | Format-Table -AutoSize | Out-String
Write-Output 'DNS_SETUP_DONE'
Stop-Transcript

