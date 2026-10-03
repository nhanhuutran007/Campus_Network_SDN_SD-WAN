"""Sequential ASAv sync on host 2. python sync_asa.py <id> ...  (password from local credentials file)"""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(__file__))
from eve import client, password
from con import run, open_con, drain, send_lines, WRAP, LAB
from sync_ios import REPO, HERE, unl_tool, norm

PW = password("FW-ASAv 1, 2")
SKIP = re.compile(r"^(!|end$|ASA Version|: |Cryptochecksum|Building|.*\*{5})")


def cfg_lines(path):
    return [l.rstrip() for l in open(path, encoding="utf-8", errors="replace").read().replace("\r", "").splitlines()
            if l.strip() and not SKIP.match(l.strip())]


def login(ch, limit=900):
    t0, buf = time.time(), ""
    while time.time() - t0 < limit:
        ch.send("\r"); more = drain(ch, quiet=3, limit=10); buf += more
        last = buf.rstrip().splitlines()[-1] if buf.strip() else ""
        if re.search(r"[Uu]sername:\s*$", last):
            ch.send("admin\r"); drain(ch, quiet=2, limit=10); ch.send(PW + "\r"); time.sleep(3); continue
        if re.search(r"^\S+>\s*$", last):
            ch.send("enable\r"); out = drain(ch, quiet=2, limit=15)
            if "assword" in out:
                ch.send(PW + "\r"); out += drain(ch, quiet=2, limit=15)
                if "assword" in out.splitlines()[-1]:   # first boot: confirm new enable pw
                    ch.send(PW + "\r"); out += drain(ch, quiet=2, limit=15)
            buf += out
        if re.search(r"^\S+#\s*$", buf.rstrip().splitlines()[-1]):
            return buf.rstrip().splitlines()[-1].strip(), buf
        time.sleep(5)
    return None, buf


def sync(nid):
    path = REPO + unl_tool.CONFIG_MAP[nid]
    ssh = client("h2")
    log = open(os.path.join(HERE, "log_%d.txt" % nid), "w", encoding="utf-8")
    try:
        run(ssh, '%s -a start -T 0 -F "%s" -D %d >/dev/null 2>&1' % (WRAP, LAB, nid))
        time.sleep(10)
        ch = open_con(ssh, nid)
        prompt, boot = login(ch)
        log.write(boot)
        if not prompt:
            return "%d: KHONG VAO DUOC #" % nid
        out = send_lines(ch, ["terminal pager 0", "configure terminal"] + cfg_lines(path) + ["end", "write memory"], quiet=0.7)
        time.sleep(5); out += drain(ch, quiet=3, limit=30)
        log.write(out)
        errs = [l.strip() for l in out.splitlines() if re.search(r"^(ERROR|% Invalid|WARNING)", l.strip())]
        ch.send("show running-config\r"); rc = drain(ch, quiet=4, limit=90)
        log.write(rc)
        have = set(norm(l) for l in rc.splitlines())
        miss = [l for l in cfg_lines(path) if norm(l) not in have]
        host = re.search(r"^hostname (\S+)", rc, re.M)
        ch.send("show failover | include host|Failover\r"); fo = drain(ch, quiet=3, limit=20)
        log.write(fo); ch.close()
        return "%d %s: loi=%d %s | thieu=%d %s | wr=%s" % (nid, host.group(1) if host else "?", len(errs), errs[:4],
                                                          len(miss), miss[:6], "OK" if "[OK]" in out else "??")
    finally:
        run(ssh, '%s -a stop -T 0 -F "%s" -D %d >/dev/null 2>&1' % (WRAP, LAB, nid))
        log.close(); ssh.close()


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(sync(int(a)), flush=True)
