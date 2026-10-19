# python3 bwrite.py <file> <idxfile> <size>  <- raw blocks on stdin; writes in place, truncates to size
import sys, os
B = 4 << 20
fn, size = sys.argv[1], int(sys.argv[3])
if not os.path.exists(fn):
    open(fn, "wb").close()
f = open(fn, "r+b"); inp = sys.stdin.buffer
for ln in open(sys.argv[2]):
    i = int(ln); buf = b""
    while len(buf) < B:
        c = inp.read(B - len(buf))
        if not c:
            sys.exit("short stream at block %d" % i)
        buf += c
    f.seek(i * B); f.write(buf)
f.truncate(size); f.close()
print("written")
