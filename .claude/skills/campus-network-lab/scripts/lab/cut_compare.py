#!/usr/bin/env python3
"""cut_compare.py <nhan-che-do> [so-lan] [ca,ca,...] : do 6 kich ban cat lien ket S1-S6 tai Campus chinh (28/11/2026).

Chay TREN server EVE (Python 3.5: khong f-string). Dau do = 4 icmp_probe.py (0,1 s, giu nguyen id = mot luong
lien tuc) chay trong namespace lt_m99 gan vao VLAN 99 (vnet0_96, 10.1.99.200/24, route 10.1.0.0/16 qua Core-SW1),
toi mot may moi VLAN. Cat that = ha tap cua dau OVS (ip link set ... down), giu HOLD s, bat lai, cho POST s.
Dung chung cho che do SDN (Ryu) va che do doi chung RSTP (OVS standalone + RSTP + NORMAL) de so cung dieu kien.
Ket qua: moi ca mot dong JSON vao /root/loadtest/cutcmp.jsonl va in bang tom tat.
"""
import json
import subprocess
import sys
import time

TAP = {'D1-C1': 'vunl0_5_6', 'D1-C2': 'vunl0_5_7', 'D2-C1': 'vunl0_8_7', 'D1-D2': 'vunl0_5_5',
       'A4-D1': 'vunl0_69_1'}
CASES = [('S1', ['D1-C1']), ('S2', ['A4-D1']), ('S3', ['D1-D2']), ('S4', ['D2-C1']),
         ('S5', ['A4-D1', 'D2-C1']), ('S6', ['D1-C1', 'D1-C2'])]
TARGETS = sys.argv[4].split(',') if len(sys.argv) > 4 else \
    ['10.1.10.100', '10.1.20.100', '10.1.30.100', '10.1.40.100']
import os
PRE, HOLD, POST, IV = 5.0, float(os.environ.get("HOLD", "20")), 25.0, 0.1
OUT = '/root/loadtest/cutcmp.jsonl'


def sh(cmd):
    return subprocess.call(cmd, shell=True)


def probes(secs):
    return [(d, subprocess.Popen(['ip', 'netns', 'exec', 'lt_m99', 'python3', '/root/loadtest/icmp_probe.py', d,
                                  str(secs), '--interval', str(IV), '--same-id'],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)) for d in TARGETS]


def outages(rx, t_cut, t_rest, t_end):
    """Gian doan dai nhat (s) trong cua so cat va cua so khoi phuc, tinh tu thoi diem GUI cua cac goi co tra loi."""
    sent = sorted(r[0] for r in rx)
    cut = rest = 0.0
    edges = [t_cut - 1.0] + [s for s in sent if t_cut - 1.0 <= s <= t_end] + [t_end]
    for a, b in zip(edges, edges[1:]):
        g = max(0.0, b - a - IV)
        if g < 0.05:
            continue
        if a < t_rest:
            cut = max(cut, g)
        else:
            rest = max(rest, g)
    return round(cut, 1), round(rest, 1)


def run_case(mode, name, links, rep):
    taps = [TAP[l] for l in links]
    ps = probes(PRE + HOLD + POST)
    time.sleep(PRE)
    t_cut = time.time()
    for t in taps:
        sh('ip link set %s down' % t)
    if os.environ.get('FLUSH') == '1':
        # bien the "STP dong nhat": xoa bang MAC dong tren Core-SW1/2 moi 2 s tu luc cat den 5 s sau khi noi lai,
        # gia lap viec TC xoa MAC o moi VLAN (PVST+ tron RSTP chi xoa VLAN 1)
        flush_end = time.time() + HOLD + 5.0
        import socket
        import threading

        def flusher():
            cons = []
            for nid in (3, 4):
                s = socket.create_connection(('127.0.0.1', 32768 + nid), timeout=3)
                cons.append(s)
            while time.time() < flush_end:
                for s in cons:
                    try:
                        s.sendall(b'\rclear mac address-table dynamic\r')
                    except OSError:
                        pass
                time.sleep(2.0)
            for s in cons:
                s.close()
        threading.Thread(target=flusher, daemon=True).start()
    time.sleep(HOLD)
    t_rest = time.time()
    for t in taps:
        sh('ip link set %s up' % t)
    res = {'mode': mode, 'case': name, 'links': '+'.join(links), 'rep': rep,
           't_cut': round(t_cut, 3), 't_rest': round(t_rest, 3), 'targets': {}}
    for d, p in ps:
        out, _ = p.communicate()
        try:
            j = json.loads(out.decode())
        except ValueError:
            res['targets'][d] = {'error': 'no output'}
            continue
        c, r = outages(j['rx'], t_cut, t_rest, t_rest + POST - 1.0)
        res['targets'][d] = {'sent': j['sent'], 'recv': j['recv'], 'cut_s': c, 'restore_s': r}
    with open(OUT, 'a') as f:
        f.write(json.dumps(res) + '\n')
    worst_c = max(v.get('cut_s', -1) for v in res['targets'].values())
    worst_r = max(v.get('restore_s', -1) for v in res['targets'].values())
    print('%-5s %-4s lan %d  %-13s cat %5.1f s  khoi phuc %5.1f s  %s' % (
        mode, name, rep, '+'.join(links), worst_c, worst_r,
        ' '.join('%s:%s/%s' % (d.split('.')[2], v.get('recv'), v.get('sent')) for d, v in sorted(res['targets'].items()))))
    sys.stdout.flush()


def main():
    mode = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    only = sys.argv[3].split(',') if len(sys.argv) > 3 and sys.argv[3] else None
    for rep in range(1, reps + 1):
        for name, links in CASES:
            if only and name not in only:
                continue
            run_case(mode, name, links, rep)
            time.sleep(5)


if __name__ == '__main__':
    main()
