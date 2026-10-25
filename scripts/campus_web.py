#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
campus_web.py  –  Giao dien WEB giam sat / do luong Campus SDN + SD-WAN
================================================================
Web server nho (chi thu vien chuan) + giao dien trinh duyet. KHONG dung console
hay SSH vao host EVE-NG (10.215.28.26): moi so lieu lay tu chinh thiet bi theo
IP cua no, dung kieu NOC van hanh that:
  * vManage REST API (https://<IP vManage>, mac dinh 10.9.0.10): trang thai
    thiet bi, BFD, control, bo dem interface
  * vEdge tu ping / traceroute qua vManage (Monitor > Troubleshooting)
  * ping tu chinh may chay web toi IP thiet bi
Logic do nam o sdwan_monitor.py. Cac tab chi DO / KIEM CHUNG, khong sua cau
hinh thiet bi.
Ngoai le: tab "Ky cert vEdge" (sdwan_certsign.py) SSH thang toi IP vEdge / vManage /
vSmart / vBond tren CONTROLLER-LAN 10.9.0.0/24 de cai cert + whitelist - van khong
qua host EVE.

Cach chay (tren may Win trong lab 10.9.0.20, cung LAN controller site 900):
  python campus_web.py                       # http://127.0.0.1:8080
  python campus_web.py --vmanage 10.9.0.10   # IP vManage (dien san tren giao dien)
  python campus_web.py --host 0.0.0.0        # cho may khac trong LAN truy cap
                                             # (KHONG co dang nhap - chi dung trong lab)
================================================================
"""
import argparse, ipaddress, json, mimetypes, os, re, threading, webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import campus_ping_tool as core
from campus_ping_tool import SITES, HOST_IP, HOST_SITE, WAN_IFACE, SITE_VEDGES, CORE_SITE_ID, LOG_DIR, HAS_MPL
import sdwan_monitor as mon
import sdwan_reliability as rel
from campus_throughput import ThroughputTest

WEB_DIR = os.path.join(core._REPO_DIR, 'web')
LOG_MAX = 5000          # so dong log giu trong bo nho


class WebError(Exception):
    """Loi tham so -> tra ve HTTP 400 kem thong bao cho trinh duyet."""


class Var:
    def __init__(self, value=None): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


# =========================================================
#  TRANG THAI CHUNG: log + metric + tac vu nen + phien vManage
# =========================================================
class WebGUI:
    def __init__(self):
        self._lock = threading.Lock()
        self._lines = []            # [(id, ts, msg, tag)]
        self._next_id = 1
        self._stop_event = threading.Event()
        self.status = 'San sang'
        self.busy = False
        self.job = None             # ten tac vu dang chay (chi 1 tac vu 1 luc)
        self.metric_vars = {k: Var('--') for k in ('avg_lat', 'loss', 'jitter', 'min_lat', 'max_lat')}
        self.vm = None              # mon.VManage da dang nhap
        self.vm_default = mon.VMANAGE_DEFAULT

    def _log(self, msg, tag=None):
        ts = datetime.now().strftime('%H:%M:%S')
        with self._lock:
            self._lines.append((self._next_id, ts, msg, tag))
            self._next_id += 1
            del self._lines[:-LOG_MAX]

    def _set_status(self, msg, busy=False):
        self.status, self.busy = msg, busy

    def _update_metric(self, key, val):
        self.metric_vars[key].set(val)

    def _clear_log(self):
        with self._lock:
            self._lines.clear()

    def _save_log(self):
        path = os.path.join(LOG_DIR, 'log_{}.txt'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
        with self._lock:
            text = ''.join(('[{}] '.format(ts) if tag and tag not in ('sep', 'ts') else '') + msg
                           for _, ts, msg, tag in self._lines)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        self._log('[OK] Log luu: {}\n'.format(path), 'ok')
        return os.path.basename(path)

    def lines_since(self, since):
        with self._lock:
            return [{'id': i, 'ts': ts, 'msg': m, 'tag': t} for i, ts, m, t in self._lines if i > since]

    def run_job(self, name, fn, *args):
        """Chay fn trong thread nen; tu choi neu dang co tac vu khac (cac lenh nping cua
        vManage chay tuan tu, chay chong se cham va lan log)."""
        with self._lock:
            if self.job:
                raise WebError('Dang chay "{}", vui long doi hoac bam Dung.'.format(self.job))
            self.job = name
        self._stop_event.clear()

        def _run():
            try:
                fn(*args)
            except Exception as e:
                self._log('[!] Loi {}: {}\n'.format(name, e), 'err')
            finally:
                self.job = None
                self._set_status('San sang')
        threading.Thread(target=_run, daemon=True).start()

    def vmanage(self):
        if not self.vm:
            raise WebError('Chua ket noi vManage (o ben trai).')
        return self.vm


GUI = WebGUI()


class WebThroughput(ThroughputTest):
    """Thong luong: bo dem interface vEdge doc qua vManage API thay vi console."""
    def _make_reader(self, vm, vname, opts):
        return mon.VManageCounterReader(vm, mon.NAME_TO_SYSIP[vname])


THROUGHPUT = WebThroughput(GUI)


# =========================================================
#  API HANDLERS  (moi ham nhan dict JSON, tra dict JSON)
# =========================================================
def _int(d, key, lo, hi, default):
    try:
        v = int(d.get(key, default))
    except (TypeError, ValueError):
        raise WebError('{} phai la so nguyen'.format(key))
    if not lo <= v <= hi:
        raise WebError('{} phai trong khoang {}-{}'.format(key, lo, hi))
    return v


def _ip(value, label):
    try:
        ipaddress.ip_address(value)
    except ValueError:
        raise WebError('{}: "{}" khong phai dia chi IP.'.format(label, value))
    return value


def _vedge(d, key, label='vEdge'):
    name = d.get(key, '')
    if name not in mon.NAME_TO_SYSIP:
        raise WebError('Chon {}.'.format(label))
    return mon.NAME_TO_SYSIP[name]


def _site_hosts(site_name):
    return sorted(h for vd in SITES[site_name]['vlans'].values() for h in vd['hosts'])


def api_meta(_):
    return {
        'sites': [{'name': sn, 'site_id': sd['site_id'], 'color': sd['color'], 'hosts': _site_hosts(sn),
                   'vedges': [mon.VEDGE_NAMES[ip] for ip in sorted(SITE_VEDGES.get(sd['site_id'], {}))]}
                  for sn, sd in SITES.items()],
        'host_ip': HOST_IP,
        'host_site_id': {h: SITES[s]['site_id'] for h, s in HOST_SITE.items()},
        'vedges': sorted(mon.NAME_TO_SYSIP),
        'vedge_site': {n: mon.SITE_OF_SYSIP[ip] for n, ip in mon.NAME_TO_SYSIP.items()},
        'wan_iface': WAN_IFACE,
        'core_site_id': CORE_SITE_ID,
        'cases': mon.CASE_NAMES,
        'deps': {'matplotlib': HAS_MPL},
        'vm_default': GUI.vm_default,
    }


def api_poll(q):
    since = int(q.get('since', 0) or 0)
    vm = GUI.vm
    return {'lines': GUI.lines_since(since), 'status': GUI.status, 'busy': GUI.busy, 'job': GUI.job,
            'vmanage': '{}@{}'.format(vm.user, vm.host) if vm else '',
            'metrics': {k: v.get() for k, v in GUI.metric_vars.items()}}


def api_vm_connect(d):
    host, user = d.get('host', '').strip(), d.get('user', '').strip() or 'admin'
    if not host or not d.get('password'):
        raise WebError('Nhap IP vManage va mat khau.')
    vm = mon.VManage(host, user, d['password'])
    try:
        vm.login()
        n = len(vm.devices())
    except mon.VManageError as e:
        GUI._log('[vManage] {}\n'.format(e), 'err')
        raise WebError(str(e))
    GUI.vm = vm
    mon._SRC_CACHE.clear()
    GUI._log('[vManage] Dang nhap OK {}@{} - {} thiet bi trong fabric\n'.format(user, host, n), 'ok')
    return {'vmanage': '{}@{}'.format(user, host), 'devices': n}


def api_vm_disconnect(_):
    if GUI.job:
        raise WebError('Dang chay "{}" - doi xong roi moi ngat.'.format(GUI.job))
    GUI.vm = None
    GUI._log('[vManage] Da ngat phien\n', 'info')
    return {}


def api_overview(q):
    try:
        return {'devices': mon.overview(GUI.vmanage(), quick=q.get('quick') == '1'), 'time': datetime.now().strftime('%H:%M:%S')}
    except mon.VManageError as e:
        raise WebError(str(e))


def api_vedge_detail(q):
    try:
        return mon.vedge_detail(GUI.vmanage(), _vedge(q, 'name'))
    except mon.VManageError as e:
        raise WebError(str(e))


def _ping_opts(d):
    dst = d.get('dst', '')
    if dst not in HOST_IP:
        raise WebError('Chon host dich.')
    src = d.get('src', '')
    if src != 'local':
        src = _vedge(d, 'src', 'vEdge nguon')
        GUI.vmanage()
    return src, dst, HOST_IP[dst]


def api_ping(d):
    src, dst, ip = _ping_opts(d)
    GUI.run_job('Ping Test', mon.ping_job, GUI, GUI.vm, src, dst, ip,
                _int(d, 'count', 1, 100, 5), _int(d, 'timeout', 1, 10, 2))
    return {}


def api_ping_continuous(d):
    src, dst, ip = _ping_opts(d)
    GUI.run_job('Ping lien tuc', mon.ping_loop_job, GUI, GUI.vm, src, dst, ip, _int(d, 'timeout', 1, 10, 2))
    return {}


def api_traceroute(d):
    src, dst, ip = _ping_opts(d)
    if src == 'local':
        raise WebError('Traceroute chay tu vEdge - chon vEdge nguon.')

    def run():
        GUI._set_status('Traceroute...', True)
        GUI._log('\n[TRACE] {} -> {} ({})\n'.format(mon.VEDGE_NAMES[src], dst, ip), 'hdr')
        for line in mon.vedge_traceroute(GUI.vm, src, ip):
            GUI._log('  {}\n'.format(line), 'data')
    GUI.run_job('Traceroute', run)
    return {}


def api_stop(_):
    GUI._stop_event.set()
    GUI._set_status('Dang dung...' if GUI.job else 'San sang')
    return {}


def api_cases(d):
    n = len(mon.CASE_NAMES)
    cases = sorted({int(c) for c in d.get('cases', []) if str(c).isdigit() and 1 <= int(c) <= n})
    if not cases:
        raise WebError('Chon it nhat 1 Case.')
    GUI.run_job('So sanh site', mon.cases_job, GUI, GUI.vmanage(), cases, _int(d, 'count', 1, 50, 5),
                _int(d, 'tp_window', 20, 900, 60), _int(d, 'tp_interval', 5, 60, 10))
    return {}


def api_log_clear(_):
    GUI._clear_log()
    return {}


def api_log_save(_):
    return {'file': GUI._save_log()}


def api_files(_):
    files = []
    for name in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, name)
        if os.path.isfile(path) and name.lower().endswith(('.png', '.csv', '.txt')):
            st = os.stat(path)
            files.append({'name': name, 'size': st.st_size, 'mtime': st.st_mtime})
    files.sort(key=lambda f: f['mtime'], reverse=True)
    return {'files': files}


def api_failover_run(d):
    watch, probe = _vedge(d, 'watch', 'vEdge bi cat'), _vedge(d, 'probe', 'vEdge do')
    if watch == probe:
        raise WebError('vEdge do phai khac vEdge bi cat (vEdge mat link thi khong tu ping qua overlay duoc).')
    target = _ip(d.get('target', '').strip(), 'IP dich')
    if target.startswith('10.200.'):
        raise WebError('{} la system-ip - hay ping 1 host/gateway trong LAN cua site.'.format(target))
    opts = {'watch': watch, 'probe': probe, 'target': target,
            'wait_cut': _int(d, 'wait_cut', 10, 600, 120), 'duration': _int(d, 'duration', 10, 300, 60)}
    GUI.run_job('Failover Test', mon.failover_job, GUI, GUI.vmanage(), opts)
    return {}


def api_rel_failover(d):
    since = d.get('since', '').strip()
    try:
        since = datetime.strptime(since, '%Y-%m-%d') if since else None
    except ValueError:
        raise WebError('Ngay bat dau dang YYYY-MM-DD.')
    GUI.run_job('Tong hop failover', rel.failover_summary_job, GUI, {'since': since})
    return {}


def api_rel_controller(d):
    opts = {'probe': _vedge(d, 'probe', 'vEdge do'), 'target': _ip(d.get('target', '').strip(), 'IP dich'),
            'wait_down': _int(d, 'wait_down', 30, 1800, 300), 'duration': _int(d, 'duration', 60, 3600, 900),
            'interval': _int(d, 'interval', 3, 30, 5)}
    GUI.run_job('Controller Recovery', rel.controller_recovery_job, GUI, GUI.vmanage(), opts)
    return {}


def api_rel_availability(d):
    opts = {'target': _ip(d.get('target', '').strip(), 'IP dich vu'),
            'duration_s': _int(d, 'minutes', 5, 24 * 60, 60) * 60, 'interval': _int(d, 'interval', 10, 600, 30)}
    GUI.run_job('Availability', rel.availability_job, GUI, GUI.vmanage(), opts)
    return {}


def api_throughput_run(d):
    vname = d.get('vedge', '')
    if vname not in WAN_IFACE or vname not in mon.NAME_TO_SYSIP:
        raise WebError('Chon vEdge.')
    opts = {'vedge': vname, 'interval': _int(d, 'interval', 5, 60, 5), 'duration': _int(d, 'duration', 10, 900, 60),
            'scope': 'all' if d.get('scope') == 'all' else 'wan', 'gen_src': ''}
    GUI.run_job('Do thong luong', THROUGHPUT._thread, GUI.vmanage(), opts)
    return {}


def api_throughput_state(q):
    return THROUGHPUT.snapshot(_int(q, 'since', 0, 10 ** 9, 0))


# ---- Ky cert vEdge: SSH thang IP thiet bi tren CONTROLLER-LAN (sdwan_certsign.py) ----
def _certsign():
    try:
        import sdwan_certsign
    except ImportError as e:
        raise WebError('Thieu thu vien cho tab Ky cert: {} (pip install paramiko)'.format(e))
    return sdwan_certsign


def _cs_opts(d, need_vedge):
    """Mat khau chi giu trong bo nho cua tac vu, khong log. vManage de trong -> dung
    phien vManage dang ket noi; vSmart/vBond de trong -> = mat khau vManage."""
    cs = _certsign()
    user = d.get('user', '').strip() or 'admin'
    vm_pw = d.get('vm_pw') or (GUI.vm.password if GUI.vm and GUI.vm.host == cs.ob.VMANAGE_IP else '')
    if not vm_pw:
        raise WebError('Nhap mat khau vManage (hoac ket noi vManage {} o ben trai).'.format(cs.ob.VMANAGE_IP))
    opts = {'vm_user': user, 'vedge_user': user, 'vm_pw': vm_pw, 'vs_pw': d.get('vs_pw') or vm_pw,
            'vb_pw': d.get('vb_pw') or vm_pw, 'resign': bool(d.get('resign')),
            'verify_s': _int(d, 'verify', 60, 900, 240),
            'vm': GUI.vm if GUI.vm and GUI.vm.host == cs.ob.VMANAGE_IP else None}
    if need_vedge:
        if not d.get('vedge_pw'):
            raise WebError('Nhap mat khau vEdge (da dat luc go lenh bat SSH tren console).')
        opts['vedge_pw'] = d['vedge_pw']
        opts['hostname'] = _hostname(d)
    return cs, opts


def _hostname(d):
    hostname = d.get('hostname', '').strip()
    if hostname and not re.match(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$', hostname):
        raise WebError('Ten vEdge chi gom chu, so, - va _ (toi da 32 ky tu).')
    return hostname or None


def api_cs_day0(q):
    """Lenh toi thieu go tren console vEdge moi (IP vpn 0 + SSH); phan con lai tool day qua SSH."""
    cs = _certsign()
    wan_if = q.get('wan_if', '').strip() or 'ge0/0'
    if not re.match(r'^ge\d+/\d+$', wan_if):
        raise WebError('Interface WAN dang ge0/0.')
    e, lines = cs.ssh_bootstrap(_hostname(q), wan_if)
    return {'entry': e, 'config': '\n'.join(lines), 'vlan': cs.ob.CONTROLLER_VLAN}


def api_cs_registry(_):
    reg = _certsign().ob.load_registry()
    keys = ('hostname', 'system_ip', 'site_id', 'vpn0_ip', 'chassis', 'status', 'updated', 'via')
    return {'entries': sorted(({k: v.get(k, '') for k in keys} for v in reg.values()),
                              key=lambda v: str(v['system_ip']))}


def api_cs_sign(d):
    ips = [s.strip() for s in re.split(r'[\s,;]+', d.get('ips', '')) if s.strip()]
    if not ips:
        raise WebError('Nhap IP vpn 0 cua vEdge (10.9.0.x).')
    cs, opts = _cs_opts(d, True)
    for ip in ips:
        if ipaddress.ip_address(_ip(ip, 'IP vEdge')) not in cs.ob.LAN_NET:
            raise WebError('{} khong thuoc CONTROLLER-LAN {}.'.format(ip, cs.ob.LAN_NET))
    if len(set(ips)) != len(ips):
        raise WebError('IP vEdge bi trung.')

    def run():
        ok = 0
        for i, ip in enumerate(ips, 1):
            if GUI._stop_event.is_set():
                GUI._log('[CERTSIGN] Da dung truoc {}\n'.format(ip), 'info')
                break
            GUI._set_status('Ky cert {} ({}/{})'.format(ip, i, len(ips)), True)
            ok += bool(cs.certsign(ip, opts, GUI._log, GUI._stop_event))
        GUI._log('[CERTSIGN] Xong: {}/{} vEdge vao fabric\n'.format(ok, len(ips)), 'ok' if ok == len(ips) else 'err')
    GUI.run_job('Ky cert vEdge', run)
    return {}


def _vm_on_ca(cs):
    vm = GUI.vmanage()
    if vm.host != cs.ob.VMANAGE_IP:
        raise WebError('Can ket noi vManage {} (CA) - dang ket noi {}.'.format(cs.ob.VMANAGE_IP, vm.host))
    return vm


def api_as_list(_):
    """WAN Edge List cho che do vManage tu ky. OTP khong gui ve trinh duyet."""
    cs = _certsign()
    try:
        rows = cs.wan_edge_list(_vm_on_ca(cs))
    except mon.VManageError as e:
        raise WebError(str(e))
    for r in rows:
        r['token'] = bool(r['token'] and r['state'] == 'tokengenerated')
        r['decom'] = not r['free'] and (not r['system_ip'] or r['system_ip'].startswith(cs.STAGING_NET))
    return {'entries': rows}


def api_as_decommission(d):
    cs = _certsign()
    vm, uuid = _vm_on_ca(cs), d.get('uuid', '')
    e = next((x for x in cs.wan_edge_list(vm) if x['uuid'] == uuid), None)
    if e is None:
        raise WebError('Khong co muc {} trong WAN Edge List.'.format(uuid))
    if d.get('confirm', '').strip() != (e['hostname'] or uuid[:8]):
        raise WebError('Go dung "{}" de xac nhan.'.format(e['hostname'] or uuid[:8]))
    try:
        cs.decommission(vm, uuid, GUI._log)
    except (cs.OnboardError, mon.VManageError) as ex:
        GUI._log('[AUTOSIGN] Decommission loi: {}\n'.format(ex), 'err')
        raise WebError(str(ex))
    return {}


def api_as_activate(d):
    cs = _certsign()
    vm = _vm_on_ca(cs)
    ip = _ip(d.get('ip', '').strip(), 'IP vEdge')
    if ipaddress.ip_address(ip) not in cs.ob.LAN_NET:
        raise WebError('{} khong thuoc CONTROLLER-LAN {}.'.format(ip, cs.ob.LAN_NET))
    uuid = d.get('uuid', '')
    if not any(x['uuid'] == uuid and x['free'] for x in cs.wan_edge_list(vm)):
        raise WebError('Chon 1 muc WAN Edge List dang trong (tokengenerated).')
    if not d.get('vedge_pw'):
        raise WebError('Nhap mat khau vEdge (da dat luc go lenh bat SSH tren console).')
    opts = {'vm': vm, 'hostname': _hostname(d), 'vm_user': vm.user, 'vm_pw': vm.password, 'vedge_user': d.get('user', '').strip() or 'admin',
            'vedge_pw': d['vedge_pw'], 'verify_s': _int(d, 'verify', 60, 900, 300)}

    def run():
        GUI._set_status('Kich hoat {} (vManage tu ky)'.format(ip), True)
        cs.activate(ip, uuid, opts, GUI._log, GUI._stop_event)
    GUI.run_job('vManage tu ky', run)
    return {}


def api_cs_rewhitelist(d):
    cs, opts = _cs_opts(d, False)

    def run():
        GUI._set_status('Day lai whitelist (SSH)...', True)
        ok = cs.rewhitelist(opts, GUI._log)
        GUI._log('[REWHITELIST] {}\n'.format('Du 3/3 controller' if ok else 'Chua du 3 controller - xem log'),
                 'ok' if ok else 'err')
    GUI.run_job('Day lai whitelist', run)
    return {}


ROUTES = {
    ('GET', '/api/meta'): api_meta,
    ('GET', '/api/poll'): api_poll,
    ('GET', '/api/files'): api_files,
    ('GET', '/api/overview'): api_overview,
    ('GET', '/api/vedge'): api_vedge_detail,
    ('POST', '/api/vmanage/connect'): api_vm_connect,
    ('POST', '/api/vmanage/disconnect'): api_vm_disconnect,
    ('POST', '/api/ping'): api_ping,
    ('POST', '/api/ping/continuous'): api_ping_continuous,
    ('POST', '/api/traceroute'): api_traceroute,
    ('POST', '/api/stop'): api_stop,
    ('POST', '/api/cases'): api_cases,
    ('POST', '/api/log/clear'): api_log_clear,
    ('POST', '/api/log/save'): api_log_save,
    ('POST', '/api/failover/run'): api_failover_run,
    ('POST', '/api/reliability/failover'): api_rel_failover,
    ('POST', '/api/reliability/controller'): api_rel_controller,
    ('POST', '/api/reliability/availability'): api_rel_availability,
    ('GET', '/api/throughput'): api_throughput_state,
    ('POST', '/api/throughput/run'): api_throughput_run,
    ('GET', '/api/certsign/day0'): api_cs_day0,
    ('GET', '/api/certsign/registry'): api_cs_registry,
    ('POST', '/api/certsign/sign'): api_cs_sign,
    ('POST', '/api/certsign/rewhitelist'): api_cs_rewhitelist,
    ('GET', '/api/autosign/list'): api_as_list,
    ('POST', '/api/autosign/decommission'): api_as_decommission,
    ('POST', '/api/autosign/activate'): api_as_activate,
}


# =========================================================
#  HTTP SERVER
# =========================================================
class Handler(BaseHTTPRequestHandler):
    server_version = 'CampusWeb/2.0'

    def log_message(self, fmt, *args):      # bo log truy cap (poll moi giay rat on)
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, base, name, download=False):
        path = os.path.realpath(os.path.join(base, name))
        if not path.startswith(os.path.realpath(base) + os.sep) or not os.path.isfile(path):
            return self._send(404, {'error': 'Khong tim thay file'})
        ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype.endswith('javascript'):
            ctype += '; charset=utf-8'
        with open(path, 'rb') as f:
            data = f.read()
        extra = {'Content-Disposition': 'attachment; filename="{}"'.format(os.path.basename(path))} if download else None
        self._send(200, data, ctype, extra)

    def _dispatch(self, method):
        url = urlparse(self.path)
        if method == 'GET' and url.path in ('/', '/index.html'):
            return self._file(WEB_DIR, 'index.html')
        if method == 'GET' and url.path.startswith('/files/'):
            q = parse_qs(url.query)
            return self._file(LOG_DIR, unquote(url.path[len('/files/'):]), download='dl' in q)
        fn = ROUTES.get((method, url.path))
        if not fn:
            return self._send(404, {'error': 'Khong co API {}'.format(url.path)})
        try:
            if method == 'GET':
                data = {k: v[-1] for k, v in parse_qs(url.query).items()}
            else:
                n = int(self.headers.get('Content-Length') or 0)
                data = json.loads(self.rfile.read(n) or b'{}')
            self._send(200, fn(data) or {})
        except WebError as e:
            self._send(400, {'error': str(e)})
        except Exception as e:
            GUI._log('[!] Loi API {}: {}\n'.format(url.path, e), 'err')
            self._send(500, {'error': str(e)})

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        # chan trang web la goi API (CSRF) khi server mo ra LAN
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self._send(403, {'error': 'Origin khong hop le'})
        self._dispatch('POST')


def main():
    ap = argparse.ArgumentParser(description='Campus Network SDN + SD-WAN - giao dien web (vManage API)')
    ap.add_argument('--host', default='127.0.0.1', help='dia chi lang nghe (mac dinh 127.0.0.1)')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--no-browser', action='store_true', help='khong tu mo trinh duyet')
    ap.add_argument('--vmanage', default=mon.VMANAGE_DEFAULT,
                    help='IP vManage dien san tren giao dien (mac dinh {})'.format(mon.VMANAGE_DEFAULT))
    args = ap.parse_args()
    GUI.vm_default = args.vmanage

    # Windows: SO_REUSEADDR cho 2 tien trinh cung nghe 1 cong -> trinh duyet gap server cu
    ThreadingHTTPServer.allow_reuse_address = os.name != 'nt'
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        raise SystemExit('[!] Cong {} dang bi chiem ({}) - tat web cu (taskkill /F /IM python.exe) roi chay lai'.format(args.port, e))
    srv.daemon_threads = True
    url = 'http://{}:{}/'.format('127.0.0.1' if args.host in ('0.0.0.0', '') else args.host, args.port)
    print('Campus web tool: {}  (Ctrl+C de thoat)'.format(url))
    print('Du lieu lay tu vManage API {} + ping tu may nay - khong dung console/SSH host EVE.'.format(args.vmanage))
    if args.host not in ('127.0.0.1', 'localhost'):
        print('[!] Dang mo cho may khac truy cap - web KHONG co dang nhap, chi dung trong mang lab.')
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
