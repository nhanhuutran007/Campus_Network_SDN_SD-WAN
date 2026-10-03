"""h1run.py <id> <kind ios|asa>: dump host1 live running-config to h1_<id>.txt (read-only)"""
import sys
from eve import client, password
from con import drain
nid,kind=int(sys.argv[1]),sys.argv[2]
s=client("h1")
ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",33536+nid),("127.0.0.1",0)); ch.settimeout(0.3)
ch.send("q"); drain(ch,quiet=1.5,limit=5)
ch.send("\r"); o=drain(ch,quiet=2,limit=8); last=o.strip().splitlines()[-1] if o.strip() else ""
if last.endswith(">"):
    ch.send("enable\r"); o=drain(ch,quiet=2,limit=8)
    if "assword" in o: ch.send(password("FW-ASAv 1, 2")+"\r"); drain(ch,quiet=2,limit=8)
ch.send(("terminal pager 0" if kind=="asa" else "terminal length 0")+"\r"); drain(ch,quiet=1.5,limit=8)
ch.send("show running-config\r"); r=drain(ch,quiet=4,limit=120)
open("h1_%d.txt"%nid,"w",encoding="utf-8").write(r); print(nid,len(r.splitlines()),"lines")
ch.close(); s.close()
