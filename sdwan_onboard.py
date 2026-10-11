#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdwan_onboard.py  –  Tu dong onboard vEdge moi cam vao Switch32 (Site 900)
================================================================
Quy trinh 9 buoc PKI trong skill (sdwan-viptela.md) chay tu dong qua console
EVE-NG (SSH host EVE -> direct-tcpip 127.0.0.1:33536+id), dung cho viec mo
rong chi nhanh: tao node vEdge moi tren EVE, noi 1 cong vao Switch32 la tool
tu lam phan con lai.

  1. Do vEdge moi: doc .unl tren host EVE, tim node vtedge co link chung
     network voi Switch32 ma chua co trong danh sach (khong cham console)
  2. Switch32: cong noi vEdge -> access VLAN 10 (CONTROLLER-LAN 10.9.0.0/24)
  3. vEdge: dang nhap (doi mat khau lan dau neu la may moi), dan cau hinh
     co ban site 900: system-ip 10.200.90.N, vpn 0 10.9.0.(99+N)/24 biz-internet
  4. CSR -> scp len vManage -> ky bang CA cu /home/admin/ca (vshell) ->
     scp cert + root CA ve -> cai root chain roi cai cert
  5. request vedge add tren vManage + vSmart + vBond
  6. Cho control connection vbond/vmanage/vsmart Up

