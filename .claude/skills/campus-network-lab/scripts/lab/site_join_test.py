#!/usr/bin/env python3
"""site_join_test.py [so_lan] : do thoi gian mot site gia nhap fabric SD-WAN. CHAY TREN SERVER EVE (qua runsrv.py).

Tat ca hai vEdge cua Site 500 (node 65, 23) de site roi khoi fabric, cho cac site khac xoa tuyen, roi bat lai.
Moc 0 = luc ra lenh bat nguon. Ghi cac moc (giay):
  ctrl  : vSmart thay control connection cua vEdge dau tien / ca hai
  omp   : phien OMP voi vSmart len (dau tien / ca hai)
  bfd1  : vEdge1 Site 200 co phien BFD dau tien toi Site 500
  bfd_all : du so phien BFD nhu truoc khi tat
  ping  : goi ICMP dau tien tu Server Farm (lt_farm) toi mang LAN Site 500 (lt_c500, 10.5.1.1) co tra loi
Khong doi cau hinh thiet bi nao. Ghi /root/loadtest/site_join.jsonl
"""
import json, os, re, subprocess, sys, tempfile, time
from scon import Con

cred = json.load(sys.stdin)
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = "/root/loadtest/site_join.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))
NODES, SYS = ["65", "23"], "10.200.50."
DOWN_WAIT, LIMIT = 90, 720


def sh(c):
    return subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True).stdout


def log(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ns_c500():
    if os.path.exists("/var/run/netns/lt_c500"):
        return
    if sh("ss -tln | grep -c ':%d '" % (32768 + 67)).strip() != "0":
        raise SystemExit("Brand-FW Site 500 dang chay: khong tao namespace trung dia chi")
    sh("ip netns add lt_c500; ip link add v_c500 type veth peer name e0 netns lt_c500; ip link set v_c500 master vnet0_100 up")
    sh("ip netns exec lt_c500 ip link set lo up; ip netns exec lt_c500 ip link set e0 up")
    sh("ip netns exec lt_c500 ip addr add 10.5.1.1/30 dev e0; ip netns exec lt_c500 ip route add default via 10.5.1.2")


def state(vs, ve):
    c = vs.cmd("show control connections | include " + SYS, 30)
    o = vs.cmd("show omp peers | include " + SYS, 30)
    b = ve.cmd("show bfd sessions | include " + SYS, 30)
    ctrl = set(re.findall(r"(10\.200\.50\.\d+)\s.*\sup\s", c))
    omp = set(re.findall(r"(10\.200\.50\.\d+)\s.*\sup\s", o))
    bfd = len(re.findall(r"^10\.200\.50\.\d+\s+\d+\s+up\s", b, re.M))
    return ctrl, omp, bfd


ns_c500()
vs, ve = Con(34), Con(29)
d1, d2 = vs.login(cred["vSmart (34)"]), ve.login(cred["vEdge chi nhánh"])
try:
    for i in range(REPS):
        ctrl, omp, bfd0 = state(vs, ve)
        log({"test": "truoc", "run": i + 1, "ctrl": sorted(ctrl), "omp": sorted(omp), "bfd": bfd0})
        if len(ctrl) < 2 or bfd0 == 0:
            log({"test": "bo-qua", "ly_do": "site 500 chua day du truoc khi do"})
            break
        f = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt")
        # ping -D in dau thoi gian tung goi tra loi; dung duoc giua chung (icmp_probe chi in ket qua khi chay het)
        p = subprocess.Popen(["ip", "netns", "exec", "lt_farm", "ping", "-D", "-n", "-i", "0.2", "-W", "1", "10.5.1.1"], stdout=f)
        time.sleep(10)
        t_stop = time.time()
        sh("/root/stopn.sh " + " ".join(NODES))
        try:
            time.sleep(DOWN_WAIT)
            ctrl, omp, bfd = state(vs, ve)
        finally:  # du co loi console cung phai bat lai node
            t0 = time.time()
            st = sh("/root/startn.sh " + " ".join(NODES)).split("\n")
        m = {"start_cmd_s": round(time.time() - t0, 1)}
        while time.time() - t0 < LIMIT:
            ctrl, omp, bfd = state(vs, ve)
            t = round(time.time() - t0, 1)
            for k, ok in (("ctrl_1", len(ctrl) >= 1), ("ctrl_2", len(ctrl) >= 2), ("omp_1", len(omp) >= 1), ("omp_2", len(omp) >= 2),
                          ("bfd_1", bfd >= 1), ("bfd_all", bfd >= bfd0)):
                if ok and k not in m:
                    m[k] = t
            if "bfd_all" in m and "omp_2" in m:
                break
            time.sleep(2)
        time.sleep(15)
        p.terminate()
        p.wait()
        rx = [[float(x)] for x in re.findall(r"^\[(\d+\.\d+)\] 64 bytes", open(f.name).read(), re.M)]
        os.unlink(f.name)
        first = next((r[0] for r in rx if r[0] > t0), None)
        last_before = max((r[0] for r in rx if r[0] < t0), default=None)
        m.update({"test": "join", "run": i + 1, "bfd_muc_tieu": bfd0, "start": st[:2],
                  "ping_s": round(first - t0, 1) if first else None,
                  "mat_sau_tat_s": round(last_before - t_stop, 1) if last_before else None})
        log(m)
        time.sleep(60)
finally:
    vs.close(d1)
    ve.close(d2)
    sh("ip link del v_c500 2>/dev/null; ip netns del lt_c500 2>/dev/null")
    log({"test": "ket-thuc"})
