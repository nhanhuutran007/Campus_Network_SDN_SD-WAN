# python3 bread.py <file> <idxfile>  -> raw 4MiB blocks to stdout in idx order
import sys
B = 4 << 20
f = open(sys.argv[1], "rb"); out = sys.stdout.buffer
for ln in open(sys.argv[2]):
    i = int(ln); f.seek(i * B); out.write(f.read(B).ljust(B, b"\0"))
out.flush()
