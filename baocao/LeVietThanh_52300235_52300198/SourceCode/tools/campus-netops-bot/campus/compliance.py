"""Kiểm tuân thủ các bất biến của đồ án trên running-config (chỉ đọc).

Mỗi quy tắc là hàm thuần `(device, running) -> list[(đạt?, mô tả)]`, kiểm thử offline được.
Bất biến lấy từ thiết kế: DHCP pool .100–.199, relay 10.1.90.10, VRRP gateway .1,
System-IP 10.200.<site>.x, site-id đúng site, màu TLOC khớp transport, ISP lọc default từ khách hàng.
"""
from __future__ import annotations

import re

SYSIP_OCTET = {"100": "100", "200": "200", "300": "30", "400": "40", "500": "50"}


def _blocks(running: str, head: str) -> dict[str, str]:
    """Tách khối IOS `interface X` … đến dòng không thụt lề tiếp theo."""
    out, cur, buf = {}, None, []
    for line in running.splitlines():
        if line and not line.startswith(" "):
            if cur:
                out[cur] = "\n".join(buf)
            m = re.match(rf"^{head}\s+(\S+)", line)
            cur, buf = (m.group(1) if m else None), []
        elif cur:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf)
    return out


def core_rules(dev, running: str):
    res = []
    svis = _blocks(running, "interface")
    for v in (10, 20, 30, 40):
        body = svis.get(f"Vlan{v}", "")
        res.append(("ip helper-address 10.1.90.10" in body, f"Vlan{v} relay DHCP tới 10.1.90.10"))
        res.append((f"vrrp {v} ip 10.1.{v}.1" in body, f"Vlan{v} VRRP gateway 10.1.{v}.1"))
    return res


def brandfw_rules(dev, running: str):
    s = dev.site[0]
    pools = re.findall(r"^dhcpd address (10\.\d+\.\d+)\.(\d+)-10\.\d+\.\d+\.(\d+) (\S+)", running, re.M)
    res = [(bool(pools), "có dhcpd address")]
    for net, lo, hi, name in pools:
        res.append((lo == "100" and hi == "199" and net.startswith(f"10.{s}."),
                    f"pool {name} {net}.{lo}-{hi} theo quy ước 10.{s}.x.100–199"))
    for name in sorted({p[3] for p in pools}):
        res.append((re.search(rf"^dhcpd enable {re.escape(name)}\s*$", running, re.M) is not None,
                    f"dhcpd enable {name}"))
    return res


def _vedge_ifaces(running: str):
    """Duyệt từng dòng: khối `interface geX` kết thúc khi gặp dòng có thụt lề ≤ dòng interface."""
    out, cur, indent, buf = [], None, 0, []
    for line in running.splitlines():
        stripped = line.lstrip()
        ind = len(line) - len(stripped)
        if cur is not None and stripped and ind <= indent:
            out.append((cur, "\n".join(buf)))
            cur = None
        m = re.match(r"interface (ge\S+)\s*$", stripped)
        if m and cur is None:
            cur, indent, buf = m.group(1), ind, []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out.append((cur, "\n".join(buf)))
    return out


def vedge_rules(dev, running: str):
    res = []
    site = re.search(r"^\s*site-id\s+(\d+)", running, re.M)
    sysip = re.search(r"^\s*system-ip\s+(\S+)", running, re.M)
    res.append((bool(site) and site.group(1) == dev.site, f"site-id = {dev.site}"))
    want = SYSIP_OCTET.get(dev.site)
    res.append((bool(sysip) and bool(want) and sysip.group(1).startswith(f"10.200.{want}."),
                f"system-ip 10.200.{want}.x (hiện {sysip.group(1) if sysip else '?'})"))
    # màu TLOC: interface có ip 203.0.113.x → biz-internet, 100.64.x → mpls
    for name, body in _vedge_ifaces(running):
        ip = re.search(r"ip address (\d+\.\d+)\.", body)
        color = re.search(r"color (\S+)", body)
        if not ip or not color:
            continue
        want_c = {"203.0": "biz-internet", "100.64": "mpls"}.get(ip.group(1))
        if want_c:
            res.append((color.group(1) == want_c, f"{name} {ip.group(1)}.x màu {color.group(1)} (phải {want_c})"))
    return res


def internet_rules(dev, running: str):
    ce = re.findall(r"^\s*neighbor (203\.0\.113\.\d+) remote-as (650\d\d)", running, re.M)
    res = [(bool(ce), "có BGP neighbor khách hàng 650xx")]
    for ip, asn in ce:
        res.append((re.search(rf"neighbor {re.escape(ip)} prefix-list NO_DEFAULT_IN in", running) is not None,
                    f"neighbor {ip} (AS {asn}) lọc default vào (NO_DEFAULT_IN) — thiếu là sự cố 25/10"))
    return res


RULES = {
    "Core-SW1": core_rules, "Core-SW2": core_rules,
    "Brand-FW-S200": brandfw_rules, "Brand-FW-S300": brandfw_rules, "Brand-FW-S400": brandfw_rules,
    "Internet": internet_rules,
}
for _n in ("vEdge1-S100", "vEdge2-S100", "vEdge1-S200", "vEdge2-S200", "vEdge1-S300", "vEdge2-S300",
           "vEdge1-S400", "vEdge2-S400", "vEdge-S500"):
    RULES[_n] = vedge_rules


def render(device: str, results) -> str:
    bad = [d for ok, d in results if not ok]
    head = f"{'✅' if not bad else '❌'} {device}: {len(results) - len(bad)}/{len(results)} đạt"
    return "\n".join([head] + [f"   ❌ {d}" for d in bad])
