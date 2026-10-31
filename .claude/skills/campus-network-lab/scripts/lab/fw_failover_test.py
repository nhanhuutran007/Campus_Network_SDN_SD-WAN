"""fw_failover_test.py <ten-kich-ban> <node-id-trigger> <ios|asa|host> "<lenh;;lenh>" [warmup] [sau]

Do gian doan khi failover FW-ASAv HA Site 100: ping lien tuc tu Core-SW1 (Vlan10 -> 8.8.8.8, Internet)
va Core-SW2 (Vlan90 -> 10.2.1.1, Site 200 qua SD-WAN), gay su co bang lenh console (hoac lenh tren host EVE),
ghi thoi diem tung goi '!'/'.' roi tinh RTO (khoang khong co goi thanh cong) va so goi mat.
Ket qua: log/fw-failover/<kich-ban>_<thoi-gian>.csv (+ in tom tat).
"""
import csv, os, sys, threading, time
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client, password, PORT_BASE
sys.stdout.reconfigure(encoding="utf-8")

FLOWS = [  # (ten, node Core, lenh ping)
    ("S100-VLAN10->Internet", 3, "ping 8.8.8.8 source Vlan10 repeat 100000 timeout 1"),
    ("S100-VLAN90->Site200", 4, "ping 10.2.1.1 source Vlan90 repeat 100000 timeout 1"),
]


def drain(ch, quiet=1.5, limit=20):
    buf, t0, last = "", time.time(), time.time()
    while time.time() - t0 < limit:
        try:
            d = ch.recv(65535)
            if d:
                buf += d.decode(errors="replace"); last = time.time(); continue
        except Exception:
            pass
        if time.time() - last > quiet:
            break
        time.sleep(0.05)
    return buf


def console(ssh, nid, kind):
    ch = ssh.get_transport().open_channel("direct-tcpip", ("127.0.0.1", PORT_BASE + nid), ("127.0.0.1", 0))
    ch.settimeout(0.2); ch.send("\r"); o = drain(ch)
    last = o.strip().splitlines()[-1] if o.strip() else ""
    if last.endswith(">"):
        ch.send("enable\r"); o = drain(ch)
        if kind == "asa" and "assword" in o:
            ch.send(password("FW-ASAv 1, 2") + "\r"); drain(ch)
    ch.send("terminal pager 0\r" if kind == "asa" else "terminal length 0\r"); drain(ch)
    return ch


def run_flow(ssh, name, nid, cmd, stop, events):
    ch = console(ssh, nid, "ios"); ch.send(cmd + "\r")
    head = ""  # bo qua header (dong "source address of 10.x.x.x" co dau cham)
    while not stop.is_set():
        try:
            d = ch.recv(65535).decode(errors="replace")
        except Exception:
            continue
        now = time.time()
        if head is not None:
            head += d
            if "source address of" not in head or "\n" not in head.split("source address of", 1)[1]:
                continue
            d = head.split("source address of", 1)[1].split("\n", 1)[1]; head = None
        for c in d:
            if c in "!.U":
                events.append((now, name, c))
    ch.send("\x1e"); time.sleep(0.5); ch.send("\x1ex"); drain(ch, 1, 4); ch.close()


def main():
    scen, tnode, tkind, tcmds = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(";;")
    warm = float(sys.argv[5]) if len(sys.argv) > 5 else 15
    after = float(sys.argv[6]) if len(sys.argv) > 6 else 90
    ssh = client("h1"); stop = threading.Event(); events = []
    th = [threading.Thread(target=run_flow, args=(ssh, n, i, c, stop, events), daemon=True) for n, i, c in FLOWS]
    for t in th:
        t.start()
    time.sleep(warm)
    t_trig = time.time()
    if tkind == "host":
        for c in tcmds:
            _, o, _ = ssh.exec_command(c, timeout=60); o.read()
    else:
        ch = console(ssh, int(tnode), tkind)
        for c in tcmds:
            ch.send(c + "\r"); time.sleep(1.5)
        ch.close()
    print(f"trigger {datetime.fromtimestamp(t_trig):%H:%M:%S} -> {tcmds}")
    time.sleep(after); stop.set()
    for t in th:
        t.join(10)
    ssh.close()
    os.makedirs("log/fw-failover", exist_ok=True)
    out = f"log/fw-failover/{scen}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["epoch", "rel_s", "flow", "result"])
        for ts, n, c in sorted(events):
            w.writerow([f"{ts:.3f}", f"{ts - t_trig:.3f}", n, c])
    print("file", out)
    for n, _, _ in FLOWS:
        ev = [(ts, c) for ts, f, c in sorted(events) if f == n]
        ok = [ts for ts, c in ev if c == "!"]
        lost = sum(1 for ts, c in ev if c != "!" and ts >= t_trig)
        gaps = [(b - a, a) for a, b in zip(ok, ok[1:]) if b >= t_trig]
        g, at = max(gaps) if gaps else (0, t_trig)
        print(f"{n}: gui {len(ev)}, mat {lost} sau trigger, RTO {g:.2f} s (tu +{at - t_trig:.1f} s)")


if __name__ == "__main__":
    main()
