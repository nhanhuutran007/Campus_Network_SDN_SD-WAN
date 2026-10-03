"""n9.py <port> "cmd;;cmd": run shell cmds on node 9 serial console (host1), login as eve if needed"""
import sys, re, time
from eve import client, password
from con import drain
port, cmds = int(sys.argv[1]), sys.argv[2].split(";;")
s=client("h1"); ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",port),("127.0.0.1",0)); ch.settimeout(0.3)
try:
    ch.send("\r"); o=drain(ch,quiet=2,limit=10)
    if o.rstrip().endswith("login:"):
        ch.send("eve\r"); o=drain(ch,quiet=2,limit=10)
        if "assword" in o:
            ch.send(password("SDN_CONTROLLER node 9")+"\r"); o=drain(ch,quiet=3,limit=15)
    for c in cmds:
        m="__D%d__"%int(time.time()*1000)
        ch.send(c+"; echo "+m+"\r")
        buf=""; t0=time.time()
        while time.time()-t0<60 and buf.count(m)<2:
            buf+=drain(ch,quiet=1,limit=5)
        print(buf)
finally:
    ch.close(); s.close()
