"""fix.py <id> <ios|asa> "line;;line;;..."  start -> apply in config mode -> wr -> show run into log_<id>.txt -> stop"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from eve import client
from con import run, open_con, drain, send_lines, WRAP, LAB
from sync_ios import wait_prompt
from sync_asa import login

nid, kind, lines = int(sys.argv[1]), sys.argv[2], [l for l in sys.argv[3].split(";;") if l]
s = client("h2")
try:
    run(s, '%s -a start -T 0 -F "%s" -D %d >/dev/null 2>&1' % (WRAP, LAB, nid)); time.sleep(10)
    ch = open_con(s, nid)
    if kind == "asa":
        p, _ = login(ch); pre = ["terminal pager 0"]
    else:
        p, _ = wait_prompt(ch); pre = ["enable", "terminal length 0"]
    print("prompt", p)
    out = send_lines(ch, pre + ["configure terminal"] + lines + ["end", "write memory"], quiet=0.8)
    time.sleep(4); out += drain(ch, quiet=3, limit=30)
    print("\n".join(l for l in out.splitlines() if "%" in l or "ERROR" in l or "[OK]" in l))
    ch.send("show running-config\r"); rc = drain(ch, quiet=6, limit=180)
    open("log_%d.txt" % nid, "w", encoding="utf-8").write(out + rc)
    ch.close()
finally:
    run(s, '%s -a stop -T 0 -F "%s" -D %d >/dev/null 2>&1' % (WRAP, LAB, nid)); s.close()
