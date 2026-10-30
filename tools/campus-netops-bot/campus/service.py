"""API mức cao dùng chung cho LangGraph agent, MCP server và Telegram bot.

Mọi hàm trả `Result(ok, text)` — trạng thái lỗi đi theo cờ `ok`, không đoán từ chữ
"error" trong output (output `show interfaces` luôn có "0 input errors").
"""
from __future__ import annotations

import datetime
import logging
import os
import re
import time
from dataclasses import dataclass

from . import compliance as cp
from . import diagnose as dg
from . import dhcp_local, drift, guard, inventory
from .change import ChangeError, ChangeManager
from .console import ConsoleError, EveConsole, SshTransport
from .credentials import CredentialError
from .labapi import LabApiError, Ryu, VManage, alarm_target, is_recovery
from .redact import redact

log = logging.getLogger(__name__)
MAX_OUTPUT = 15000

_console: EveConsole | None = None


def console():
    """NETOPS_TRANSPORT=ssh: in-band qua IP quản trị (NetOps-Server trong topo).
    Mặc định console: qua console EVE (công cụ của người quản trị lab, ngoài băng)."""
    global _console
    if _console is None:
        _console = SshTransport() if os.getenv("NETOPS_TRANSPORT") == "ssh" else EveConsole()
    return _console


def in_scope(dev) -> bool:
    """Thiết bị NetOps quản lý được với transport hiện tại."""
    if not dev.managed:
        return False
    return bool(dev.mgmt_ip) if os.getenv("NETOPS_TRANSPORT") == "ssh" else True


@dataclass
class Result:
    ok: bool
    text: str

    def __str__(self):
        return self.text if self.ok else f"LỖI: {self.text}"


def list_devices(site: str | None = None) -> Result:
    devs = inventory.by_site(site)
    if not devs:
        return Result(False, f"Không có thiết bị nào ở site '{site}'. Site hợp lệ: 100, 200, 300, 400, 500, 900, SP.")
    rows = [f"{d.name:<18} node {d.node_id:<3} site {d.site:<4} {d.role:<16} {d.platform}"
            + (f"  {d.mgmt_ip}" if d.mgmt_ip else "")
            + ("" if in_scope(d) else "  (ngoài phạm vi)") for d in devs]
    return Result(True, "\n".join(rows))


def _resolve(name: str):
    dev = inventory.resolve(name)
    if dev is None:
        return None, Result(False, f"Không tìm thấy thiết bị '{name}'. Gọi list_devices để xem tên đúng.")
    if not in_scope(dev):
        return None, Result(False, f"{dev.name} ({dev.platform}) ngoài phạm vi quản lý của bot"
                                   + (" — NetOps-Server chỉ quản lý thiết bị có SSH in-band." if dev.managed else "."))
    return dev, None


def run_command(device: str, command: str) -> Result:
    """Chạy một lệnh chỉ-đọc (show/ping/traceroute) trên thiết bị theo tên hoặc node-id."""
    dev, err = _resolve(device)
    if err:
        return err
    ok, cmd = guard.check(dev.platform, command)
    if not ok:
        return Result(False, cmd)
    log.info("run %s (node %s): %s", dev.name, dev.node_id, cmd)
    try:
        out = console().run(dev, [cmd])[0]
    except (ConsoleError, CredentialError) as e:
        return Result(False, str(e))
    out = redact(out)
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n[!] Output dài {len(out)} ký tự, đã cắt — dùng '| include' để lọc."
    return Result(True, f"[{dev.name} / node {dev.node_id}] {cmd}\n{out}")


def ping(device: str, target: str, vpn: str | None = None) -> Result:
    """Ping từ thiết bị. `vpn` = VPN Viptela hoặc VRF IOS (tuỳ chọn)."""
    dev, err = _resolve(device)
    if err:
        return err
    cmd = f"ping {target}"
    if vpn:
        cmd = f"ping vpn {vpn} {target}" if dev.platform == "viptela" else f"ping vrf {vpn} {target}"
    return run_command(dev.name, cmd)


# ======================================================================== Giai đoạn 2: REST + chẩn đoán

_vmanage: VManage | None = None
_ryu: Ryu | None = None


def vmanage() -> VManage:
    global _vmanage
    if _vmanage is None:
        _vmanage = VManage(console())
    return _vmanage


