import sys
p = sys.argv[1]
b = open(p, "rb").read()
r = [(b'<node id="64" name="SwitchBrand"', b'<node id="75" name="SwitchBrand"'), (b'<config id="64">', b'<config id="75">')]
for o, n in r:
    assert b.count(o) == 1, o
    assert b.count(n.split(b' name')[0] if b'node' in n else n) == 0, n
    b = b.replace(o, n)
open(p, "wb").write(b)
print("patched")
