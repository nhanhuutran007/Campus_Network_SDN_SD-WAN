"""vncui.py <node> <step> [...] : GUI steps on a host1 node's VNC (Windows PCs) via SSH tunnel.
Steps: click:X,Y  dclick:X,Y  key:ctrl-l (vncdotool key names, '-' joins combos)
       type:TEXT (Shift handled for symbols)  wait:SECONDS  shot:OUT.png
Example: vncui.py 73 click:218,585 wait:5 key:ctrl-l "type:http://10.1.99.10:8080/" key:enter wait:8 shot:out.png"""
import os, sys, socket, threading, select, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client
node = int(sys.argv[1])
s = client("h1"); tr = s.get_transport()
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); lport = srv.getsockname()[1]
def pump():
    c, _ = srv.accept(); ch = tr.open_channel("direct-tcpip", ("127.0.0.1", 33536 + node), ("127.0.0.1", 0))
    while True:
        r, _, _ = select.select([c, ch], [], [], 900)
        if not r: break
        for x in r:
            d = x.recv(65536)
            if not d: return
            (ch if x is c else c).sendall(d)
threading.Thread(target=pump, daemon=True).start()
from vncdotool import api
v = api.connect("127.0.0.1::%d" % lport, password=None, timeout=40)
SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
           "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": chr(92), ":": ";",
           '"': "'", "<": ",", ">": ".", "?": "/", "~": "`"}
for mod in ("shift", "ctrl", "alt"):
    v.keyUp(mod)
for st in sys.argv[2:]:
    op, _, arg = st.partition(":")
    if op in ("click", "dclick"):
        x, y = (int(n) for n in arg.split(","))
        v.mouseMove(x, y); time.sleep(0.3); v.mousePress(1)
        if op == "dclick":
            time.sleep(0.1); v.mousePress(1)
        time.sleep(0.5)
    elif op == "key":
        v.keyPress(arg); time.sleep(0.5)
    elif op == "type":
        for ch in arg:
            if ch in SHIFTED:
                v.keyDown("shift"); v.keyPress(SHIFTED[ch]); v.keyUp("shift")
            else:
                v.keyPress("space" if ch == " " else ch)
            time.sleep(0.04)
        time.sleep(0.5)
    elif op == "wait":
        time.sleep(float(arg))
    elif op == "shot":
        v.captureScreen(arg); print("saved", arg)
v.disconnect(); api.shutdown()
