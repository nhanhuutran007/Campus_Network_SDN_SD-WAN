"""sdn_perf_test.py [--count 5] [--extra 10.1.40.102:40]

Bai thu muc tieu 3 (hieu nang giua cac VLAN) trong campus chinh Site 100:
  - VPC14/19 (VLAN 10), VPC20/21 (20), VPC15/16 (30), VPC17 (40) lay IP qua DHCP
  - moi VPC nguon (chay SONG SONG) ping tung dich (VPC con lai + --extra) --count goi
  - tinh RTT tb/min/max, jitter (trung binh |RTT_i - RTT_{i-1}|), mat goi
  - day ket qua len controller POST /campus/perf (tab Hieu nang) + ghi CSV
"""
import argparse
import csv
import json
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sdn_vlan_test import Lab, vpc, REPO  # noqa: E402

VPCS = {14: 10, 19: 10, 20: 20, 21: 20, 15: 30, 16: 30, 17: 40}
RTT = re.compile(r"bytes from ([\d.]+) icmp_seq=\d+ ttl=\d+ time=([\d.]+) ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--extra", default="10.1.40.102:40", help="dich them ip:vlan (PC Linux)")
    a = ap.parse_args()
    lab = Lab()
    ips = {}
    for n in VPCS:
        out = vpc(lab, n, ["ip dhcp"])
        m = re.search(r"DORA IP ([\d.]+)/", out)
        if m:
            ips[n] = m.group(1)
        print("VPC%d VLAN %d -> %s" % (n, VPCS[n], ips.get(n, "KHONG CO IP")))
    dsts = [(ip, VPCS[n], "VPC%d" % n) for n, ip in ips.items()]
    if a.extra:
        ip, v = a.extra.split(":")
        dsts.append((ip, int(v), ip))
    rows, lock = [], threading.Lock()

    def worker(n):
        my = Lab()
        targets = [d for d in dsts if d[0] != ips[n]]
        out = vpc(my, n, ["ping %s -c %d" % (d[0], a.count) for d in targets])
        for ip, v, name in targets:
            rtts = [float(t) for src, t in RTT.findall(out) if src == ip]
            jit = (sum(abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))) / (len(rtts) - 1)
                   if len(rtts) > 1 else None)
            with lock:
                rows.append({"src": "VPC%d" % n, "src_vlan": VPCS[n], "dst": name, "dst_vlan": v,
                             "sent": a.count, "recv": len(rtts),
                             "avg": round(sum(rtts) / len(rtts), 3) if rtts else None,
                             "min": min(rtts) if rtts else None, "max": max(rtts) if rtts else None,
                             "jitter": round(jit, 3) if jit is not None else None})
    th = [threading.Thread(target=worker, args=(n,)) for n in ips]
    t0 = time.time()
    for t in th:
        t.start()
    for t in th:
        t.join()
    print("Do %d cap trong %.0f s" % (len(rows), time.time() - t0))
    summ = lab.post("/campus/perf", {"rows": rows, "count": a.count})
    print("Trong VLAN: %s" % summ.get("intra_vlan"))
    print("Khac VLAN : %s" % summ.get("inter_vlan"))
    out_dir = os.path.join(REPO, "log", "sdn-eval")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "perf_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["src_vlan"], r["src"], r["dst_vlan"], r["dst"])))
    print("CSV:", os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
