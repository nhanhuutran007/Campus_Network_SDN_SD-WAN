#!/usr/bin/env python3
"""sdn_stress_test.py <lenh> : do tai cao Site 100 bang iperf3 that. CHAY TREN SERVER EVE (root), khong can mat khau.

Tao network namespace noi vao bridge EVE (vnet0_<net>) cua cong Access/Farm/DMZ, dong vai may tram that.
Moi namespace chi them 1 veth vao bridge; `down` go sach, khong doi cau hinh thiet bi nao.

  up / down / status           tao, go, xem namespace
  path <ns_nguon> <ns_dich> [--rates 5,10,..] [--tcp-repeat 3] [--time 20] [--port 5201]
                               TCP lap + UDP tang dan, kem do dong thoi control plane
  macflood <ns> --rates 50,200,500 [--time 20]
                               tai dieu khien: moi giay N MAC nguon moi => packet-in
Ket qua them vao /root/loadtest/stress.jsonl
"""
import argparse, json, os, random, re, socket, struct, subprocess, threading, time, urllib.request

OUT = "/root/loadtest/stress.jsonl"
CTL = "http://10.1.99.10:8080"
# ten: (net .unl, ip, gateway) -- IP ngoai dai DHCP .100-.199
NS = {
    "a1": (32, "10.1.10.241/24", "10.1.10.1"),    # Access-SW1, VLAN 10
    "a1b": (33, "10.1.10.242/24", "10.1.10.1"),   # Access-SW1, VLAN 10
    "a2": (34, "10.1.20.241/24", "10.1.20.1"),    # Access-SW2, VLAN 20
    "a3": (36, "10.1.30.241/24", "10.1.30.1"),    # Access-SW3, VLAN 30
    "a4": (39, "10.1.40.241/24", "10.1.40.1"),    # Access-SW4, VLAN 40
    "farm": (99, "10.1.90.241/24", "10.1.90.1"),  # SwitchServerFarm, VLAN 90
    "dmz": (49, "10.1.1.13/28", "10.1.1.1"),      # SwitchDMZ, sau tuong lua
    "mgmt": (96, "10.1.99.200/24", None),         # VLAN 99, chi de doc REST + do control plane
    # Chi nhanh va Site 500: may tram sau Brand-FW, qua overlay SD-WAN
    "s200": (58, "10.2.60.241/24", "10.2.60.1"),
    "s300": (82, "10.3.90.241/24", "10.3.90.1"),
    "s400": (89, "10.4.50.241/24", "10.4.50.1"),
    "s500": (97, "10.5.10.241/24", "10.5.10.1"),
}


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    if check and r.returncode:
        raise SystemExit("LOI: %s\n%s" % (cmd, r.stdout))
    return r.stdout


def up(names):
    for n in names:
        net, ip, gw = NS[n]
        if os.path.exists("/var/run/netns/lt_" + n):
            continue
        sh("ip netns add lt_%s" % n, True)
        sh("ip link add lth_%s type veth peer name ltv_%s" % (n, n), True)
        sh("ip link set ltv_%s netns lt_%s" % (n, n), True)
        sh("ip link set lth_%s master vnet0_%d up" % (n, net), True)
        ns = "ip netns exec lt_%s " % n
        sh(ns + "ip link set lo up; " + ns + "ip link set ltv_%s up" % n, True)
        sh(ns + "ip addr add %s dev ltv_%s" % (ip, n), True)
        if gw:
            sh(ns + "ip route add default via %s" % gw, True)
        # TSO/GSO/checksum phai tat: frame di vao tap cua VM phai dung MTU va co checksum that
        sh(ns + "ethtool -K ltv_%s tx off tso off gso off gro off >/dev/null" % n)
        sh("ethtool -K lth_%s tx off tso off gso off gro off >/dev/null" % n)
        print("up", n, ip)


def down():
    for n in NS:
        sh("ip link del lth_%s 2>/dev/null; ip netns del lt_%s 2>/dev/null" % (n, n))
    print("da go namespace:", sh("ip netns list | grep -c lt_").strip(), "con lai")


def rest(path):
    cmd = "ip netns exec lt_mgmt curl -s -m 4 %s%s" % (CTL, path)
    try:
        return json.loads(sh(cmd))
    except Exception:
        return None


