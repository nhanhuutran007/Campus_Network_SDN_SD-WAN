"""sdn_policy_test.py [--vpc 19] [--target 10.1.40.102] [--src vlan:10] [--dst vlan:40] [--proto icmp]

Bai thu muc tieu 5 (quan ly chinh sach tap trung) cho SDN campus Site 100:
  1) Truoc: VPC ping target (khac VLAN), gateway VLAN cua VPC va DHCP-Server
  2) POST /campus/policy (deny src<->dst, hai chieu) -> thoi gian ap toi barrier 4 Access
  3) Trong khi luat ap: target phai bi chan, gateway + DHCP-Server van thong; bo dem luat tang
  4) Xoa luat -> target thong lai
Ghi log/sdn-eval/policy_<ngay>.json.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sdn_vlan_test import Lab, vpc, REPO  # noqa: E402


def pings(lab, node, targets):
    out = vpc(lab, node, ["ping %s -c 3" % t for t in targets])
    return {t: out.count("bytes from %s" % t) for t in targets}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vpc", type=int, default=19)
    ap.add_argument("--target", default="10.1.40.102")
    ap.add_argument("--gateway", default="10.1.10.1")
    ap.add_argument("--src", default="vlan:10")
    ap.add_argument("--dst", default="vlan:40")
    ap.add_argument("--proto", default="icmp")
    a = ap.parse_args()
    lab = Lab()
    tg = [a.target, a.gateway, "10.1.90.10"]
    res = {"rule": {"src": a.src, "dst": a.dst, "proto": a.proto}}
    res["before"] = pings(lab, a.vpc, tg)
    print("Truoc:      %s" % res["before"])
    r = lab.post("/campus/policy", {"action": "add", "rule": {
        "name": "Thu cach ly %s-%s" % (a.src, a.dst), "action": "deny", "src": a.src,
        "dst": a.dst, "proto": a.proto, "bidir": True, "prio": 100}})
    if not r or r.get("error"):
        sys.exit("API loi: %s" % r)
    pid = r["policy"]
    time.sleep(1.5)
    ev = [e for e in lab.get("/campus/events") if e["id"] == r["id"]][0]
    res["apply"] = {k: ev.get(k) for k in ("converge_ms", "switches", "flow_mods")}
    print("Ap luat #%d: %s ms (%s Access, %s flow-mod)" % (pid, ev.get("converge_ms"),
                                                         ev.get("switches"), ev.get("flow_mods")))
    res["during"] = pings(lab, a.vpc, tg)
    print("Khi ap luat: %s" % res["during"])
    time.sleep(6)       # cho chu ky dem goi (5 s)
    st = [p for p in lab.get("/campus/policies") if p["id"] == pid]
    res["matched_packets"] = st[0]["packets"] if st else None
    print("Goi khop luat: %s" % res["matched_packets"])
    r2 = lab.post("/campus/policy", {"action": "delete", "id": pid})
    time.sleep(1.5)
    ev2 = [e for e in lab.get("/campus/events") if e["id"] == r2["id"]][0]
    res["remove_ms"] = ev2.get("converge_ms")
    res["after"] = pings(lab, a.vpc, tg)
    print("Sau khi xoa (%s ms): %s" % (res["remove_ms"], res["after"]))
    ok = (res["before"][a.target] == 3 and res["during"][a.target] == 0
          and res["during"][a.gateway] == 3 and res["after"][a.target] == 3)
    res["pass"] = ok
    print("KET QUA:", "DAT" if ok else "CHUA DAT")
    out_dir = os.path.join(REPO, "log", "sdn-eval")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "policy_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    json.dump(res, open(path, "w", encoding="utf-8"), indent=1)
    print("JSON:", os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
