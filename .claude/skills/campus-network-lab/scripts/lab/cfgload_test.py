"""cfgload_test.py <node> <tag mat khau> <file_ra.jsonl> [so_lan] : do thoi gian nap cau hinh mot vEdge qua console. Chay tren laptop.

Buoc 1 luu running-config. Moi lan do: go VPN dich vu (`no vpn 1`, commit) de lan nap sau la thay doi that, roi dan lai
toan bo running-config da luu (tru khoi aaa) va commit; do tu dong dau tien toi "Commit complete".
Cuoi cung so running-config voi ban da luu: phai trung khop.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client, password, PORT_BASE

NID, TAG, OUT = int(sys.argv[1]), sys.argv[2], sys.argv[3]
REPS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ssh = client("h1")
ch = ssh.get_transport().open_channel("direct-tcpip", ("127.0.0.1", PORT_BASE + NID), ("127.0.0.1", 0))
ch.settimeout(0.1)


def expect(pat, to=30):
    buf, t0 = "", time.time()
    while time.time() - t0 < to:
        try:
            buf += ANSI.sub("", ch.recv(65535).decode(errors="replace"))
        except Exception:
            pass
        if re.search(pat, buf[-300:]):
            return buf
    raise TimeoutError(repr(buf[-200:]))


def cmd(c, to=60):
    ch.send(c + "\r")
    return expect(r"# ?$", to)


def commit(to=120):
    """commit; thong bao he thong co the chen vao console sau "Commit complete" nen khong cho prompt"""
    ch.send("commit\r")
    o = expect(r"Commit complete|Aborted|rror", to)
    assert "Commit complete" in o, o[-200:]
    t = time.time()
    time.sleep(4)
    ch.send("\r")
    expect(r"# ?$", 20)
    return t


def running():
    o = cmd("show running-config | nomore", 60).replace("\r", "")
    body = o.split("show running-config | nomore", 1)[-1]
    return [l.rstrip() for l in body.split("\n") if l.strip() and not re.search(r"# ?$", l)]


ch.send("\r")
o = expect(r"(login: ?$|# ?$)", 20)
did = False
if re.search(r"login: ?$", o[-30:]):
    ch.send("admin\r")
    expect(r"Password: ?$", 15)
    ch.send(password(TAG) + "\r")
    o = expect(r"(login: ?$|# ?$)", 40)
    if re.search(r"login: ?$", o[-30:]):
        raise SystemExit("LOGIN FAILED")
    did = True
cmd("paginate false")
before = running()
# bo khoi aaa (chua mat khau bam) khoi phan dan lai
paste, skip = [], False
for l in before:
    if l == " aaa":
        skip = True
        continue
    if skip:
        if l == " !":
            skip = False
        continue
    paste.append(l)
print("so dong cau hinh:", len(before), "dan lai:", len(paste), flush=True)
try:
    for i in range(REPS):
        cmd("config")
        cmd("no vpn 1")
        commit()
        cmd("end")
        time.sleep(5)
        cmd("config")
        t0 = time.time()
        for l in paste:
            o = cmd(l, 20)
            if "syntax error" in o or "Error" in o:
                raise RuntimeError("dong %r: %r" % (l, o[-150:]))
        t1 = time.time()
        t2 = commit()
        cmd("end")
        after = running()
        rec = {"node": NID, "run": i + 1, "dong": len(paste), "dan_s": round(t1 - t0, 1), "commit_s": round(t2 - t1, 1),
               "tong_s": round(t2 - t0, 1), "khop_cau_hinh": after == before, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        if after != before:
            rec["khac"] = [l for l in before if l not in after][:5] + ["+" + l for l in after if l not in before][:5]
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        open(OUT, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        if after != before:
            break
        time.sleep(20)
finally:
    if did:
        ch.send("end\r")
        time.sleep(1)
        ch.send("exit\r")
        time.sleep(1)
    ch.close()
    ssh.close()
