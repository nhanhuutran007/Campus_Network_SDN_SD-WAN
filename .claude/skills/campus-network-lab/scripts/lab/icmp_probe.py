#!/usr/bin/env python3
"""icmp_probe.py <dst> <giay> [--interval 0.2] [--same-id] : dau do ICMP, in JSON danh sach thoi diem nhan.

Mac dinh moi goi mot ICMP id moi, nhu moi luong moi: tuong lua khong gan goi vao ket noi cu.
--same-id giu nguyen id nhu lenh ping thuong (mot luong lien tuc).
Chay trong namespace: ip netns exec lt_s500 python3 icmp_probe.py 10.2.60.241 60
"""
import argparse, json, select, socket, struct, time


def cksum(b):
    s = sum(struct.unpack("!%dH" % (len(b) // 2), b[:len(b) // 2 * 2]))
    if len(b) % 2:
        s += b[-1] << 8
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return ~s & 0xffff


ap = argparse.ArgumentParser()
ap.add_argument("dst")
ap.add_argument("secs", type=float)
ap.add_argument("--interval", type=float, default=0.2)
ap.add_argument("--same-id", action="store_true")
a = ap.parse_args()
s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
t0 = time.time()
nxt = t0
seq = 0
ident = 0x4c00
pending = {}
rx = []
while True:
    now = time.time()
    if now - t0 >= a.secs and (not pending or now - t0 >= a.secs + 1.5):
        break
    if now >= nxt and now - t0 < a.secs:
        seq = (seq + 1) & 0xffff
        i = ident if a.same_id else (ident + seq) & 0xffff
        h = struct.pack("!BBHHH", 8, 0, 0, i, seq)
        d = b"campus-probe-" + b"x" * 19
        pkt = struct.pack("!BBHHH", 8, 0, cksum(h + d), i, seq) + d
        s.sendto(pkt, (a.dst, 0))
        pending[(i, seq)] = now
        nxt += a.interval
    r, _, _ = select.select([s], [], [], min(0.02, max(0, nxt - time.time())))
    if r:
        data, addr = s.recvfrom(2048)
        hl = (data[0] & 15) * 4
        if addr[0] == a.dst and data[hl] == 0:
            i, q = struct.unpack("!HH", data[hl + 4:hl + 8])
            t = pending.pop((i, q), None)
            if t is not None:
                rx.append([round(t, 3), round(time.time(), 3)])
print(json.dumps({"sent": seq, "recv": len(rx), "t0": t0, "rx": rx}))
