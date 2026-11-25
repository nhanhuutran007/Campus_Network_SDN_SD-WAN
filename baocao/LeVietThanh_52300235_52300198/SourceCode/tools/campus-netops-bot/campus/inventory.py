"""Danh mục thiết bị Campus (nguồn: `Campus Network SDN SD-WAN.unl` + bảng node-id của đồ án).

Tên trong `.unl` trùng nhau (nhiều `vEdge1`, `SW`, `Brand-FW`) nên bot dùng tên duy nhất
theo site; node-id là khoá thật. `verify_against_unl()` đối chiếu bảng này với file `.unl`.

platform:
  ios     IOS/IOL (switch/router)        — đọc qua console, enable không mật khẩu
  vios    vIOS router (Internet/MPLS)    — như ios
  asa     ASAv (FW HA, Brand-FW)         — enable bằng mật khẩu
  viptela vEdge/vManage/vSmart/vBond     — đăng nhập admin ở console
  khác    ovs/linux/vpcs/windows         — chỉ liệt kê, GĐ1 chưa điều khiển
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MANAGED = {"ios", "vios", "asa", "viptela"}


@dataclass(frozen=True)
class Device:
    name: str
    node_id: int
    site: str
    role: str
    platform: str
    cred_tag: str = ""          # khoá dòng trong file credentials (không phải mật khẩu)
    unl_name: str = ""          # tên node trong .unl (để đối chiếu)
    aliases: tuple = field(default_factory=tuple)
    note: str = ""
    mgmt_ip: str = ""           # IP quản trị in-band (SSH từ NetOps-Server); rỗng = ngoài phạm vi SSH
    mgmt_alt: str = ""          # IP dự phòng khi đường chính không tới được (Brand-FW: outside2 qua vEdge2)

    @property
    def managed(self) -> bool:
        return self.platform in MANAGED


FW = "FW-ASAv 1, 2"
VE100 = "vEdge Site 100"
VEBR = "vEdge chi nhánh"

_D = Device
DEVICES: list[Device] = [
    # --- Site 100: Campus chính ---
    # FW: SSH vào Management0/0 (management-only, VLAN 99) — chỉ đọc (ASA chưa có rollback tự động)
    _D("FW-ASAv-Active", 1, "100", "firewall", "asa", FW, "FW-ASAv-Active", ("fw1", "fw-active"), mgmt_ip="10.1.99.33"),
    _D("FW-ASAv-Standby", 2, "100", "firewall", "asa", FW, "FW-ASAv-Standby", ("fw2", "fw-standby"), mgmt_ip="10.1.99.34"),
    # mgmt_ip: Core dùng SVI Vlan90 (Vlan99 của Core-SW2 shutdown có chủ đích); switch phụ dùng VLAN 99
    _D("Core-SW1", 3, "100", "core", "ios", "", "Core-SW1", ("core1",), mgmt_ip="10.1.90.2"),
    _D("Core-SW2", 4, "100", "core", "ios", "", "Core-SW2", ("core2",), mgmt_ip="10.1.90.3"),
    # SwitchDMZ chỉ nối cổng DMZ của FW (VLAN 101), không có VLAN 99 về Core → chỉ quản trị ngoài băng (console)
    _D("SwitchDMZ", 7, "100", "dmz", "ios", "", "SwitchDMZ", ("dmz",)),
    _D("SwitchServerFarm", 24, "100", "server-farm", "ios", "", "SwitchServerFarm", ("farm",), mgmt_ip="10.1.99.32"),
    _D("vEdge1-S100", 28, "100", "vedge", "viptela", VE100, "vEdge1"),
    _D("vEdge2-S100", 6, "100", "vedge", "viptela", VE100, "vEdge2"),
    _D("Dist-SW1", 5, "100", "distribution", "ovs", "", "Dist-SW1"),
    _D("Dist-SW2", 8, "100", "distribution", "ovs", "", "Dist-SW2"),
    _D("Access-SW1", 68, "100", "access", "ovs", "", "Access-SW1"),
    _D("Access-SW2", 66, "100", "access", "ovs", "", "Access-SW2"),
    _D("Access-SW3", 70, "100", "access", "ovs", "", "Access-SW3"),
    _D("Access-SW4", 69, "100", "access", "ovs", "", "Access-SW4"),
    _D("SDN_CONTROLLER", 9, "100", "sdn-controller", "linux", "", "SDN_CONTROLLER", ("ryu",)),
    _D("DHCP-Server", 72, "100", "server", "windows", "", "DHCP-Server"),
    _D("Mail-Server", 13, "100", "server", "windows", "", "Mail-Server"),
    _D("Web-Server", 22, "100", "server", "linux", "", "Web-Server"),
    _D("Syslog-Server", 25, "100", "server", "windows", "", "Syslog-Server"),
    _D("PC-Management", 73, "100", "pc", "windows", "", "PC-Management"),
    # --- Site 200 Cần Thơ / 300 Đà Nẵng / 400 Nha Trang ---
    # Nhóm 2 (30/10): quản trị in-band qua overlay SD-WAN (VPN 1). Brand-FW: SSH vào outside1 (route về 10/8 đi
    # outside1 → vEdge1, ASA trả gói quản trị ra đúng cổng nhận) và outside2 dự phòng; switch: SVI VLAN 99.
    _D("Brand-FW-S200", 37, "200", "firewall", "asa", FW, "Brand-FW", mgmt_ip="10.2.1.1", mgmt_alt="10.2.1.5"),
    _D("Brand-FW-S300", 39, "300", "firewall", "asa", FW, "Brand-FW", mgmt_ip="10.3.1.1", mgmt_alt="10.3.1.5"),
    _D("Brand-FW-S400", 38, "400", "firewall", "asa", FW, "Brand-FW", mgmt_ip="10.4.1.1", mgmt_alt="10.4.1.5"),
    _D("SwitchBrand-S200", 63, "200", "switch", "ios", "", "SwitchBrand", mgmt_ip="10.2.99.2"),
    _D("SwitchBrand-S300", 62, "300", "switch", "ios", "", "SwitchBrand", mgmt_ip="10.3.99.2"),
    _D("SwitchBrand-S400", 75, "400", "switch", "ios", "", "SwitchBrand", mgmt_ip="10.4.99.2"),   # server 25/10: id 75 (repo .unl cũ: 64)
    _D("SW-S200-1", 55, "200", "switch", "ios", "", "SW", mgmt_ip="10.2.99.11"),
    _D("SW-S200-2", 56, "200", "switch", "ios", "", "SW", mgmt_ip="10.2.99.12"),
    _D("SW-S300-1", 58, "300", "switch", "ios", "", "SW", mgmt_ip="10.3.99.11"),
    _D("SW-S300-2", 59, "300", "switch", "ios", "", "SW", mgmt_ip="10.3.99.12"),
    _D("SW-S400-1", 57, "400", "switch", "ios", "", "SW", mgmt_ip="10.4.99.12"),
    _D("SW-S400-2", 60, "400", "switch", "ios", "", "SW", mgmt_ip="10.4.99.11"),
    _D("vEdge1-S200", 29, "200", "vedge", "viptela", VEBR, "vEdge1"),
    _D("vEdge2-S200", 42, "200", "vedge", "viptela", VEBR, "vEdge2"),
    _D("vEdge1-S300", 30, "300", "vedge", "viptela", VEBR, "vEdge1"),
    _D("vEdge2-S300", 40, "300", "vedge", "viptela", VEBR, "vEdge2"),
    _D("vEdge1-S400", 31, "400", "vedge", "viptela", VEBR, "vEdge1"),
    _D("vEdge2-S400", 41, "400", "vedge", "viptela", VEBR, "vEdge2"),
    # --- Site 500 ---
    _D("vEdge-S500", 65, "500", "vedge", "viptela", VEBR, "vEdge", ("vedge65",),
       note="mật khẩu chưa chắc khớp nhóm vEdge chi nhánh"),
    _D("SW-S500", 10, "500", "switch", "ios", "", "SW-S500"),
    # --- Site 900: SD-WAN controller ---
    _D("vManage", 33, "900", "sdwan-controller", "viptela", "vManager (33)", "vManager", ("vmanager",)),
    _D("vSmart", 34, "900", "sdwan-controller", "viptela", "vSmart (34)", "vSmart"),
    _D("vBond", 35, "900", "sdwan-controller", "viptela", "vBond (35)", "vBond"),
    _D("Switch32", 32, "900", "switch", "ios", "", "Switch"),
    _D("Switch61", 61, "900", "switch", "ios", "", "SW"),
    # --- Nhà cung cấp ---
    _D("Internet", 26, "SP", "provider", "vios", "", "Internet", ("isp",)),
    _D("MPLS", 27, "SP", "provider", "vios", "", "MPLS"),
]

BY_ID = {d.node_id: d for d in DEVICES}
_NODE_RE = re.compile(r"^(?:node\s*|id\s*)?(\d{1,3})$", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[\s_]+", "-", s.strip().lower())


def resolve(query: str) -> Device | None:
    """Tìm thiết bị theo tên, alias, hoặc node-id ("29", "node 29")."""
    q = query.strip()
    m = _NODE_RE.match(q)
    if m:
        return BY_ID.get(int(m.group(1)))
    n = _norm(q)
    for d in DEVICES:
        if n == _norm(d.name) or n in (_norm(a) for a in d.aliases):
            return d
    return None


def by_site(site: str | None = None) -> list[Device]:
    if not site:
        return list(DEVICES)
    s = site.strip().upper().removeprefix("SITE").strip()
    return [d for d in DEVICES if d.site == s]


def verify_against_unl(unl_path: str) -> list[str]:
    """Trả về danh sách lỗi (rỗng = khớp): id phải tồn tại, tên và template .unl phải đúng."""
    with open(unl_path, encoding="utf-8") as f:
        text = f.read()
    nodes = {int(i): (n, t) for i, n, t in
             re.findall(r'<node id="(\d+)" name="([^"]*)"[^>]*?template="([^"]*)"', text)}
    errors = []
    for d in DEVICES:
        if d.node_id not in nodes:
            errors.append(f"{d.name}: node {d.node_id} không có trong .unl")
            continue
        name, template = nodes[d.node_id]
        if d.unl_name and name != d.unl_name:
            errors.append(f"{d.name}: .unl đặt tên node {d.node_id} là '{name}', bảng ghi '{d.unl_name}'")
        if template not in _TEMPLATES[d.platform]:
            errors.append(f"{d.name}: template .unl '{template}' không hợp platform '{d.platform}'")
    return errors


_TEMPLATES = {
    "ios": {"iol"}, "vios": {"vios"}, "asa": {"asav"},
    "viptela": {"vtedge", "vtmgmt", "vtsmart", "vtbond"},
    "ovs": {"linux"}, "linux": {"linux"}, "windows": {"win", "winserver"},
}
