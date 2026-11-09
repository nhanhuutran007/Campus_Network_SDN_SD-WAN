#!/usr/bin/env python3
"""hc.py : kiem tra suc khoe (chi doc) server + lab, chay tren server. In tung dong, dong cuoi OK/CANH BAO."""
import json, os, subprocess, sys, urllib.request

def sh(c, t=60):
    try:
        return subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=t).stdout.strip()
    except subprocess.TimeoutExpired:
        return "TIMEOUT"

warn = []
load = float(open("/proc/loadavg").read().split()[0])
mem = sh("free -g | sed -n 2p").split()
lock = sh('journalctl -k --since "-15 min" --no-pager | grep -cE "soft lockup|hung_task|blocked for|oom-kill|rcu.*stall"')
print("server: load %.1f/48, RAM dung %s/%s GB, lockup 15 phut: %s, uptime tu %s" % (load, mem[2], mem[1], lock, sh("uptime -s")))
if load > 36:
    warn.append("load cao")
if lock not in ("0", ""):
    warn.append("co lockup")

down = [t for t in sh("ls /sys/class/net | grep '^vunl0_'").split() if open("/sys/class/net/%s/operstate" % t).read().strip() == "down"]
print("tap down:", down or "khong")
if down:
    warn.append("tap down")

ns = "ip netns exec lt_mgmt "
t = sh(ns + "curl -s -m 8 http://10.1.99.10:8080/campus/topology")
try:
    j = json.loads(t)
    sw = sum(1 for n in j["nodes"] if n.get("connected"))
    lk = j.get("links") or []
    up = sum(1 for l in lk if l.get("up", l.get("connected", True)))
    print("Ryu: %d switch ket noi, %d/%d link" % (sw, up, len(lk)))
    if sw != 6:
        warn.append("Ryu %d/6" % sw)
except Exception as e:
    print("Ryu: khong doc duoc", t[:80])
    warn.append("Ryu loi")

T = [("s500", "10.5.10.1"), ("s500", "10.2.60.241"), ("s500", "10.3.90.241"), ("s500", "10.4.50.241"), ("s500", "10.1.90.10"), ("s500", "8.8.8.8"),
     ("s200", "10.3.90.241"), ("s200", "10.4.50.241"), ("s300", "10.4.50.241"), ("a1", "10.1.40.241"), ("a1", "10.1.90.241"), ("a1", "10.1.1.13"), ("a1", "8.8.8.8"), ("farm", "10.2.60.241")]
for n, d in T:
    o = sh("ip netns exec lt_%s ping -q -n -c 5 -i 0.3 -W 2 %s | tail -2 | tr '\\n' ' '" % (n, d), 20)
    rx = o.split(" received")[0].split()[-1] if " received" in o else "?"
    print(" %-5s -> %-13s nhan %s/5" % (n, d, rx))
    if rx in ("0", "?"):
        warn.append("%s->%s" % (n, d))
print("KET LUAN:", "OK" if not warn else "CANH BAO " + ", ".join(warn))
