"""asa.py <id> "cmd;;cmd" [wait] : ASA console (enable via cred file), each cmd waits for output"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client, password
sys.stdout.reconfigure(encoding="utf-8")
def drain(ch, quiet=2, limit=30):
    buf=""; t0=time.time(); last=time.time()
    while time.time()-t0<limit:
        try:
            d=ch.recv(65535)
            if d: buf+=d.decode(errors="replace"); last=time.time(); continue
        except Exception: pass
        if time.time()-last>quiet: break
        time.sleep(0.1)
    return buf
nid=int(sys.argv[1]); cmds=sys.argv[2].split(";;"); q=float(sys.argv[3]) if len(sys.argv)>3 else 3
s=client("h1"); ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",33536+nid),("127.0.0.1",0)); ch.settimeout(0.3)
ch.send("\r"); o=drain(ch,2,10); last=o.strip().splitlines()[-1] if o.strip() else ""
print("PROMPT:",repr(last[-60:]))
if last.endswith("(config)#") or last.endswith(")#"): ch.send("end\r"); drain(ch,1.5,5)
if last.endswith(">"):
    ch.send("enable\r"); o=drain(ch,2,8)
    if "assword" in o: ch.send(password("FW-ASAv 1, 2")+"\r"); o=drain(ch,2,8)
ch.send("terminal pager 0\r"); drain(ch,1.5,8)
for c in cmds:
    ch.send(c+"\r"); print(drain(ch,q,120).replace("\r",""))
ch.close(); s.close()