class Monitor:
    """Do dong thoi: REST controller, ping VLAN 99 toi controller, CPU cac VM OVS, tai host."""

    def __init__(self):
        self.stop = threading.Event()
        self.samples = []
        self.fail = 0

    def start(self):
        self.ping = subprocess.Popen("exec ip netns exec lt_mgmt ping -i 0.2 -W 1 10.1.99.10", shell=True,
                                     stdout=subprocess.PIPE, universal_newlines=True)
        self.th = threading.Thread(target=self.run, daemon=True)
        self.th.start()

    def run(self):
        while not self.stop.wait(5):
            l = rest("/campus/load?n=1")
            if not l or "latest" not in l:
                self.fail += 1
                continue
            s = l["latest"]
            try:
                self.samples.append({
                    "cpu": s["ctl"]["cpu_pct"], "ryu": s["ctl"]["ryu_cpu_pct"], "pktin": s["ctl"]["pktin_ps_total"],
                    "d1_mbps": s["sw"]["5"]["mbps"], "d2_mbps": s["sw"]["8"]["mbps"],
                    "c1_mbps": s["core"]["Core-SW1"]["uplink_mbps"], "c2_mbps": s["core"]["Core-SW2"]["uplink_mbps"],
                    "c1_cpu": s["core"]["Core-SW1"].get("cpu"), "c2_cpu": s["core"]["Core-SW2"].get("cpu"),
                    "host": float(open("/proc/loadavg").read().split()[0])})
            except (KeyError, TypeError):
                pass

    def finish(self):
        self.stop.set()
        self.th.join(8)
        self.ping.send_signal(2)
        out = self.ping.communicate(timeout=5)[0]
        m = re.search(r"(\d+) packets transmitted, (\d+) received", out)
        r = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)", out)
        res = {"rest_fail": self.fail, "ctl_ping_sent": int(m.group(1)) if m else 0,
               "ctl_ping_recv": int(m.group(2)) if m else 0, "ctl_rtt_avg": float(r.group(2)) if r else None,
               "ctl_rtt_max": float(r.group(3)) if r else None}
        for k in ("cpu", "ryu", "pktin", "d1_mbps", "d2_mbps", "c1_mbps", "c2_mbps", "c1_cpu", "c2_cpu", "host"):
            v = [x[k] for x in self.samples if x.get(k) is not None]
            if v:
                res[k + "_avg"] = round(sum(v) / len(v), 2)
                res[k + "_max"] = round(max(v), 2)
        return res


def health():
    t = rest("/campus/topology") or {}
    nodes = t.get("nodes")
    return {"switches": sum(1 for n in nodes if n.get("connected")) if nodes else None,
            "links": len(t["links"]) if "links" in t else None}


