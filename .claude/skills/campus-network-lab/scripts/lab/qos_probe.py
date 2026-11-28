#!/usr/bin/env python3
"""qos_probe.py : do chat luong theo lop (thoai EF, video AF41, thuong BE) qua overlay SD-WAN (28/11/2026).

Chay TREN server EVE (Python 3.5, khong f-string). Hai dau la network namespace tren cung may chu nen dung chung
dong ho -> do duoc tre MOT CHIEU that, khong chi RTT.
  rx <secs> <out.json>                       : chay trong ns dich, nghe UDP 5001/5002/5003, ghi DSCP nhan duoc
  tx <dst> <secs> <video_kbps> <out.json>    : chay trong ns nguon
  run <src_ns> <dst_ns> <dst> <secs> <label> [bulk_streams] [video_kbps]
                                             : dieu phoi ca hai + (tuy chon) iperf3 TCP lam nghen; in tom tat,
                                               ghi 1 dong JSON vao /root/loadtest/qos.jsonl (kem chuoi theo tung giay)
Lop: voice = 160 byte moi 20 ms, TOS 0xB8 (EF 46); video = 1200 byte, toc do video_kbps, TOS 0x88 (AF41 34);
     be = 160 byte moi 20 ms, TOS 0 (doi chung cung nhip voi thoai).
MOS thoai: E-model rut gon (ITU-T G.107), G.711 co PLC (Ie=0, Bpl=25,1), tre = mot chieu + 2*jitter + 20 ms.
"""
import json
import math
import select
import socket
import struct
import subprocess
import sys
import time

PORTS = {'voice': 5001, 'video': 5002, 'be': 5003}
TOS = {'voice': 0xB8, 'video': 0x88, 'be': 0x00}
HDR = struct.Struct('!IdB')
IP_RECVTOS = 13


def rx(secs, out):
    socks = {}
    for c, p in PORTS.items():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_IP, IP_RECVTOS, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
        s.bind(('0.0.0.0', p))
        socks[s] = c
    rec = {c: [] for c in PORTS}
    tos_seen = {c: {} for c in PORTS}
    end = time.time() + secs
    while time.time() < end:
        r, _, _ = select.select(list(socks), [], [], 0.2)
        for s in r:
            data, anc, _, _ = s.recvmsg(2048, 64)
            now = time.time()
            if len(data) < HDR.size:
                continue
            seq, ts, _ = HDR.unpack_from(data)
            tos = None
            for lvl, typ, val in anc:
                if lvl == socket.SOL_IP and typ in (1, IP_RECVTOS):
                    tos = val[0]
            c = socks[s]
            rec[c].append((seq, ts, now))
            tos_seen[c][str(tos)] = tos_seen[c].get(str(tos), 0) + 1
    json.dump({'rec': rec, 'tos': tos_seen}, open(out, 'w'))


def tx(dst, secs, video_kbps, out):
    s = {}
    for c in PORTS:
        k = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        k.setsockopt(socket.SOL_IP, socket.IP_TOS, TOS[c])
        s[c] = k
    size = {'voice': 160, 'video': 1200, 'be': 160}
    iv = {'voice': 0.02, 'be': 0.02, 'video': 1200 * 8.0 / (video_kbps * 1000.0)}
    seq = {c: 0 for c in PORTS}
    t0 = time.time()
    nxt = {c: t0 for c in PORTS}
    while True:
        now = time.time()
        if now - t0 >= secs:
            break
        for c in PORTS:
            if now >= nxt[c]:
                seq[c] += 1
                pkt = HDR.pack(seq[c], now, 0) + b'x' * (size[c] - HDR.size)
                try:
                    s[c].sendto(pkt, (dst, PORTS[c]))
                except OSError:
                    pass
                nxt[c] += iv[c]
        time.sleep(max(0.0, min(nxt.values()) - time.time()))
    json.dump({'sent': seq, 't0': t0, 'secs': secs}, open(out, 'w'))


def mos(delay_ms, jitter_ms, loss_pct):
    d = delay_ms + 2 * jitter_ms + 20.0
    idd = 0.024 * d + (0.11 * (d - 177.3) if d > 177.3 else 0.0)
    ie = 95.0 * loss_pct / (loss_pct + 25.1)
    r = max(0.0, min(100.0, 93.2 - idd - ie))
    return round(1 + 0.035 * r + 7e-6 * r * (r - 60) * (100 - r), 2)


