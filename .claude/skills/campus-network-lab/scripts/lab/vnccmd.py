"""vnccmd.py <node> <out.png> [login] "cmd" ...: type into a host1 node's VNC console via SSH tunnel, then capture the screen.
'login' first -> type eve + OVS password. Literal args: SUDOPASS types the OVS password (sudo prompts);
INV inverts letter case (Caps Lock flips on every VNC connect); CTRLC sends Ctrl+C."""
import os, sys, socket, threading, select, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client, password

node, out = int(sys.argv[1]), sys.argv[2]
args = sys.argv[3:]
s = client("h1")
tr = s.get_transport()
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(1)
lport = srv.getsockname()[1]


def pump():
    c, _ = srv.accept()
    ch = tr.open_channel("direct-tcpip", ("127.0.0.1", 33536 + node), ("127.0.0.1", 0))
    while True:
        r, _, _ = select.select([c, ch], [], [], 120)
        if not r:
            break
        for x in r:
            d = x.recv(65536)
            if not d:
                return
            (ch if x is c else c).sendall(d)


threading.Thread(target=pump, daemon=True).start()
from vncdotool import api

v = api.connect("127.0.0.1::%d" % lport, password=None, timeout=60)
BS = chr(92)
SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
           "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": BS, ":": ";",
           '"': "'", "<": ",", ">": ".", "?": "/", "~": "`"}


def key(k):
    v.keyPress("space" if k == " " else k)


INV = [False]
def typ(t):
    for c in t:
        if INV[0] and c.isalpha():
            c = c.lower() if c.isupper() else c.upper()
        if c in SHIFTED:
            v.keyDown("shift"); key(SHIFTED[c]); v.keyUp("shift")
        else:
            key(c)
        time.sleep(0.03)  # throttle: long lines dropped keys without this
    v.keyPress("enter")


# release modifiers a previous session may have left pressed (stuck Shift looked like an inverted Caps Lock)
for mod in ("shift", "ctrl", "alt"):
    v.keyUp(mod)
if args and args[0] == "login":
    args = args[1:]
    typ("eve"); time.sleep(2)
    typ(password("OVS node 5, 8")); time.sleep(4)
for c in args:
    if c == "CAPS":
        v.keyPress("caplk"); time.sleep(1)
        continue
    if c == "CTRLC":
        v.keyDown("ctrl"); v.keyPress("c"); v.keyUp("ctrl"); time.sleep(1)
        continue
    if c == "INV":
        INV[0] = True
        continue
    if c == "SUDOPASS":
        typ(password("OVS node 5, 8")); time.sleep(3)
        continue
    typ(c); time.sleep(4 + 0.06 * len(c))  # vncdotool queues keys asynchronously
v.captureScreen(out)
v.disconnect()
api.shutdown()
print("saved", out)