Danh sach vEdge da onboard (chassis/serial) luu o log/onboard_registry.json
-> dung de "day lai whitelist" sau khi controller reboot (cac vEdge ky tay
khong nam trong certificate/vedge/list cua vManage nen nut push API khong cuu
duoc). Mat khau chi nhan qua tham so luc chay, khong ghi ra file/log.
================================================================
"""
import ipaddress, json, os, re, shlex, time
import xml.etree.ElementTree as ET
from datetime import datetime

from campus_ping_tool import (
    LOG_DIR, VEDGE_NODE_IDS, VMANAGE_NODE_ID, console_open, ios_wake, _last_line, _read_chan, _read_until,
)

SWITCH_NODE_ID  = 32                 # Switch32 - switch LAN controller site 900
VSMART_NODE_ID  = 34
VBOND_NODE_ID   = 35
CONTROLLER_VLAN = 10
LAN_NET         = ipaddress.ip_network('10.9.0.0/24')
LAN_GW          = '10.9.0.2'         # SVI Vlan10 tren Switch32
VMANAGE_IP      = '10.9.0.10'        # vManage = CA (scp CSR/cert)
VBOND_IP        = '10.9.0.12'
ORG             = 'site-900'
SITE_ID         = 900
CA_DIR          = '/home/admin/ca'   # CA cu SDWAN-Lab-RootCA (root-ca.pem/.key)
LAB_NAME        = 'Campus Network SDN SD-WAN.unl'
REGISTRY        = os.path.join(LOG_DIR, 'onboard_registry.json')
# cong Switch32 dang noi ha tang (configs/05-Site900-Controller/Switch32) -> cam doi VLAN
PROTECTED_PORTS = {'e0/0': 'vBond', 'e0/1': 'vSmart', 'e0/2': 'vManage', 'e0/3': 'Win',
                   'e1/0': 'Internet', 'e1/1': 'MPLS', 'e1/2': 'vEdge65 WAN'}

# vEdge-Spare (node 23) da ky tay 08/10/2026 - dua san vao danh sach de cap
# phat IP khong trung va de nut "day lai whitelist" bao ca node nay.
SEED = {'23': {'node': 23, 'hostname': 'vEdge-Spare', 'system_ip': '10.200.90.1', 'site_id': 900,
               'vpn0_ip': '10.9.0.100', 'wan_if': 'ge0/0', 'sw_port': 'e1/3',
               'chassis': 'ce69e515-b477-47d1-9379-fe3d2aa9ab8f',
               'serial': '050CC67238AF8949E4AE8D4CDF8083AA9A73F98D', 'status': 'done'}}


class OnboardError(RuntimeError):
    pass


# =========================================================
#  DANH SACH vEdge DA ONBOARD
# =========================================================
def load_registry():
    try:
        with open(REGISTRY, encoding='utf-8') as f:
            reg = json.load(f)
    except (OSError, ValueError):
        reg = {}
    for k, v in SEED.items():
        reg.setdefault(k, dict(v))
    return reg


def save_entry(entry):
    reg = load_registry()
    entry['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    reg[str(entry['node'])] = entry
    with open(REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)


def forget(node):
    reg = load_registry()
    if reg.pop(str(node), None) is None:
        return False
    with open(REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    return True


def allocate(reg, skip=()):
    """N nho nhat chua dung -> (N, system-ip 10.200.90.N, vpn0 10.9.0.(99+N))."""
    used = {e.get('system_ip') for e in reg.values()} | {e.get('vpn0_ip') for e in reg.values()} | set(skip)
    for n in range(1, 100):
        sip, lan = '10.200.90.{}'.format(n), '10.9.0.{}'.format(99 + n)
        if sip not in used and lan not in used:
            return n, sip, lan
    raise OnboardError('het dia chi 10.9.0.100-198 cho vEdge site 900')


def default_hostname(n):
    return 'vEdge-Spare' if n == 1 else 'vEdge-Spare{}'.format(n)


# =========================================================
#  DO vEdge MOI TU .unl TREN HOST EVE (chi doc)
# =========================================================
def _host(ssh, cmd, timeout=40):
    _, out, _ = ssh.exec_command(cmd, timeout=timeout)
    return out.read().decode('utf-8', errors='replace')


def find_lab(ssh, override=''):
    if override:
        return override
    path = _host(ssh, "find /opt/unetlab/labs -name {} 2>/dev/null | head -1".format(shlex.quote(LAB_NAME))).strip()
    if path:
        return path
    # fallback: lab co instance dang chay chua Switch32
    for uuid in sorted(set(re.findall(r'/tmp/\d+/([0-9a-f-]{36})/',
                                      _host(ssh, 'ls -d /opt/unetlab/tmp/*/*/{} 2>/dev/null'.format(SWITCH_NODE_ID))))):
        path = _host(ssh, "grep -rl --include='*.unl' 'id=\"{}\"' /opt/unetlab/labs 2>/dev/null | head -1".format(uuid)).strip()
        if path:
            return path
    raise OnboardError('khong tim thay file lab .unl tren host EVE (nhap duong dan tay)')


def sw_port_long(short):
    """'e1/3' (ten trong .unl) -> 'Ethernet1/3' (IOS)."""
    m = re.match(r'^e(\d+/\d+)$', short or '')
    return 'Ethernet' + m.group(1) if m else short


def discover(ssh, lab_override=''):
    """Tra ve (lab_path, [candidate]) - moi candidate la vEdge noi vao Switch32
    chua co trong danh sach onboard va khong phai vEdge chi nhanh dang chay."""
    lab = find_lab(ssh, lab_override)
    raw = _host(ssh, 'cat {}'.format(shlex.quote(lab)), 60)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise OnboardError('doc .unl loi: {}'.format(e))
    nodes = {n.get('id'): n for n in root.iter('node')}
    sw = nodes.get(str(SWITCH_NODE_ID))
    if sw is None:
        raise OnboardError('.unl khong co node {} (Switch32)'.format(SWITCH_NODE_ID))
    sw_nets = {i.get('network_id'): i.get('name') for i in sw.iter('interface') if i.get('network_id') not in (None, '0')}
    reg = load_registry()
    busy = {str(v) for v in VEDGE_NODE_IDS.values()}
    out = []
    for nid, n in nodes.items():
        if n.get('template') != 'vtedge' and not (n.get('image') or '').startswith('vtedge'):
            continue
        for i in n.iter('interface'):
            net = i.get('network_id')
            if net in sw_nets:
                e = reg.get(nid, {})
                out.append({'node': int(nid), 'name': n.get('name'), 'wan_if': i.get('name'),
                            'sw_port': sw_nets[net], 'status': e.get('status', 'new'),
                            'known': nid in busy, 'protected': sw_nets[net] in PROTECTED_PORTS})
    out.sort(key=lambda c: c['node'])
    return lab, out


# =========================================================
#  CONSOLE (Viptela CLI / IOS / vshell)
# =========================================================
class Console:
    def __init__(self, ssh, node_id, name):
        self.name, self.node = name, node_id
        try:
            self.chan = console_open(ssh, node_id)
        except Exception as e:
            raise OnboardError('khong mo duoc console {} (node {}): {}'.format(name, node_id, e))

    def close(self):
        try: self.chan.close()
        except Exception: pass

    def read(self, timeout, answers=(), prompt=True):
        """Doc toi prompt '#'. answers = [[regex, tra loi, so lan toi da], ...]
        cho cac cau hoi giua chung (yes/no, password, organization-unit).
        Hoi qua so lan cho phep (vd sai mat khau) -> Ctrl-C va bao loi, tranh
        thu mat khau lien tuc gay khoa tai khoan."""
        buf, pos = '', 0
        used = [0] * len(answers)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.chan.recv_ready():
                time.sleep(0.15); continue
            buf += self.chan.recv(65535).decode('utf-8', errors='replace')
            tail = _last_line(buf[pos:])
            for k, (rx, reply, limit) in enumerate(answers):
                if re.search(rx, tail, re.I):
                    if used[k] >= limit:
                        self.chan.send('\x03'); time.sleep(1)
                        raise OnboardError('{}: hoi lai "{}" - sai tra loi/mat khau?'.format(self.name, tail[-60:]))
                    used[k] += 1
                    self.chan.send(reply + '\n'); pos = len(buf)
                    break
            else:
                if prompt and tail.endswith('#'):
                    return buf
        raise OnboardError('{}: het {}s chua thay prompt (cuoi: {!r})'.format(self.name, timeout, _last_line(buf)[-80:]))

    def cli(self, cmd, timeout=30, answers=()):
        self.chan.send(cmd + '\n')
        return self.read(timeout, answers)

    def probe(self):
        """Console da san sang chua (vEdge moi boot mat 10-15 phut)."""
        self.chan.send('\n')
        tail = _last_line(_read_chan(self.chan, timeout=3))
        return bool(re.search(r'(login\s*:|#|>)\s*$', tail, re.I))

    # ---- Viptela ----
    def login(self, user, passwords, new_pw=None):
        """Vao prompt exec '#'. Thu lan luot passwords (moi mat khau 1 lan);
        vEdge moi (admin/admin) bat dat mat khau dau tien -> dat new_pw."""
        passwords = [p for p in passwords if p]
        for _ in range(3):
            self.chan.send('\n')
            buf = _read_chan(self.chan, timeout=3)
            tail = _last_line(buf)
            if re.search(r'uncommitted changes', buf, re.I):
                self.chan.send('no\n'); time.sleep(1); continue
            if '(config' in tail:
                self.chan.send('end\n'); time.sleep(1); continue
            if tail.endswith('#'):
                return
            if re.search(r'login\s*:\s*$', tail, re.I):
                break
        else:
            raise OnboardError('{}: khong thay prompt login/# (cuoi: {!r})'.format(self.name, tail[-60:]))
        for pw in passwords:
            self.chan.send(user + '\n')
            _read_until(self.chan, 'assword', 8)
            self.chan.send(pw + '\n'); time.sleep(2)
            buf = _read_chan(self.chan, timeout=5)
            tail = _last_line(buf)
            if tail.endswith('#'):
                return
            if tail.lower().endswith('password:') and 'incorrect' not in buf.lower():
                # dang nhap lan dau: bat buoc doi mat khau, nhap 2 lan cung gia tri
                if not new_pw:
                    raise OnboardError('{} yeu cau dat mat khau moi - nhap "Mat khau vEdge"'.format(self.name))
                self.chan.send(new_pw + '\n'); _read_until(self.chan, 'assword', 8)
                self.chan.send(new_pw + '\n'); time.sleep(2)
                buf = _read_chan(self.chan, timeout=5)
                if _last_line(buf).endswith('#'):
                    return
                raise OnboardError('{}: dat mat khau moi bi tu choi ({!r}) - vEdge cam 3 ky tu lien tiep '
                                   'nhu "123"/"abc"'.format(self.name, _last_line(buf)[-80:]))
            if not re.search(r'login\s*:\s*$', tail, re.I):
                _read_until(self.chan, 'login:', 5)
        raise OnboardError('{}: dang nhap that bai (sai mat khau?)'.format(self.name))

    def commit(self, lines):
        self.cli('config', 15)
        for line in lines:
            self.chan.send(line + '\n'); time.sleep(0.25)
        time.sleep(1); _read_chan(self.chan, timeout=3)     # bo prompt cua tung dong, tranh doc nham
        self.chan.send('commit\n')
        res, deadline = '', time.time() + 90
        while time.time() < deadline and not re.search(r'Commit complete|No modifications|Aborted|Error|failed', res):
            res += _read_chan(self.chan, timeout=3)
        if 'Commit complete' not in res and 'No modifications to commit' not in res:
            self.chan.send('abort\n'); time.sleep(1); _read_chan(self.chan, timeout=2)
            why = re.findall(r'^.*(?:Aborted|Error|failed).*$', res, re.M | re.I) or [_last_line(res)]
            raise OnboardError('{}: commit loi: {}'.format(self.name, ' | '.join(w.strip() for w in why)[-200:]))
        self.cli('end', 10)
        return res

    # ---- vshell (vManage) ----
    def vshell(self):
        self.chan.send('vshell\n'); time.sleep(1.5); _read_chan(self.chan, timeout=3)
        self.chan.send('stty -echo cols 500; export PS1="VSH# "\n'); time.sleep(0.8); _read_chan(self.chan, timeout=2)

    def sh(self, cmd, timeout=40):
        self.chan.send('echo "@@""B@@"; {}; echo; echo "@@""E@@"\n'.format(cmd))
        m = re.search(r'@@B@@(.*)@@E@@', _read_until(self.chan, '@@E@@', timeout), re.S)
        if not m:
            raise OnboardError('{}: lenh vshell khong tra ket qua: {}'.format(self.name, cmd[:60]))
        return m.group(1).replace('\r', '').strip()

    def vshell_exit(self):
        self.chan.send('stty echo; exit\n'); time.sleep(1); _read_chan(self.chan, timeout=2)


def local_props(con):
    out = con.cli('show control local-properties', 30)
    get = lambda k: (re.search(r'^\s*' + re.escape(k) + r'\s+(\S+)', out, re.M) or [None, ''])[1]
    return {'chassis': get('chassis-num/unique-id'), 'serial': get('serial-num'),
            'validity': get('certificate-validity'), 'chain': get('root-ca-chain-status'),
            'cert': get('certificate-status')}


# =========================================================
#  CAC BUOC ONBOARD
# =========================================================
def switch_port(ssh, log, port, hostname, wr, ips_to_check=()):
    """Dua cong Switch32 ve access VLAN 10. Tra ve tap IP trong ips_to_check
    dang co may tra loi ping (de tranh cap trung)."""
    long = sw_port_long(port)
    if port in PROTECTED_PORTS:
        raise OnboardError('Switch32 {} la cong ha tang ({}) - khong cau hinh lai'.format(port, PROTECTED_PORTS[port]))
    con = Console(ssh, SWITCH_NODE_ID, 'Switch32')
    try:
        tail = ios_wake(con.chan)
        if tail.endswith('>'):
            con.chan.send('enable\n'); time.sleep(1)
            if not _last_line(_read_chan(con.chan, timeout=3)).endswith('#'):
                raise OnboardError('Switch32 hoi enable password - cau hinh cong tay')
        con.cli('terminal length 0', 10)
        cur = con.cli('show running-config interface {}'.format(long), 20)
        if 'Invalid input' in cur:
            raise OnboardError('Switch32 khong co {}'.format(long))
        ok = re.search(r'switchport access vlan {}\b'.format(CONTROLLER_VLAN), cur) and \
            'switchport mode access' in cur and not re.search(r'^\s*shutdown', cur, re.M)
        if ok:
            log('      Switch32 {} da la access VLAN {} - giu nguyen\n'.format(long, CONTROLLER_VLAN), 'ok')
        else:
            for c in ('configure terminal', 'interface ' + long, 'description To {} (onboard tool)'.format(hostname),
                      'switchport mode access', 'switchport access vlan {}'.format(CONTROLLER_VLAN),
                      'no shutdown', 'end'):
                out = con.cli(c, 15)
                if 'Invalid input' in out or '% ' in out.split('\n', 1)[-1]:
                    raise OnboardError('Switch32 tu choi "{}": {!r}'.format(c, _last_line(out)))
            if wr:
                con.cli('write memory', 30)
            log('      Switch32 {} -> access VLAN {}{}\n'.format(long, CONTROLLER_VLAN, ' (da write memory)' if wr else ''), 'ok')
        alive = set()
        for ip in ips_to_check:
            if '!' in con.cli('ping {} repeat 2 timeout 1'.format(ip), 15):
                alive.add(ip)
        return alive
    finally:
        con.close()


def base_config(e):
    return ['system', ' host-name ' + e['hostname'], ' system-ip ' + e['system_ip'],
            ' site-id {}'.format(e.get('site_id', SITE_ID)), ' organization-name ' + ORG, ' vbond ' + VBOND_IP, ' exit',
            'vpn 0', ' interface ' + e['wan_if'], '  no ip dhcp-client',
            '  ip address {}/{}'.format(e['vpn0_ip'], LAN_NET.prefixlen),
            '  tunnel-interface', '   encapsulation ipsec', '   color biz-internet', '   allow-service all', '   exit',
            '  no shutdown', '  exit', ' ip route 0.0.0.0/0 ' + LAN_GW, ' exit']


def _scp(con, src, dst, vm_pw, timeout=90):
    out = con.cli('request execute vpn 0 scp {} {}'.format(src, dst), timeout,
                  answers=[[r'\(yes/no', 'yes', 1], [r'assword:\s*$', vm_pw, 1]])
    if re.search(r'denied|No such file|not found|lost connection|Connection (refused|timed out)|No route', out, re.I):
        raise OnboardError('scp {} -> {} loi: {!r}'.format(src, dst, _last_line(out)))


def sign_on_vmanage(ssh, log, csr, crt, vm_user, vm_pw):
    con = Console(ssh, VMANAGE_NODE_ID, 'vManage')
    try:
        con.login(vm_user, [vm_pw])
        con.vshell()
        try:
            ls = con.sh('cd {} && ls root-ca.pem root-ca.key {} 2>&1'.format(CA_DIR, csr))
            if 'No such' in ls or 'cannot' in ls:
                raise OnboardError('thieu file tren vManage {}: {}'.format(CA_DIR, ls))
            subj = con.sh('openssl req -noout -subject -in {}'.format(csr))
            log('      CSR subject: {}\n'.format(subj), 'data')
            if not re.search(r'O\s*=\s*Cisco Systems', subj) or not re.search(r'OU\s*=\s*' + ORG, subj):
                raise OnboardError('subject CSR sai (can O=Cisco Systems, OU={}) - khong ky'.format(ORG))
            res = con.sh('openssl x509 -req -in {} -CA root-ca.pem -CAkey root-ca.key -CAcreateserial -out {} '
                         '-days 730 -sha256 2>&1; echo RC=$?; chmod 644 {}'.format(csr, crt, crt), 60)
            if 'RC=0' not in res:
                raise OnboardError('openssl ky loi: {}'.format(res[-200:]))
            log('      Da ky {} bang CA {}\n'.format(crt, CA_DIR), 'ok')
        finally:
            con.vshell_exit()
    finally:
        con.close()


CONTROLLERS = (  # (ten, node, khoa mat khau trong opts, lenh kiem tra)
    ('vManage', VMANAGE_NODE_ID, 'vm_pw', 'show control valid-vedges'),
    ('vSmart', VSMART_NODE_ID, 'vs_pw', 'show control valid-vedges'),
    ('vBond', VBOND_NODE_ID, 'vb_pw', 'show orchestrator valid-vedges'),
)


def whitelist(ssh, log, entries, opts):
    """request vedge add cho moi entry tren ca 3 controller. Tra ve so controller OK."""
    ok = 0
    for name, nid, key, show in CONTROLLERS:
        pw = opts.get(key) or (opts.get('vm_pw') if key == 'vb_pw' else '')
        if not pw:
            log('      [!] {}: chua nhap mat khau -> bo qua (vEdge se khong len {})\n'.format(name, name), 'err')
            continue
        con = None
        try:
            con = Console(ssh, nid, name)
            con.login(opts.get('vm_user') or 'admin', [pw])
            good = True
            for e in entries:
                con.cli('request vedge add chassis-num {} serial-num {}'.format(e['chassis'], e['serial']), 30)
                chk = con.cli('{} | include {}'.format(show, e['chassis']), 20)
                hit = e['chassis'] in chk.split('\n', 1)[-1]
                good &= hit
                log('      {:<8} {} ({}) {}\n'.format(name, e['hostname'], e['chassis'][:8],
                                                   'OK' if hit else 'KHONG thay trong valid-vedges'),
                    'ok' if hit else 'err')
            ok += good
        except Exception as ex:
            log('      [!] {}: {}\n'.format(name, ex), 'err')
        finally:
            if con: con.close()
    return ok


def wait_control(con, log, timeout, stop=None):
    """Poll 'show control connections' toi khi vmanage + vsmart Up."""
    t0 = time.time()
    while True:
        out = con.cli('show control connections', 30)
        up = {p: bool(re.search(r'^\s*{}\b.*\bup\b'.format(p), out, re.M | re.I)) for p in ('vbond', 'vmanage', 'vsmart')}
        if up['vmanage'] and up['vsmart']:
            log('      control: {} ({:.0f}s)\n'.format(', '.join(p + ' Up' for p, v in up.items() if v), time.time() - t0), 'ok')
            return True
        if time.time() - t0 > timeout or (stop and stop.is_set()):
            log('      control chua du sau {:.0f}s: {}\n'.format(time.time() - t0, up), 'err')
            hist = con.cli('show control connections-history | include CONNECT|DOWN|ERR|BID', 30)
            for line in [l for l in hist.replace('\r', '').split('\n')[1:-1] if l.strip()][:6]:
                log('        ' + line.strip() + '\n', 'data')
            log('      Goi y: BIDNTVRFD = thieu whitelist; "interface not configured" -> request reboot vEdge\n', 'info')
            return False
        time.sleep(15)


def onboard(ssh, log, e, opts, stop=None):
    """Chay du cac buoc cho 1 vEdge. e = entry registry (node, hostname,
    system_ip, vpn0_ip, wan_if, sw_port). Luu trang thai sau moi buoc."""
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[ONBOARD] node {} -> {} / system-ip {} / vpn0 {} {}\n'.format(
        e['node'], e['hostname'], e['system_ip'], e['vpn0_ip'], e['wan_if']), 'hdr')
    e.setdefault('site_id', SITE_ID)
    step = 'switch'
    try:
        if e.get('sw_port') and opts.get('cfg_switch', True):
            log('  [1/6] Switch32 cong {}\n'.format(e['sw_port']), 'info')
            if switch_port(ssh, log, e['sw_port'], e['hostname'], opts.get('wr', True), [e['vpn0_ip']]):
                log('      [!] {} dang co may tra loi ping - neu khong phai chinh vEdge nay (chay lai) '
                    'thi se trung IP\n'.format(e['vpn0_ip']), 'err')
        elif not opts.get('switch_done'):
            log('  [1/6] Bo qua cau hinh Switch32\n', 'info')

        step = 'config'
        log('  [2/6] Cau hinh co ban vEdge (console node {})\n'.format(e['node']), 'info')
        con = Console(ssh, e['node'], e['hostname'])
        try:
            con.login('admin', [opts.get('vedge_pw'), 'admin'], new_pw=opts.get('vedge_pw'))
            con.cli('screen-length 0', 10)
            con.commit(base_config(e))
            e['status'] = 'configured'; save_entry(e)
            log('      Commit complete\n', 'ok')

            step = 'cert'
            p = local_props(con)
            csr, crt = e['hostname'].lower() + '.csr', e['hostname'].lower() + '.crt'
            if p['validity'] == 'Valid' and p['chain'] == 'Installed' and not opts.get('resign'):
                log('  [3/6] Da co cert hop le (serial {}) - khong ky lai\n'.format(p['serial']), 'ok')
            else:
                log('  [3/6] Tao CSR + ky tren vManage (CA {})\n'.format(CA_DIR), 'info')
                out = con.cli('request csr upload /home/admin/' + csr, 90,
                              answers=[[r'organi[sz]ation', ORG, 4], [r'\[yes,no\]', 'yes', 2]])
                if re.search(r'error|fail', out, re.I):
                    raise OnboardError('tao CSR loi: {!r}'.format(_last_line(out)))
                _scp(con, '/home/admin/' + csr, 'admin@{}:{}/{}'.format(VMANAGE_IP, CA_DIR, csr), opts['vm_pw'])
                sign_on_vmanage(ssh, log, csr, crt, opts.get('vm_user') or 'admin', opts['vm_pw'])
                for f in (crt, 'root-ca.pem'):
                    _scp(con, 'admin@{}:{}/{}'.format(VMANAGE_IP, CA_DIR, f), '/home/admin/' + f, opts['vm_pw'])
                for c in ('request root-cert-chain install /home/admin/root-ca.pem',
                          'request certificate install /home/admin/' + crt):
                    out = con.cli(c, 90, answers=[[r'\[yes,no\]', 'yes', 2]])
                    if re.search(r'error|fail', out, re.I):
                        raise OnboardError('"{}" loi: {!r}'.format(c, _last_line(out)))
                p = local_props(con)
                if p['validity'] != 'Valid':
                    raise OnboardError('cert sau khi cai chua Valid ({})'.format(p))
                log('      Cert Valid, root chain {}, serial {}\n'.format(p['chain'], p['serial']), 'ok')
            if not p['chassis'] or not p['serial']:
                raise OnboardError('khong doc duoc chassis/serial tu local-properties')
            e.update(chassis=p['chassis'], serial=p['serial'], status='signed'); save_entry(e)

            step = 'whitelist'
            log('  [4/6] Whitelist tren vManage / vSmart / vBond\n', 'info')
            n_ok = whitelist(ssh, log, [e], opts)
            e['status'] = 'whitelisted' if n_ok == 3 else 'whitelist {}/3'.format(n_ok); save_entry(e)

            step = 'verify'
            log('  [5/6] Cho control connection (toi da {}s)\n'.format(opts.get('verify_s', 240)), 'info')
            up = wait_control(con, log, opts.get('verify_s', 240), stop)
        finally:
            con.close()
        e['status'] = 'done' if up else 'verify-fail'; save_entry(e)
        log('  [6/6] {} {}\n'.format(e['hostname'], 'DA VAO FABRIC - san sang lam chi nhanh moi' if up
                                     else 'chua len du controller - xem log'), 'ok' if up else 'err')
        return up
    except Exception as ex:
        e['status'] = 'failed:' + step; save_entry(e)
        log('  [!] Dung o buoc {}: {}\n'.format(step, ex), 'err')
        return False


def new_entry(cand, reg, overrides=None, skip=()):
    """Entry moi cho 1 candidate. Node da tung chay do (loi giua chung) thi
    giu hostname/IP cu de chay lai khong cap them dia chi."""
    o = overrides or {}
    old = reg.get(str(cand['node']), {})
    if old.get('system_ip') and old.get('vpn0_ip') and old['vpn0_ip'] not in skip:
        hostname, sip, lan = old.get('hostname'), old['system_ip'], old['vpn0_ip']
    else:
        others = {k: v for k, v in reg.items() if k != str(cand['node'])}
        n, sip, lan = allocate(others, skip)
        hostname = default_hostname(n)
    e = {'node': cand['node'], 'hostname': o.get('hostname') or hostname,
         'system_ip': o.get('system_ip') or sip, 'site_id': SITE_ID, 'vpn0_ip': o.get('vpn0_ip') or lan,
         'wan_if': o.get('wan_if') or cand.get('wan_if') or 'ge0/0', 'sw_port': o.get('sw_port', cand.get('sw_port', '')),
         'status': old.get('status', 'new')}
    for k in ('chassis', 'serial'):
        if old.get(k): e[k] = old[k]
    return e


def watch(ssh, log, opts, stop, interval=30):
    """Che do tu dong: quet .unl moi `interval` giay; vEdge moi noi vao
    Switch32 va da boot xong -> onboard. Node loi khong tu thu lai (tranh
    khoa tai khoan do dang nhap sai lien tuc) - bam Onboard tay sau khi sua."""
    log('\n[WATCH] Tu dong do vEdge moi tren Switch32 moi {}s (bam Dung de thoat)\n'.format(interval), 'hdr')
    seen = {}

    def note(node, state, msg, tag='info'):
        if seen.get(node) != state:
            log(msg, tag)
        seen[node] = state

    while not stop.is_set():
        try:
            lab, cands = discover(ssh, opts.get('lab', ''))
            for c in cands:
                if stop.is_set(): break
                if c['known'] or c['status'] == 'done':
                    continue
                if c['protected']:
                    note(c['node'], 'protected', '  [!] node {} noi vao cong ha tang Switch32 {} - doi sang cong trong '
                         '(vd e1/3 tro di)\n'.format(c['node'], c['sw_port']), 'err')
                    continue
                if c['status'] != 'new':
                    note(c['node'], c['status'], '  node {} dang o trang thai "{}" -> khong tu thu lai, '
                         'bam Onboard tay sau khi sua\n'.format(c['node'], c['status']))
                    continue
                try:
                    con = Console(ssh, c['node'], c['name'])
                    try: ready = con.probe()
                    finally: con.close()
                except OnboardError:
                    ready = False
                if not ready:
                    note(c['node'], 'boot', '  node {} ({}) noi Switch32 {} - console chua san sang '
                         '(dang boot / chua start?)\n'.format(c['node'], c['name'], c['sw_port']))
                    continue
                log('  [+] Phat hien vEdge moi: node {} ({}) {} <-> Switch32 {}\n'.format(
                    c['node'], c['name'], c['wan_if'], c['sw_port']), 'ok')
                reg = load_registry()
                alive = set()
                if c['sw_port'] and opts.get('cfg_switch', True):
                    # ping truoc vai IP sap cap tu Switch32 -> bo IP dang co may dung
                    pool, skip = [], set()
                    for _ in range(5):
                        _, sip, lan = allocate(reg, skip)
                        pool.append(lan); skip |= {sip, lan}
                    log('  [1/6] Switch32 cong {}\n'.format(c['sw_port']), 'info')
                    alive = switch_port(ssh, log, c['sw_port'], 'vEdge node {}'.format(c['node']),
                                        opts.get('wr', True), pool)
                    if alive:
                        log('      IP dang co may tra loi, bo qua: {}\n'.format(', '.join(sorted(alive))), 'info')
                e = new_entry(c, reg, skip=alive)
                onboard(ssh, log, e, dict(opts, cfg_switch=False, switch_done=True), stop)
                seen[c['node']] = 'handled'
        except Exception as ex:
            log('  [!] Loi quet: {}\n'.format(ex), 'err')
        for _ in range(interval):
            if stop.is_set(): break
            time.sleep(1)
    log('[WATCH] Da dung\n', 'info')


def rename(ssh, log, e, opts):
    """Doi host-name / system-ip / site-id (buoc dau khi bien vEdge thanh chi
    nhanh moi). Cert gan voi chassis nen khong can ky lai."""
    log('\n[ONBOARD] Doi danh tinh node {}: {} / {} / site {}\n'.format(
        e['node'], e['hostname'], e['system_ip'], e['site_id']), 'hdr')
    con = Console(ssh, e['node'], 'vEdge node {}'.format(e['node']))
    try:
        con.login('admin', [opts.get('vedge_pw')])
        con.commit(['system', ' host-name ' + e['hostname'], ' system-ip ' + e['system_ip'],
                    ' site-id {}'.format(e['site_id']), ' exit'])
    finally:
        con.close()
    save_entry(e)
    log('  Commit complete. Viec tay con lai: doi day WAN/LAN tren EVE, vpn 0 WAN + BGP + vpn 1 LAN '
        '(mau configs/07-Site500/vEdge65), them site vao ALL_EDGES/BRANCHES tren vSmart.\n', 'ok')
