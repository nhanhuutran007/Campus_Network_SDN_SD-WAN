"""Console driver for EVE host 2 (tenant 0).
python con.py start|stop|wipe|status <id>
python con.py send <id> <file-with-lines>   (lines sent one by one, prompt-aware)
python con.py cmd <id> "line1;;line2"
"""
import re, sys, time, os
sys.path.insert(0, os.path.dirname(__file__))
from eve import client

LAB = "/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl"
UUID = "ecf7c5b8-8c91-4616-953e-10b367b388e6"
WRAP = "/opt/unetlab/wrappers/unl_wrapper"
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\x1b[=>]")
PROMPT = re.compile(r"(\S+(\(config[^)]*\))?[#>]\s*$|login:\s*$|[Pp]assword:\s*$|\[yes/no\]:?\s*$|\[confirm\]\s*$)")


def clean(b):
    return ANSI.sub(b"", b.replace(b"\x00", b"")).decode("utf-8", "replace")


def run(ssh, c, t=300):
    _, o, e = ssh.exec_command(c, timeout=t)
    return o.read().decode() + e.read().decode()


def port(ssh, nid):
    return 32768 + int(nid)


def open_con(ssh, nid):
    ch = ssh.get_transport().open_channel("direct-tcpip", ("127.0.0.1", port(ssh, nid)), ("127.0.0.1", 0))
    ch.settimeout(0.3)
    return ch


def drain(ch, quiet=1.0, limit=60, until=None):
    buf, last, t0 = "", time.time(), time.time()
    while time.time() - t0 < limit:
        try:
            d = ch.recv(65535)
            if d:
                buf += clean(d); last = time.time()
                continue
        except Exception:
            pass
        tail = buf.rstrip("\r\n ")[-200:] if buf else ""
        if until is not None:
            if re.search(until, buf):
                break
        elif time.time() - last >= quiet and PROMPT.search(buf.splitlines()[-1] if buf.splitlines() else ""):
            break
        elif time.time() - last >= quiet * 6:
            break
    return buf


def send_lines(ch, lines, wait=0.15, quiet=0.6):
    out = ""
    for ln in lines:
        ch.send(ln + "\r")
        out += drain(ch, quiet=quiet, limit=120)
    return out


if __name__ == "__main__":
    act, nid = sys.argv[1], sys.argv[2]
    ssh = client("h2")
    if act in ("start", "stop", "wipe"):
        print(run(ssh, '%s -a %s -T 0 -F "%s" -D %s; echo rc=$?' % (WRAP, act, LAB, nid)))
    elif act == "status":
        print(run(ssh, "ss -tlnp | grep ':%d ' ; ls -la /opt/unetlab/tmp/0/%s/%s/ 2>&1 | head; free -m | sed -n 2p" % (port(ssh, nid), UUID, nid)))
    elif act in ("send", "cmd"):
        lines = open(sys.argv[3], encoding="utf-8").read().splitlines() if act == "send" else sys.argv[3].split(";;")
        ch = open_con(ssh, nid)
        ch.send("\r")
        pre = drain(ch, quiet=1.5, limit=float(os.environ.get("PRE", "20")))
        print("--- pre:", pre[-400:])
        out = send_lines(ch, lines, quiet=float(os.environ.get("Q", "0.6")))
        sys.stdout.buffer.write(out.encode("utf-8", "replace"))
        ch.close()
    ssh.close()
