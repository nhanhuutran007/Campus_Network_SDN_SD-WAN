# usage: python3 bhash.py <labdir> <out>  -> lines "<rel> <size> <md5-per-4MiB,...>"
import os, sys, hashlib
B = 4 << 20
root, out = sys.argv[1], sys.argv[2]
with open(out + ".part", "w") as o:
    for n in sorted(os.listdir(root), key=lambda s: int(s) if s.isdigit() else 0):
        if not n.isdigit() or n == "33":
            continue
        f = os.path.join(root, n, "virtioa.qcow2")
        if not os.path.isfile(f):
            continue
        hs = []
        with open(f, "rb") as fh:
            while True:
                b = fh.read(B)
                if not b:
                    break
                hs.append(hashlib.md5(b).hexdigest()[:16])
        o.write("%s %d %s\n" % (n, os.path.getsize(f), ",".join(hs)))
        o.flush()
os.rename(out + ".part", out)
