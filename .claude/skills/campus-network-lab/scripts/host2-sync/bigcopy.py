"""Resumable copy of a big file host1 -> host2 in 1 GiB chunks (4 MiB blocks, gzip), md5 per chunk.
python bigcopy.py <src-on-h1> <dst-on-h2>   progress in bigcopy_done.txt; final full md5 compare."""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eve import client
B = 4 << 20
CH = 256  # blocks per chunk = 1 GiB

def run(c, cmd):
    _, o, e = c.exec_command(cmd)
    return o.read().decode().strip()

def same(src, dst, k, nblk):
    """md5 of chunk k on both hosts (parallel); True if identical -> already copied."""
    first, last = k * CH, min((k + 1) * CH, nblk)
    dd = "dd if=%s bs=4M skip=%d count=%d 2>/dev/null | md5sum" % ("{}", first, last - first)
    res = {}
    def h(tag, path):
        c = client(tag); res[tag] = run(c, dd.format(path)).split()[0]; c.close()
    ts = [threading.Thread(target=h, args=("h1", src)), threading.Thread(target=h, args=("h2", dst))]
    [t.start() for t in ts]; [t.join() for t in ts]
    return res.get("h1") == res.get("h2")


def chunk(src, dst, k, nblk, size):
    a, b = client("h1"), client("h2")
    for c in (a, b):
        c.get_transport().window_size = 2 ** 27
    first, last = k * CH, min((k + 1) * CH, nblk)
    lst = "".join("%d\n" % i for i in range(first, last))
    for c in (a, b):
        s = c.open_sftp(); fh = s.open("/tmp/idx_big.txt", "w"); fh.write(lst); fh.close(); s.close()
    _, ao, _ = a.exec_command("python3 /tmp/bread.py %s /tmp/idx_big.txt | gzip -1" % src)
    bi, bo, be = b.exec_command("gunzip -c | python3 /tmp/bwrite.py %s /tmp/idx_big.txt %d" % (dst, size))
    ch = ao.channel; tot = 0
    while True:
        blk = ch.recv(1 << 20)
        if not blk:
            break
        bi.write(blk); tot += len(blk)
    bi.channel.shutdown_write()
    r = (bo.read().decode() + be.read().decode()).strip()
    cnt = last - first
    dd = "dd if=%s bs=4M skip=%d count=%d 2>/dev/null | md5sum" % ("{}", first, cnt)
    ma = run(a, dd.format(src)).split()[0]; mb = run(b, dd.format(dst)).split()[0]
    a.close(); b.close()
    return ma == mb, tot, r

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    a = client("h1"); size = int(run(a, "stat -c %s " + src)); a.close()
    b = client("h2"); run(b, "mkdir -p %s" % os.path.dirname(dst)); b.close()
    nblk = (size + B - 1) // B; nch = (nblk + CH - 1) // CH
    done = set(open("bigcopy_done.txt").read().split()) if os.path.exists("bigcopy_done.txt") else set()
    print("%s size=%d chunks=%d" % (src, size, nch), flush=True)
    t0 = time.time()
    for k in range(nch):
        key = "%s#%d" % (dst, k)
        if key in done:
            continue
        try:
            if same(src, dst, k, nblk):
                open("bigcopy_done.txt", "a").write(key + "\n")
                print("chunk %d/%d da co san (md5 khop) - bo qua" % (k + 1, nch), flush=True)
                continue
        except Exception as e:
            print("chunk %d check retry %s" % (k + 1, repr(e)[:150]), flush=True)
        for attempt in range(5):
            try:
                ts = time.time(); ok, tot, r = chunk(src, dst, k, nblk, size)
                if ok:
                    open("bigcopy_done.txt", "a").write(key + "\n")
                    print("chunk %d/%d OK gz=%dMB %.0fs" % (k + 1, nch, tot >> 20, time.time() - ts), flush=True)
                    break
                print("chunk %d MISMATCH %s" % (k + 1, r[:100]), flush=True)
            except Exception as e:
                print("chunk %d retry %d %s" % (k + 1, attempt + 1, repr(e)[:150]), flush=True); time.sleep(60)
        else:
            print("FAILED chunk %d" % (k + 1), flush=True); sys.exit(1)
    a, b = client("h1"), client("h2")
    run(b, "chown root:unl %s; chmod 664 %s" % (dst, dst))
    ma = run(a, "md5sum " + src).split()[0]; mb = run(b, "md5sum " + dst).split()[0]
    print("%s %s md5 h1=%s h2=%s total %.0f min" % ("FILE-OK" if ma == mb else "FILE-MISMATCH", dst, ma, mb, (time.time() - t0) / 60), flush=True)
