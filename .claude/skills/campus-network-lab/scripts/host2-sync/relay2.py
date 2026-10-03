"""gzip-stream host1:src -> PC -> host2:dst, md5 compared at both ends.
python relay2.py <src> <dst> [owner]   (several pairs: relay2.py -l listfile, lines 'src|dst|owner')"""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(__file__))
from eve import client


def q(p):
    return "'" + p.replace("'", "'\\''") + "'"


def one(src, dst, owner=""):
    a, b = client("h1"), client("h2")
    for c in (a, b):
        c.get_transport().window_size = 2 ** 27
    md5a = {}
    t = threading.Thread(target=lambda: md5a.setdefault("v", a.exec_command("md5sum " + q(src))[1].read().decode().split()[0]))
    t.start()
    _, ao, _ = a.exec_command("gzip -1 -c " + q(src))
    d = os.path.dirname(dst)
    bi, bo, be = b.exec_command("mkdir -p %s && gunzip -c > %s.part && md5sum %s.part" % (q(d), q(dst), q(dst)))
    t0, n = time.time(), 0
    ch = ao.channel
    while True:
        blk = ch.recv(1 << 20)
        if not blk:
            break
        bi.write(blk); n += len(blk)
    bi.channel.shutdown_write()
    mb = bo.read().decode().split()
    t.join()
    ok = mb and mb[0] == md5a.get("v")
    if ok:
        cmd = "mv -f %s.part %s" % (q(dst), q(dst))
        if owner:
            cmd += " && chown %s %s && chmod 664 %s" % (owner, q(dst), q(dst))
        b.exec_command(cmd)[1].read()
    print("%s %s gz=%dMB %.0fs md5=%s" % ("OK" if ok else "MISMATCH", dst, n >> 20, time.time() - t0, md5a.get("v")), flush=True)
    a.close(); b.close()
    return ok


if __name__ == "__main__":
    if sys.argv[1] == "-l":
        for ln in open(sys.argv[2]):
            if ln.strip() and not ln.startswith("#"):
                p = ln.strip().split("|")
                if os.path.exists("done.txt") and p[1] in open("done.txt").read():
                    print("SKIP (done)", p[1]); continue
                for attempt in range(3):
                    try:
                        if one(p[0], p[1], p[2] if len(p) > 2 else ""):
                            open("done.txt", "a").write(p[1] + "\n"); break
                    except Exception as e:
                        print("retry", attempt + 1, p[1], repr(e)[:120], flush=True); time.sleep(60)
                else:
                    print("FAILED", p[1], flush=True)
    else:
        one(*sys.argv[1:])
