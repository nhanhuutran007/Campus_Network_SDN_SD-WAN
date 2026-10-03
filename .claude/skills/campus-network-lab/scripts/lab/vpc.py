"""vpc.py <id> "cmd;;cmd" : VPCS console"""
import sys,time
exec(open(__file__.replace("vpc.py","asa.py")).read().split("nid=int")[0])
nid=int(sys.argv[1]); cmds=sys.argv[2].split(";;")
s=client("h1"); ch=s.get_transport().open_channel("direct-tcpip",("127.0.0.1",33536+nid),("127.0.0.1",0)); ch.settimeout(0.3)
ch.send("\r"); print(drain(ch,2,8).strip().splitlines()[-1:])
for c in cmds:
    ch.send(c+"\r"); print(drain(ch,4,60).replace("\r",""))
ch.close(); s.close()
