"""sdn_recovery_test.py [--target IP] [--links A4-D1,D1-C1] [--modes silent,admin] [--hold 15] [--gap 12]
                       [--node 5 --node-hold 30 --node-boot 180]   (tat han 1 OVS bang unl_wrapper)

Bai thu muc tieu 2 (thoi gian khoi phuc khi mat lien ket) cho SDN campus Site 100.
Goi REST cua campus_switch_13/noc tren SDN_CONTROLLER qua host 1 (node 9 co IP LAN
o ens6 - xem CTL), khong can VNC:
  1) bat ping lien tuc tu controller toi --target (mac dinh PC-HanhChinh-S100)
  2) voi moi lien ket x che do: cat -> giu --hold s -> khoi phuc -> nghi --gap s
  3) lay su kien (detect/converge/total) + cac lan mat goi cua ping
  4) ghi log/sdn-eval/recovery_<ngay>.csv va in bang tom tat
"""
import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client  # noqa: E402

CTL = os.environ.get("SDN_CTL", "http://10.215.28.71:8080")
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", ".."))


class Api(object):
    def __init__(self):
        self.c = client("h1")

    def _run(self, cmd):
        _, o, _ = self.c.exec_command(cmd, timeout=30)
        return o.read().decode(errors="replace")

    def get(self, path):
        return json.loads(self._run("curl -s -m 10 %s%s" % (CTL, path)) or "null")

    def post(self, path, body):
        data = json.dumps(body).replace("'", "")
        return json.loads(self._run("curl -s -m 10 -X POST -H 'Content-Type: application/json' -d '%s' %s%s"
                                    % (data, CTL, path)) or "null")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="10.1.40.102")
    ap.add_argument("--links", default="A4-D1,D1-C1")
    ap.add_argument("--modes", default="silent,admin")
    ap.add_argument("--hold", type=float, default=15)
    ap.add_argument("--gap", type=float, default=12)
    ap.add_argument("--interval", type=float, default=0.1)
    ap.add_argument("--node", type=int, default=0, help="dpid/node-id OVS de tat han (vd 5 = Dist-SW1)")
    ap.add_argument("--node-hold", type=float, default=30)
    ap.add_argument("--node-boot", type=float, default=180)
    a = ap.parse_args()
    api = Api()
    s = api.get("/noc/summary")
    print("controller: %s/%s switch, %s/%s lien ket, goc %s" % (
        s["switches_up"], s["switches_total"], s["links_up"], s["links_total"], s["root"]))
    api.post("/campus/pinger", {"target": a.target, "action": "reset"})
    api.post("/campus/pinger", {"target": a.target, "action": "start", "interval": a.interval})
    time.sleep(5)
    start_id = max([e["id"] for e in api.get("/campus/events")] or [0])
    runs = []
    if a.node:
        wrap = ("/opt/unetlab/wrappers/unl_wrapper -a %s -T 6 -F "
                "'/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl' -D " + str(a.node) +
                " </dev/null >/dev/null 2>&1; echo rc=$?")
        t_down = api.get("/noc/summary") and time.time()
        print("tat node %d: %s" % (a.node, api._run(wrap % "stop").strip()))
        time.sleep(a.node_hold)
        print("bat node %d: %s" % (a.node, api._run(wrap % "start").strip()))
        time.sleep(a.node_boot)
        evs = [e for e in api.get("/campus/events") if e["id"] > start_id]
        ping = [p for p in api.get("/campus/pinger") if p["target"] == a.target][0]
        api.post("/campus/pinger", {"target": a.target, "action": "stop"})
        print()
        print("Su kien:")
        for e in evs:
            print("  %s %-12s %-6s %-55s detect=%s converge=%s total=%s" % (
                time.strftime("%H:%M:%S", time.localtime(e["ts"])), e["kind"], e.get("link") or "",
                e["detail"][:55], e.get("detect_ms"), e.get("converge_ms"), e.get("total_ms")))
        print("Mat goi: %s" % ["%d goi / %s ms" % (o["lost"], o["duration_ms"]) for o in ping["outages"]])
        print("ping %s: gui %s, mat %s%%" % (a.target, ping["sent"], ping["loss_pct"]))
        out_dir = os.path.join(REPO, "log", "sdn-eval")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "node%d_%s.json" % (a.node, time.strftime("%Y%m%d_%H%M%S")))
        json.dump({"events": evs, "outages": ping["outages"], "sent": ping["sent"],
                   "loss_pct": ping["loss_pct"]}, open(path, "w", encoding="utf-8"), indent=1)
        print("JSON:", os.path.relpath(path, REPO))
        return
    for link in a.links.split(","):
        for mode in a.modes.split(","):
            # Moc thoi gian lay tu DONG HO CONTROLLER (r['ts']), khong dung dong ho may nay
            r = api.post("/campus/linktest", {"link": link, "action": "down", "mode": mode})
            print("cat %-6s %-6s %s" % (link, mode, "OK" if r and not r.get("error") else r))
            time.sleep(a.hold)
            r2 = api.post("/campus/linktest", {"link": link, "action": "up", "mode": mode})
            time.sleep(a.gap)
            runs.append((link, mode, r["ts"], r2["ts"] + a.gap))
    evs = [e for e in api.get("/campus/events") if e["id"] > start_id]
    ping = [p for p in api.get("/campus/pinger") if p["target"] == a.target][0]
    api.post("/campus/pinger", {"target": a.target, "action": "stop"})
    rows = []
    for link, mode, t0, t1 in runs:
        down = [e for e in evs if e["kind"] == "link_down" and e.get("link") == link and t0 - 5 <= e["ts"] <= t1]
        up = [e for e in evs if e["kind"] == "link_up" and e.get("link") == link and t0 - 5 <= e["ts"] <= t1]
        outs = [o for o in ping["outages"] if t0 - 1 <= o["start"] <= t1]
        t_up = t1 - a.gap
        cut_out = [o for o in outs if o["start"] < t_up]
        back_out = [o for o in outs if o["start"] >= t_up]
        d = down[0] if down else {}
        rows.append({
            "link": link, "mode": mode,
            "detect_ms": d.get("detect_ms"), "converge_ms": d.get("converge_ms"),
            "total_ms": d.get("total_ms"), "switches": d.get("switches"), "flow_mods": d.get("flow_mods"),
            "announced": d.get("announced"),
            "lost_on_cut": sum(o["lost"] for o in cut_out),
            "outage_cut_ms": max([o["duration_ms"] for o in cut_out] or [0]),
            "restore_converge_ms": up[0].get("converge_ms") if up else None,
            "lost_on_restore": sum(o["lost"] for o in back_out),
            "outage_restore_ms": max([o["duration_ms"] for o in back_out] or [0]),
        })
    out_dir = os.path.join(REPO, "log", "sdn-eval")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "recovery_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n%-6s %-6s %9s %9s %9s %5s %7s %10s %8s" % ("link", "mode", "detect", "converge", "total",
                                                         "lost", "outage", "restore_lost", "restore_out"))
    for r in rows:
        print("%-6s %-6s %9s %9s %9s %5s %7s %10s %8s" % (
            r["link"], r["mode"], r["detect_ms"], r["converge_ms"], r["total_ms"], r["lost_on_cut"],
            r["outage_cut_ms"], r["lost_on_restore"], r["outage_restore_ms"]))
    print("\nping %s: gui %s, mat %s%%, RTT tb %s ms (chu ky %ss)" % (
        a.target, ping["sent"], ping["loss_pct"], ping["rtt_avg"], a.interval))
    print("CSV:", os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
