"""Sequential IOL/vIOS sync on host 2: start -> wait -> paste configs/ -> wr -> verify -> stop.
python sync_ios.py <id> [<id> ...]"""
import sys, os, re, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from eve import client
from con import run, open_con, drain, send_lines, WRAP, LAB
sys.path.insert(0, r"D:/OneDrive/HUUNHAN/STUDENT/NAM3(HK3)/DuAnCNTT/Campus_Network_SDN_SD-WAN/.claude/skills/campus-network-lab/scripts")
import unl_tool
REPO = r"D:/OneDrive/HUUNHAN/STUDENT/NAM3(HK3)/DuAnCNTT/Campus_Network_SDN_SD-WAN/configs/"
HERE = os.path.dirname(os.path.abspath(__file__))
norm = lambda s: re.sub(r"\s+", " ", s.strip())
SKIP = re.compile(r"^(!|end$|version |Building|Current configuration|: |.*\*{5})")


def cfg_lines(path):
    out, inb = [], False
    for l in open(path, encoding="utf-8", errors="replace").read().replace("\r", "").splitlines():
        if inb:
            inb = "^C" not in l
            continue
        if l.startswith("banner "):
            inb = l.count("^C") < 2
            continue
        if l.strip() and not SKIP.match(l.strip()):
            out.append(l.rstrip())
    return out


def wait_prompt(ch, limit=int(os.environ.get("WAITP", "240"))):
    t0, buf = time.time(), ""
    while time.time() - t0 < limit:
        ch.send("\r")
        buf += drain(ch, quiet=2, limit=6)
        last = buf.rstrip().splitlines()[-1] if buf.strip() else ""
        if re.search(r"initial configuration dialog\?\s*\[yes/no\]:?\s*$", buf.rstrip()):
            ch.send("no\r"); time.sleep(3); buf += drain(ch, quiet=3, limit=30); continue
        if re.search(r"\[yes/no\]:?\s*$", last):
            ch.send("yes\r"); time.sleep(2); continue
        if re.search(r"^\S+[>#]\s*$", last):
            # stable check: console quiet and prompt echoed back twice
            ok = 0
            for _ in range(6):
                ch.send("\r"); more = drain(ch, quiet=4, limit=10); buf += more
                ml = more.strip().splitlines()
                ok = ok + 1 if (len(ml) <= 2 and ml and re.search(r"^\S+[>#]\s*$", ml[-1])) else 0
                if ok >= 2:
                    return ml[-1].strip(), buf
            continue
        time.sleep(3)
    return None, buf


def sync(nid):
    path = REPO + unl_tool.CONFIG_MAP[nid]
    ssh = client("h2")
    log = open(os.path.join(HERE, "log_%d.txt" % nid), "w", encoding="utf-8")
    try:
        r = run(ssh, '%s -a start -T 0 -F "%s" -D %d 2>&1 | tail -1' % (WRAP, LAB, nid))
        time.sleep(8)
        ch = open_con(ssh, nid)
        prompt, boot = wait_prompt(ch)
        log.write(boot)
        if not prompt:
            return "%d: KHONG THAY PROMPT" % nid
        lines = ["enable", "terminal length 0", "configure terminal"] + cfg_lines(path) + ["end", "write memory"]
        out = send_lines(ch, lines, quiet=0.5)
        time.sleep(3); out += drain(ch, quiet=2, limit=20)
        log.write(out)
        errs = [l for l in out.splitlines() if re.search(r"% (Invalid|Incomplete|Ambiguous)|^%", l.strip())]
        ch.send("show running-config\r"); rc = drain(ch, quiet=3, limit=60)
        log.write(rc)
        have = set(norm(l) for l in rc.splitlines())
        miss = [l for l in cfg_lines(path) if norm(l) not in have and norm(l) not in ("ip routing",)]
        host = re.search(r"^hostname (\S+)", rc, re.M)
        ch.close()
        return "%d %s: prompt=%s | loi=%d %s | thieu=%d %s | wr=%s" % (
            nid, host.group(1) if host else "?", prompt, len(errs), errs[:3], len(miss), miss[:6],
            "OK" if "[OK]" in out else "??")
    finally:
        run(ssh, '%s -a stop -T 0 -F "%s" -D %d >/dev/null 2>&1' % (WRAP, LAB, nid))
        log.close(); ssh.close()


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(sync(int(a)), flush=True)