def ryu() -> Ryu:
    global _ryu
    if _ryu is None:
        _ryu = Ryu(console())
    return _ryu


def _execute(title: str, steps, default_device: str | None = None) -> dg.Report:
    """Chạy các bước theo thứ tự, gom lệnh liên tiếp cùng thiết bị vào một phiên console.
    Dừng ở lớp lỗi đầu tiên; thiết bị không mở được console = lớp đó FAIL."""
    checks: list[dg.Check] = []
    i = 0
    while i < len(steps):
        dev_name = steps[i][1] or default_device
        j = i
        while j < len(steps) and (steps[j][1] or default_device) == dev_name:
            j += 1
        group = steps[i:j]
        dev = inventory.resolve(dev_name)
        try:
            outs = console().run(dev, [s[2] for s in group])
        except (ConsoleError, CredentialError) as e:
            checks.append(dg.Check(group[0][0], dg.FAIL, f"không vào được {dev.name}: {e}"))
            return dg.Report(title, dg.stop_after_fail(checks, [s[0] for s in steps[i + 1:]]))
        for k, (step, out) in enumerate(zip(group, outs)):
            c = step[3](out)
            c.evidence = [redact(e) for e in c.evidence]
            checks.append(c)
            if c.status == dg.FAIL:
                return dg.Report(title, dg.stop_after_fail(checks, [s[0] for s in steps[i + k + 1:]]))
        i = j
    return dg.Report(title, checks)


def diagnose_vedge(device: str) -> Result:
    dev = inventory.resolve(device)
    if dev is None or dev.role != "vedge":
        return Result(False, f"'{device}' không phải vEdge. Dùng list_devices để xem tên vEdge.")
    title = f"Chẩn đoán {dev.name} (node {dev.node_id}, site {dev.site})"
    if in_scope(dev):
        return Result(True, _execute(title, dg.VEDGE_STEPS, dev.name).render())
    # Ngoài phạm vi SSH (NetOps-Server trong topo) → đọc qua API vManage, như vận hành SD-WAN ngoài đời
    try:
        info = _vm_device(dev.name)
        if not info:
            return Result(False, f"vManage không có thiết bị host-name '{dev.name}'.")
        sid = info.get("system-ip")
        if info.get("reachability") != "reachable":
            rep = dg.Report(title + " — qua vManage API", dg.stop_after_fail(
                [dg.Check("Quản lý: vManage ↔ thiết bị", dg.FAIL, f"vManage báo {info.get('reachability')} "
                          f"(system-ip {sid}) — không lấy được dữ liệu realtime",
                          hint="Node tắt, hoặc mất control connection: kiểm console vEdge, cổng WAN, "
                               "route tới vBond 10.9.0.12, chứng chỉ/whitelist.")],
                [s[0] for s in dg.VEDGE_API_STEPS]))
            return Result(True, rep.render())
        checks = []
        for i, (layer, path, parse) in enumerate(dg.VEDGE_API_STEPS):
            c = parse(vmanage().device_data(path, sid))
            c.evidence = [redact(e) for e in c.evidence]
            checks.append(c)
            if c.status == dg.FAIL:
                checks = dg.stop_after_fail(checks, [s[0] for s in dg.VEDGE_API_STEPS[i + 1:]])
                break
    except (LabApiError, CredentialError) as e:
        return Result(False, f"Không đọc được {dev.name} qua vManage: {e}")
    return Result(True, dg.Report(title + f" — qua vManage API, system-ip {sid}", checks).render())


_vm_cache: dict = {"ts": 0.0, "map": {}}


def _vm_device(host: str) -> dict | None:
    """Bản ghi thiết bị trong vManage theo host-name (system-ip, reachability); cache 60 s."""
    if time.time() - _vm_cache["ts"] > 60:
        _vm_cache["map"] = {d.get("host-name", "").lower(): d for d in vmanage().devices()}
        _vm_cache["ts"] = time.time()
    return _vm_cache["map"].get(host.lower())


