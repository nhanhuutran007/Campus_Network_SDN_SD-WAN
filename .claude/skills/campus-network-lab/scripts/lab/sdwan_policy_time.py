#!/usr/bin/env python3
"""sdwan_policy_time.py [so_lan] : do thoi gian ap/go chinh sach SD-WAN tap trung. CHAY TREN SERVER EVE (qua runsrv.py).

Them sequence 5 (drop ICMP 10.2.60.241 -> 10.1.90.241) vao data-policy DP_BRANCH tren vSmart roi commit;
dau do ICMP 20 goi/giay tu Server Farm (lt_farm) toi may tram Site 200 (lt_s200) cho biet luc mat phang du lieu
tai vEdge Site 200 bat dau chan. Sau do go sequence va commit, do luc thong lai. Dong ho deu la cua server.
  t_ap  = goi bi chan dau tien - luc gui lenh commit
  t_go  = goi thong lai dau tien - luc gui lenh commit go
Luon go sequence khi ket thuc. Ghi /root/loadtest/policy_time.jsonl
"""
import json, os, subprocess, sys, tempfile, time
from scon import Con

cred = json.load(sys.stdin)
PW = cred["vSmart (34)"]
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
OUT = "/root/loadtest/policy_time.jsonl"
SRC, DST, IV = "farm", "10.2.60.241", 0.05
SEQ = "policy data-policy DP_BRANCH vpn-list VPN_LAN sequence 5"
ADD = [SEQ + " match protocol 1", SEQ + " match source-ip 10.2.60.241/32", SEQ + " match destination-ip 10.1.90.241/32",
       SEQ + " action drop count TEST_ENF"]
HERE = os.path.dirname(os.path.abspath(__file__))


def log(rec):
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def probe(secs):
    f = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json")
    p = subprocess.Popen(["ip", "netns", "exec", "lt_" + SRC, "python3", os.path.join(HERE, "icmp_probe.py"), DST, str(secs),
                          "--interval", str(IV)], stdout=f)
    return p, f.name


def cfg(con, lines):
    """vao config, go cac dong (chua commit). Dung neu co loi cu phap."""
    con.cmd("config", 10)
    for l in lines:
        o = con.cmd(l, 15)
        if "rror" in o or "nvalid" in o:
            con.cmd("abort", 10)
            raise RuntimeError("loi cau hinh: %r" % o[-200:])
        con.cmd("top", 10)


def commit(con):
    t0 = time.time()
    o = con.cmd("commit", 90)
    t1 = time.time()
    if "Commit complete" not in o:
        con.cmd("abort", 10)
        raise RuntimeError("commit loi: %r" % o[-300:])
    con.cmd("end", 10)
    return t0, t1


def present(con):
    return "sequence 5" in con.cmd("show running-config policy data-policy DP_BRANCH | include sequence", 20)


con = Con(34)
did = con.login(PW)
try:
    if present(con):
        cfg(con, ["no " + SEQ])
        commit(con)
    for i in range(REPS):
        p, name = probe(50)
        time.sleep(8)
        cfg(con, ADD)
        a0, a1 = commit(con)
        time.sleep(15)
        cfg(con, ["no " + SEQ])
        r0, r1 = commit(con)
        p.wait()
        d = json.load(open(name))
        os.unlink(name)
        tx = [r[0] for r in d["rx"]]  # thoi diem gui cua cac goi co tra loi
        gap = max(zip(tx, tx[1:]), key=lambda g: g[1] - g[0]) if len(tx) > 1 else (None, None)
        rec = {"test": "data-policy", "run": i + 1, "sent": d["sent"], "recv": len(tx), "interval": IV,
               "commit_ap_s": round(a1 - a0, 2), "commit_go_s": round(r1 - r0, 2)}
        if gap[0] and gap[1] - gap[0] > 1:
            rec.update({"t_ap_s": round(gap[0] + IV - a0, 2), "t_go_s": round(gap[1] - r0, 2),
                        "chan_s": round(gap[1] - gap[0] - IV, 2),
                        "truoc_commit_mat": sum(1 for a, b in zip(tx, tx[1:]) if b < a0 and b - a > 3 * IV)})
        else:
            rec["loi"] = "khong thay khoang chan"
        log(rec)
        time.sleep(10)
finally:
    try:
        if present(con):
            cfg(con, ["no " + SEQ])
            commit(con)
        log({"test": "ket-thuc", "sequence5_con": present(con)})
    finally:
        con.close(did)
