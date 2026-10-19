"""python delta.py <node>...  : copy changed 4MiB blocks host1 -> host2, then full md5 compare."""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eve import client
U = "ecf7c5b8-8c91-4616-953e-10b367b388e6"
B = 4 << 20

def load(fn):
    d = {}
    for ln in open(fn):
        p = ln.split()
        d[p[0]] = (int(p[1]), p[2].split(",") if len(p) > 2 else [])
    return d

def run(c, cmd):
    _, o, e = c.exec_command(cmd)
    return o.read().decode().strip()

def node(n, A, Bh):
    sz, ha = A[n]
    hb = Bh.get(n, (0, []))[1]
    idx = [i for i, h in enumerate(ha) if i >= len(hb) or hb[i] != h]
    src = "/opt/unetlab/tmp/6/%s/%s/virtioa.qcow2" % (U, n)
    dst = "/opt/unetlab/tmp/0/%s/%s/virtioa.qcow2" % (U, n)
    a, b = client("h1"), client("h2")
    for c in (a, b):
        c.get_transport().window_size = 2 ** 27
    t0 = time.time()
    if idx:
        lst = "".join("%d\n" % i for i in idx)
        for c in (a, b):
            s = c.open_sftp(); fh = s.open("/tmp/idx_%s.txt" % n, "w"); fh.write(lst); fh.close(); s.close()
        run(b, "mkdir -p /opt/unetlab/tmp/0/%s/%s" % (U, n))
        _, ao, _ = a.exec_command("python3 /tmp/bread.py %s /tmp/idx_%s.txt | gzip -1" % (src, n))
        bi, bo, be = b.exec_command("gunzip -c | python3 /tmp/bwrite.py %s /tmp/idx_%s.txt %d" % (dst, n, sz))
        ch = ao.channel; tot = 0
        while True:
            blk = ch.recv(1 << 20)
            if not blk:
                break
            bi.write(blk); tot += len(blk)
        bi.channel.shutdown_write()
        r = bo.read().decode().strip() + be.read().decode().strip()
    else:
        tot, r = 0, "nochange"
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("a", run(a, "md5sum " + src).split()[0]))
    th.start(); mb = run(b, "chown root:unl %s; md5sum %s" % (dst, dst)).split()[0]; th.join()
    ok = mb == res["a"]
    for c in (a, b):
        run(c, "rm -f /tmp/idx_%s.txt" % n)
    print("%s node %s blocks=%d/%d gz=%dMB %.0fs %s md5=%s" % ("OK" if ok else "MISMATCH", n, len(idx), len(ha), tot >> 20, time.time() - t0, r, res["a"]), flush=True)
    a.close(); b.close()
    return ok

if __name__ == "__main__":
    A, Bh = load("h1_bh.txt"), load("h2_bh.txt")
    for n in (sys.argv[1:] or sorted(A, key=int)):
        for k in range(3):
            try:
                if node(n, A, Bh): break
                Bh.pop(n, None)  # mismatch -> full copy next try
            except Exception as e:
                print("retry", n, repr(e)[:150], flush=True); time.sleep(30)
