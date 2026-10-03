"""Safe Viptela console login: waits for each prompt, stops after ONE failure (avoid lockout)."""
import re, time
from eve import password
from con import drain


def wait_for(ch, pat, limit=60):
    buf, t0 = "", time.time()
    while time.time() - t0 < limit:
        buf += drain(ch, quiet=1.5, limit=5)
        if re.search(pat, buf):
            return buf
    return None


def vlogin(ch, tag, boot_limit=600):
    """returns prompt line or raises. Assumes console at login: or at a CLI prompt."""
    t0 = time.time()
    while time.time() - t0 < boot_limit:
        ch.send("\r")
        b = wait_for(ch, r"(login:\s*$|\S+#\s*$)", limit=15)
        if b and re.search(r"\S+#\s*$", b.rstrip() + " ") and not b.rstrip().endswith("login:"):
            return b.strip().splitlines()[-1]
        if b and b.rstrip().endswith("login:"):
            break
        time.sleep(10)
    else:
        raise RuntimeError("no login prompt")
    ch.send("admin\r")
    if wait_for(ch, r"[Pp]assword:\s*$", limit=20) is None:
        raise RuntimeError("no Password: prompt")
    time.sleep(0.5)
    ch.send(password(tag) + "\r")
    b = wait_for(ch, r"(\S+#\s*$|login:\s*$|incorrect)", limit=40)
    if b is None or "incorrect" in b or b.rstrip().endswith("login:"):
        raise RuntimeError("LOGIN FAILED - stop, do not retry (lockout risk). device said: " + repr((b or "")[-300:]))
    return b.strip().splitlines()[-1]
