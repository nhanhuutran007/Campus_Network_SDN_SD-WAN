"""ovs_mode.py rstp|sdn <node> [<node>...] : doi che do 1 OVS qua VNC, tu kiem chung bang REST Ryu (28/11/2026).

Console VNC cua OVS doi trang thai Caps Lock giua cac phien khong doan truoc duoc (QEMU tu dong bo Caps theo keysym).
Lenh go sai hoa/thuong chi bao "command not found" nen vo hai. Script go mot phien, kiem chung bang dau hieu tu
ben ngoai; neu chua dat thi go lai voi INV (dao hoa/thuong), toi da 6 lan.
  rstp : gỡ controller, standalone, xoa flow/group, them flow NORMAL (RSTP da bat truoc) -> dau hieu: Ryu mat DPID.
  sdn  : tat RSTP, secure, xoa flow, chay lai campus-ovs-restore (dat lai controller) -> dau hieu: Ryu thay DPID.
"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "host2-sync"))
from eve import client

SCR = os.environ.get("SCR", ".")
CMDS = {
    "rstp": ["ovs-vsctl del-controller br0", "ovs-vsctl set-fail-mode br0 standalone",
             "ovs-ofctl -O OpenFlow13 del-flows br0", "ovs-ofctl -O OpenFlow13 del-groups br0",
             "ovs-ofctl -O OpenFlow13 add-flow br0 priority=0,actions=NORMAL",
             "ovs-vsctl get bridge br0 rstp_enable fail_mode; ovs-ofctl -O OpenFlow13 dump-flows br0 | wc -l"],
    # dark: secure + bang flow rong -> switch bo moi goi (khong the co vong); dau hieu: mat ping IP quan tri
    "dark": ["ovs-vsctl set-fail-mode br0 secure", "ovs-ofctl -O OpenFlow13 del-flows br0",
             "ovs-ofctl -O OpenFlow13 del-groups br0"],
    "sdn": ["ovs-vsctl set-fail-mode br0 secure", "ovs-ofctl -O OpenFlow13 del-flows br0",
            "ovs-vsctl set bridge br0 rstp_enable=false", "systemctl restart campus-ovs-restore",
            "ovs-vsctl get bridge br0 rstp_enable fail_mode stp_enable; ovs-vsctl get-controller br0"],
}
MGMT = {5: "10.1.99.11", 8: "10.1.99.12", 68: "10.1.99.21", 66: "10.1.99.22", 70: "10.1.99.23", 69: "10.1.99.24"}


def mgmt_alive(node):
    c = client("h1")
    _, o, _ = c.exec_command("ip netns exec lt_m99 ping -c 3 -W 1 %s | grep -o '[0-9]* received'" % MGMT[node],
                             timeout=20)
    out = o.read().decode().strip()
    c.close()
    return not out.startswith("0 ")


def ryu_dpids():
    c = client("h1")
    _, o, _ = c.exec_command("ip netns exec lt_m99 curl -s -m 5 http://10.1.99.10:8080/stats/switches", timeout=20)
    out = o.read().decode()
    c.close()
    try:
        return set(json.loads(out))
    except ValueError:
        return None


def done(mode, node):
    if mode == "dark":
        time.sleep(3)
        return not mgmt_alive(node)
    for _ in range(20 if mode == "sdn" else 4):
        d = ryu_dpids()
        if d is not None and ((node not in d) if mode == "rstp" else (node in d)):
            return True
        time.sleep(5)
    return False


def main():
    mode, nodes = sys.argv[1], [int(x) for x in sys.argv[2:]]
    for n in nodes:
        ok = False
        for attempt in range(6):
            inv = ["INV"] if attempt % 2 else []
            out = os.path.join(SCR, "mode_%s_%d.png" % (mode, n))
            subprocess.call([sys.executable, os.path.join(HERE, "vnccmd.py"), str(n), out] + inv + CMDS[mode],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
            ok = done(mode, n)
            print("node %d %s lan %d %s -> %s" % (n, mode, attempt + 1, "INV" if inv else "thuong", "OK" if ok else "chua"))
            sys.stdout.flush()
            if ok:
                break
        if not ok:
            print("node %d: KHONG DAT sau 6 lan, dung lai" % n)
            sys.exit(1)


if __name__ == "__main__":
    main()
