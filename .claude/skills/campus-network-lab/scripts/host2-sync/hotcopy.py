"""For nodes running on host 1: stop on host1 -> relay overlay(s) -> start on host1 -> verify console port.
python hotcopy.py <id> [<id> ...]"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from eve import client
from relay2 import one

U = "ecf7c5b8-8c91-4616-953e-10b367b388e6"
LAB = "/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl"
W = "/opt/unetlab/wrappers/unl_wrapper"


def sh(c, cmd, t=300):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read() + e.read()).decode(errors="replace")


def listening(c, nid):
    return sh(c, "ss -tln | grep -c ':%d '" % (33536 + nid)).strip() != "0"


for a in sys.argv[1:]:
    n = int(a)
    h1 = client("h1")
    files = sh(h1, "cd /opt/unetlab/tmp/6/%s/%d && ls *.qcow2" % (U, n)).split()
    print("== node %d files %s" % (n, files), flush=True)
    sh(h1, '%s -a stop -T 6 -F "%s" -D %d >/dev/null 2>&1' % (W, LAB, n))
    for _ in range(30):
        if not listening(h1, n) and sh(h1, "pgrep -fc 'qemu.*-D %d ' || true" % n).strip() in ("0", ""):
            break
        time.sleep(2)
    print("  stopped on host1:", not listening(h1, n), flush=True)
    h1.close()
    ok = True
    try:
        for f in files:
            src = "/opt/unetlab/tmp/6/%s/%d/%s" % (U, n, f)
            dst = "/opt/unetlab/tmp/0/%s/%d/%s" % (U, n, f)
            for attempt in range(3):
                try:
                    if one(src, dst, "unl0:unl"):
                        break
                except Exception as e:
                    print("  retry", attempt + 1, repr(e)[:100], flush=True); time.sleep(30)
            else:
                ok = False
    finally:
        h1 = client("h1")
        sh(h1, '%s -a start -T 6 -F "%s" -D %d >/dev/null 2>&1' % (W, LAB, n))
        time.sleep(8)
        print("  restarted on host1, console listening:", listening(h1, n), "| copy ok:", ok, flush=True)
        h1.close()
