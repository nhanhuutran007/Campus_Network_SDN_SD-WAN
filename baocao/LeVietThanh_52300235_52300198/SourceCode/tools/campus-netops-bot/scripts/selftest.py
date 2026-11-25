"""Tự kiểm NetOps-Server sau khi cài (chạy trên chính máy chủ trong topo):

    python scripts\\selftest.py          → in bảng ĐẠT/LỖI và ghi logs\\selftest.txt

Kiểm theo lớp: DNS nội bộ → HTTPS ra Internet qua FW (Telegram, LLM) → SSH in-band tới từng
thiết bị trong phạm vi → REST Ryu → REST vManage. Không thay đổi gì trên thiết bị.
"""
import os
import socket
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
import requests  # noqa: E402

from campus import inventory, service  # noqa: E402

rows = []


def check(name, fn):
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
    rows.append((ok, name, detail, time.time() - t0))
    print(f"{'ĐẠT' if ok else 'LỖI'}  {name:<34} {detail}  ({time.time() - t0:.1f}s)", flush=True)


def dns(host):
    return lambda: (True, socket.gethostbyname(host))


def https(url, ok_codes=(200, 301, 302, 401, 404)):
    def f():
        r = requests.get(url, timeout=15)
        return r.status_code in ok_codes, f"HTTP {r.status_code}"
    return f


LLM_BASE = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")


def llm():
    """Gọi thật 1 lượt hội thoại ngắn (tốn 1 yêu cầu của gói free) để chắc key + model dùng được."""
    model = os.getenv("LLM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    r = requests.post(f"{LLM_BASE}/chat/completions", timeout=60,
                      headers={"Authorization": f"Bearer {os.getenv('API_KEY', '')}"},
                      json={"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]})
    if r.ok:
        return True, f"{model} HTTP 200"
    try:
        err = r.json().get("error", {})
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
    except ValueError:
        msg = r.text
    return False, f"{model} HTTP {r.status_code}: {msg[:80]}"


def ssh(dev):
    def f():
        res = service.run_command(dev.name, "show version | include uptime")
        return res.ok, res.text.splitlines()[-1].strip()[:90] if res.ok else res.text[:120]
    return f


def ryu():
    h = service.ryu().health()
    sw = h.get("switches", [])
    return all(s.get("connected") for s in sw) and bool(sw), \
        f"{sum(1 for s in sw if s.get('connected'))}/{len(sw)} OVS, {h.get('links_up')}/{h.get('links_total')} link"


def vmanage():
    d = service.vmanage().devices()
    up = sum(1 for x in d if x.get("reachability") == "reachable")
    return bool(d), f"{up}/{len(d)} reachable"


if __name__ == "__main__":
    print(f"NetOps selftest {time.strftime('%Y-%m-%d %H:%M:%S')}  transport={os.getenv('NETOPS_TRANSPORT', 'console')}")
    check("DNS api.telegram.org", dns("api.telegram.org"))
    llm_host = LLM_BASE.split("/")[2]
    check(f"DNS {llm_host}", dns(llm_host))
    check("HTTPS Telegram (qua FW)", https("https://api.telegram.org"))
    check("LLM (key + model, qua FW)", llm)
    for d in inventory.DEVICES:
        if service.in_scope(d):
            check(f"SSH {d.name} {d.mgmt_ip}", ssh(d))
    if os.getenv("SDN_CTL"):
        check("Ryu REST " + os.getenv("SDN_CTL"), ryu)
    if os.getenv("VMANAGE_URL"):
        check("vManage REST " + os.getenv("VMANAGE_URL"), vmanage)
    ok = sum(1 for r in rows if r[0])
    summary = f"KẾT QUẢ: {ok}/{len(rows)} đạt"
    print(summary)
    logdir = os.getenv("NETOPS_LOG_DIR") or os.path.join(ROOT, "logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "selftest.txt"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{'OK ' if r[0] else 'ERR'} {r[1]} | {r[2]}\n")
        f.write(summary + "\n")
    sys.exit(0 if ok == len(rows) else 1)
