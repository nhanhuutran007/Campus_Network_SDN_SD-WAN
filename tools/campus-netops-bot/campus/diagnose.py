"""Chẩn đoán theo lớp: link → L2 → L3 → dịch vụ → overlay. Dừng ở lớp đầu tiên sai.

Mỗi lớp là một hàm thuần `parse(output) -> Check` (kiểm thử offline được); phần chạy lệnh
gom theo thiết bị để mỗi thiết bị chỉ mở console một lần. LLM chỉ tóm tắt kết quả, không đoán.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
ICON = {OK: "✅", WARN: "⚠️", FAIL: "❌", SKIP: "⏸"}


@dataclass
class Check:
    layer: str
    status: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    hint: str = ""


@dataclass
class Report:
    title: str
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        st = [c.status for c in self.checks]
        return FAIL if FAIL in st else WARN if WARN in st else OK

    def render(self, evidence: bool = True) -> str:
        out = [f"🩺 {self.title}"]
        for c in self.checks:
            out.append(f"{ICON[c.status]} {c.layer}: {c.summary}")
            if evidence and c.status in (FAIL, WARN):
                out += [f"     │ {e}" for e in c.evidence[:6]]
            if c.hint and c.status in (FAIL, WARN):
                out.append(f"     → {c.hint}")
        first = next((c for c in self.checks if c.status == FAIL), None)
        if first:
            out.append(f"\nKết luận: lỗi đầu tiên ở lớp **{first.layer}** — xử lý lớp này trước, các lớp sau phụ thuộc vào nó.")
        elif self.status == WARN:
            out.append("\nKết luận: hoạt động nhưng có cảnh báo (mất dự phòng hoặc lệch thiết kế) — xem các dòng ⚠️.")
        else:
            out.append("\nKết luận: mọi lớp đều bình thường.")
        return "\n".join(out)


def stop_after_fail(checks: list[Check], remaining: list[str]) -> list[Check]:
    return checks + [Check(r, SKIP, "chưa kiểm (dừng ở lớp lỗi đầu tiên)") for r in remaining]


# ------------------------------------------------------------------ vEdge
def vedge_interfaces(out: str) -> Check:
    blocks = re.findall(r"interface vpn 0 interface (\S+) af-type ipv4\n((?: .*\n?)+)", out)
    transport = []
    for name, body in blocks:
        f = dict(re.findall(r"^\s*(\S+)\s+(.*?)\s*$", body, re.M))
        if f.get("port-type") == "transport":
            transport.append((name, f.get("ip-address", "-"), f.get("if-admin-status"), f.get("if-oper-status")))
    ev = [f"{n} {ip} admin {a} / oper {o}" for n, ip, a, o in transport]
    up = [t for t in transport if t[2] == "Up" and t[3] == "Up"]
    if not transport:
        return Check("L1 Giao diện WAN", FAIL, "không thấy cổng transport nào trong VPN 0", ev,
                     "Kiểm `vpn 0 interface ... tunnel-interface` trong config.")
    if not up:
        return Check("L1 Giao diện WAN", FAIL, "mọi cổng transport đều down", ev,
                     "Kiểm link EVE / `no shutdown`; NIC ảo treo chiều nhận thì quét tx_dropped của tap.")
    if len(up) < len(transport):
        return Check("L1 Giao diện WAN", WARN, f"{len(up)}/{len(transport)} cổng transport up", ev)
    return Check("L1 Giao diện WAN", OK, ", ".join(f"{n} {ip} Up" for n, ip, _, _ in up), ev)


def vedge_bgp(out: str) -> Check:
    rows = re.findall(r"^(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s+.*?\s(\S+)\s*$", out, re.M)
    ev = [f"neighbor {ip} AS {asn} {st}" for ip, asn, st in rows]
    est = [r for r in rows if r[2] == "established"]
    if not rows:
        return Check("L3 Underlay BGP", FAIL, "không có BGP neighbor trong VPN 0", ev,
                     "Underlay CE–PE của đồ án là eBGP — kiểm `router bgp` trong vpn 0.")
    if not est:
        return Check("L3 Underlay BGP", FAIL, "không neighbor nào established", ev,
                     "Ping PE (IP .2 của /30), kiểm AS và filter trên router Internet/MPLS.")
    st = OK if len(est) == len(rows) else WARN
    return Check("L3 Underlay BGP", st, f"{len(est)}/{len(rows)} neighbor established", ev)


def vedge_default_route(out: str) -> Check:
    rows = [l.strip() for l in out.splitlines() if "0.0.0.0/0" in l]
    sel = [l for l in rows if re.search(r"\bF,S\b", l)]
    if not sel:
        return Check("L3 Default route VPN 0", FAIL, "không có default route được chọn", rows,
                     "Không có default thì không tới được vBond/vSmart — kiểm `default-originate` phía PE.")
    return Check("L3 Default route VPN 0", OK, re.sub(r"\s+", " ", sel[0])[:80], rows)


def vedge_control(out: str) -> Check:
    c = {k: int(v) for k, v in re.findall(r"(\w+)_counts\s+(\d+)", out)}
    ev = [f"{k}={v}" for k, v in c.items()]
    missing = [k for k in ("vsmart", "vmanage") if c.get(k, 0) == 0]
    if missing:
        return Check("Dịch vụ: Control connections", FAIL, "thiếu kết nối tới " + ", ".join(missing), ev,
                     "Xem `show control connections-history`: lỗi CRTVERFL/whitelist → kiểm cert và "
                     "`request vsmart-upload serial-file`; không thấy vBond → kiểm route tới 10.9.0.12.")
    return Check("Dịch vụ: Control connections", OK,
                 f"vSmart {c.get('vsmart', 0)}, vManage {c.get('vmanage', 0)}, vBond {c.get('vbond', 0)}", ev)


def vedge_omp(out: str) -> Check:
    rows = re.findall(r"^(\d+\.\d+\.\d+\.\d+)\s+vsmart\s+.*?\s(up|down|init\S*)\s+(\S+)\s+(\S+)\s*$", out, re.M)
    ev = [f"vSmart {ip} {st} R/I/S {ris}" for ip, st, _, ris in rows]
    if not rows or not any(r[1] == "up" for r in rows):
        return Check("Dịch vụ: OMP", FAIL, "không có OMP peer vSmart up", ev,
                     "Control đã up mà OMP down → kiểm `omp` và policy trên vSmart.")
    return Check("Dịch vụ: OMP", OK, "; ".join(ev))


def vedge_bfd(out: str) -> Check:
    rows = re.findall(r"^(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s+(up|down|init)\s+(\S+)\s+(\S+)", out, re.M)
    ev = [f"{ip} site {site} {st} {lc}→{rc}" for ip, site, st, lc, rc in rows]
    up = [r for r in rows if r[2] == "up"]
    if not rows:
        return Check("Overlay BFD", FAIL, "không có phiên BFD nào", ev,
                     "Kiểm màu TLOC (Internet=biz-internet, MPLS=mpls) và `show omp tlocs`.")
    if not up:
        return Check("Overlay BFD", FAIL, f"0/{len(rows)} phiên up", ev,
                     "Underlay thông mà BFD down: kiểm màu TLOC, IPsec, NIC ảo treo (tx_dropped tap).")
    if len(up) < len(rows):
        down = [e for e, r in zip(ev, rows) if r[2] != "up"]
        return Check("Overlay BFD", WARN, f"{len(up)}/{len(rows)} phiên up", down)
    return Check("Overlay BFD", OK, f"{len(up)}/{len(rows)} phiên up, tới site " +
                 ", ".join(sorted({r[1] for r in up})))


# (tên lớp, thiết bị — None = thiết bị đang chẩn đoán, lệnh, hàm phân tích)
VEDGE_STEPS = [
    ("L1 Giao diện WAN", None, "show interface vpn 0", vedge_interfaces),
    ("L3 Underlay BGP", None, "show bgp summary", vedge_bgp),
    ("L3 Default route VPN 0", None, "show ip route vpn 0 0.0.0.0/0", vedge_default_route),
    ("Dịch vụ: Control connections", None, "show control summary", vedge_control),
    ("Dịch vụ: OMP", None, "show omp peers", vedge_omp),
    ("Overlay BFD", None, "show bfd sessions", vedge_bfd),
]


def run_layers(title: str, outputs: list[str], steps) -> Report:
    """`outputs[i]` là output của `steps[i]`; None = chưa chạy (thiết bị không mở được)."""
    checks = []
    for i, (step, out) in enumerate(zip(steps, outputs)):
        c = step[3](out)
        checks.append(c)
        if c.status == FAIL:
            # lớp trên chưa đáng tin khi lớp dưới hỏng
            return Report(title, stop_after_fail(checks, [s[0] for s in steps[i + 1:]]))
    return Report(title, checks)


# ------------------------------------------------------------------ DHCP chi nhánh (Brand-FW)
def ios_trunk(out: str) -> Check:
    # "on 802.1q" = cấu hình tường minh; "auto/desirable n-802.1q" = DTP tự thoả thuận (vẫn chạy, lệch thiết kế)
    rows = re.findall(r"^(\S+)\s+(on|auto|desirable)\s+(n-)?802\.1q\s+trunking", out, re.M | re.I)
    if not rows:
        return Check("L2 Trunk SwitchBrand", FAIL, "không có cổng trunk 802.1q", out.splitlines()[:6],
                     "IOL: `switchport trunk encapsulation dot1q` phải đứng TRƯỚC `switchport mode trunk`.")
    dtp = [r[0] for r in rows if r[1].lower() != "on"]
    if dtp:
        return Check("L2 Trunk SwitchBrand", WARN, f"trunk {', '.join(r[0] for r in rows)} — {', '.join(dtp)} do DTP "
                     "tự thoả thuận", [l for l in out.splitlines() if "trunking" in l and l.split()[0] in dtp][:4],
                     "Thiết kế yêu cầu trunk tường minh: `switchport trunk encapsulation dot1q` + `switchport mode trunk` "
                     "(+ `switchport nonegotiate`) ở cả hai đầu.")
    return Check("L2 Trunk SwitchBrand", OK, "trunk: " + ", ".join(r[0] for r in rows))


def asa_gateways(site: str):
    def parse(out: str) -> Check:
        rows = re.findall(rf"^(\S+)\s+(10\.{site[0]}\.\d+\.1)\s+\S+\s+\S+\s+(up|down|administratively down)\s+(up|down)",
                          out, re.M)
        ev = [f"{n} {ip} {s}/{p}" for n, ip, s, p in rows]
        bad = [r for r in rows if r[2] != "up" or r[3] != "up"]
        if not rows:
            return Check("L3 Gateway Brand-FW", FAIL, f"không thấy gateway 10.{site[0]}.x.1", out.splitlines()[:8],
                         "Kiểm sub-interface VLAN và `nameif` trên Brand-FW.")
        if bad:
            return Check("L3 Gateway Brand-FW", FAIL, f"{len(bad)}/{len(rows)} gateway down", ev,
                         "Sub-interface down thường do cổng vật lý cha `shutdown` hoặc link EVE.")
        return Check("L3 Gateway Brand-FW", OK, ", ".join(f"{n} {ip}" for n, ip, _, _ in rows))
    return parse


def asa_dhcpd_state(out: str) -> Check:
    conf = re.findall(r"Interface (\S+), Configured for DHCP SERVER", out)
    if not conf:
        return Check("Dịch vụ: dhcpd", FAIL, "dhcpd chưa bật trên interface nào", out.splitlines()[:6],
                     "Thiếu `dhcpd address 10.x.y.100-10.x.y.199 <nameif>` + `dhcpd enable <nameif>`.")
    return Check("Dịch vụ: dhcpd", OK, "đang cấp trên " + ", ".join(conf))


def asa_dhcpd_binding(out: str) -> Check:
    leases = re.findall(r"^\s*(10\.\d+\.\d+\.\d+)\s+(\S+)", out, re.M)
    if not leases:
        return Check("Ứng dụng: lease", WARN, "chưa có lease nào", [],
                     "dhcpd bật mà không có lease → PC chưa xin (VPCS: `ip dhcp`) hoặc VLAN access sai trên SW.")
    return Check("Ứng dụng: lease", OK, f"{len(leases)} lease: " + ", ".join(l[0] for l in leases[:6]))


# ------------------------------------------------------------------ Chi nhánh qua SD-WAN (nhóm 2)
def sdwan_edges(site: str, rows: list[dict]) -> Check:
    """Hai vEdge của site theo vManage: cả hai mất = chi nhánh mất overlay; mất một = mất dự phòng."""
    layer = "SD-WAN: 2 vEdge (vManage)"
    edges = [r for r in rows if str(r.get("site-id")) == site and r.get("host-name", "").lower().startswith("vedge")]
    if not edges:
        return Check(layer, FAIL, f"vManage không có vEdge nào site-id {site}", [],
                     "vEdge chưa onboard hoặc sai `system site-id`.")
    ev = [f"{r.get('host-name')} {r.get('system-ip')} {r.get('reachability')} BFD "
          f"{r.get('bfdSessionsUp', '?')}/{r.get('bfdSessions', '?')}" for r in edges]
    up = [r for r in edges if r.get("reachability") == "reachable"]
    if not up:
        return Check(layer, FAIL, f"0/{len(edges)} vEdge reachable — chi nhánh mất overlay", ev,
                     "Chẩn đoán từng vEdge: /diag vEdge1-S" + site + " (lớp WAN/BGP/control).")
    bfd_down = [r for r in up if str(r.get("bfdSessionsUp")) in ("0", "None")]
    if len(up) < len(edges) or bfd_down:
        return Check(layer, WARN, f"{len(up)}/{len(edges)} vEdge reachable"
                     + (f", {len(bfd_down)} vEdge không có BFD up" if bfd_down else "") + " — mất dự phòng", ev,
                     "Chi nhánh còn chạy trên một vEdge; chẩn đoán vEdge lỗi bằng /diag <tên vEdge>.")
    return Check(layer, OK, "; ".join(ev))


TRACK_WAN = {"1": "outside1 → vEdge1", "2": "outside2 → vEdge2"}


def asa_tracks(out: str) -> Check:
    """`show track` của Brand-FW: track 1/2 (SLA monitor) quyết định route qua vEdge1/vEdge2."""
    layer = "WAN Brand-FW (track SLA)"
    rows = re.findall(r"^Track (\d+)\s*\n(?:.*\n)*?\s*Reachability is (Up|Down)", out, re.M)
    if not rows:
        return Check(layer, FAIL, "không có track SLA", out.splitlines()[:6],
                     "Brand-FW cần `sla monitor` + `track` cho 2 đường WAN (route ... track 1/2).")
    ev = [f"track {n} ({TRACK_WAN.get(n, '?')}): {st}" for n, st in rows]
    down = [n for n, st in rows if st != "Up"]
    if len(down) == len(rows):
        return Check(layer, FAIL, "mọi đường WAN của Brand-FW đều Down", ev,
                     "Kiểm link Brand-FW ↔ vEdge (outside1/outside2) và vEdge có route tới đích SLA.")
    if down:
        return Check(layer, WARN, f"{len(down)}/{len(rows)} đường WAN Down — đang chạy đường còn lại", ev,
                     "Route có `track` đã tự chuyển; kiểm vEdge phía đường Down.")
    return Check(layer, OK, ", ".join(ev))


def trunk(layer: str):
    """ios_trunk với tên lớp riêng (dùng cho từng switch truy cập)."""
    def parse(out: str) -> Check:
        c = ios_trunk(out)
        c.layer = layer
        return c
    return parse


# ------------------------------------------------------------------ DHCP Site 100 (Core + relay)
def core_svis(out: str) -> Check:
    rows = re.findall(r"^(Vlan(?:10|20|30|40))\s+(\S+)\s+\S+\s+\S+\s+(up|down|administratively down)\s+(up|down)",
                      out, re.M)
    ev = [f"{n} {ip} {s}/{p}" for n, ip, s, p in rows]
    bad = [r for r in rows if r[2] != "up" or r[3] != "up"]
    if len(rows) < 4 or bad:
        return Check("L3 SVI Core-SW1", FAIL, f"{len(rows) - len(bad)}/4 SVI VLAN 10–40 up", ev,
                     "SVI down = không còn cổng nào trong VLAN đó up → kiểm L2 phía OVS (Ryu).")
    return Check("L3 SVI Core-SW1", OK, ", ".join(f"{n} {ip}" for n, ip, _, _ in rows))


def core_helper(out: str) -> Check:
    n = len(re.findall(r"ip helper-address 10\.1\.90\.10", out))
    if n < 4:
        return Check("Dịch vụ: DHCP relay", FAIL, f"{n}/4 SVI có `ip helper-address 10.1.90.10`", [],
                     "Thêm `ip helper-address 10.1.90.10` vào SVI thiếu.")
    return Check("Dịch vụ: DHCP relay", OK, f"{n} SVI relay tới 10.1.90.10")


def ping_ok(layer: str, hint: str):
    def parse(out: str) -> Check:
        m = re.search(r"Success rate is (\d+) percent \((\d+)/(\d+)\)", out)
        if not m or m.group(1) == "0":
            return Check(layer, FAIL, "không ping được", out.strip().splitlines()[-2:], hint)
        st = OK if m.group(1) == "100" else WARN
        return Check(layer, st, f"{m.group(2)}/{m.group(3)} gói")
    return parse


# ------------------------------------------------------------------ SDN (Ryu /campus/health)
def sdn_report(h: dict) -> Report:
    sw = h.get("switches", [])
    conn = [s for s in sw if s.get("connected")]
    ev = [f"{s['name']}: {'kết nối' if s.get('connected') else 'MẤT'}; {s.get('mgmt_paths', 0)} đường VLAN 99"
          for s in sw]
    checks = []
    if len(conn) < len(sw) or not sw:
        checks.append(Check("Kênh điều khiển OpenFlow", FAIL, f"{len(conn)}/{len(sw)} OVS kết nối Ryu",
                            [e for e, s in zip(ev, sw) if not s.get("connected")],
                            "OVS mất controller giữ flow cũ (fail_mode secure). Kiểm VLAN 99 tới 10.1.99.10:6653."))
    else:
        checks.append(Check("Kênh điều khiển OpenFlow", OK, f"{len(conn)}/{len(sw)} OVS kết nối Ryu"))
    lu, lt = h.get("links_up", 0), h.get("links_total", 0)
    checks.append(Check("L2 Liên kết OVS", OK if lu == lt else FAIL, f"{lu}/{lt} link up",
                        [m for lvl, m in h.get("issues", []) if "Lien ket" in m],
                        "" if lu == lt else "Link chết: kiểm tap EVE và cổng OVS (`ovs-vsctl show`)."))
    one = [s["name"] for s in sw if s.get("mgmt_paths") == 1]
    zero = [s["name"] for s in sw if s.get("mgmt_paths") == 0]
    if zero:
        checks.append(Check("Dự phòng VLAN 99", FAIL, "không còn đường quản trị: " + ", ".join(zero)))
    elif one:
        checks.append(Check("Dự phòng VLAN 99", WARN, "chỉ còn 1 đường: " + ", ".join(one)))
    else:
        checks.append(Check("Dự phòng VLAN 99", OK, "mọi OVS có ≥ 2 đường quản trị"))
    c = h.get("controller", {})
    n, mx = c.get("stalls_1h", 0), c.get("stall_max_ms_1h", 0)
    checks.append(Check("Controller", WARN if n and mx > 3000 else OK,
                        f"khựng {n} lần/giờ, lâu nhất {mx / 1000:.1f} s; CPU {c.get('cpu_pct')}%",
                        hint="Khựng > 6 s làm OVS mất kết nối rồi nối lại; nguyên nhân thường do host dùng chung."))
    return Report("SDN Site 100 (Ryu)", checks)


# ------------------------------------------------------------------ vEdge qua API vManage (không SSH)
# Cùng các lớp như bản CLI; dữ liệu lấy từ /dataservice/device/*?deviceId=<system-ip>.
def api_interfaces(rows: list[dict]) -> Check:
    tr = [r for r in rows if str(r.get("vpn-id")) == "0" and r.get("port-type") == "transport"
          and r.get("af-type") == "ipv4"]
    ev = [f"{r.get('ifname')} {r.get('ip-address')} admin {r.get('if-admin-status')} / oper "
          f"{r.get('if-oper-status')} (rx-drops {r.get('rx-drops')})" for r in tr]
    up = [r for r in tr if r.get("if-admin-status") == "Up" and r.get("if-oper-status") == "Up"]
    name = "L1 Giao diện WAN"
    if not tr:
        return Check(name, FAIL, "vManage không thấy cổng transport nào", ev)
    if not up:
        return Check(name, FAIL, "mọi cổng transport đều down", ev,
                     "Kiểm link EVE / `no shutdown`; NIC ảo treo chiều nhận thì quét tx_dropped của tap.")
    if len(up) < len(tr):
        return Check(name, WARN, f"{len(up)}/{len(tr)} cổng transport up", ev)
    return Check(name, OK, ", ".join(f"{r.get('ifname')} {r.get('ip-address')} Up" for r in up), ev)


def api_bgp(rows: list[dict]) -> Check:
    rows = [r for r in rows if str(r.get("vpn-id")) == "0"]
    ev = [f"neighbor {r.get('peer-addr')} AS {r.get('as')} {r.get('state')}" for r in rows]
    est = [r for r in rows if r.get("state") == "established"]
    if not rows:
        return Check("L3 Underlay BGP", FAIL, "không có BGP neighbor trong VPN 0", ev,
                     "Underlay CE–PE của đồ án là eBGP — kiểm `router bgp` trong vpn 0.")
    if not est:
        return Check("L3 Underlay BGP", FAIL, "không neighbor nào established", ev,
                     "Ping PE (IP .2 của /30), kiểm AS và filter trên router Internet/MPLS.")
    return Check("L3 Underlay BGP", OK if len(est) == len(rows) else WARN,
                 f"{len(est)}/{len(rows)} neighbor established", ev)


def api_default_route(rows: list[dict]) -> Check:
    d = [r for r in rows if str(r.get("vpn-id")) == "0" and r.get("prefix") == "0.0.0.0/0"
         and "F" in str(r.get("rstatus", ""))]
    if not d:
        return Check("L3 Default route VPN 0", FAIL, "không có default route được chọn", [],
                     "Không có default thì không tới được vBond/vSmart — kiểm `default-originate` phía PE.")
    return Check("L3 Default route VPN 0", OK, "; ".join(
        f"{r.get('protocol')} via {r.get('nexthop-addr')} {r.get('nexthop-ifname')}" for r in d[:3]))


def api_control(rows: list[dict]) -> Check:
    up: dict[str, int] = {}
    for r in rows:
        if r.get("state") == "up":
            up[r.get("peer-type")] = up.get(r.get("peer-type"), 0) + 1
    ev = [f"{r.get('peer-type')} {r.get('system-ip')} {r.get('state')} qua {r.get('local-color')}" for r in rows]
    missing = [k for k in ("vsmart", "vmanage") if not up.get(k)]
    if missing:
        return Check("Dịch vụ: Control connections", FAIL, "thiếu kết nối tới " + ", ".join(missing), ev,
                     "Xem `show control connections-history`: lỗi CRTVERFL/whitelist → kiểm cert; không thấy "
                     "vBond → kiểm route tới 10.9.0.12.")
    return Check("Dịch vụ: Control connections", OK, f"vSmart {up.get('vsmart', 0)}, vManage {up.get('vmanage', 0)}", ev)


def api_omp(rows: list[dict]) -> Check:
    up = [r for r in rows if r.get("type") == "vsmart" and r.get("state") == "up"]
    ev = [f"vSmart {r.get('peer')} {r.get('state')}" for r in rows]
    if not up:
        return Check("Dịch vụ: OMP", FAIL, "không có OMP peer vSmart up", ev,
                     "Control đã up mà OMP down → kiểm `omp` và policy trên vSmart.")
    return Check("Dịch vụ: OMP", OK, "; ".join(ev))


def api_bfd(rows: list[dict]) -> Check:
    ev = [f"{r.get('system-ip')} site {r.get('site-id')} {r.get('state')} {r.get('local-color')}→{r.get('color')}"
          for r in rows]
    up = [r for r in rows if r.get("state") == "up"]
    if not rows:
        return Check("Overlay BFD", FAIL, "không có phiên BFD nào", ev,
                     "Kiểm màu TLOC (Internet=biz-internet, MPLS=mpls) và `show omp tlocs`.")
    if not up:
        return Check("Overlay BFD", FAIL, f"0/{len(rows)} phiên up", ev,
                     "Underlay thông mà BFD down: kiểm màu TLOC, IPsec, NIC ảo treo (tx_dropped tap).")
    if len(up) < len(rows):
        return Check("Overlay BFD", WARN, f"{len(up)}/{len(rows)} phiên up",
                     [e for e, r in zip(ev, rows) if r.get("state") != "up"])
    return Check("Overlay BFD", OK, f"{len(up)}/{len(rows)} phiên up, tới site "
                 + ", ".join(sorted({str(r.get('site-id')) for r in up})))


# (tên lớp, đường dẫn API, hàm phân tích)
VEDGE_API_STEPS = [
    ("L1 Giao diện WAN", "/dataservice/device/interface", api_interfaces),
    ("L3 Underlay BGP", "/dataservice/device/bgp/neighbors", api_bgp),
    ("L3 Default route VPN 0", "/dataservice/device/ip/routetable", api_default_route),
    ("Dịch vụ: Control connections", "/dataservice/device/control/connections", api_control),
    ("Dịch vụ: OMP", "/dataservice/device/omp/peers", api_omp),
    ("Overlay BFD", "/dataservice/device/bfd/sessions", api_bfd),
]


# ------------------------------------------------------------------ FW-ASAv HA (SSH in-band, chỉ đọc)
def asa_failover(out: str) -> Check:
    me = re.search(r"This host:\s*(\w+)\s*-\s*([\w ]+?)\s*$", out, re.M)
    peer = re.search(r"Other host:\s*(\w+)\s*-\s*([\w ]+?)\s*$", out, re.M)
    ev = [l.strip() for l in out.splitlines() if "host:" in l]
    if not me:
        return Check("HA Failover", FAIL, "không đọc được trạng thái failover", ev)
    if not peer or "Standby Ready" not in peer.group(2):
        return Check("HA Failover", WARN, f"unit này {me.group(2)}, unit kia "
                     f"{peer.group(2) if peer else 'không thấy'} — mất dự phòng", ev,
                     "Kiểm link failover Gi0/5 (10.1.255.0/29) và unit Standby có đang chạy.")
    return Check("HA Failover", OK, f"{me.group(1)} {me.group(2)} / {peer.group(1)} {peer.group(2)}")


def asa_interfaces(out: str) -> Check:
    rows = re.findall(r"^(GigabitEthernet\S+|Management\S+)\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+\S+\s+"
                      r"(up|down|administratively down)\s+(up|down)", out, re.M)
    bad = [f"{n} {ip} {s}/{p}" for n, ip, s, p in rows if s != "up" or p != "up"]
    if not rows:
        return Check("L1/L2 Interface", FAIL, "không có interface nào có IP", out.splitlines()[:6])
    if bad:
        return Check("L1/L2 Interface", FAIL, f"{len(bad)}/{len(rows)} interface có IP bị down", bad)
    return Check("L1/L2 Interface", OK, f"{len(rows)}/{len(rows)} interface có IP up")


def asa_ospf(out: str) -> Check:
    rows = re.findall(r"^(\d+\.\d+\.\d+\.\d+)\s+\d+\s+(\S+)\s+\S+\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)", out, re.M)
    full = [r for r in rows if r[1].startswith("FULL")]
    ev = [f"{r[0]} {r[1]} qua {r[3]}" for r in rows]
    if len(full) < 2:
        return Check("L3 OSPF với Core", FAIL if not full else WARN, f"{len(full)}/2 neighbor FULL", ev,
                     "Mất neighbor Core-SW1/2 → kiểm link inside/inside2 và `network` OSPF.")
    return Check("L3 OSPF với Core", OK, "; ".join(ev))


def asa_default(out: str) -> Check:
    m = re.search(r"Gateway of last resort is (\S+) to network 0\.0\.0\.0", out)
    if not m:
        return Check("L3 Default route", FAIL, "không có default route", [],
                     "FW-ASAv cần default về vEdge Site 100 (outside 10.1.3.2 / outside2).")
    return Check("L3 Default route", OK, f"qua {m.group(1)}")


def asp_counts(out: str) -> dict[str, int]:
    return {k: int(n) for _, k, n in re.findall(r"^\s*(.+?)\s+\((\S+)\)\s+(\d+)\s*$", out, re.M)}


def asa_asp_drop(out: str, prev: dict[str, int] | None = None) -> Check:
    """Bộ đếm asp drop là tích luỹ → chỉ cảnh báo khi TĂNG so với lần đọc trước (prev)."""
    name = "Dịch vụ: gói bị huỷ (asp drop)"
    cur = asp_counts(out)
    if prev is None:
        top = sorted(cur.items(), key=lambda kv: -kv[1])[:3]
        return Check(name, OK, "đã ghi mốc bộ đếm (tích luỹ: " + (", ".join(f"{k} {n}" for k, n in top) or "0")
                     + ") — lần chẩn đoán sau sẽ báo phần tăng thêm")
    delta = {k: n - prev.get(k, 0) for k, n in cur.items() if n - prev.get(k, 0) > 0}
    ev = [f"{k}: +{n}" for k, n in sorted(delta.items(), key=lambda kv: -kv[1])[:5]]
    if delta.get("no-adjacency"):
        return Check(name, WARN, f"no-adjacency tăng +{delta['no-adjacency']} — dấu hiệu định tuyến bất đối xứng", ev,
                     "ASA không ECMP khác interface: kiểm route chiều về các VLAN có trỏ cùng Core với master VRRP.")
    return Check(name, OK, "tăng từ lần trước: " + (", ".join(ev[:3]) or "không có"))


ASA_STEPS = [
    ("HA Failover", None, "show failover | include host:", asa_failover),
    ("L1/L2 Interface", None, "show interface ip brief", asa_interfaces),
    ("L3 OSPF với Core", None, "show ospf neighbor", asa_ospf),
    ("L3 Default route", None, "show route | include Gateway of last resort", asa_default),
    ("Dịch vụ: gói bị huỷ (asp drop)", None, "show asp drop", asa_asp_drop),
]


# ------------------------------------------------------------------ DHCP-Server (đọc tại chỗ trên node 72)
def dhcp_scopes(scopes: list[dict]) -> Check:
    ev = [f"{s.get('ScopeId')}: dùng {s.get('InUse')}/{int(s.get('InUse', 0)) + int(s.get('Free', 0))} "
          f"({float(s.get('PercentageInUse', 0)):.0f}%)" for s in scopes]
    name = "Ứng dụng: scope trên DHCP-Server"
    if not scopes:
        return Check(name, FAIL, "không có scope nào", [], "Kiểm role DHCP và 4 scope VLAN 10/20/30/40 trên node 72.")
    full = [s for s in scopes if int(s.get("Free", 0)) == 0]
    if full:
        return Check(name, FAIL, f"{len(full)} scope HẾT địa chỉ", ev,
                     "Pool .100–.199 đã cạn: xoá lease cũ hoặc giảm thời hạn lease.")
    return Check(name, OK, f"{len(scopes)} scope, đã cấp {sum(int(s.get('InUse', 0)) for s in scopes)} địa chỉ", ev)
