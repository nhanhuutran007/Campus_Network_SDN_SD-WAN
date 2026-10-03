"""sdn_load_test.py [--phase 60] [--vpc 19] [--target 10.1.40.102]

Bai thu muc tieu 4 (tai tren Core va Distribution) cho SDN campus Site 100.
Ba pha, moi pha --phase giay, lay mau /campus/load (5 s/mau):
  1) nen          : mang ranh
  2) luu luong    : VPC ping goi 1400 B lien tuc toi target + controller ping 50 lan/s
  3) luu luong + su co: nhu (2) va cat D1-C1 (admin) giua pha, khoi phuc cuoi pha
Tinh trung binh / dinh cho Dist-SW1/2, uplink Core-SW1/2, controller (CPU, packet-in/s).
Ghi log/sdn-eval/load_<ngay>.json + .csv
"""
import argparse
import csv
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sdn_vlan_test import Lab, vpc, REPO  # noqa: E402

METRICS = [("Dist-SW1 Mbps", lambda s: s["sw"]["5"]["mbps"]), ("Dist-SW1 pps", lambda s: s["sw"]["5"]["pps"]),
           ("Dist-SW1 pkt-in/s", lambda s: s["sw"]["5"]["pktin_ps"]),
           ("Dist-SW2 Mbps", lambda s: s["sw"]["8"]["mbps"]), ("Dist-SW2 pps", lambda s: s["sw"]["8"]["pps"]),
           ("Dist-SW2 pkt-in/s", lambda s: s["sw"]["8"]["pktin_ps"]),
           ("Core-SW1 uplink Mbps", lambda s: s["core"]["Core-SW1"]["uplink_mbps"]),
           ("Core-SW1 uplink pps", lambda s: s["core"]["Core-SW1"]["uplink_pps"]),
           ("Core-SW2 uplink Mbps", lambda s: s["core"]["Core-SW2"]["uplink_mbps"]),
           ("Controller CPU %", lambda s: s["ctl"]["cpu_pct"]), ("Ryu CPU %", lambda s: s["ctl"]["ryu_cpu_pct"]),
           ("Packet-in/s tong", lambda s: s["ctl"]["pktin_ps_total"])]


def summarize(samples):
    out = {}
    for name, f in METRICS:
        vals = []
        for s in samples:
            try:
                vals.append(float(f(s)))
            except (KeyError, TypeError):
                pass
        out[name] = {"avg": round(sum(vals) / len(vals), 2) if vals else None,
                     "max": round(max(vals), 2) if vals else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=float, default=60)
    ap.add_argument("--vpc", type=int, default=19)
    ap.add_argument("--target", default="10.1.40.102")
    a = ap.parse_args()
    lab = Lab()
    phases = {}

    def window(label, extra=None):
        t_start = lab.get("/campus/load?n=1")["latest"]["ts"]
        if extra:
            extra()
        time.sleep(a.phase)
        hist = lab.get("/campus/load?n=200")["history"]
        smp = [h for h in hist if h["ts"] > t_start]
        phases[label] = {"samples": len(smp), "stats": summarize(smp)}
        print("pha %-22s %d mau" % (label, len(smp)))

    window("1 nen")
    # Luu luong: VPC ping lien tuc (luong rieng vi console VPC chan) + pinger controller
    count = int(a.phase * 2 / 0.05) + 50

    def vpc_load():
        vpc(lab_vpc, a.vpc, ["ping %s -c %d -i 50 -l 1400" % (a.target, count)])
    lab_vpc = Lab()
    th = threading.Thread(target=vpc_load, daemon=True)
    th.start()
    lab.post("/campus/pinger", {"target": a.target, "action": "reset"})
    lab.post("/campus/pinger", {"target": a.target, "action": "start", "interval": 0.02})
    window("2 luu luong")

    def cut():
        def later():
            time.sleep(a.phase / 3)
            lab2 = Lab()
            lab2.post("/campus/linktest", {"link": "D1-C1", "action": "down", "mode": "admin"})
            time.sleep(a.phase / 3)
            lab2.post("/campus/linktest", {"link": "D1-C1", "action": "up", "mode": "admin"})
        threading.Thread(target=later, daemon=True).start()
    window("3 luu luong + su co", cut)
    lab.post("/campus/pinger", {"target": a.target, "action": "stop"})
    p = [x for x in lab.get("/campus/pinger") if x["target"] == a.target][0]
    res = {"phase_seconds": a.phase, "phases": phases,
           "pinger": {k: p[k] for k in ("sent", "loss_pct", "rtt_avg", "jitter")}}
    out_dir = os.path.join(REPO, "log", "sdn-eval")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json.dump(res, open(os.path.join(out_dir, "load_%s.json" % stamp), "w", encoding="utf-8"), indent=1)
    names = list(phases)
    with open(os.path.join(out_dir, "load_%s.csv" % stamp), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chi so"] + ["%s (tb)" % n for n in names] + ["%s (dinh)" % n for n in names])
        for m, _ in METRICS:
            w.writerow([m] + [phases[n]["stats"][m]["avg"] for n in names] +
                       [phases[n]["stats"][m]["max"] for n in names])
    print("\n%-22s" % "chi so (trung binh)" + "".join("%18s" % n for n in names))
    for m, _ in METRICS:
        print("%-22s" % m + "".join("%18s" % phases[n]["stats"][m]["avg"] for n in names))
    print("\nping controller->%s: %s" % (a.target, res["pinger"]))
    print("CSV/JSON: log/sdn-eval/load_%s.*" % stamp)


if __name__ == "__main__":
    main()
