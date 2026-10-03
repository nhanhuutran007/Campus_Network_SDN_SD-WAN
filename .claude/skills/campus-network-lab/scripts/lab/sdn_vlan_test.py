"""sdn_vlan_test.py [--vid 50] [--name "Phong Lab"] [--port Access-SW1.ens7] [--vpc 19] [--keep]

Bai thu muc tieu 1 (thoi gian them VLAN / khu vuc mang) cho SDN campus Site 100:
  1) SDN: POST /campus/vlan (them VLAN, gan cong access) -> thoi gian toi barrier
  2) Truyen thong: day doan IOS do controller sinh len Core-SW1, Core-SW2 qua
     console (node 3, 4) -> do thoi gian tung thiet bi, dem so lenh
  3) Kiem chung dau-cuoi: VPC dat IP tinh .100, ping gateway VRRP .1 va 10.1.90.10
  4) Don dep (tru khi --keep): xoa VLAN o ca hai phia, VPC ve DHCP VLAN goc
Ghi log/sdn-eval/vlan_<ngay>.json.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "host2-sync"))
from eve import client  # noqa: E402

CTL = os.environ.get("SDN_CTL", "http://10.215.28.71:8080")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
CORE = {"Core-SW1": 3, "Core-SW2": 4}


def drain(ch, quiet=1.5, limit=30):
    buf, t0, last = "", time.time(), time.time()
    while time.time() - t0 < limit:
        try:
            d = ch.recv(65535)
            if d:
                buf += d.decode(errors="replace")
                last = time.time()
                continue
        except Exception:
            pass
        if time.time() - last > quiet:
            break
        time.sleep(0.05)
    return buf


class Lab(object):
    def __init__(self):
        self.c = client("h1")

    def sh(self, cmd):
        _, o, _ = self.c.exec_command(cmd, timeout=40)
        return o.read().decode(errors="replace")

    def get(self, path):
        return json.loads(self.sh("curl -s -m 10 %s%s" % (CTL, path)) or "null")

    def post(self, path, body):
        data = json.dumps(body).replace("'", "")
        return json.loads(self.sh("curl -s -m 10 -X POST -H 'Content-Type: application/json' -d '%s' %s%s"
                                  % (data, CTL, path)) or "null")

    def console(self, node, lines, quiet=1.5):
        ch = self.c.get_transport().open_channel("direct-tcpip", ("127.0.0.1", 33536 + node), ("127.0.0.1", 0))
        ch.settimeout(0.2)
        ch.send("\r")
        out = drain(ch, 1.5, 8)
        if out.strip().endswith(">"):
            ch.send("enable\r")
            drain(ch, 1.0, 5)
        t0 = time.time()
        log = ""
        for l in lines:
            ch.send(l + "\r")
            log += drain(ch, quiet if not l.startswith("write") else 4.0, 60)
        dt = time.time() - t0
        ch.close()
        return dt, log


def vpc(lab, node, cmds):
    ch = lab.c.get_transport().open_channel("direct-tcpip", ("127.0.0.1", 33536 + node), ("127.0.0.1", 0))
    ch.settimeout(0.2)
    ch.send("\r")
    drain(ch, 1, 5)
    out = ""
    for c in cmds:
        ch.send(c + "\r")
        out += drain(ch, 3.5, 40)
    ch.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vid", type=int, default=50)
    ap.add_argument("--name", default="Phong Lab")
    ap.add_argument("--port", default="Access-SW1.ens7")
    ap.add_argument("--vpc", type=int, default=19)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    lab = Lab()
    res = {"vid": a.vid, "port": a.port}
    out_dir = os.path.join(REPO, "log", "sdn-eval")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "vlan_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    try:
        run(lab, a, res)
    finally:            # luu ket qua tung buoc ke ca khi loi giua chung
        json.dump(res, open(path, "w", encoding="utf-8"), indent=1)
        print("JSON:", os.path.relpath(path, REPO))


def run(lab, a, res):
    v = a.vid

    # 1) SDN
    r = lab.post("/campus/vlan", {"action": "add", "vid": v, "name": a.name, "ports": [a.port]})
    if not r or r.get("error"):
        sys.exit("API loi: %s" % r)
    time.sleep(2)
    ev = [e for e in lab.get("/campus/events") if e["id"] == r["id"]][0]
    res["sdn"] = {k: ev.get(k) for k in ("converge_ms", "switches", "flow_mods", "core_commands")}
    print("SDN: them VLAN %d -> %s ms (%s OVS, %s flow-mod)" % (v, ev.get("converge_ms"),
                                                             ev.get("switches"), ev.get("flow_mods")))
    # 2) Truyen thong: day cau hinh Core qua console
    res["traditional"] = {}
    for core, node in CORE.items():
        lines = [l for l in r["core_config"][core].splitlines() if l.strip()]
        dt, log = lab.console(node, lines)
        bad = [l for l in log.splitlines() if "% Invalid" in l or "% Incomplete" in l]
        res["traditional"][core] = {"seconds": round(dt, 1), "commands": len(lines), "errors": bad}
        print("CLI %s: %d lenh, %.1f s %s" % (core, len(lines), dt, ("LOI " + str(bad)) if bad else "OK"))
    time.sleep(5)       # VRRP bau master
    # 3) Kiem chung dau-cuoi
    out = vpc(lab, a.vpc, ["ip 10.1.%d.100/24 10.1.%d.1" % (v, v), "ping 10.1.%d.1 -c 3" % v,
                           "ping 10.1.90.10 -c 3"])
    ok_gw = out.count("bytes from 10.1.%d.1" % v)
    ok_srv = out.count("bytes from 10.1.90.10")
    res["end_to_end"] = {"gateway_replies": ok_gw, "server_replies": ok_srv}
    print("VPC%d (10.1.%d.100): gateway %d/3, DHCP-Server %d/3" % (a.vpc, v, ok_gw, ok_srv))
    # 4) Don dep
    if not a.keep:
        r2 = lab.post("/campus/vlan", {"action": "delete", "vid": v})
        time.sleep(2)
        ev2 = [e for e in lab.get("/campus/events") if e["id"] == r2["id"]][0]
        res["sdn_delete_ms"] = ev2.get("converge_ms")
        for core, node in CORE.items():
            lines = [l for l in r2["core_config"][core].splitlines() if l.strip()]
            dt, _ = lab.console(node, lines)
            res.setdefault("traditional_delete", {})[core] = round(dt, 1)
        out = vpc(lab, a.vpc, ["ip dhcp"])
        print("Don dep: xoa VLAN %d (SDN %s ms), VPC%d ve DHCP: %s" % (
            v, ev2.get("converge_ms"), a.vpc, (out.split("DORA")[-1].strip().splitlines() or ["?"])[0][:40]))


if __name__ == "__main__":
    main()
