"""Đọc DHCP Server của Windows tại chỗ (bot chạy trên chính DHCP-Server node 72).

Dùng module PowerShell DhcpServer (có sẵn khi cài role DHCP, Server 2012 R2 trở lên). Chỉ đọc.
Trên máy khác (laptop, Linux) `available()` = False và các hàm trả lỗi rõ ràng.
"""
from __future__ import annotations

import json
import os
import subprocess

_PS = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]


class DhcpError(Exception):
    pass


def _ps_json(script: str) -> list[dict]:
    try:
        r = subprocess.run(_PS + [script + " | ConvertTo-Json -Compress"], capture_output=True, text=True,
                           timeout=60, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        raise DhcpError(f"Không chạy được PowerShell: {type(e).__name__}") from None
    if r.returncode != 0:
        raise DhcpError(r.stderr.strip().splitlines()[0] if r.stderr.strip() else f"PowerShell lỗi {r.returncode}")
    out = r.stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def available() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(_ps_json("Get-Module -ListAvailable DhcpServer | Select-Object -First 1 Name"))
    except (DhcpError, ValueError):
        return False


def scopes() -> list[dict]:
    return _ps_json("Get-DhcpServerv4ScopeStatistics | Select-Object "
                    "@{n='ScopeId';e={$_.ScopeId.IPAddressToString}},Free,InUse,PercentageInUse")


def leases(scope_id: str) -> list[dict]:
    if not all(p.isdigit() for p in scope_id.split(".")) or scope_id.count(".") != 3:
        raise DhcpError(f"ScopeId không hợp lệ: {scope_id}")
    return _ps_json(f"Get-DhcpServerv4Lease -ScopeId {scope_id} | Select-Object "
                    "@{n='IP';e={$_.IPAddress.IPAddressToString}},ClientId,HostName,AddressState,"
                    "@{n='Expiry';e={if ($_.LeaseExpiryTime) {$_.LeaseExpiryTime.ToString('dd/MM HH:mm')} else {''}}}")
