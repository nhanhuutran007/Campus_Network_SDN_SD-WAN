#!/usr/bin/env python3
"""branch_failover_test.py : do RTO khi cat that lien ket cua vEdge. CHAY TREN SERVER EVE (root).

Cat bang `ip link set <tap> down` tren server, tuong duong rut day: thiet bi khong thay su kien link.
May tram la namespace cua sdn_stress_test.py (phai `up` truoc). Hai dau do icmp_probe.py cung chay, 5 goi/giay:
  - luong moi: moi goi mot ICMP id (nhu ket noi moi);
  - luong dang chay: giu nguyen id (nhu ket noi dai, bi tuong lua gan vao duong cu neu khong co floating-conn).

  branch_failover_test.py --name s500-mpls --src s500 --dst 10.2.60.241 --taps vunl0_65_2 --reps 5 --hold 60
  branch_failover_test.py --name s500-nen --src s500 --dst 10.2.60.241 --baseline 300

RTO = tu luc cat toi goi tra loi dau tien sau khoang im lang lon nhat. Them vao /root/loadtest/failover.jsonl
"""
import argparse, json, os, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/root/loadtest/failover.jsonl"


def probe(a, secs, same):
    f = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json")
    cmd = ["ip", "netns", "exec", "lt_" + a.src, "python3", os.path.join(HERE, "icmp_probe.py"), a.dst, str(secs)]
    if same:
        cmd.append("--same-id")
    return subprocess.Popen(cmd, stdout=f), f.name


def result(p):
    pr, name = p
    pr.wait()
    d = json.load(open(name))
    os.unlink(name)
    return d


def outage(rx, t_event, t_end):
    """Khoang im lang lon nhat co diem ket thuc sau moc su kien; tra ve (giay tu moc toi luc thong lai, do dai)."""
    best = None
    for a, b in zip(rx, rx[1:]):
        if b[1] <= t_event or a[1] >= t_end:
            continue
        g = b[1] - a[1]
        if best is None or g > best[1]:
            best = (b[1] - t_event, g)
    return (round(best[0], 2), round(best[1], 2)) if best else (None, None)


def save(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False), flush=True)


def baseline(a):
    d = result(probe(a, a.baseline, False))
    rtt = sorted(r[1] - r[0] for r in d["rx"])
    gaps = sorted(((y[1] - x[1]) for x, y in zip(d["rx"], d["rx"][1:])), reverse=True)[:5]
    save({"name": a.name, "test": "baseline", "src": a.src, "dst": a.dst, "secs": a.baseline, "sent": d["sent"],
          "recv": d["recv"], "loss_pct": round(100.0 * (d["sent"] - d["recv"]) / d["sent"], 2) if d["sent"] else None,
          "rtt_median_ms": round(rtt[len(rtt) // 2] * 1000, 1) if rtt else None,
          "rtt_p95_ms": round(rtt[int(len(rtt) * .95)] * 1000, 1) if rtt else None,
          "rtt_max_ms": round(rtt[-1] * 1000, 1) if rtt else None, "gaps_top": [round(g, 2) for g in gaps]})


def run(a):
    taps = a.taps.split(",")
    for i in range(a.reps):
        total = a.settle + a.hold + a.settle_back
        n, s = probe(a, total, False), probe(a, total, True)
        time.sleep(a.settle)
        t_cut = time.time()
        for t in taps:
            subprocess.run(["ip", "link", "set", t, "down"])
        time.sleep(a.hold)
        t_up = time.time()
        for t in taps:
            subprocess.run(["ip", "link", "set", t, "up"])
        dn, ds = result(n), result(s)
        rec = {"name": a.name, "test": "cut", "run": i + 1, "src": a.src, "dst": a.dst, "taps": taps, "hold": a.hold}
        for k, d in (("new", dn), ("same", ds)):
            rec["rto_" + k], rec["gap_" + k] = outage(d["rx"], t_cut, t_up - 0.5)
            rec["back_" + k], rec["backgap_" + k] = outage(d["rx"], t_up, t_up + a.settle_back)
            rec["sent_" + k], rec["recv_" + k] = d["sent"], d["recv"]
        save(rec)
        time.sleep(a.gap)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--taps", default="")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--hold", type=int, default=60)
    ap.add_argument("--settle", type=int, default=15)
    ap.add_argument("--settle-back", dest="settle_back", type=int, default=45)
    ap.add_argument("--gap", type=int, default=30)
    ap.add_argument("--baseline", type=int, default=0)
    a = ap.parse_args()
    baseline(a) if a.baseline else run(a)
