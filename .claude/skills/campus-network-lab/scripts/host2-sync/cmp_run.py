"""cmp_run.py <id>: diff host1 live run (h1_<id>.txt) vs host2 run (last show running-config in log_<id>.txt)"""
import sys,re,difflib
nid=sys.argv[1]
def body(t):
    t=t.split("show running-config")[-1]
    L=[re.sub(r"\s+$","",l) for l in t.replace("\r","").splitlines()]
    return [l for l in L if l.strip() and not re.match(r"^(: |Cryptochecksum|\S+[#>]\s*$|!|ntp clock-period|Building|Current configuration|Last configuration)",l)]
a=body(open("h1_%s.txt"%nid,encoding="utf-8").read()); b=body(open("log_%s.txt"%nid,encoding="utf-8").read())
d=[l for l in difflib.unified_diff(a,b,"host1","host2",n=0,lineterm="") if not l.startswith("@@")]
print("node",nid,"h1=%d h2=%d diff=%d"%(len(a),len(b),len(d)-2 if d else 0)); print("\n".join(d[2:60]))
