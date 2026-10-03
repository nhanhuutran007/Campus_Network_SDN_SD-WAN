"""rd.py <id> ios|vedge "cmd;;cmd" -> console commands on host1 (IOS: enable + terminal length 0; vEdge: login admin, paginate false, exit afterwards)"""
import os, sys, time, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client, password
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
nid,kind=int(sys.argv[1]),sys.argv[2]; cmds=sys.argv[3].split(";;")
s=client("h1"); ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",33536+nid),("127.0.0.1",0)); ch.settimeout(0.3)
ch.send("\r"); o=drain(ch,2,10); last=o.strip().splitlines()[-1] if o.strip() else ""
print("PROMPT:",repr(last))
if kind=="ios":
    if last.endswith(">"): ch.send("enable\r"); drain(ch,2,8)
    ch.send("terminal length 0\r"); drain(ch,1.5,8)
elif kind=="vedge":
    if last.rstrip().endswith("login:"):
        ch.send("admin\r"); drain(ch,2,10); ch.send(password("vEdge chi nhánh")+"\r"); o=drain(ch,3,30)
        if "incorrect" in o or o.rstrip().endswith("login:"): print("LOGIN FAILED"); sys.exit(1)
        print("login OK")
    ch.send("paginate false\r"); drain(ch,1.5,8)
for c in cmds:
    ch.send(c+"\r"); print(drain(ch,3,90))
if kind=="vedge" and last.rstrip().endswith("login:"): ch.send("exit\r"); drain(ch,1,3)
ch.close(); s.close()
