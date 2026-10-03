"""h1lines.py <id>: print host1 running-config as paste lines joined by ;; (filtered)"""
import sys,re
t=open("h1_%s.txt"%sys.argv[1],encoding="utf-8").read().split("show running-config")[-1].replace("\r","")
out=[];skip=False
for l in t.splitlines():
    s=l.rstrip()
    if skip:
        if s.strip()=="quit": skip=False
        continue
    if s.startswith("crypto ca certificate chain"): skip=True; continue
    if not s.strip() or re.match(r"^(!|: |ASA Version|Cryptochecksum|Building|Current|end$|pager lines|\S+[#>]\s*$|terminal )",s.strip()) or "*****" in s: continue
    out.append(s)
print(";;".join(out))
