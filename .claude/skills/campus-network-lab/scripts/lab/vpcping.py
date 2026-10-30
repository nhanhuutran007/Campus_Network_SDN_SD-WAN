"""vpcping.py <vpc_id> <target> <count> <tap[,tap]|none> <cut_at_s> <hold_s> : CHAY TREN HOST 1 (eve.py put roi python3). VPCS ping -i 100 (data plane, khong qua controller) trong khi ha tap that; in so goi mat + cac chuoi mat lien tiep."""
import socket,sys,time,threading,subprocess,re
vid,tgt,cnt,tap,cut_at,hold=int(sys.argv[1]),sys.argv[2],int(sys.argv[3]),sys.argv[4],float(sys.argv[5]),float(sys.argv[6])
PORT_BASE=int(__import__("os").environ.get("PORT_BASE","32768"))
s=socket.create_connection(("127.0.0.1",PORT_BASE+vid),5); s.settimeout(0.3)
def drain(t):
    b=b"";end=time.time()+t
    while time.time()<end:
        try: b+=s.recv(65535)
        except socket.timeout: pass
    return b.decode(errors="replace")
def typ(line):
    for ch in line: s.send(ch.encode()); time.sleep(0.15)
    s.send(b"\r")
s.send(b"\r"); drain(1)
typ("ping %s -c %d -i 100"%(tgt,cnt))
t0=time.time()
def cutter():
    time.sleep(cut_at); [subprocess.call(["ip","link","set",x,"down"]) for x in tap.split(",")]; print("CUT",round(time.time()-t0,2),flush=True)
    time.sleep(hold); [subprocess.call(["ip","link","set",x,"up"]) for x in tap.split(",")]; print("RESTORE",round(time.time()-t0,2),flush=True)
if tap!="none": threading.Thread(target=cutter,daemon=True).start()
out=drain(cnt*0.1+hold+20)
seqs=sorted(set(int(m) for m in re.findall(r"icmp_seq=(\d+) ttl",out)))
miss=[i for i in range(1,cnt+1) if i not in seqs]
runs=[];cur=[]
for i in miss:
    if cur and i==cur[-1]+1: cur.append(i)
    else:
        if cur: runs.append(cur)
        cur=[i]
if cur: runs.append(cur)
print("replies %d/%d lost %d"%(len(seqs),cnt,len(miss)))
print("gaps (seq start,len*100ms):",[(r[0],len(r)*100) for r in runs])
