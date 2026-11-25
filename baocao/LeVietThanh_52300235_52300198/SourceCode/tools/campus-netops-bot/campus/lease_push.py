"""Đẩy bảng lease DHCP sang web đo đạc ở Site 900 (10.9.0.20).

Web ở Site 900 nằm phía transport (VPN 0) nên không tới được Brand-FW chi nhánh (VPN 1). Bot nằm
trong VPN 1 (DHCP-Server 10.1.90.10) nên đọc được lease, rồi POST sang web qua đường Site 100 → FW
→ vEdge → transport (FW cho 10.1.90.0/24 → 10.0.0.0/8). Web dùng bảng này tra IP hiện tại của
từng PC theo MAC/Client ID, thay cho IP ghi cứng.

Chỉ đọc: `show dhcpd binding` trên Brand-FW và Get-DhcpServerv4Lease tại chỗ.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# Brand-FW làm DHCP server cho chi nhánh (Site 500 chưa có SSH netops → chưa đọc)
SITE_FW = {"200": "Brand-FW-S200", "300": "Brand-FW-S300", "400": "Brand-FW-S400"}
# Scope VLAN người dùng Site 100 trên DHCP-Server (node 72)
SITE100_SCOPES = ("10.1.10.0", "10.1.20.0", "10.1.30.0", "10.1.40.0")

_ASA_ROW = re.compile(r"^\s*(10\.\d+\.\d+\.\d+)\s+([0-9A-Fa-f.]+)\s+(\d+)\s+seconds", re.M)


def parse_asa_binding(out: str) -> list[dict]:
    """`show dhcpd binding` của ASA → [{ip, client_id, expires_s}]."""
    return [{"ip": ip, "client_id": cid.lower(), "expires_s": int(sec)} for ip, cid, sec in _ASA_ROW.findall(out)]


def _run_show(device: str, command: str) -> str:
    from . import service          # import muộn: tránh vòng import, test thay bằng hàm giả
    dev, err = service._resolve(device)
    if err:
        raise RuntimeError(err.text)
    return service.console().run(dev, [command])[0]


def collect(run=_run_show, dhcp=None) -> dict:
    """Gom lease mọi nguồn; nguồn lỗi ghi vào `errors`, các nguồn khác vẫn gửi."""
    leases, errors = [], {}
    for site, fw in SITE_FW.items():
        try:
            for row in parse_asa_binding(run(fw, "show dhcpd binding")):
                leases.append(dict(row, site=site, source=fw))
        except Exception as e:          # noqa: BLE001 — một FW lỗi không được chặn các FW khác
            errors[fw] = f"{type(e).__name__}: {str(e)[:120]}"
    if dhcp is None:
        from . import dhcp_local as dhcp
    if dhcp.available():
        for scope in SITE100_SCOPES:
            try:
                for x in dhcp.leases(scope):
                    if x.get("IP") and x.get("ClientId"):
                        leases.append({"ip": x["IP"], "client_id": str(x["ClientId"]).lower(), "site": "100",
                                       "source": "DHCP-Server", "hostname": x.get("HostName") or "",
                                       "state": x.get("AddressState") or ""})
            except Exception as e:      # noqa: BLE001
                errors[f"DHCP-Server {scope}"] = f"{type(e).__name__}: {str(e)[:120]}"
    else:
        errors["DHCP-Server"] = "bot không chạy trên DHCP-Server (không có module DhcpServer)"
    return {"collected_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "collector": "campus-netops-bot", "leases": leases, "errors": errors}


def push(payload: dict, url: str, token: str, timeout: int = 15) -> str:
    """POST JSON sang web; trả về thông điệp ngắn từ web. Lỗi mạng/HTTP → RuntimeError."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-Lease-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"web trả HTTP {e.code}: {e.read(200).decode('utf-8', 'replace')}") from None
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"không tới được {url}: {getattr(e, 'reason', e)}") from None
