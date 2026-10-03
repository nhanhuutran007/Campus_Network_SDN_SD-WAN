"""h1v.py <id> <credtag> "cmd;;cmd": safe login on host1 Viptela console then run commands"""
import sys
from eve import client
from con import drain
from vlogin import vlogin
nid,tag,cmds=int(sys.argv[1]),sys.argv[2],sys.argv[3].split(";;")
s=client("h1"); ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",33536+nid),("127.0.0.1",0)); ch.settimeout(0.3)
try:
    print("prompt:",vlogin(ch,tag,boot_limit=900))
    ch.send("screen-length 0\r"); drain(ch,quiet=2,limit=10)
    for c in cmds:
        ch.send(c+"\r"); print(drain(ch,quiet=4,limit=90))
finally:
    ch.close(); s.close()
