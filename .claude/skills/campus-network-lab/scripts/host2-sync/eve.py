"""SSH helper: python eve.py <h1|h2> "<cmd>"   | put/get: python eve.py <h> put local remote
Password is read from the local credentials file at runtime, never printed."""
import os, re, sys, paramiko

CRED = os.path.expanduser(r"~/.claude/campus-lab-credentials.md")
HOSTS = {"h1": ("10.215.28.26", "EVE host 1"), "h2": ("10.0.227.112", "EVE host 2")}


def password(tag):
    for line in open(CRED, encoding="utf-8"):
        if line.startswith("|") and tag in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            return cells[2].strip("`")
    raise SystemExit("no credential for " + tag)


def client(h):
    ip, tag = HOSTS[h]
    ip = os.environ.get("EVE_" + h.upper(), ip)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username="root", password=password(tag), timeout=15,
              look_for_keys=False, allow_agent=False)
    return c


if __name__ == "__main__":
    h = sys.argv[1]
    c = client(h)
    if sys.argv[2] in ("put", "get"):
        s = c.open_sftp()
        (s.put if sys.argv[2] == "put" else s.get)(sys.argv[3], sys.argv[4])
        print("ok")
    else:
        _, o, e = c.exec_command(sys.argv[2], timeout=int(os.environ.get("T", "600")))
        sys.stdout.buffer.write(o.read())
        err = e.read().decode(errors="replace")
        err = "\n".join(l for l in err.splitlines() if "mesg:" not in l)
        if err.strip():
            sys.stderr.write(err + "\n")
