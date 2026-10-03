"""vnccap.py <node> <out.png> : capture VNC screen of host1 node via SSH tunnel"""
import os, sys, socket, threading, select
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client
node, out = int(sys.argv[1]), sys.argv[2]
s = client("h1"); tr = s.get_transport()
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); lport = srv.getsockname()[1]
def pump():
    c, _ = srv.accept(); ch = tr.open_channel("direct-tcpip", ("127.0.0.1", 33536 + node), ("127.0.0.1", 0))
    while True:
        r, _, _ = select.select([c, ch], [], [], 30)
        if not r: break
        for x in r:
            d = x.recv(65536)
            if not d: return
            (ch if x is c else c).sendall(d)
threading.Thread(target=pump, daemon=True).start()
from vncdotool import api
v = api.connect("127.0.0.1::%d" % lport, password=None, timeout=40)
v.captureScreen(out); v.disconnect(); api.shutdown(); print("saved", out)
