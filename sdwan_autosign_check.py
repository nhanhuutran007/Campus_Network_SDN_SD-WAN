#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdwan_autosign_check.py  –  Kiem tra vManage co the TU KY cert vEdge (Automated) khong
==================================================================================
CHI DOC qua REST API cua vManage (theo IP vManage, khong console/SSH, khong qua EVE host):
  1. Phien ban vManage
  2. Cai dat Certificate Authority / vEdge Cloud Certificate Authorization
  3. WAN Edge List: muc nao da dung (co system-ip) / muc nao con TRONG (dung cho vEdge moi)
  4. Root certificate ma vManage phat cho vEdge
Tuy chon --bootstrap <UUID>: xem bootstrap (cloud-init) cua 1 muc -> co UUID + OTP token.
  Luu y: goi nay CO THE khien vManage sinh token moi (doi trang thai muc do) -> chi chay khi
  da chon muc trong de dung.

Chay tren may lab (vd 10.9.0.20):
    python sdwan_autosign_check.py                    # hoi mat khau
    python sdwan_autosign_check.py --vmanage 10.9.0.10 --user admin
    python sdwan_autosign_check.py --bootstrap <UUID>
Ket qua tho luu vao log/autosign_check_<thoigian>.json -> gui file nay de phan tich.
"""
import argparse, getpass, json, os, sys
from datetime import datetime

from sdwan_monitor import VManage, VManageError, VMANAGE_DEFAULT
from campus_ping_tool import LOG_DIR

SETTING_PATHS = [                      # ten endpoint khac nhau giua cac ban vManage -> thu het
    'settings/configuration/certificate',
    'settings/configuration/vedgecloud',
    'settings/configuration/certificate/vedgecloud',
]


def try_get(vm, path, dump):
    try:
        d = vm.get(path)
        dump[path] = d
        return d
    except VManageError as e:
        dump[path] = {'error': str(e)}
        return None


def section(title):
    print('\n=== {} ==='.format(title))


def main():
    ap = argparse.ArgumentParser(description='Kiem tra vManage tu ky cert vEdge (chi doc)')
    ap.add_argument('--vmanage', default=VMANAGE_DEFAULT)
    ap.add_argument('--user', default='admin')
    ap.add_argument('--password')
    ap.add_argument('--bootstrap', metavar='UUID', help='xem bootstrap cloud-init cua 1 muc WAN Edge List')
    a = ap.parse_args()
    pw = a.password or getpass.getpass('Mat khau vManage {}@{}: '.format(a.user, a.vmanage))

    vm = VManage(a.vmanage, a.user, pw)
    try:
        vm.login()
    except VManageError as e:
        print('LOI:', e)
        return 1
    dump = {'vmanage': a.vmanage, 'time': datetime.now().isoformat()}

    section('1. Phien ban')
    d = try_get(vm, 'client/server', dump)
    srv = (d or {}).get('data', d) or {}
    print('vManage version:', srv.get('platformVersion') or srv.get('version') or '(khong ro)')

    section('2. Cai dat ky cert')
    for p in SETTING_PATHS:
        d = try_get(vm, p, dump)
        if d is None:
            print('  {:<48} khong co (ban nay khong ho tro)'.format(p))
        else:
            rows = d.get('data', d) if isinstance(d, dict) else d
            print('  {:<48} {}'.format(p, json.dumps(rows, ensure_ascii=False)[:300]))
    print('  -> Tim truong kieu "certificateauthority"/"vedgecloud": "vmanage" = Automated (vManage tu ky),'
          ' "manual" = ky tay.')

    section('3. WAN Edge List (system/device/vedges)')
    d = try_get(vm, 'system/device/vedges', dump)
    rows = (d or {}).get('data', []) if isinstance(d, dict) else []
    used, free = [], []
    for r in rows:
        (used if r.get('system-ip') or r.get('host-name') else free).append(r)
    fmt = '  {:<38} {:<12} {:<14} {:<15} {:<22} {}'
    print(fmt.format('UUID/chassis', 'model', 'host-name', 'system-ip', 'cert-state', 'validity'))
    for r in used + free:
        print(fmt.format(r.get('uuid') or r.get('chasisNumber') or '-', str(r.get('deviceModel') or '-')[:12],
                         r.get('host-name') or '-', r.get('system-ip') or '-',
                         r.get('vedgeCertificateState') or '-', r.get('validity') or '-'))
    print('  Tong {} muc: {} da dung, {} con trong.'.format(len(rows), len(used), len(free)))
    if free:
        print('  -> Co the dung muc trong cho vEdge moi: --bootstrap <UUID> de xem OTP token.')
    else:
        print('  -> KHONG con muc trong: can upload WAN Edge List moi (file serial / CSV) truoc.')

    section('4. Root certificate vManage phat cho vEdge')
    d = try_get(vm, 'certificate/rootcertificate', dump)
    pem = (d or {}).get('rootcertificate', '') if isinstance(d, dict) else ''
    print('  {}'.format('co ({} ky tu PEM)'.format(len(pem)) if pem else 'khong lay duoc'))

    if a.bootstrap:
        section('5. Bootstrap cloud-init cua ' + a.bootstrap)
        d = try_get(vm, 'system/device/bootstrap/device/{}?configtype=cloudinit'.format(a.bootstrap), dump)
        cfg = (d or {}).get('bootstrapConfig', '') if isinstance(d, dict) else ''
        print(cfg or json.dumps(d, ensure_ascii=False)[:1500])

    os.makedirs(LOG_DIR, exist_ok=True)
    out = os.path.join(LOG_DIR, 'autosign_check_{}.json'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(dump, f, ensure_ascii=False, indent=1)
    print('\nDa luu ket qua tho: ' + out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
