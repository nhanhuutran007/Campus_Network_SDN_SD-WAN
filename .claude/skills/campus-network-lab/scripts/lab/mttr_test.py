"""mttr_test.py <file_ra.jsonl> [so_lan] [ten_su_co,...] : do thoi gian xu ly su co co cong cu ho tro. Chay tren laptop.

Moi su co duoc gay that roi do bon doan (giay, dong ho laptop):
  phat_hien : tu luc gay loi toi khi he thong giam sat ghi nhan (alarm vManage / health cua Ryu); su co khong sinh
              canh bao thi de trong (nguoi dung bao).
  chan_doan : thoi gian chay bai chan doan theo lop cua NetOps Bot (service.diagnose) va lop loi dau tien no chi ra.
  sua       : thoi gian thuc hien thao tac khac phuc (da biet nguyen nhan).
  phuc_hoi  : tu luc sua xong toi khi bai chan doan sach tro lai.
Su co:
  wan   : dut MPLS cua vEdge1 Site 200 (ha tap tren server, thiet bi khong thay link down)
  sdn   : dut uplink Access-SW1 - Dist-SW1
  l2    : shutdown cong SwitchBrand Site 200 noi xuong switch truy cap 1
  relay : mat ip helper-address tren SVI Vlan10 cua Core-SW1
Can: EVE_HOST, SDN_CTL (nsrelay.py tren server), namespace lt_mgmt. Moi thay doi deu duoc tra lai, khong luu cau hinh.
"""
import json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "campus-netops-bot"))
sys.path.insert(0, os.path.join(HERE, "..", "host2-sync"))
from campus import service  # noqa: E402
from eve import client, PORT_BASE  # noqa: E402

OUT = sys.argv[1]
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
ONLY = sys.argv[3].split(",") if len(sys.argv) > 3 else ["sdn", "wan", "l2", "relay"]
ssh = client("h1")


def srv(cmd):
    _, o, _ = ssh.exec_command(cmd, timeout=30)
    return o.read().decode(errors="replace")


def ios(nid, cmds):
    ch = ssh.get_transport().open_channel("direct-tcpip", ("127.0.0.1", PORT_BASE + nid), ("127.0.0.1", 0))
    ch.settimeout(0.2)

    def rd(pat, to=15):
        buf, t0 = "", time.time()
        while time.time() - t0 < to:
            try:
                buf += ch.recv(65535).decode(errors="replace")
            except Exception:
                pass
            if re.search(pat, buf[-200:]):
                return buf
        raise TimeoutError("node %d: %r" % (nid, buf[-120:]))
    ch.send("\r")
    o = rd(r"[>#] ?$")
    if o.rstrip().endswith(">"):
        ch.send("enable\r")
        rd(r"# ?$")
    out = ""
    for c in cmds:
        ch.send(c + "\r")
        out += rd(r"# ?$")
    ch.close()
    return out


def log(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def diag(target):
    t0 = time.time()
    r = service.diagnose(target)
    dt = time.time() - t0
    bad = [l.strip() for l in r.text.splitlines() if l.strip().startswith(("❌", "⚠️"))]
    return round(dt, 1), (bad[0] if bad else None), r


def vm_alarm_ids():
    return {a.get("uuid") for a in service.vmanage().alarms(hours=1)}


def detect_vmanage(host_ip):
    seen = vm_alarm_ids()

    def wait(t0, limit=180):
        while time.time() - t0 < limit:
            for a in service.vmanage().alarms(hours=1):
                if a.get("uuid") not in seen and host_ip in json.dumps(a):
                    return round(time.time() - t0, 1), a.get("type")
            time.sleep(3)
        return None, None
    return wait


def detect_ryu():
    def wait(t0, limit=120):
        while time.time() - t0 < limit:
            h = service.ryu().health()
            if h.get("links_up") != h.get("links_total"):
                return round(time.time() - t0, 1), "links %s/%s" % (h.get("links_up"), h.get("links_total"))
            time.sleep(0.5)
        return None, None
    return wait


FAULTS = {
    "sdn": dict(target="sdn", inject=lambda: srv("ip link set vunl0_68_1 down"), fix=lambda: srv("ip link set vunl0_68_1 up"),
                detect=detect_ryu),
    "wan": dict(target="vEdge1-S200", inject=lambda: srv("ip link set vunl0_29_3 down"), fix=lambda: srv("ip link set vunl0_29_3 up"),
                detect=lambda: detect_vmanage("10.200.200.1")),
    "l2": dict(target="site 200", inject=lambda: ios(63, ["configure terminal", "interface e0/0", "shutdown", "end"]),
               fix=lambda: ios(63, ["configure terminal", "interface e0/0", "no shutdown", "end"]), detect=None),
    "relay": dict(target="dhcp 100", inject=lambda: ios(3, ["configure terminal", "interface Vlan10", "no ip helper-address 10.1.90.10", "end"]),
                  fix=lambda: ios(3, ["configure terminal", "interface Vlan10", "ip helper-address 10.1.90.10", "end"]), detect=None),
}

for name in ONLY:
    f = FAULTS[name]
    dt, bad, r = diag(f["target"])
    log({"su_co": name, "test": "nen", "chan_doan_s": dt, "loi": bad})
    if bad and name != "l2" and not bad.startswith("⚠️"):
        print(r.text)
        log({"su_co": name, "test": "bo-qua", "ly_do": "chua sach truoc khi gay loi"})
        continue
    base_bad = bad
    for i in range(REPS):
        rec = {"su_co": name, "test": "do", "run": i + 1}
        try:
            waiter = f["detect"]() if f["detect"] else None
            t0 = time.time()
            f["inject"]()
            rec["gay_loi_s"] = round(time.time() - t0, 1)
            if waiter:
                rec["phat_hien_s"], rec["tin_hieu"] = waiter(t0)
            else:
                time.sleep(5)
            rec["chan_doan_s"], rec["lop_loi"], r = diag(f["target"])
            rec["ket_luan"] = [l for l in r.text.splitlines() if l.startswith("Kết luận")][:1]
        finally:
            t1 = time.time()
            f["fix"]()
            rec["sua_s"] = round(time.time() - t1, 1)
        t2 = time.time()
        while time.time() - t2 < 420:
            dt, bad, _r = diag(f["target"])
            if bad == base_bad:
                rec["phuc_hoi_s"] = round(time.time() - t2 - dt, 1) if time.time() - t2 - dt > 0 else 0.0
                rec["phuc_hoi_xac_nhan_s"] = round(time.time() - t2, 1)
                break
            time.sleep(3)
        log(rec)
        time.sleep(45)
ssh.close()
