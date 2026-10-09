#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
campus_web.py  –  Ban WEB cua campus_ping_tool.py
================================================================
Chay web server nho (chi dung thu vien chuan) va mo giao dien tren trinh duyet.
TOAN BO logic do luong / dieu khien console / vManage API lay tu
campus_ping_tool.py (khong sua file do - ban desktop Tkinter van chay binh
thuong). File nay chi:
  * thay tk.StringVar / messagebox / Treeview bang tham so JSON tu trinh duyet
  * gom log + metric + trang thai de trinh duyet doc dinh ky (/api/poll)
  * phuc vu anh PNG / CSV trong log/ de xem ngay tren web

Cach chay:
  python campus_web.py                 # http://127.0.0.1:8080
  python campus_web.py --port 9000
  python campus_web.py --host 0.0.0.0  # cho may khac trong LAN truy cap
                                       # (KHONG co dang nhap - chi dung trong lab)
================================================================
"""
import argparse, ipaddress, json, mimetypes, os, re, threading, webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import campus_ping_tool as core
from campus_ping_tool import (
    SITES, HOST_IP, HOST_SITE, VPC_NODE_IDS, VEDGE_NODE_IDS, WAN_IFACE, SITE_VEDGES, CORE_SITE_ID,
    LOG_DIR, HAS_MPL, HAS_SSH, CampusPingGUI, FailoverTab, VlanTab, PolicyTab, vlan_network,
)
import sdwan_onboard as onb

WEB_DIR = os.path.join(core._SCRIPT_DIR, 'web')
LOG_MAX = 5000          # so dong log giu trong bo nho


class Var:
    """Thay tk.StringVar/IntVar/BooleanVar: cac ham worker goc chi goi .get()/.set()."""
    def __init__(self, value=None): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


def _detk(cls):
    """Lay cac ham cua 1 lop Tkinter (khong ke __init__/__dunder__) sang 1 lop
    thuong de goi lai worker goc ma khong can tao cua so Tk."""
    return type(cls.__name__ + 'Core', (),
                {k: v for k, v in vars(cls).items() if not k.startswith('__')})


class WebError(Exception):
    """Loi tham so -> tra ve HTTP 400 kem thong bao cho trinh duyet."""


# =========================================================
#  TRANG THAI CHUNG (thay cho CampusPingGUI)
# =========================================================
class WebGUI(_detk(CampusPingGUI)):
    def __init__(self):
        self._lock = threading.Lock()
        self._lines = []            # [(id, ts, msg, tag)]
        self._next_id = 1
        self._stop_event = threading.Event()
        self._ssh_client = None
        self.ssh_info = ''
        self.status = 'San sang'
        self.busy = False           # thanh tien trinh (giong progress bar ban desktop)
        self.job = None             # ten tac vu dang chay (chi 1 tac vu 1 luc)
        self.metric_vars = {k: Var('--') for k in ('avg_lat', 'loss', 'jitter', 'min_lat', 'max_lat')}
        # cac "o nhap" ma worker goc doc qua .get()
        for name in ('ssh_var', 'vpcs_var', 'src_var', 'dst_var', 'count_var',
                     'timeout_var', 'batch_count_var'):
            setattr(self, name, Var())
        self._boot_log()

    # ---- thay cac ham gan voi widget Tk ----
    def after(self, ms, fn=None, *args):
        """Worker goc goi self.after(0, cap_nhat_widget) -> tren web khong co widget."""

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

    # ---- chay tac vu nen ----
    def run_job(self, name, fn, *args):
        """Chay fn trong thread nen; tu choi neu dang co tac vu khac (moi tac vu
        deu dung console thiet bi -> chay chong len nhau se lan output)."""
        with self._lock:
            if self.job:
                raise WebError('Dang chay "{}", vui long doi hoac bam Dung.'.format(self.job))
            self.job = name

        def _run():
            try:
                fn(*args)
            except Exception as e:
                self._log('[!] Loi {}: {}\n'.format(name, e), 'err')
            finally:
                self.job = None
                if self.busy:
                    self._set_status('San sang')
        threading.Thread(target=_run, daemon=True).start()

    def ssh(self, required=True):
        if required and not self._ssh_client:
            raise WebError('Chua ket noi SSH toi host EVE-NG (o tren cung trang).')
        return self._ssh_client


GUI = WebGUI()


# =========================================================
#  TAB NANG CAO  (tai dung worker goc)
# =========================================================
class WebFailover(_detk(FailoverTab)):
    def __init__(self, gui):
        self.gui = gui
        for name in ('vedge_var', 'color_var', 'src_var', 'target_var', 'duration_var',
                     'vuser_var', 'vpass_var'):
            setattr(self, name, Var())


class WebVlan(_detk(VlanTab)):
    def __init__(self, gui):
        self.gui = gui
        self.registry = self._load_registry()

    def _commit(self, key, entry):
        """Ban goc cap nhat Treeview qua after(); web chi can luu file."""
        entry['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.registry[key] = entry
        self._save_registry()

    def rows(self):
        out = []
        for key in sorted(self.registry, key=int):
            e = self.registry[key]
            out.append({'vid': int(key), 'cfg': e['cfg'], 'status': e['status'],
                        'subnet': str(vlan_network(e['cfg'])), 'edits': len(e.get('history', [])),
                        'updated': e.get('updated', '')})
        return out


class WebPolicy(_detk(PolicyTab)):
    def __init__(self, gui):
        self.gui = gui


FAILOVER, VLAN, POLICY = WebFailover(GUI), WebVlan(GUI), WebPolicy(GUI)


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


def _site_hosts(site_name):
    return sorted(h for vd in SITES[site_name]['vlans'].values() for h in vd['hosts'])


def api_meta(_):
    branch_vpcs = sorted(h for h in VPC_NODE_IDS
                         if h in HOST_SITE and SITES[HOST_SITE[h]]['site_id'] != CORE_SITE_ID)
    return {
        'sites': [{'name': sn, 'site_id': sd['site_id'], 'color': sd['color'], 'hosts': _site_hosts(sn)}
                  for sn, sd in SITES.items()],
        'host_ip': HOST_IP,
        'host_site_id': {h: SITES[s]['site_id'] for h, s in HOST_SITE.items()},
        'vpcs': sorted(VPC_NODE_IDS),
        'branch_vpcs': branch_vpcs,
        'wan_iface': WAN_IFACE,
        'core_site_id': CORE_SITE_ID,
        'system_ips': {ip: n for d in SITE_VEDGES.values() for ip, n in d.items()},
        'deps': {'matplotlib': HAS_MPL, 'paramiko': HAS_SSH},
        'log_dir': LOG_DIR,
        'ssh_defaults': {'host': '10.215.28.26', 'user': 'root', 'port': 22},
    }


def api_poll(q):
    since = int(q.get('since', 0) or 0)
    return {'lines': GUI.lines_since(since), 'status': GUI.status, 'busy': GUI.busy, 'job': GUI.job,
            'ssh': GUI.ssh_info if GUI._ssh_client else '',
            'metrics': {k: v.get() for k, v in GUI.metric_vars.items()}}


def api_ssh_connect(d):
    if not HAS_SSH:
        raise WebError('Thieu thu vien: pip install paramiko')
    import paramiko
    host, user = d.get('host', '').strip(), d.get('user', '').strip()
    port = _int(d, 'port', 1, 65535, 22)
    if not host or not user:
        raise WebError('Nhap Host va User.')
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect(host, port=port, username=user, password=d.get('password', ''), timeout=10)
    except Exception as e:
        GUI._log('[SSH] Loi: {}\n'.format(e), 'err')
        raise WebError('Ket noi SSH that bai: {}'.format(e))
    if GUI._ssh_client:
        try: GUI._ssh_client.close()
        except Exception: pass
    GUI._ssh_client, GUI.ssh_info = c, '{}@{}:{}'.format(user, host, port)
    GUI._log('[SSH] Ket noi OK -> {}\n'.format(GUI.ssh_info), 'ok')
    GUI._set_status('SSH: {}'.format(host))
    return {'ssh': GUI.ssh_info}


def api_ssh_disconnect(_):
    if GUI.job:
        raise WebError('Dang chay "{}" - doi xong roi moi ngat SSH.'.format(GUI.job))
    if GUI._ssh_client:
        try: GUI._ssh_client.close()
        except Exception: pass
    GUI._ssh_client, GUI.ssh_info = None, ''
    GUI._log('[SSH] Da ngat ket noi\n', 'info')
    return {}


def _ping_opts(d):
    use_ssh = bool(d.get('ssh'))
    if use_ssh:
        GUI.ssh()
    GUI.ssh_var.set(use_ssh)
    GUI.vpcs_var.set(bool(d.get('vpcs')))
    GUI.src_var.set(d.get('src', ''))
    GUI.dst_var.set(d.get('dst', ''))
    GUI.count_var.set(_int(d, 'count', 1, 300, 10))
    GUI.timeout_var.set(_int(d, 'timeout', 1, 10, 2))
    if GUI.dst_var.get() not in HOST_IP:
        raise WebError('Chon host dich.')


def api_ping(d):
    _ping_opts(d)
    GUI._stop_event.clear()
    GUI.run_job('Ping Test', GUI._ping_thread)
    return {}


def api_ping_continuous(d):
    _ping_opts(d)
    GUI._stop_event.clear()
    GUI.run_job('Ping lien tuc', GUI._continuous_ping_thread)
    return {}


def api_stop(_):
    GUI._stop_event.set()
    GUI._set_status('Dang dung...' if GUI.job else 'San sang')
    return {}


def api_discover(_):
    ssh = GUI.ssh()
    GUI.run_job('Auto-Discover IPs', GUI._discover_thread, ssh)
    return {}


def api_cases(d):
    cases = sorted({int(c) for c in d.get('cases', []) if str(c).isdigit() and 1 <= int(c) <= 6})
    if not cases:
        raise WebError('Chon it nhat 1 Case.')
    use_ssh = bool(d.get('ssh'))
    if use_ssh:
        GUI.ssh()
    GUI.ssh_var.set(use_ssh)
    GUI.vpcs_var.set(bool(d.get('vpcs')))
    GUI.batch_count_var.set(_int(d, 'count', 1, 200, 10))
    GUI.run_job('Batch Cases', GUI._cases_thread, cases)
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


# ---- Failover ----
def _failover_opts(d):
    vname, color = d.get('vedge', ''), d.get('color', '')
    if color not in WAN_IFACE.get(vname, {}):
        raise WebError('{} khong co mau WAN "{}".'.format(vname, color))
    f = FAILOVER
    f.vedge_var.set(vname); f.color_var.set(color)
    f.vuser_var.set(d.get('vuser', '').strip() or 'admin'); f.vpass_var.set(d.get('vpass', ''))
    return vname, WAN_IFACE[vname][color]


def api_failover_run(d):
    if not d.get('confirm'):
        raise WebError('Tick xac nhan "shutdown/no-shutdown THAT" truoc khi chay.')
    ssh = GUI.ssh()
    _failover_opts(d)
    target = _ip(d.get('target', '').strip(), 'IP dich')
    sysips = api_meta(None)['system_ips']
    if target in sysips:
        raise WebError('{} la system-ip cua {} - khong ping duoc. Hay ping 1 host/gateway o site khac '
                       '(vd 10.1.10.1, 10.3.80.100).'.format(target, sysips[target]))
    if d.get('src') not in VPC_NODE_IDS:
        raise WebError('Chon VPC nguon.')
    FAILOVER.src_var.set(d['src']); FAILOVER.target_var.set(target)
    FAILOVER.duration_var.set(_int(d, 'duration', 20, 300, 60))
    GUI.run_job('Failover Test', FAILOVER._thread, ssh)
    return {}


def api_failover_restore(d):
    ssh = GUI.ssh()
    vname, iface = _failover_opts(d)
    # khong qua run_job: khoi phuc phai chay duoc ca khi test dang treo
    threading.Thread(target=FAILOVER._restore_thread, args=(ssh, vname, iface), daemon=True).start()
    return {}


# ---- VLAN ----
def _vlan_form(d):
    """Giong VlanTab._read_form nhung doc tu JSON."""
    vid = _int(d, 'vid', 1, 4094, 0)
    g = lambda k: str(d.get(k, '')).strip()
    cfg = {'name': g('name') or 'TEST_VLAN', 'ip1': g('ip1'), 'ip2': g('ip2'), 'vip': g('vip'),
           'prefix': g('prefix'), 'vrid': g('vrid'), 'dual': bool(d.get('dual'))}
    try:
        if not 8 <= int(cfg['prefix']) <= 30:
            raise WebError('Prefix phai trong khoang 8-30')
        net = vlan_network(cfg)
        for k in ('ip2', 'vip') if cfg['dual'] else ('vip',):
            if cfg[k] and ipaddress.ip_address(cfg[k]) not in net:
                raise WebError('{} ({}) khong thuoc subnet {}'.format(k, cfg[k], net))
    except ValueError as e:
        raise WebError('Tham so khong hop le: {}'.format(e))
    if cfg['dual'] and not cfg['ip2']:
        raise WebError('Thieu IP SVI Core-SW2')
    if cfg['vip'] and not cfg['vrid']:
        raise WebError('Co VRRP VIP thi phai co VRRP Group ID')
    return vid, cfg


def _vlan_opts(d):
    remote = d.get('remote', '')
    if d.get('verify', True) and remote not in VPC_NODE_IDS:
        raise WebError('Chon VPC site khac de kiem chung.')
    return {'verify': bool(d.get('verify', True)), 'remote': remote, 'fw_pw': d.get('fw_pw', ''),
            'vm_user': d.get('vm_user', '').strip() or 'admin', 'vm_pw': d.get('vm_pw', ''),
            'wr': bool(d.get('wr'))}


def _vlan_job(name, target, *args):
    ssh = GUI.ssh()
    VLAN.registry = VLAN._load_registry()
    GUI.run_job(name, target, ssh, *args)


def api_vlan_list(_):
    VLAN.registry = VLAN._load_registry()
    return {'rows': VLAN.rows()}


def api_vlan_add(d):
    vid, cfg = _vlan_form(d)
    e = VLAN._load_registry().get(str(vid))
    if e and e['status'] == 'active':
        raise WebError('VLAN {} dang active. Dung "Sua VLAN" de thay doi.'.format(vid))
    _vlan_job('Them VLAN {}'.format(vid), VLAN._add_thread, _vlan_opts(d), vid, cfg)
    return {}


def api_vlan_edit(d):
    vid, cfg = _vlan_form(d)
    e = VLAN._load_registry().get(str(vid))
    if not e or e['status'] != 'active':
        raise WebError('VLAN {} khong co trong danh sach active (VLAN ID khong the sua; '
                       'muon doi ID hay Xoa roi Them moi).'.format(vid))
    if cfg == e['cfg']:
        raise WebError('Cau hinh khong thay doi.')
    _vlan_job('Sua VLAN {}'.format(vid), VLAN._edit_thread, _vlan_opts(d), vid, e['cfg'], cfg, True)
    return {}


def api_vlan_delete(d):
    vid = _int(d, 'vid', 1, 4094, 0)
    e = VLAN._load_registry().get(str(vid))
    if e and e['status'] == 'deleted':
        raise WebError('VLAN {} da bi xoa truoc do.'.format(vid))
    cfg = e['cfg'] if e else _vlan_form(d)[1]
    _vlan_job('Xoa VLAN {}'.format(vid), VLAN._delete_thread, _vlan_opts(d), vid, cfg)
    return {}


def api_vlan_restore(d):
    key = str(_int(d, 'vid', 1, 4094, 0))
    e = VLAN._load_registry().get(key)
    if not e:
        raise WebError('VLAN {} khong co trong danh sach.'.format(key))
    if e['status'] == 'deleted':
        _vlan_job('Khoi phuc VLAN {}'.format(key), VLAN._add_thread, _vlan_opts(d), int(key), dict(e['cfg']), True)
    elif e.get('history'):
        _vlan_job('Hoan tac VLAN {}'.format(key), VLAN._edit_thread, _vlan_opts(d), int(key),
                  e['cfg'], dict(e['history'][-1]), False)
    else:
        raise WebError('VLAN {} dang active va chua tung bi sua.'.format(key))
    return {}


def api_vlan_forget(d):
    if GUI.job and GUI.job.endswith('VLAN'):
        raise WebError('Dang co thao tac VLAN, vui long doi.')
    key = str(_int(d, 'vid', 1, 4094, 0))
    VLAN.registry = VLAN._load_registry()
    if VLAN.registry.pop(key, None) is None:
        raise WebError('VLAN {} khong co trong danh sach.'.format(key))
    VLAN._save_registry()
    return {}


# ---- Chinh sach tap trung ----
def api_policy_run(d):
    ssh = GUI.ssh()
    groups = {'W'} if d.get('only_whitelist') else set(d.get('groups', [])) & {'W', 'DP', 'AAR', 'CP'}
    if not groups:
        raise WebError('Tick it nhat 1 nhom kiem tra.')
    if not d.get('vm_pw'):
        raise WebError('Nhap vManage pass (counter policy doc qua vManage API).')
    opts = {'src': d.get('src', ''), 'farm': _ip(d.get('farm', '').strip(), 'IP Server Farm'),
            'dmz': _ip(d.get('dmz', '').strip(), 'IP DMZ'), 'icmp': _ip(d.get('icmp', '').strip(), 'IP dich ICMP'),
            'count': _int(d, 'count', 3, 100, 10), 'vm_user': d.get('vm_user', '').strip() or 'admin',
            'vm_pw': d['vm_pw'], 'groups': groups}
    if groups & {'DP', 'AAR'} and opts['src'] not in VPC_NODE_IDS:
        raise WebError('Chon VPC nguon.')
    GUI.run_job('Chinh sach tap trung', POLICY._thread, ssh, opts)
    return {}


# ---- Onboard vEdge moi (Site 900) ----
def _onb_opts(d, need_vm=True):
    opts = {'vedge_pw': d.get('vedge_pw', ''), 'vm_user': d.get('vm_user', '').strip() or 'admin',
            'vm_pw': d.get('vm_pw', ''), 'vs_pw': d.get('vs_pw', ''), 'vb_pw': d.get('vb_pw', ''),
            'cfg_switch': bool(d.get('cfg_switch', True)), 'wr': bool(d.get('wr', True)),
            'resign': bool(d.get('resign')), 'verify_s': _int(d, 'verify_s', 30, 900, 240),
            'lab': d.get('lab', '').strip()}
    if need_vm and not opts['vm_pw']:
        raise WebError('Nhap vManage pass (ky cert + whitelist).')
    return opts


def _onb_job(name, fn, *args):
    def run():
        GUI._set_status(name + '...', True)
        fn(*args)
    GUI._stop_event.clear()
    GUI.run_job(name, run)


def api_onboard_list(_):
    reg = onb.load_registry()
    return {'rows': [reg[k] for k in sorted(reg, key=int)]}


def api_onboard_scan(d):
    ssh = GUI.ssh()
    try:
        lab, cands = onb.discover(ssh, d.get('lab', '').strip())
    except onb.OnboardError as e:
        raise WebError(str(e))
    reg, skip = onb.load_registry(), set()
    for c in cands:
        if c['status'] != 'done' and not c['known']:
            e = onb.new_entry(c, reg, skip=skip)
            skip |= {e['system_ip'], e['vpn0_ip']}
            c['suggest'] = {k: e[k] for k in ('hostname', 'system_ip', 'vpn0_ip')}
    GUI._log('[ONBOARD] Quet {}: {} vEdge noi Switch32\n'.format(lab, len(cands)), 'info')
    return {'lab': lab, 'candidates': cands}


def _onb_entry(d):
    node = _int(d, 'node', 1, 1024, 0)
    if node in VEDGE_NODE_IDS.values():
        raise WebError('Node {} la vEdge chi nhanh dang chay - khong onboard lai.'.format(node))
    g = lambda k: str(d.get(k, '')).strip()
    e = {'node': node, 'hostname': g('hostname'), 'system_ip': _ip(g('system_ip'), 'System-IP'),
         'vpn0_ip': _ip(g('vpn0_ip'), 'IP vpn 0'), 'wan_if': g('wan_if') or 'ge0/0', 'sw_port': g('sw_port'),
         'site_id': onb.SITE_ID}
    if not re.fullmatch(r'[A-Za-z][\w-]{0,31}', e['hostname']):
        raise WebError('Hostname chi gom chu, so, "-", "_" (toi da 32 ky tu).')
    lan = ipaddress.ip_address(e['vpn0_ip'])
    if lan not in onb.LAN_NET or int(str(lan).split('.')[-1]) < 100 or int(str(lan).split('.')[-1]) > 199:
        raise WebError('IP vpn 0 phai trong 10.9.0.100-199 (tranh controller .10-.12, gateway .2).')
    if not re.fullmatch(r'ge\d+/\d+', e['wan_if']):
        raise WebError('Interface vEdge dang geX/Y (vd ge0/0).')
    if e['sw_port'] and not re.fullmatch(r'e\d+/\d+', e['sw_port']):
        raise WebError('Cong Switch32 dang eX/Y (vd e1/3) hoac de trong.')
    reg = onb.load_registry()
    for k, o in reg.items():
        if k != str(node) and (o.get('system_ip') == e['system_ip'] or o.get('vpn0_ip') == e['vpn0_ip']):
            raise WebError('Trung dia chi voi node {} ({}).'.format(k, o.get('hostname')))
    old = reg.get(str(node), {})
    for k in ('chassis', 'serial'):
        if old.get(k): e[k] = old[k]
    return e


def api_onboard_run(d):
    ssh = GUI.ssh()
    e, opts = _onb_entry(d), _onb_opts(d)
    _onb_job('Onboard vEdge node {}'.format(e['node']), onb.onboard, ssh, GUI._log, e, opts, GUI._stop_event)
    return {}


def api_onboard_watch(d):
    ssh = GUI.ssh()
    opts = _onb_opts(d)
    _onb_job('Tu dong onboard', onb.watch, ssh, GUI._log, opts, GUI._stop_event, _int(d, 'interval', 10, 600, 30))
    return {}


def api_onboard_whitelist(d):
    ssh = GUI.ssh()
    opts = _onb_opts(d)
    entries = [e for e in api_onboard_list(None)['rows'] if e.get('chassis') and e.get('serial')]
    if not entries:
        raise WebError('Chua co vEdge nao co chassis/serial trong danh sach.')

    def run():
        GUI._log('\n[ONBOARD] Day lai whitelist {} vEdge ky tay len 3 controller\n'.format(len(entries)), 'hdr')
        n = onb.whitelist(ssh, GUI._log, entries, opts)
        GUI._log('  Ket qua: {}/3 controller OK\n'.format(n), 'ok' if n == 3 else 'err')
    _onb_job('Day lai whitelist', run)
    return {}


def api_onboard_rename(d):
    ssh = GUI.ssh()
    node = str(_int(d, 'node', 1, 1024, 0))
    old = onb.load_registry().get(node)
    if not old or not old.get('serial'):
        raise WebError('Node {} chua onboard xong (chua co cert).'.format(node))
    e = dict(old, hostname=str(d.get('hostname', '')).strip(), system_ip=_ip(str(d.get('system_ip', '')).strip(), 'System-IP'),
             site_id=_int(d, 'site_id', 1, 4294967295, old.get('site_id', onb.SITE_ID)))
    if not re.fullmatch(r'[A-Za-z][\w-]{0,31}', e['hostname']):
        raise WebError('Hostname khong hop le.')
    if not d.get('vedge_pw'):
        raise WebError('Nhap mat khau vEdge.')
    _onb_job('Doi danh tinh node {}'.format(node), onb.rename, ssh, GUI._log, e, {'vedge_pw': d['vedge_pw']})
    return {}


def api_onboard_forget(d):
    if GUI.job and 'onboard' in GUI.job.lower():
        raise WebError('Dang chay "{}", vui long doi.'.format(GUI.job))
    if not onb.forget(_int(d, 'node', 1, 1024, 0)):
        raise WebError('Node khong co trong danh sach.')
    return {}


ROUTES = {
    ('GET', '/api/meta'): api_meta,
    ('GET', '/api/poll'): api_poll,
    ('GET', '/api/files'): api_files,
    ('GET', '/api/vlan'): api_vlan_list,
    ('POST', '/api/ssh/connect'): api_ssh_connect,
    ('POST', '/api/ssh/disconnect'): api_ssh_disconnect,
    ('POST', '/api/ping'): api_ping,
    ('POST', '/api/ping/continuous'): api_ping_continuous,
    ('POST', '/api/stop'): api_stop,
    ('POST', '/api/discover'): api_discover,
    ('POST', '/api/cases'): api_cases,
    ('POST', '/api/log/clear'): api_log_clear,
    ('POST', '/api/log/save'): api_log_save,
    ('POST', '/api/failover/run'): api_failover_run,
    ('POST', '/api/failover/restore'): api_failover_restore,
    ('POST', '/api/vlan/add'): api_vlan_add,
    ('POST', '/api/vlan/edit'): api_vlan_edit,
    ('POST', '/api/vlan/delete'): api_vlan_delete,
    ('POST', '/api/vlan/restore'): api_vlan_restore,
    ('POST', '/api/vlan/forget'): api_vlan_forget,
    ('POST', '/api/policy/run'): api_policy_run,
    ('GET', '/api/onboard'): api_onboard_list,
    ('POST', '/api/onboard/scan'): api_onboard_scan,
    ('POST', '/api/onboard/run'): api_onboard_run,
    ('POST', '/api/onboard/watch'): api_onboard_watch,
    ('POST', '/api/onboard/whitelist'): api_onboard_whitelist,
    ('POST', '/api/onboard/rename'): api_onboard_rename,
    ('POST', '/api/onboard/forget'): api_onboard_forget,
}


# =========================================================
#  HTTP SERVER
# =========================================================
class Handler(BaseHTTPRequestHandler):
    server_version = 'CampusWeb/1.0'

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
    ap = argparse.ArgumentParser(description='Campus Network SDN + SD-WAN - giao dien web')
    ap.add_argument('--host', default='127.0.0.1', help='dia chi lang nghe (mac dinh 127.0.0.1)')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--no-browser', action='store_true', help='khong tu mo trinh duyet')
    args = ap.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    url = 'http://{}:{}/'.format('127.0.0.1' if args.host in ('0.0.0.0', '') else args.host, args.port)
    print('Campus web tool: {}  (Ctrl+C de thoat)'.format(url))
    if args.host not in ('127.0.0.1', 'localhost'):
        print('[!] Dang mo cho may khac truy cap - web KHONG co dang nhap, chi dung trong mang lab.')
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if GUI._ssh_client:
            GUI._ssh_client.close()


if __name__ == '__main__':
    main()