def diagnose_fw(device: str = "FW-ASAv-Active") -> Result:
    dev = inventory.resolve(device)
    if dev is None or dev.platform != "asa" or dev.site != "100":
        return Result(False, "Chẩn đoán FW hỗ trợ FW-ASAv-Active / FW-ASAv-Standby.")
    if not in_scope(dev):
        return Result(False, f"{dev.name} ngoài phạm vi quản lý của bot.")
    prev = _asp_prev.get(dev.name)

    def asp(out: str):
        _asp_prev[dev.name] = dg.asp_counts(out)
        return dg.asa_asp_drop(out, prev)

    steps = [s if s[3] is not dg.asa_asp_drop else (s[0], s[1], s[2], asp) for s in dg.ASA_STEPS]
    return Result(True, _execute(f"Chẩn đoán {dev.name} (HA, interface, OSPF, default, asp drop)",
                                 steps, dev.name).render())


_asp_prev: dict[str, dict[str, int]] = {}


def dhcp_status(scope: str | None = None) -> Result:
    """Scope/lease trên DHCP-Server — chỉ khi bot chạy ngay trên node 72."""
    if not dhcp_local.available():
        return Result(False, "Máy chạy bot không phải DHCP-Server (không có module PowerShell DhcpServer).")
    try:
        if scope:
            ls = dhcp_local.leases(scope)
            rows = [f"{x.get('IP'):<15} {str(x.get('HostName') or '-'):<22} {x.get('ClientId')}  hết hạn {x.get('Expiry')}"
                    for x in ls]
            return Result(True, f"Lease scope {scope}: {len(ls)}\n" + "\n".join(rows))
        return Result(True, dg.Report("DHCP-Server 10.1.90.10", [dg.dhcp_scopes(dhcp_local.scopes())]).render())
    except dhcp_local.DhcpError as e:
        return Result(False, str(e))


BRANCH = {"200": ("Brand-FW-S200", "SwitchBrand-S200"),
          "300": ("Brand-FW-S300", "SwitchBrand-S300"),
          "400": ("Brand-FW-S400", "SwitchBrand-S400")}


def diagnose_dhcp(site: str) -> Result:
    s = site.strip().upper().removeprefix("SITE").strip()
    if s in BRANCH:
        fw, sw = BRANCH[s]
        steps = [
            ("L2 Trunk SwitchBrand", sw, "show interfaces trunk", dg.ios_trunk),
            ("L3 Gateway Brand-FW", fw, "show interface ip brief", dg.asa_gateways(s)),
            ("Dịch vụ: dhcpd", fw, "show dhcpd state", dg.asa_dhcpd_state),
            ("Ứng dụng: lease", fw, "show dhcpd binding", dg.asa_dhcpd_binding),
        ]
        return Result(True, _execute(f"Chẩn đoán DHCP Site {s} (Brand-FW làm DHCP server)", steps).render())
    if s == "100":
        title = "Chẩn đoán DHCP Site 100 (OVS/Ryu → Core-SW1 relay → DHCP-Server 10.1.90.10)"
        try:
            sdn = dg.sdn_report(ryu().health())
            l2 = sdn.checks[:2]
        except LabApiError as e:
            l2 = [dg.Check("L2 SDN (Ryu)", dg.WARN, f"không đọc được Ryu: {e}")]
        if any(c.status == dg.FAIL for c in l2):
            rest = ["L3 SVI Core-SW1", "Dịch vụ: DHCP relay", "Dịch vụ: tới DHCP-Server"]
            return Result(True, dg.Report(title, dg.stop_after_fail(l2, rest)).render())
        steps = [
            ("L3 SVI Core-SW1", "Core-SW1", "show ip interface brief | include Vlan", dg.core_svis),
            ("Dịch vụ: DHCP relay", "Core-SW1", "show running-config | include helper-address", dg.core_helper),
            ("Dịch vụ: tới DHCP-Server", "Core-SW1", "ping 10.1.90.10 source Vlan10",
             dg.ping_ok("Dịch vụ: tới DHCP-Server", "Core thông VLAN mà không tới Server Farm → kiểm "
                        "SwitchServerFarm và DHCP-Server (node 72, Windows — kiểm tay qua VNC).")),
        ]
        rep = _execute(title, steps)
        rep.checks = l2 + rep.checks
        # bot chạy trên chính DHCP-Server → thêm lớp cuối: scope/lease thật trên server
        if rep.status != dg.FAIL and dhcp_local.available():
            try:
                rep.checks.append(dg.dhcp_scopes(dhcp_local.scopes()))
            except dhcp_local.DhcpError as e:
                rep.checks.append(dg.Check("Ứng dụng: scope trên DHCP-Server", dg.WARN, f"không đọc được: {e}"))
        return Result(True, rep.render())
    return Result(False, "Chẩn đoán DHCP hỗ trợ site 100, 200, 300, 400 (Site 500 dùng dhcp-server của vEdge: "
                         "chẩn đoán vEdge-S500).")


