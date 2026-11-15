"""sla_stats.py <gio> <file_ra.txt> [file_tho.jsonl] : ty le thoa SLA theo thoi gian tu thong ke app-route cua vManage.

Chay tren laptop, chi doc (API vManage qua tunnel SSH cua server EVE, dung lop VManage cua NetOps Bot).
Moi ban ghi app-route la gia tri trung binh mat goi / tre / jitter cua mot duong ham trong mot chu ky.
  - Ty le ban ghi thoa tung lop SLA (theo mau transport cuc bo).
  - Theo cap site va cua so 10 phut: co it nhat mot duong ham thoa SLA (dieu kien de AAR giu duoc SLA).
Nguong lay tu chinh sach tren vSmart: SLA_REALTIME 2% / 150 ms / 50 ms; SLA_BUSINESS 5% / 300 ms / 100 ms.
"""
import collections, json, os, sys, time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "campus-netops-bot"))
from campus import service  # noqa: E402

HOURS, OUT = int(sys.argv[1]), sys.argv[2]
RAW = sys.argv[3] if len(sys.argv) > 3 else None
SLA = {"SLA_REALTIME": (2, 150, 50), "SLA_BUSINESS": (5, 300, 100)}
FIELDS = ("entry_time", "local_system_ip", "remote_system_ip", "local_color", "remote_color", "loss_percentage", "latency", "jitter")

vm = service.vmanage()
s = vm._session()
base = vm.ep.base()
q = {"query": {"condition": "AND", "rules": [{"value": [str(HOURS)], "field": "entry_time", "type": "date", "operator": "last_n_hours"}]},
     "size": 10000}
r = s.post(base + "/dataservice/statistics/approute/page?count=10000", json=q, timeout=120)
if r.status_code != 200:
    r = s.post(base + "/dataservice/statistics/approute", json=q, timeout=120)
r.raise_for_status()
j = r.json()
recs = []
raw = open(RAW, "w") if RAW else None
while True:
    data = j.get("data", [])
    for d in data:
        t = {k: d.get(k) for k in FIELDS}
        recs.append(t)
        if raw:
            raw.write(json.dumps(t) + "\n")
    pi = j.get("pageInfo", {})
    print("da lay", len(recs), "hasMore", pi.get("hasMoreData"), flush=True)
    if not pi.get("hasMoreData") or not pi.get("scrollId") or not data:
        break
    r = s.get(base + "/dataservice/statistics/approute/page?scrollId=" + pi["scrollId"] + "&count=10000", timeout=120)
    r.raise_for_status()
    j = r.json()
if raw:
    raw.close()


def site(ip):
    p = ip.split(".")[2]
    return {"100": "100", "200": "200", "30": "300", "40": "400", "50": "500"}.get(p, p)


def ok(d, cls):
    lo, la, ji = SLA[cls]
    return d["loss_percentage"] <= lo and d["latency"] <= la and d["jitter"] <= ji


recs = [d for d in recs if d["loss_percentage"] is not None and d["latency"] is not None and d["jitter"] is not None]
lines = []
if recs:
    t0, t1 = min(d["entry_time"] for d in recs), max(d["entry_time"] for d in recs)
    wins = {d["entry_time"] // 600000 for d in recs}
    f = lambda t: time.strftime("%d/%m %H:%M", time.gmtime(t / 1000))
    lines.append("# Ty le thoa SLA tu vManage API (statistics/approute), lay %s UTC" % time.strftime("%d/%m/%Y %H:%M", time.gmtime()))
    lines.append("ban ghi %d; tu %s den %s UTC; %d cua so 10 phut co du lieu = %.1f gio" % (len(recs), f(t0), f(t1), len(wins), len(wins) / 6))
    for cls in SLA:
        lines.append("== %s (mat <= %d%%, tre <= %d ms, jitter <= %d ms)" % ((cls,) + SLA[cls]))
        n = sum(1 for d in recs if ok(d, cls))
        lines.append("  moi ban ghi: %.3f%% (%d/%d)" % (100.0 * n / len(recs), n, len(recs)))
        by = collections.defaultdict(lambda: [0, 0])
        for d in recs:
            b = by[d["local_color"]]
            b[1] += 1
            b[0] += ok(d, cls)
        for c in sorted(by):
            lines.append("  mau %-13s %.3f%% (%d/%d)" % (c, 100.0 * by[c][0] / by[c][1], by[c][0], by[c][1]))
        # cap site x cua so: co it nhat 1 duong ham thoa
        pw = collections.defaultdict(lambda: [False, False])  # (cap, cua so) -> [co mpls thoa, co bat ky thoa]
        for d in recs:
            a, b = site(d["local_system_ip"]), site(d["remote_system_ip"])
            if a == b:
                continue
            k = (tuple(sorted((a, b))), d["entry_time"] // 600000)
            v = pw[k]
            if ok(d, cls):
                v[1] = True
                if d["local_color"] == "mpls" and d["remote_color"] == "mpls":
                    v[0] = True
        tot = len(pw)
        lines.append("  cap site x cua so 10 phut: co duong ham thoa %.3f%% (%d/%d); rieng mpls-mpls thoa %.3f%%" % (
            100.0 * sum(v[1] for v in pw.values()) / tot, sum(v[1] for v in pw.values()), tot,
            100.0 * sum(v[0] for v in pw.values()) / tot))
        pp = collections.defaultdict(lambda: [0, 0])
        for (pair, _w), v in pw.items():
            pp[pair][1] += 1
            pp[pair][0] += v[1]
        for pair in sorted(pp):
            lines.append("    %s-%s: %.2f%% (%d/%d)" % (pair[0], pair[1], 100.0 * pp[pair][0] / pp[pair][1], pp[pair][0], pp[pair][1]))
    for name, key in (("mat goi %", "loss_percentage"), ("tre ms", "latency"), ("jitter ms", "jitter")):
        for c in ("mpls", "biz-internet"):
            v = sorted(d[key] for d in recs if d["local_color"] == c)
            if v:
                lines.append("phan bo %s, mau %s: trung vi %s, p95 %s, p99 %s, max %s" % (name, c, v[len(v) // 2], v[int(len(v) * .95)], v[int(len(v) * .99)], v[-1]))
else:
    lines.append("khong co ban ghi")
open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
