"""aar_degrade_test.py : thu AAR khi MPLS suy giam. Chay tren laptop (doc vEdge qua console, netem qua SSH).

Tang tre tren tap MPLS cua vEdge1 Site 100 bang netem, luong ICMP 5 goi/giay tu Server Farm toi Site 200.
Moi chu ky doc bo dem tunnel, so goi gui them tren tung color; doc trung binh tre/mat cua app-route.
Co bo hen gio tren server tu go netem de khong bao gio ket tre neu laptop mat ket noi.
Ghi JSONL (duong dan la tham so dau tien).
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "host2-sync"))
from eve import client

OUT = sys.argv[1]
TAP, DELAY = "vunl0_28_3", "400ms"
DST = "100.64.200.1"
REMOTE = "10.200.200.1"
PERIOD = 60
BEFORE, DURING_MAX, AFTER_MAX = 3, 14, 12
ssh = client("h1")


def srv(cmd):
    _, o, _ = ssh.exec_command(cmd, timeout=30)
    return o.read().decode(errors="replace")


def vedge(cmds):
    r = subprocess.run([sys.executable, os.path.join(HERE, "rd.py"), "28", "vedge", ";;".join(cmds)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=150, env=os.environ)
    return r.stdout.decode(errors="replace")


def sample():
    o = vedge(["show tunnel statistics | tab | include " + DST, "show app-route stats remote-system-ip " + REMOTE])
    tx = {}
    for l in o.splitlines():
        p = l.split()
        if len(p) >= 12 and p[0] == "ipsec" and p[2] == DST:
            tx[p[6]] = int(p[9])  # local color -> tx pkts
    stats = {}
    for b in re.split(r"(?=app-route statistics )", o):
        m = re.search(r"local-color\s+(\S+)|app-route statistics \S+ \S+ \S+ \S+ \S+", b)
        c = re.search(r"\b(mpls|biz-internet)\b", b)
        if not c:
            continue
        ml = re.findall(r"mean-latency\s+(\d+)", b)
        lo = re.findall(r"mean-loss\s+(\d+)", b)
        if ml:
            stats.setdefault(c.group(1), {"lat": ml[-1], "loss": lo[-1] if lo else None})
    return tx, stats, o


def log(rec):
    rec["t"] = time.strftime("%H:%M:%S")
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def period(phase, prev):
    t0 = time.time()
    time.sleep(max(1, PERIOD))
    tx, st, raw = sample()
    dt = time.time() - t0
    d = {c: round((tx[c] - prev[c]) / dt, 1) for c in tx if c in prev}
    log({"phase": phase, "pps": d, "stats": st})
    return tx, raw


srv("nohup ip netns exec lt_farm ping -q -i 0.2 -c 9000 -W 1 10.2.60.241 >/tmp/aar_ping.txt 2>&1 &")
prev, _st, raw = sample()
print(raw[-1500:], flush=True)
for _ in range(BEFORE):
    prev, _r = period("truoc", prev)
srv("modprobe sch_netem; tc qdisc replace dev %s root netem delay %s" % (TAP, DELAY))
srv("nohup sh -c 'sleep 1300; tc qdisc del dev %s root netem' >/dev/null 2>&1 &" % TAP)
t_on = time.time()
log({"phase": "bat-netem", "qdisc": srv("tc qdisc show dev " + TAP).strip()})
moved = None
for i in range(DURING_MAX):
    prev, _r = period("suy-giam", prev)
    ppsm = json.loads(open(OUT, encoding="utf-8").read().splitlines()[-1])["pps"]
    if moved is None and ppsm.get("biz-internet", 0) > ppsm.get("mpls", 0) + 2:
        moved = round(time.time() - t_on)
        log({"phase": "da-chuyen", "sau_giay": moved})
    if moved and time.time() - t_on > moved + 2 * PERIOD:
        break
srv("tc qdisc del dev %s root netem 2>/dev/null; true" % TAP)
t_off = time.time()
log({"phase": "go-netem", "qdisc": srv("tc qdisc show dev " + TAP).strip()})
back = None
for i in range(AFTER_MAX):
    prev, _r = period("phuc-hoi", prev)
    ppsm = json.loads(open(OUT, encoding="utf-8").read().splitlines()[-1])["pps"]
    if back is None and ppsm.get("mpls", 0) > ppsm.get("biz-internet", 0) + 2:
        back = round(time.time() - t_off)
        log({"phase": "da-quay-ve", "sau_giay": back})
        break
srv("pkill -INT -f '[l]t_farm ping' ; sleep 1; for p in $(pgrep -f 'ping -q -i 0.2 -c 9000'); do kill -INT $p; done; sleep 1; tail -2 /tmp/aar_ping.txt")
log({"phase": "ket-thuc", "moved_s": moved, "back_s": back, "ping": srv("tail -2 /tmp/aar_ping.txt").strip()})
ssh.close()
