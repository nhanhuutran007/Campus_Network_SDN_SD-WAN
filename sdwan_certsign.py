#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdwan_certsign.py  –  Tu dong ky cert + whitelist vEdge moi QUA IP THIET BI
==================================================================================
Khong dung console/SSH cua host EVE (10.215.28.26): tool SSH thang toi vEdge,
vManage (CA), vSmart, vBond tren CONTROLLER-LAN 10.9.0.0/24 - giong mot trien khai
that, noi khong co hypervisor de console vao. Chay tren may lab Win 10.9.0.20.

Mo hinh "staging" site 900 (CA enterprise SDWAN-Lab-RootCA giu nguyen):
  0. Ky thuat vien cam vEdge vao Switch32 (VLAN 10), dan Day-0 tren console
     cua thiet bi (lenh --day0 in san cau hinh, IP cap tu dong khong trung)
  1. Tool SSH vEdge (vpn 0, allow-service sshd) -> doc system-ip/host-name/org
  2. CSR -> vEdge scp len vManage -> SSH vManage, vshell, ky openssl bang CA cu
     -> vEdge scp cert + root CA ve -> cai root chain roi cai cert
  3. request vedge add tren vManage + vSmart + vBond (SSH tung controller)
  4. Cho control vmanage + vsmart Up, xac nhan bang vManage API (reachable)
Sau do dua vEdge ra chi nhanh theo runbook "vEdge du phong" (sdwan-viptela.md):
cert gan voi chassis nen doi system-ip/site khong can ky lai.

  python sdwan_certsign.py --day0                    # in Day-0 cho vEdge ke tiep
  python sdwan_certsign.py --day0 --hostname vEdge-S600
  python sdwan_certsign.py 10.9.0.102                # ky cert + whitelist vEdge do
  python sdwan_certsign.py 10.9.0.102 --resign       # ky lai du cert dang Valid
  python sdwan_certsign.py --rewhitelist             # day lai whitelist sau khi controller reboot

