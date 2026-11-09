#!/usr/bin/env python3
"""node_sampler.py <nhan> <giay> [chu_ky] : CPU/RAM tung node nhin tu server (khong dang nhap thiet bi). Them vao /root/loadtest/node_cpu.jsonl"""
import json, os, re, sys, time

LAB = "/opt/unetlab/tmp/0/"
HZ = os.sysconf("SC_CLK_TCK")


def snap():
    r = {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            cwd = os.readlink("/proc/%s/cwd" % p)
            if not cwd.startswith(LAB):
                continue
            m = re.search(r"/(\d+)$", cwd)
            if not m:
                continue
            s = open("/proc/%s/stat" % p).read().rsplit(")", 1)[1].split()
            cpu = int(s[11]) + int(s[12])
            rss = int(s[21]) * 4096 / 1048576
            n = int(m.group(1))
            a = r.setdefault(n, [0, 0.0])
            a[0] += cpu
            a[1] += rss
        except (OSError, IndexError, ValueError):
            pass
    return r, time.time()


label, secs = sys.argv[1], float(sys.argv[2])
per = float(sys.argv[3]) if len(sys.argv) > 3 else 30
end = time.time() + secs
a, ta = snap()
with open("/root/loadtest/node_cpu.jsonl", "a") as f:
    while time.time() < end:
        time.sleep(per)
        b, tb = snap()
        cpu = {n: round((b[n][0] - a[n][0]) / HZ / (tb - ta) * 100, 1) for n in b if n in a}
        f.write(json.dumps({"label": label, "ts": time.strftime("%H:%M:%S"), "load": float(open("/proc/loadavg").read().split()[0]),
                            "cpu": cpu, "rss_mb": {n: round(b[n][1]) for n in b}}) + "\n")
        f.flush()
        a, ta = b, tb
