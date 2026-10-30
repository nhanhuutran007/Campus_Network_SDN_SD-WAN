"""Ảnh chụp sức khoẻ thiết bị trước/sau thay đổi cấu hình.

So sánh theo nguyên tắc "không được mất": mọi interface up/up, BGP neighbor established,
OSPF neighbor FULL, VRRP state, control connection, phiên BFD có trước thay đổi phải còn
sau thay đổi. Thứ mới xuất hiện (Loopback mới, neighbor mới) không tính là lỗi.
"""
from __future__ import annotations

import re

# lệnh chụp theo nền tảng; Viptela chạy được cả trong config mode nhờ tiền tố "do "
SNAPSHOT_CMDS = {
    "ios": ["show ip interface brief", "show ip bgp summary", "show ip ospf neighbor", "show vrrp brief"],
    "viptela": ["show interface vpn 0", "show bgp summary", "show control summary", "show bfd sessions"],
}
SNAPSHOT_CMDS["vios"] = SNAPSHOT_CMDS["ios"]


def _ios(outs: list[str]) -> dict[str, set]:
    brief, bgp, ospf, vrrp = outs
    return {
        "interface up/up": {m.group(1) for m in re.finditer(
            r"^(\S+)\s+\S+\s+\S+\s+\S+\s+up\s+up\s*$", brief, re.M)},
        "BGP established": {m.group(1) for m in re.finditer(
            r"^(\d+\.\d+\.\d+\.\d+)\s+4\s+\d+\s+.*?\s(\d+)\s*$", bgp, re.M)},
        "OSPF FULL": {m.group(1) for m in re.finditer(r"^(\d+\.\d+\.\d+\.\d+)\s+\d+\s+FULL", ospf, re.M)},
        "VRRP": {f"{m.group(1)} grp {m.group(2)} {m.group(3)}" for m in re.finditer(
            r"^(\S+)\s+(\d+)\s+\d+\s+\d+\s.*?\b(Master|Backup)\b", vrrp, re.M)},
    }


def _viptela(outs: list[str]) -> dict[str, set]:
    iface, bgp, control, bfd = outs
    transport_up = set()
    for name, body in re.findall(r"interface vpn 0 interface (\S+) af-type ipv4\n((?: .*\n?)+)", iface):
        f = dict(re.findall(r"^\s*(\S+)\s+(.*?)\s*$", body, re.M))
        if f.get("port-type") == "transport" and f.get("if-oper-status") == "Up":
            transport_up.add(name)
    counts = {k: int(v) for k, v in re.findall(r"(\w+)_counts\s+(\d+)", control)}
    return {
        "transport up": transport_up,
        "BGP established": {m.group(1) for m in re.finditer(
            r"^(\d+\.\d+\.\d+\.\d+)\s+\d+\s+.*\sestablished\s*$", bgp, re.M)},
        "control": {f"{k}#{i}" for k in ("vsmart", "vmanage") for i in range(counts.get(k, 0))},
        "BFD up": {f"{m.group(1)} {m.group(2)}->{m.group(3)}" for m in re.finditer(
            r"^(\d+\.\d+\.\d+\.\d+)\s+\d+\s+up\s+(\S+)\s+(\S+)", bfd, re.M)},
    }


def parse(platform: str, outs: list[str]) -> dict[str, set]:
    return _viptela(outs) if platform == "viptela" else _ios(outs)


def compare(before: dict[str, set], after: dict[str, set]) -> list[str]:
    """Danh sách thứ đã MẤT sau thay đổi (rỗng = đạt)."""
    lost = []
    for k, items in before.items():
        for x in sorted(items - after.get(k, set())):
            lost.append(f"{k}: {x}")
    return lost


def summary(snap: dict[str, set]) -> str:
    return ", ".join(f"{k} {len(v)}" for k, v in snap.items())
