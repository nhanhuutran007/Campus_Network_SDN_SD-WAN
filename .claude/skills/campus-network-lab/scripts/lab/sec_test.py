#!/usr/bin/env python3
"""sec_test.py up|scan|esp|down : phep thu bao mat (28/11/2026), chay TREN server EVE (Python 3.5).

up   : tao 2 namespace dong vai may tan cong
         lt_b200 tren LAN Site 200 VLAN 60 (vnet0_58, cung doan voi VPC43): 10.2.60.250/24, gw 10.2.60.1
         lt_dmz  tren DMZ Site 100 (vnet0_49, cung doan voi Web-Server):   10.1.1.13/28,  gw 10.1.1.1
scan : quet cong TCP (connect, het han 2 s) theo 3 phep thu, in JSON moi dong va bang tom tat
         T1 chi nhanh -> DMZ (Web 10.1.1.10, Mail 10.1.1.11)
         T2 DMZ -> mang noi bo (DHCP/DNS 10.1.90.10, Core-SW1 10.1.90.2, may tram 10.1.10.101)
         T3 chi nhanh -> Server Farm va Core (10.1.90.10, 10.1.90.2)
esp  : bat goi tren transport cua vEdge1/vEdge2 Site 200 va tren LAN cua vEdge1 trong luc lt_b200 ping 10.1.90.10
down : go 2 namespace
open = co SYN-ACK; closed = RST (toi duoc may dich nhung cong dong); filtered = het han (bi chan tren duong).
"""
import json
import subprocess
import sys

NS = {'lt_b200': ('vnet0_58', '10.2.60.250/24', '10.2.60.1'),
      'lt_dmz': ('vnet0_49', '10.1.1.13/28', '10.1.1.1')}
PORTS = [22, 23, 25, 53, 80, 135, 143, 443, 445, 587, 993, 3306, 3389, 8080]
TESTS = [('T1', 'lt_b200', ['10.1.1.10', '10.1.1.11']),
         ('T2', 'lt_dmz', ['10.1.90.10', '10.1.90.2', '10.1.10.101']),
         ('T3', 'lt_b200', ['10.1.90.10', '10.1.90.2'])]
PROBE = r'''
import socket, sys, errno
h, p = sys.argv[1], int(sys.argv[2])
s = socket.socket(); s.settimeout(2.0)
try:
    s.connect((h, p)); print("open")
except socket.timeout:
    print("filtered")
except OSError as e:
    print("closed" if e.errno == errno.ECONNREFUSED else "filtered")
'''


def sh(cmd):
    return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode(errors='replace')


def up():
    for n, (br, ip, gw) in sorted(NS.items()):
        if n in sh('ip netns list'):
            print(n, 'da co')
            continue
        v = 'v_' + n[3:]
        sh('ip netns add %s; ip link add %s type veth peer name e0 netns %s; ip link set %s master %s up; '
           'ip netns exec %s ip link set lo up; ip netns exec %s ip link set e0 up' % (n, v, n, v, br, n, n))
        sh('ip netns exec %s ip addr add %s dev e0; ip netns exec %s ip route add default via %s' % (n, ip, n, gw))
        print(n, ip, 'tren', br, sh('ip netns exec %s ping -c 2 -W 1 %s | tail -1 || true' % (n, gw)).strip())


def scan():
    open('/root/loadtest/sec_probe.py', 'w').write(PROBE)
    for name, ns, hosts in TESTS:
        for h in hosts:
            res = {}
            for p in PORTS:
                res[p] = sh('ip netns exec %s python3 /root/loadtest/sec_probe.py %s %d' % (ns, h, p)).strip()
            icmp = 'ok' if subprocess.call('ip netns exec %s ping -c 2 -W 1 %s >/dev/null' % (ns, h),
                                           shell=True) == 0 else 'drop'
            line = {'test': name, 'src': ns, 'dst': h, 'icmp': icmp, 'tcp': res}
            open('/root/loadtest/sec_test.jsonl', 'a').write(json.dumps(line) + '\n')
            print('%s %-8s -> %-12s icmp=%-4s open=%s closed=%s filtered=%s' % (
                name, ns, h, icmp,
                ','.join(str(p) for p in PORTS if res[p] == 'open') or '-',
                ','.join(str(p) for p in PORTS if res[p] == 'closed') or '-',
                ','.join(str(p) for p in PORTS if res[p] == 'filtered') or '-'))
            sys.stdout.flush()


def esp():
    taps = [('vEdge1-S200 MPLS', 'vunl0_29_3'), ('vEdge2-S200 Internet', 'vunl0_42_1'),
            ('vEdge1-S200 LAN', 'vunl0_29_1')]
    procs = []
    for label, t in taps:
        procs.append((label, t, subprocess.Popen('timeout 12 tcpdump -nn -i %s -c 6 "icmp or (udp and not port 53)" 2>/dev/null'
                                                 % t, shell=True, stdout=subprocess.PIPE)))
    subprocess.call('ip netns exec lt_b200 ping -c 8 -i 0.5 10.1.90.10 >/dev/null', shell=True)
    for label, t, p in procs:
        out = p.communicate()[0].decode(errors='replace')
        print('==== %s (%s)' % (label, t))
        print(out)
    print('==== mot goi tren transport, dang hex (khong thay noi dung ICMP)')
    print(sh('timeout 8 tcpdump -nn -X -i vunl0_29_3 -c 1 "udp and not port 53" 2>/dev/null & '
             'sleep 1; ip netns exec lt_b200 ping -c 3 10.1.90.10 >/dev/null; wait'))


def down():
    for n in NS:
        subprocess.call('ip link del v_%s 2>/dev/null; ip netns del %s 2>/dev/null' % (n[3:], n), shell=True)
    print(sh('ip netns list'))


if __name__ == '__main__':
    {'up': up, 'scan': scan, 'esp': esp, 'down': down}[sys.argv[1]]()
