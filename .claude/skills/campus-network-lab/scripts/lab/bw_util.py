#!/usr/bin/env python3
"""bw_util.py : tong hop muc su dung bang thong (Bandwidth Utilization). CHAY TREN SERVER EVE (root), chi doc + iperf3.

  bw_util.py idle <giay>                       nen: % su dung tung cong OVS (API /noc/ports cua Console) va toc do
                                               tren cac cong transport cua vEdge (bo dem tap tren server)
  bw_util.py lan <ns_nguon> <ns_dich> <ip_dich> <rates Mbit/s>   tai UDP qua LAN SDN, doc % su dung cong OVS khi co tai
  bw_util.py wan <ns_nguon> <ns_dich> <ip_dich> <rates Mbit/s>   tai UDP qua overlay, doc toc do tren tap transport
Can nsrelay.py (127.0.0.1:18080 -> Ryu). Ghi /root/loadtest/bw_util.jsonl
"""
import json, os, subprocess, sys, time, urllib.request

OUT = "/root/loadtest/bw_util.jsonl"
CTL = "http://127.0.0.1:18080"
VEDGE = (28, 6, 29, 42, 30, 40, 31, 41, 65, 23)


def sh(c):
    return subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True).stdout


def log(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ports():
    try:
        return json.loads(urllib.request.urlopen(CTL + "/noc/ports", timeout=5).read().decode())
    except Exception:
        return []


def taps():
    r = {}
    for t in os.listdir("/sys/class/net"):
        if t.startswith("vunl0_") and int(t.split("_")[1]) in VEDGE:
            b = "/sys/class/net/%s/statistics/" % t
            # tap: rx = VM gui ra, tx = VM nhan vao
            r[t] = (int(open(b + "rx_bytes").read()), int(open(b + "tx_bytes").read()))
    return r, time.time()


def tap_rate(a, b):
    (x, ta), (y, tb) = a, b
    return {t: [round((y[t][0] - x[t][0]) * 8 / (tb - ta) / 1000, 1), round((y[t][1] - x[t][1]) * 8 / (tb - ta) / 1000, 1)]
            for t in y if t in x}


class PortAvg:
    def __init__(self):
        self.s = {}

    def add(self):
        for p in ports():
            k = "%s %s" % (p["switch"], p["name"])
            v = self.s.setdefault(k, {"speed": p.get("speed"), "util": [], "mbps": []})
            v["util"].append(p.get("util", 0))
            v["mbps"].append((p.get("rx", 0) + p.get("tx", 0)) / 1e6)

    def result(self, top=None):
        r = {k: {"speed_mbps": round((v["speed"] or 0) / 1e6), "util_tb": round(sum(v["util"]) / len(v["util"]), 3),
                 "util_max": round(max(v["util"]), 3), "mbps_tb": round(sum(v["mbps"]) / len(v["mbps"]), 3)}
             for k, v in self.s.items() if v["util"]}
        if top:
            r = dict(sorted(r.items(), key=lambda kv: -kv[1]["util_tb"])[:top])
        return r


def iperf(src, dst, ip, rate, secs, port, length=None):
    srv = subprocess.Popen("exec ip netns exec lt_%s iperf3 -s -1 -p %d" % (dst, port), shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    time.sleep(1)
    cmd = "timeout %d ip netns exec lt_%s iperf3 -c %s -p %d -u -b %sM -t %d -J --connect-timeout 5000" % (secs + 25, src, ip, port, rate, secs)
    if length:
        cmd += " -l %d" % length
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return srv, p


def iperf_result(srv, p):
    o = p.communicate()[0]
    srv.kill()
    try:
        s = json.loads(o)["end"]["sum"]
        return {"nhan_mbps": round(s["bits_per_second"] * (1 - s["lost_percent"] / 100) / 1e6, 3), "mat_pct": round(s["lost_percent"], 2),
                "jitter_ms": round(s["jitter_ms"], 3)}
    except Exception:
        return {"loi": o[-200:]}


mode = sys.argv[1]
if mode == "idle":
    secs = int(sys.argv[2])
    a = taps()
    pa = PortAvg()
    end = time.time() + secs
    while time.time() < end:
        pa.add()
        time.sleep(5)
    log({"test": "idle", "secs": secs, "ovs_ports": pa.result(), "vedge_tap_kbps_[ra,vao]": tap_rate(a, taps())})
elif mode in ("lan", "wan"):
    src, dst, ip = sys.argv[2:5]
    for i, rate in enumerate(sys.argv[5].split(",")):
        secs = 30
        srv, p = iperf(src, dst, ip, rate, secs, 5301 + i, 1300 if mode == "wan" else None)
        time.sleep(5)
        a = taps()
        pa = PortAvg()
        t_end = time.time() + secs - 10
        while time.time() < t_end:
            pa.add()
            time.sleep(2)
        b = taps()
        rec = {"test": mode, "src": src, "dst": ip, "gui_mbps": float(rate)}
        rec.update(iperf_result(srv, p))
        if mode == "lan":
            rec["ovs_ports_top"] = pa.result(top=8)
        else:
            tr = tap_rate(a, b)
            rec["vedge_tap_kbps_[ra,vao]"] = {t: v for t, v in tr.items() if max(v) > 100}
        log(rec)
        time.sleep(8)