def save(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def iperf(src, dst, port, secs, rate=None):
    ip = NS[dst][1].split("/")[0]
    srv = subprocess.Popen("exec ip netns exec lt_%s iperf3 -s -1 -p %d" % (dst, port), shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    cmd = "timeout %d ip netns exec lt_%s iperf3 -c %s -p %d -t %d -J --connect-timeout 5000" % (secs + 25, src, ip, port, secs)
    if rate:
        cmd += " -u -l 1300 -b %gM" % rate
    else:
        cmd += " -O 2"
    out = sh(cmd)
    srv.kill()
    srv.wait()
    try:
        d = json.loads(out[out.index("{"):])
    except ValueError:
        return {"error": "khong JSON: " + out[:120]}
    if d.get("error"):
        return {"error": d["error"]}
    e = d["end"]
    if rate:
        s = e["sum"]
        return {"mbps": round(s["bits_per_second"] / 1e6, 2), "lost_pct": round(s["lost_percent"], 2),
                "jitter_ms": round(s["jitter_ms"], 2)}
    return {"mbps_tx": round(e["sum_sent"]["bits_per_second"] / 1e6, 2),
            "mbps_rx": round(e["sum_received"]["bits_per_second"] / 1e6, 2),
            "retrans": e["sum_sent"].get("retransmits")}


def path(a):
    up(["mgmt", a.src, a.dst])
    print("truoc:", health())
    for i in range(a.tcp_repeat):
        m = Monitor(); m.start()
        r = iperf(a.src, a.dst, a.port, a.time)
        rec = {"test": "tcp", "src": a.src, "dst": a.dst, "run": i + 1, "secs": a.time, **r, "mon": m.finish(), "after": health()}
        save(rec); print(json.dumps(rec, ensure_ascii=False)); time.sleep(3)
        if "error" in r and i == 0:
            print("TCP loi, dung duong nay"); return
    for b in [float(x) for x in a.rates.split(",") if x]:
        m = Monitor(); m.start()
        r = iperf(a.src, a.dst, a.port, a.time, b)
        rec = {"test": "udp", "src": a.src, "dst": a.dst, "offered": b, "secs": a.time, **r, "mon": m.finish()}
        time.sleep(5); rec["after"] = health()
        save(rec); print(json.dumps(rec, ensure_ascii=False))
        if rec["after"]["switches"] not in (6, None) or r.get("lost_pct", 0) > 60:
            print("DUNG THANG: mat goi > 60% hoac controller mat switch"); break
        time.sleep(3)
    print("sau:", health())


def macflood(a):
    """Gui khung broadcast voi MAC nguon moi lien tuc (khung dau cua may tram moi) => packet-in tai Access."""
    up(["mgmt", a.src])
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind(("ltv_" + a.src, 0))  # netns se duoc vao qua lenh ngoai
    raise SystemExit("macflood phai chay qua 'ip netns exec' (xem macflood-run)")


def macflood_run(a):
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind(("ltv_" + a.src, 0))
    end = time.time() + a.time
    sent = 0
    seq = random.randint(0, 1 << 20)
    gap = 1.0 / a.rate
    nxt = time.time()
    payload = b"\x00" * 46
    while time.time() < end:
        seq += 1
        mac = b"\x02\x4c" + struct.pack(">I", seq)
        s.send(b"\xff" * 6 + mac + b"\x88\xb5" + payload)
        sent += 1
        nxt += gap
        d = nxt - time.time()
        if d > 0:
            time.sleep(d)
    print(sent)


def macflood_ladder(a):
    up(["mgmt", a.src, "a1b"])
    gw = NS["a1b"][2]
    for rate in [int(x) for x in a.rates.split(",")]:
        before = health()
        m = Monitor(); m.start()
        # luong da cai san: phai khong anh huong khi controller ban
        probe = subprocess.Popen("ip netns exec lt_a1b ping -i 0.2 -W 1 -c %d %s" % (a.time * 5, gw), shell=True,
                                 stdout=subprocess.PIPE, universal_newlines=True)
        out = sh("ip netns exec lt_%s python3 %s macflood-run %s --rate %d --time %d" % (a.src, os.path.abspath(__file__), a.src, rate, a.time))
        p = probe.communicate(timeout=30)[0]
        mm = re.search(r"(\d+) packets transmitted, (\d+) received", p)
        rr = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)", p)
        rec = {"test": "macflood", "src": a.src, "rate": rate, "secs": a.time, "sent": out.strip(),
               "probe_sent": int(mm.group(1)) if mm else 0, "probe_recv": int(mm.group(2)) if mm else 0,
               "probe_rtt_avg": float(rr.group(2)) if rr else None, "probe_rtt_max": float(rr.group(3)) if rr else None,
               "mon": m.finish(), "before": before}
        time.sleep(10); rec["after"] = health()
        save(rec); print(json.dumps(rec, ensure_ascii=False))
        if rec["after"]["switches"] not in (6, None):
            print("DUNG THANG: controller mat switch"); break
        time.sleep(15)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("src", nargs="?")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--rates", default="5,10,20,50,100,200,500")
    ap.add_argument("--rate", type=int, default=50)
    ap.add_argument("--tcp-repeat", type=int, default=3)
    ap.add_argument("--time", type=int, default=20)
    ap.add_argument("--port", type=int, default=5201)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if a.cmd == "up":
        up([a.src, a.dst] if a.src else list(NS))
    elif a.cmd == "down":
        down()
    elif a.cmd == "status":
        print(sh("ip netns list")); print(health())
    elif a.cmd == "path":
        path(a)
    elif a.cmd == "macflood":
        macflood_ladder(a)
    elif a.cmd == "macflood-run":
        macflood_run(a)