def summarize(rec, sent, t0, secs):
    out = {}
    for c in PORTS:
        rows = sorted(rec[c])
        n = len(rows)
        d = sorted((r[2] - r[1]) * 1000.0 for r in rows)
        j, prev = 0.0, None
        for seq, ts, ar in rows:
            if prev is not None:
                j += (abs((ar - ts) - (prev[1] - prev[0])) * 1000.0 - j) / 16.0
            prev = (ts, ar)
        loss = 100.0 * (sent[c] - n) / sent[c] if sent[c] else 0.0
        series = []
        for k in range(int(secs)):
            w = [r for r in rows if t0 + k <= r[1] < t0 + k + 1]
            exp = 50 if c != 'video' else None
            series.append([k, round(sum((r[2] - r[1]) for r in w) * 1000.0 / len(w), 1) if w else None, len(w)])
        out[c] = {'sent': sent[c], 'recv': n, 'loss_pct': round(loss, 2),
                  'delay_avg_ms': round(sum(d) / n, 1) if n else None,
                  'delay_p95_ms': round(d[int(0.95 * (n - 1))], 1) if n else None,
                  'delay_max_ms': round(d[-1], 1) if n else None,
                  'jitter_ms': round(j, 1), 'series': series}
    v = out['voice']
    if v['delay_avg_ms'] is not None:
        v['mos'] = mos(v['delay_avg_ms'], v['jitter_ms'], v['loss_pct'])
    b = out['be']
    if b['delay_avg_ms'] is not None:
        b['mos_neu_la_thoai'] = mos(b['delay_avg_ms'], b['jitter_ms'], b['loss_pct'])
    return out


def run(src_ns, dst_ns, dst, secs, label, bulk=0, video_kbps=600):
    me = '/root/loadtest/qos_probe.py'
    prx = subprocess.Popen(['ip', 'netns', 'exec', dst_ns, 'python3', me, 'rx', str(secs + 4), '/tmp/qos_rx.json'])
    ips = None
    if bulk:
        ips = subprocess.Popen(['ip', 'netns', 'exec', dst_ns, 'iperf3', '-s', '-1', '-p', '5201'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    ipc = None
    if bulk:
        ipc = subprocess.Popen(['ip', 'netns', 'exec', src_ns, 'iperf3', '-c', dst, '-p', '5201', '-t', str(secs + 2),
                                '-P', str(bulk), '-J'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        time.sleep(2)
    subprocess.call(['ip', 'netns', 'exec', src_ns, 'python3', me, 'tx', dst, str(secs), str(video_kbps),
                     '/tmp/qos_tx.json'])
    prx.wait()
    bulk_mbps = None
    if ipc:
        o, _ = ipc.communicate()
        try:
            bulk_mbps = round(json.loads(o.decode())['end']['sum_received']['bits_per_second'] / 1e6, 2)
        except (ValueError, KeyError):
            bulk_mbps = None
    if ips:
        ips.kill()
    r = json.load(open('/tmp/qos_rx.json'))
    t = json.load(open('/tmp/qos_tx.json'))
    s = summarize(r['rec'], t['sent'], t['t0'], secs)
    res = {'label': label, 't0': round(t['t0'], 3), 'secs': secs, 'bulk_streams': bulk, 'bulk_mbps': bulk_mbps,
           'video_kbps': video_kbps, 'tos_seen': r['tos'], 'classes': s}
    open('/root/loadtest/qos.jsonl', 'a').write(json.dumps(res) + '\n')
    print('== %s (%d s, TCP nen %s luong, %s Mbit/s)' % (label, secs, bulk, bulk_mbps))
    for c in ('voice', 'video', 'be'):
        x = s[c]
        print('  %-5s tre TB %6s ms  p95 %6s ms  jitter %5s ms  mat %5.2f %%  %s' % (
            c, x['delay_avg_ms'], x['delay_p95_ms'], x['jitter_ms'], x['loss_pct'],
            ('MOS %.2f' % x['mos']) if 'mos' in x else ''))
    print('  DSCP nhan duoc (TOS):', json.dumps(r['tos']))
    sys.stdout.flush()


if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'rx':
        rx(float(a[2]), a[3])
    elif a[1] == 'tx':
        tx(a[2], float(a[3]), float(a[4]), a[5])
    elif a[1] == 'run':
        run(a[2], a[3], a[4], int(a[5]), a[6], int(a[7]) if len(a) > 7 else 0, int(a[8]) if len(a) > 8 else 600)
