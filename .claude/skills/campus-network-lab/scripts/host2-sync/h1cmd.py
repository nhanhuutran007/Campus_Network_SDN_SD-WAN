"""h1cmd.py <id> "cmd;;cmd" : run show/ping commands on host1 console (IOS/ASA), leaves console clean"""
import sys
from eve import client, password
from con import drain
nid=int(sys.argv[1]); cmds=sys.argv[2].split(";;")
s=client("h1")
ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",33536+nid),("127.0.0.1",0)); ch.settimeout(0.3)
ch.send("q"); drain(ch,quiet=1.5,limit=5); ch.send("\r"); o=drain(ch,quiet=2,limit=8)
last=o.strip().splitlines()[-1] if o.strip() else ""
if last.endswith(">"):
    ch.send("enable\r"); o=drain(ch,quiet=2,limit=8)
    if "assword" in o: ch.send(password("FW-ASAv 1, 2")+"\r"); drain(ch,quiet=2,limit=8)
for c in cmds:
    ch.send(c+"\r"); print(drain(ch,quiet=3,limit=60))
ch.close(); s.close()
