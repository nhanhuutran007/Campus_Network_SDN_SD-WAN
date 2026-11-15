#!/usr/bin/env python3
"""nsrelay.py <cong_nghe> <netns> <ip> <cong> : chuyen tiep 127.0.0.1:<cong_nghe> cua server vao mot dich trong namespace.

Dung de doc REST cua Ryu (10.1.99.10:8080, chi toi duoc tu VLAN 99) qua tunnel SSH ma khong dat IP len server.
CHAY TREN SERVER EVE. Tu thoat sau 6 gio.
"""
import socket, subprocess, sys, threading, time

lp, ns, ip, port = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
CHILD = ("import socket,sys,threading\n"
         "s=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=10)\n"
         "s.settimeout(None)\n"
         "def up():\n"
         "    while True:\n"
         "        d=sys.stdin.buffer.raw.read(65536)\n"
         "        if not d: break\n"
         "        s.sendall(d)\n"
         "    s.shutdown(socket.SHUT_WR)\n"
         "threading.Thread(target=up,daemon=True).start()\n"
         "while True:\n"
         "    d=s.recv(65536)\n"
         "    if not d: break\n"
         "    sys.stdout.buffer.raw.write(d)\n")
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", lp))
srv.listen(16)
srv.settimeout(60)
end = time.time() + 6 * 3600


def serve(c):
    p = subprocess.Popen(["ip", "netns", "exec", ns, "python3", "-c", CHILD, ip, port], stdin=c.fileno(), stdout=c.fileno())
    p.wait()
    c.close()


while time.time() < end:
    try:
        c, _ = srv.accept()
    except socket.timeout:
        continue
    threading.Thread(target=serve, args=(c,), daemon=True).start()