Mat khau: bien moi truong SDWAN_VEDGE_PW, SDWAN_VM_PW, SDWAN_VS_PW, SDWAN_VB_PW
(vBond mac dinh = vManage); thieu thi hoi bang getpass. Khong nhan mat khau tren
command line, khong ghi ra file/log. Ket qua chung registry voi sdwan_onboard.py
(log/onboard_registry.json).
================================================================
"""
import argparse, getpass, os, re, sys, time

import paramiko

import sdwan_onboard as ob
from sdwan_onboard import OnboardError, Console

CONTROLLER_IP = {'vManage': ob.VMANAGE_IP, 'vSmart': '10.9.0.11', 'vBond': ob.VBOND_IP}
SSH_TIMEOUT = 15


class SshConsole(Console):
    """Console tren shell SSH toi IP thiet bi. Viptela co the chi cho
    keyboard-interactive -> thu password truoc, roi interactive."""

    def __init__(self, ip, user, pw, name):
        self.ip = ip
        try:
            t = paramiko.Transport((ip, 22))
            t.banner_timeout = t.auth_timeout = SSH_TIMEOUT
            t.start_client(timeout=SSH_TIMEOUT)
        except Exception as e:
            raise OnboardError('{}: khong SSH duoc {}:22 ({}) - Day-0 da co allow-service sshd/all chua?'
                               .format(name, ip, e))
        try:
            try:
                t.auth_password(user, pw)
            except paramiko.BadAuthenticationType:
                t.auth_interactive(user, lambda title, instr, prompts: [pw] * len(prompts))
        except paramiko.AuthenticationException:
            t.close()
            # dung ngay, khong thu lai: sai nhieu lan khoa tai khoan ~15 phut
            raise OnboardError('{}: SSH {} sai user/mat khau'.format(name, ip))
        self.transport = t
        chan = t.open_session()
        chan.get_pty(width=500, height=200)
        chan.invoke_shell()
        super().__init__(None, ip, name, chan=chan)

    def close(self):
        super().close()
        try: self.transport.close()
        except Exception: pass


def env_pw(var, label):
    return os.environ.get(var) or getpass.getpass('Mat khau {}: '.format(label))


def log(msg, tag=None):
    sys.stdout.write(msg); sys.stdout.flush()


def connect_controller(opts):
    keys = {'vManage': 'vm_pw', 'vSmart': 'vs_pw', 'vBond': 'vb_pw'}
    return lambda name, nid: SshConsole(CONTROLLER_IP[name], opts['vm_user'],
                                        opts.get(keys[name]) or opts['vm_pw'], name)


def running_system(con):
    out = con.cli('show running-config system', 30)
    get = lambda k: (re.search(r'^\s*' + k + r'\s+(\S+)', out, re.M) or [None, ''])[1]
    return {'hostname': get('host-name'), 'system_ip': get('system-ip'), 'site_id': get('site-id'),
            'org': get('organization-name').strip('"'), 'vbond': get('vbond')}


def vmanage_reachable(opts, system_ip, log=log, stop=None, timeout=180):
    """Xac nhan tu phia vManage (giong cach van hanh that). Khong co API thi bo qua.
    opts['vm']: phien VManage da dang nhap (web) -> dung lai, khong login them."""
    vm = opts.get('vm')
    if vm is None:
        try:
            from sdwan_monitor import VManage
            vm = VManage(ob.VMANAGE_IP, opts['vm_user'], opts['vm_pw'])
            vm.login()
        except Exception as e:
            log('      (bo qua kiem tra vManage API: {})\n'.format(str(e)[:120]), 'info')
            return None
    t0 = time.time()
    while time.time() - t0 < timeout and not (stop and stop.is_set()):
        try:
            for d in vm.devices():
                if d.get('system-ip') == system_ip and d.get('reachability') == 'reachable':
                    log('      vManage API: {} reachable ({:.0f}s)\n'.format(system_ip, time.time() - t0), 'ok')
                    return True
        except Exception as e:
            log('      (doi vManage: {})\n'.format(str(e)[:120]), 'info')
        if stop: stop.wait(15)
        else: time.sleep(15)
    log('      vManage API: {} chua reachable sau {:.0f}s\n'.format(system_ip, time.time() - t0), 'err')
    return False


def day0_config(hostname=None, wan_if='ge0/0'):
    """Cap system-ip / IP vpn 0 ke tiep chua dung (theo registry) -> (entry, cac dong cau hinh).
    Chua ghi registry: IP chi duoc giu khi certsign chay xong buoc doc system."""
    n, sip, lan = ob.allocate(ob.load_registry())
    e = {'hostname': hostname or ob.default_hostname(n), 'system_ip': sip, 'site_id': ob.SITE_ID,
         'vpn0_ip': lan, 'wan_if': wan_if}
    return e, ['config'] + ob.base_config(e) + ['commit and-quit']


def day0(a):
    e, lines = day0_config(a.hostname, a.wan_if)
    print('! Day-0 cho vEdge moi - cam {} vao Switch32 (access VLAN {}), dang nhap console thiet bi,'
          .format(a.wan_if, ob.CONTROLLER_VLAN))
    print('! go "config", dan doan duoi, roi "commit and-quit". Sau do chay:')
    print('!   python sdwan_certsign.py {}'.format(e['vpn0_ip']))
    print('\n'.join(lines))
    return 0


def certsign(ip, opts, log=log, stop=None):
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[CERTSIGN] vEdge {} (SSH truc tiep, khong qua EVE)\n'.format(ip), 'hdr')
    try:
        con = SshConsole(ip, opts['vedge_user'], opts['vedge_pw'], 'vEdge ' + ip)
    except OnboardError as ex:
        log('  [!] {}\n'.format(ex), 'err')
        return False
    step = 'system'
    e = None
    try:
        con.login(opts['vedge_user'], [opts['vedge_pw']])
        con.cli('screen-length 0', 10)
        s = running_system(con)
        log('  [1/6] {} system-ip {} site {} org "{}" vbond {}\n'.format(
            s['hostname'], s['system_ip'], s['site_id'], s['org'], s['vbond']), 'info')
        if s['org'] != ob.ORG or not s['system_ip'] or not s['vbond']:
            raise OnboardError('Day-0 chua du (can organization-name {}, system-ip, vbond) - '
                               'xem "python sdwan_certsign.py --day0"'.format(ob.ORG))
        reg = ob.load_registry()
        key = next((k for k, v in reg.items() if v.get('system_ip') == s['system_ip']), s['hostname'])
        e = dict(reg.get(key, {}))
        e.update(node=e.get('node', key), hostname=s['hostname'], system_ip=s['system_ip'],
                 site_id=int(s['site_id'] or ob.SITE_ID), vpn0_ip=ip, via='ssh')
        e.setdefault('wan_if', 'ge0/0')

        step = 'cert'
        p = ob.install_cert(con, log, s['hostname'], opts,
                            lambda csr, crt: ob.sign_on_vmanage(
                                None, log, csr, crt, opts['vm_user'], opts['vm_pw'],
                                con=SshConsole(ob.VMANAGE_IP, opts['vm_user'], opts['vm_pw'], 'vManage')))
        e.update(chassis=p['chassis'], serial=p['serial'], status='signed'); ob.save_entry(e)

        step = 'whitelist'
        log('  [4/6] Whitelist tren vManage / vSmart / vBond (SSH)\n', 'info')
        n_ok = ob.whitelist(None, log, [e], opts, connect=connect_controller(opts))
        e['status'] = 'whitelisted' if n_ok == 3 else 'whitelist {}/3'.format(n_ok); ob.save_entry(e)

        step = 'verify'
        log('  [5/6] Cho control connection (toi da {}s)\n'.format(opts['verify_s']), 'info')
        up = ob.wait_control(con, log, opts['verify_s'], stop)
    except Exception as ex:
        if e:
            e['status'] = 'failed:' + step; ob.save_entry(e)
        log('  [!] Dung o buoc {}: {}\n'.format(step, ex), 'err')
        return False
    finally:
        con.close()
    if up:
        up = vmanage_reachable(opts, e['system_ip'], log, stop) is not False
    e['status'] = 'done' if up else 'verify-fail'; ob.save_entry(e)
    log('  [6/6] {} {}\n'.format(e['hostname'], 'DA VAO FABRIC' if up else 'chua len du controller - xem log'),
        'ok' if up else 'err')
    return up


def rewhitelist(opts, log=log):
    entries = [v for v in ob.load_registry().values() if v.get('chassis') and v.get('serial')]
    log('\n[REWHITELIST] {} vEdge: {}\n'.format(len(entries), ', '.join(v['hostname'] for v in entries)), 'hdr')
    return ob.whitelist(None, log, entries, opts, connect=connect_controller(opts)) == 3


def main():
    ap = argparse.ArgumentParser(description='Ky cert + whitelist vEdge qua IP thiet bi (khong qua EVE host)')
    ap.add_argument('ip', nargs='*', help='IP vpn 0 cua vEdge da dan Day-0 (10.9.0.x)')
    ap.add_argument('--day0', action='store_true', help='in cau hinh Day-0 cho vEdge ke tiep')
    ap.add_argument('--hostname', help='voi --day0: ten vEdge (mac dinh vEdge-SpareN)')
    ap.add_argument('--wan-if', default='ge0/0', help='voi --day0: cong noi Switch32')
    ap.add_argument('--rewhitelist', action='store_true', help='day lai whitelist moi vEdge trong registry')
    ap.add_argument('--resign', action='store_true', help='ky lai du cert dang Valid')
    ap.add_argument('--user', default='admin', help='user vEdge va controller')
    ap.add_argument('--verify', type=int, default=240, help='so giay cho control Up')
    a = ap.parse_args()
    if a.day0:
        return day0(a)
    if not a.ip and not a.rewhitelist:
        ap.error('can IP vEdge, --day0 hoac --rewhitelist')

    opts = {'vm_user': a.user, 'vedge_user': a.user, 'resign': a.resign, 'verify_s': a.verify}
    if a.ip:
        opts['vedge_pw'] = env_pw('SDWAN_VEDGE_PW', 'vEdge')
    opts['vm_pw'] = env_pw('SDWAN_VM_PW', 'vManage')
    opts['vs_pw'] = env_pw('SDWAN_VS_PW', 'vSmart')
    opts['vb_pw'] = os.environ.get('SDWAN_VB_PW') or opts['vm_pw']

    ok = True
    if a.rewhitelist:
        ok &= rewhitelist(opts)
    for ip in a.ip:
        ok &= certsign(ip, opts)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