def sdn_health() -> Result:
    try:
        return Result(True, dg.sdn_report(ryu().health()).render())
    except LabApiError as e:
        return Result(False, str(e))


def sdn_flows(switch: str) -> Result:
    dev = inventory.resolve(switch)
    if dev is None or dev.platform != "ovs":
        return Result(False, f"'{switch}' không phải OVS (Dist-SW1/2, Access-SW1–4).")
    try:
        flows = ryu().flows(dev.node_id)          # DPID = node-id
    except LabApiError as e:
        return Result(False, str(e))
    by = {}
    for f in flows:
        k = (f.get("table_id", 0), hex(f.get("cookie", 0)))
        by.setdefault(k, [0, 0])
        by[k][0] += 1
        by[k][1] += f.get("packet_count", 0)
    rows = [f"bảng {t} cookie {c:<8} {n:>4} flow  {p:>10} gói" for (t, c), (n, p) in sorted(by.items())]
    return Result(True, f"{dev.name} (dpid {dev.node_id}): {len(flows)} flow\n" + "\n".join(rows))


def vmanage_devices() -> Result:
    try:
        d = vmanage().devices()
    except (LabApiError, CredentialError) as e:
        return Result(False, str(e))
    rows = []
    for x in sorted(d, key=lambda x: (x.get("site-id", ""), x.get("host-name", ""))):
        bfd = f" BFD {x.get('bfdSessionsUp')}/{x.get('bfdSessions')}" if x.get("bfdSessions") not in (None, "--") else ""
        mark = "" if x.get("reachability") == "reachable" else "  ❌"
        rows.append(f"{x.get('host-name', '?'):<14} {x.get('system-ip', ''):<14} site {x.get('site-id', ''):<4} "
                    f"{x.get('reachability', '')}{bfd}{mark}")
    ok = sum(1 for x in d if x.get("reachability") == "reachable")
    return Result(True, f"vManage: {ok}/{len(d)} thiết bị reachable\n" + "\n".join(rows))


def format_alarm(a: dict) -> str:
    t = datetime.datetime.fromtimestamp(a.get("entry_time", 0) / 1000).strftime("%d/%m %H:%M:%S")
    icon = "🟢" if is_recovery(a) else {"Critical": "🔴", "Major": "🟠"}.get(a.get("severity"), "🟡")
    hosts = alarm_target(a)
    state = "" if is_recovery(a) or a.get("active") else " (đã clear)"
    return f"{icon} {t} {a.get('rule_name_display', a.get('type'))} — {hosts}{state}: {a.get('message', '')}"


def vmanage_alarms(hours: int = 1) -> Result:
    try:
        al = vmanage().alarms(hours=max(1, min(int(hours), 168)))
    except (LabApiError, CredentialError) as e:
        return Result(False, str(e))
    if not al:
        return Result(True, f"Không có alarm quan trọng trong {hours} giờ qua (đã lọc cpu/memory-usage).")
    lines = [format_alarm(a) for a in al[-40:]]
    more = f"\n… và {len(al) - 40} alarm cũ hơn" if len(al) > 40 else ""
    return Result(True, f"{len(al)} alarm trong {hours} giờ:\n" + "\n".join(lines) + more)


def diagnose(target: str) -> Result:
    """Chọn bài chẩn đoán theo đích: 'sdn', 'fw', 'dhcp 200' / 'site 300', hoặc tên vEdge."""
    t = target.strip().lower()
    if t in ("sdn", "ryu", "ovs"):
        return sdn_health()
    if t in ("fw", "firewall", "asa"):
        return diagnose_fw()
    dev = inventory.resolve(target)
    if dev and dev.platform == "asa" and dev.site == "100":
        return diagnose_fw(dev.name)
    m = re.match(r"^(?:dhcp|site)\s*(\d{3})$", t)
    if m:
        return diagnose_dhcp(m.group(1))
    return diagnose_vedge(target)


# ======================================================================== Giai đoạn 3: thay đổi + tuân thủ + drift
_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_changes: ChangeManager | None = None


