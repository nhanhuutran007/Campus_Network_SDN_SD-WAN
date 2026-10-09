"""sdn_realcut_test.py [--cases A4-D1,D1-C1,A4-D1+D2-C1] [--hold 25] [--gap 25] [--targets ip,ip]
                      [--node 8 --node-hold 60]   (tat han 1 OVS bang unl_wrapper thay vi cat link)

Kiem thu tu phuc hoi bang cat link THAT (09/10/2026): ha tap cua dau OVS tren host 1
(`ip link set vunl6_<node>_<if> down`) - khac voi cat mo phong qua Console (flow DROP/PortMod),
switch va controller khong biet gi truoc. Moi ca:
  1) ping 0,1 s tu controller toi 1 may moi VLAN (pinger cua Console)
  2) cat -> giu --hold s -> khoi phuc -> cho toi da --gap s (va toi khi 13/13 lien ket + 6/6 switch)
  3) tinh gian doan dai nhat luc cat / luc khoi phuc, su kien, ket luan DAT/KHONG DAT
  4) day ket qua len Console (tab Kich ban, loai "cat that") va in bang tom tat
Tap: cong ensN cua OVS = vunl6_<node>_<N-3> (ens4 -> _1, ens9 -> _6, ens10 -> _7).
Moc thoi gian lay tu dong ho controller (/campus/health 'ts').
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client  # noqa: E402

CTL = os.environ.get("SDN_CTL", "http://10.215.28.97:8080")
LAB = "/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl"
# Dau OVS cua tung lien ket (khop LINKS trong campus_switch_13.py)
LINK_END = {'D1-C1': (5, 'ens9'), 'D2-C1': (8, 'ens10'), 'D1-C2': (5, 'ens10'), 'D2-C2': (8, 'ens9'),
            'D1-D2': (5, 'ens8'), 'A1-D1': (68, 'ens4'), 'A2-D1': (66, 'ens4'), 'A3-D1': (70, 'ens4'),
            'A4-D1': (69, 'ens4'), 'A1-D2': (68, 'ens5'), 'A2-D2': (66, 'ens5'), 'A3-D2': (70, 'ens5'),
            'A4-D2': (69, 'ens5')}
TARGETS = ["10.1.10.100", "10.1.20.100", "10.1.30.100", "10.1.40.102"]
LIMIT_CUT_MS, LIMIT_RESTORE_MS = 5000, 3000


def tap(lid):
    node, port = LINK_END[lid]
    return "vunl6_%d_%d" % (node, int(port[3:]) - 3)


class Api(object):
    def __init__(self):
        self.c = client("h1")

    def run(self, cmd, t=60):
        _, o, _ = self.c.exec_command(cmd, timeout=t)
        return o.read().decode(errors="replace")

    def get(self, path):
        return json.loads(self.run("curl -s -m 10 '%s%s'" % (CTL, path)) or "null")

    def post(self, path, body):
        data = json.dumps(body).replace("'", "")
        return json.loads(self.run("curl -s -m 10 -X POST -H 'Content-Type: application/json' -d '%s' %s%s"
                                   % (data, CTL, path)) or "null")

    def now(self):
        return self.get("/campus/health")["ts"]

    def healthy(self):
        s = self.get("/noc/summary")
        return s["switches_up"] == s["switches_total"] and s["links_up"] == s["links_total"]


def outage_stats(p, t0, t1):
    """Tu danh sach outages cua pinger: gian doan dai nhat bat dau trong [t0, t1)."""
    outs = [o for o in p["outages"] if t0 <= o["start"] < t1]
    return {"sent": int(round((t1 - t0) / p["interval"])), "lost": sum(o["lost"] for o in outs),
            "outage_ms": round(max([o["duration_ms"] + 1000 * p["interval"] for o in outs] or [0]), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="A4-D1,D1-C1,D2-C1,A4-D1+D2-C1")
    ap.add_argument("--hold", type=float, default=25)
    ap.add_argument("--gap", type=float, default=25)
    ap.add_argument("--targets", default=",".join(TARGETS))
    ap.add_argument("--node", type=int, default=0)
    ap.add_argument("--node-hold", type=float, default=60)
    a = ap.parse_args()
    api = Api()
    targets = [t for t in a.targets.split(",") if t]
    for t in targets:
        api.post("/campus/pinger", {"target": t, "action": "remove"})
        api.post("/campus/pinger", {"target": t, "action": "start", "interval": 0.1})
    time.sleep(4)
    cases = ["node%d" % a.node] if a.node else a.cases.split(",")
    for case in cases:
        for _ in range(60):
            if api.healthy():
                break
            time.sleep(2)
        else:
            print("%s: mang chua on dinh - bo qua" % case)
            continue
        e0 = max([e["id"] for e in api.get("/campus/events")] or [0])
        if a.node:
            wrap = ("/opt/unetlab/wrappers/unl_wrapper -a %%s -T 6 -F '%s' -D %d </dev/null >/dev/null 2>&1"
                    % (LAB, a.node))
            links, down, up, hold = [], wrap % "stop", wrap % "start", a.node_hold
        else:
            links = case.split("+")
            taps = [tap(l) for l in links]
            down = " ; ".join("ip link set %s down" % t for t in taps)
            up = " ; ".join("ip link set %s up" % t for t in taps)
            hold = a.hold
        t0 = api.now()
        api.run(down, 120)
        time.sleep(hold)
        topo = api.get("/campus/topology")
        t1 = api.now()
        api.run(up, 120)
        t_ok = None
        limit = a.gap + (240 if a.node else 60)
        while api.now() - t1 < limit:
            time.sleep(1)
            if t_ok is None and api.healthy():
                t_ok = api.now()
            if t_ok is not None and api.now() - t1 >= a.gap:
                break
        time.sleep(2)
        t2 = api.now()
        P = {p["target"]: p for p in api.get("/campus/pinger")}
        ping = {t: {"cut": outage_stats(P[t], t0, t1), "restore": outage_stats(P[t], t1, t2)}
                for t in targets if t in P}
        evs = [e for e in api.get("/campus/events?since=%d" % e0)
               if e["kind"] in ("link_down", "link_up", "switch_down", "switch_up", "controller_stall", "tree_change")]
        dn = [e for e in evs if e["kind"] == "link_down" and e.get("link") in links]
        wc = max([v["cut"]["outage_ms"] for v in ping.values()] or [0])
        wr = max([v["restore"]["outage_ms"] for v in ping.values()] or [0])
        fails = []
        if t_ok is None:
            fails.append("khong tro ve 13/13 lien ket + 6/6 switch")
        if wc > LIMIT_CUT_MS:
            fails.append("gian doan khi cat %.1f s > %d s" % (wc / 1000, LIMIT_CUT_MS // 1000))
        if wr > LIMIT_RESTORE_MS:
            fails.append("gian doan khi khoi phuc %.1f s > %d s" % (wr / 1000, LIMIT_RESTORE_MS // 1000))
        res = {"ts": t0, "id": "R-" + case, "name": ("Tat han node %d" % a.node) if a.node else "Cat that " + case,
               "links": links or ["node %d" % a.node], "kind": "cat that", "hold_s": round(t1 - t0, 1),
               "verdict": "DAT" if not fails else "KHONG DAT", "fails": fails,
               "stalls": len([e for e in evs if e["kind"] == "controller_stall"]),
               "detect_ms": [e.get("detect_ms") for e in dn], "converge_ms": [e.get("converge_ms") for e in dn],
               "restore_ms": round((t_ok - t1) * 1000) if t_ok else None,
               "worst_cut_ms": wc, "worst_restore_ms": wr,
               "ping": ping,
               "tree_during": sorted(l["id"] for l in topo["links"] if l["in_tree"]),
               "frozen_during": [n["name"] for n in topo["nodes"] if n.get("frozen")],
               "events": [[round(e["ts"] - t0, 2), e["kind"], e["detail"]] for e in evs]}
        api.post("/campus/scenario/result", res)
        print("\n=== %s (%s) giu %.0fs: %s %s" % (case, "+".join(tap(l) for l in links) if links else "unl_wrapper",
                                                hold, res["verdict"], "; ".join(fails)))
        for t, v in ping.items():
            print("  %-12s cat: mat %3d goi, gian doan %6.0f ms | khoi phuc: mat %3d, %6.0f ms" % (
                t, v["cut"]["lost"], v["cut"]["outage_ms"], v["restore"]["lost"], v["restore"]["outage_ms"]))
        print("  ve day du sau %s ms; khung controller %d lan; cay luc cat %s" % (
            res["restore_ms"], res["stalls"], res["tree_during"]))
        for e in res["events"]:
            print("   %+7.2fs %-16s %s" % tuple(e))
    for t in targets:
        api.post("/campus/pinger", {"target": t, "action": "stop"})


if __name__ == "__main__":
    main()