def changes() -> ChangeManager:
    global _changes
    if _changes is None:
        _changes = ChangeManager(console(), os.getenv("CHANGE_AUDIT_LOG", os.path.join(_BOT_DIR, "audit.log")))
    return _changes


def propose_change(device: str, commands, reason: str, requester: str, origin_chat: int = 0) -> Result:
    try:
        req = changes().propose(device, commands, reason, requester, origin_chat)
    except ChangeError as e:
        return Result(False, str(e))
    return Result(True, req.card() + f"\n\nĐã tạo yêu cầu #{req.id} — CHỜ NGƯỜI DUYỆT bấm nút trên Telegram "
                                     f"(hoặc /approve {req.id}). Bot không tự áp.")


def _targets(target: str, pool) -> list:
    t = (target or "all").strip()
    if t.lower() in ("all", "tất cả", ""):
        names = list(pool)
    elif re.fullmatch(r"(?i)(site\s*)?(\d{3}|sp)", t):
        site = re.sub(r"(?i)site\s*", "", t).upper()
        names = [n for n in pool if inventory.resolve(n).site == site]
    else:
        d = inventory.resolve(t)
        names = [d.name] if d and d.name in pool else []
    return [d for d in (inventory.resolve(n) for n in names) if in_scope(d)]


def _running(dev) -> str:
    return console().run(dev, ["show running-config"])[0]


def compliance_check(target: str = "all") -> Result:
    devs = _targets(target, cp.RULES)
    if not devs:
        return Result(False, f"Không có thiết bị nào có quy tắc tuân thủ khớp '{target}'. Có quy tắc cho: "
                             + ", ".join(cp.RULES))
    out, passed, failed, skipped = [], 0, 0, 0
    for d in devs:
        try:
            res = cp.RULES[d.name](d, _running(d))
        except (ConsoleError, CredentialError) as e:
            out.append(f"⏸ {d.name}: không truy cập được ({str(e)[:60]})")
            skipped += 1
            continue
        out.append(cp.render(d.name, res))
        if all(ok for ok, _ in res):
            passed += 1
        else:
            failed += 1
    head = f"📋 Tuân thủ: {passed} đạt, {failed} không đạt, {skipped} không truy cập được"
    return Result(True, head + "\n" + "\n".join(out))


def backup(target: str = "all") -> Result:
    devs = _targets(target, drift.PATHS)
    if not devs:
        return Result(False, f"Không có thiết bị nào khớp '{target}'.")
    folder = os.path.join(_BOT_DIR, "backups", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out, saved = [], 0
    for d in devs:
        try:
            running = _running(d)
        except (ConsoleError, CredentialError):
            out.append(f"⏸ {d.name}: không truy cập được")
            continue
        drift.save_backup(folder, d.name, running)
        saved += 1
        r = drift.diff(d.name, running)
        if r is None:
            out.append(f"💾 {d.name}: đã lưu (repo không có file để so)")
        elif r[0] == r[1] == 0:
            out.append(f"✅ {d.name}: khớp configs/")
        else:
            out.append(f"⚠️ {d.name}: lệch configs/ (+{r[0]} dòng chỉ có trên thiết bị, -{r[1]} dòng chỉ có trong repo)")
    rel = os.path.relpath(folder, _BOT_DIR) if saved else "-"
    return Result(True, f"💾 Backup {saved}/{len(devs)} thiết bị → {rel} (đã che bí mật)\n" + "\n".join(out)
                  + "\nXem chi tiết: /drift <thiết bị>")


def drift_detail(device: str) -> Result:
    dev = inventory.resolve(device)
    if dev is None or dev.name not in drift.PATHS:
        return Result(False, f"'{device}' không có file trong configs/ để so.")
    try:
        r = drift.diff(dev.name, _running(dev))
    except (ConsoleError, CredentialError) as e:
        return Result(False, str(e))
    plus, minus, lines = r
    if not lines:
        return Result(True, f"✅ {dev.name}: running-config khớp configs/{drift.PATHS[dev.name]}")
    body = "\n".join(lines[:80]) + (f"\n… còn {len(lines) - 80} dòng" if len(lines) > 80 else "")
    return Result(True, f"⚠️ {dev.name}: +{plus} / -{minus} dòng (+ = chỉ có trên thiết bị)\n{body}")
