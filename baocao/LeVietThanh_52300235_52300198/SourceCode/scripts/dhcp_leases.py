# -*- coding: utf-8 -*-
"""
dhcp_leases.py - tra IP hien tai cua PC theo bang lease DHCP do NetOps Bot day sang.

Web o Site 900 (VPN 0) khong toi duoc Brand-FW chi nhanh (VPN 1), nen bot (DHCP-Server
10.1.90.10, trong VPN 1) doc lease roi POST sang cong rieng cua web (mac dinh 8091). File luu o
log/dhcp_leases.json. Moi lan do, web doi MAC/Client ID cua tung PC voi bang nay de lay IP that,
thay cho IP ghi cung trong campus_ping_tool.SITES.

Nhan dang PC (doi chieu bang lease that 01/11/2026):
  * VPC (VPCS):   MAC 00:50:79:66:68:<node id hex>  -> ASA hien '0100.5079.6668.2b' (node 43)
  * PC Linux:     moi image mot kieu MAC -> ghi tay trong LINUX_CLIENT_ID
So sanh theo 12 ky tu hex cuoi (bo byte loai phan cung '01' cua ASA).
"""
import ipaddress, json, os, re, threading, time
from datetime import datetime

from campus_ping_tool import HOST_IP, HOST_SITE, SITES, VPC_NODE_IDS, LOG_DIR

LEASE_FILE = os.path.join(LOG_DIR, 'dhcp_leases.json')
MAX_AGE = 30 * 60          # bang cu hon 30 phut -> khong dung (bot day moi 5 phut)

# Client ID that cua PC Linux (show dhcpd binding Brand-FW, 01/11/2026). PC-HanhChinh-S100 (node 18)
# lay lease tu DHCP-Server Windows - chua doc duoc, bo sung khi bot day lease Site 100.
LINUX_CLIENT_ID = {
    'PC-YTe-S200':      '000600004700',
    'PC-TaiChinh-S300': '000600005300',
    'PC-LuHanh-S400':   '000600005200',
    'PC-Linux-S500':    '005000004000',
}

_lock = threading.Lock()
_STATIC_IP = dict(HOST_IP)          # IP ghi cung ban dau - de quay lai khi bang lease het han


def norm_id(cid):
    """'0100.5079.6668.2b' / '00-50-79-66-68-2b' / '00:50:79:66:68:2b' -> '00507966682b'."""
    h = re.sub(r'[^0-9a-f]', '', str(cid or '').lower())
    return h[-12:] if len(h) >= 12 else ''


def host_client_ids():
    ids = {h: '0050796668{:02x}'.format(n) for h, n in VPC_NODE_IDS.items()}
    ids.update(LINUX_CLIENT_ID)
    return ids


def _subnet_of(host):
    """Mang /24 cua VLAN chua host (de loai lease khac VLAN trung MAC)."""
    for sd in SITES.values():
        for vd in sd['vlans'].values():
            if host in vd['hosts']:
                return ipaddress.ip_network(vd['subnet'], strict=False)
    return None


def save(payload):
    """Kiem tra + luu bang lease bot gui. Tra ve thong diep ngan."""
    leases = payload.get('leases')
    if not isinstance(leases, list):
        raise ValueError('thieu truong leases (list)')
    clean = []
    for x in leases[:2000]:
        try:
            ip = str(ipaddress.ip_address(str(x.get('ip', ''))))
        except ValueError:
            continue
        cid = norm_id(x.get('client_id'))
        if cid:
            clean.append({'ip': ip, 'client_id': cid, 'site': str(x.get('site', '')),
                          'source': str(x.get('source', ''))[:40], 'hostname': str(x.get('hostname', ''))[:60]})
    data = {'received_at': time.time(), 'collected_at': str(payload.get('collected_at', ''))[:32],
            'errors': {str(k)[:60]: str(v)[:200] for k, v in (payload.get('errors') or {}).items()},
            'leases': clean}
    tmp = LEASE_FILE + '.tmp'
    with _lock:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, LEASE_FILE)
    return 'OK {} lease'.format(len(clean))


def load():
    try:
        with open(LEASE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def resolve(max_age=MAX_AGE):
    """-> (anh xa host -> {ip, static, source}, tuoi bang lease giay | None, loi nguon)."""
    data = load()
    age = time.time() - data['received_at'] if data else None
    by_id = {}
    if data and age <= max_age:
        for x in data['leases']:
            by_id.setdefault(x['client_id'], []).append(x)
    out = {}
    for host, cid in host_client_ids().items():
        if host not in _STATIC_IP:
            continue
        net = _subnet_of(host)
        hit = next((x for x in by_id.get(cid, []) if net is None or ipaddress.ip_address(x['ip']) in net), None)
        out[host] = {'ip': hit['ip'] if hit else _STATIC_IP[host], 'static': _STATIC_IP[host],
                     'source': hit['source'] if hit else ''}
    return out, age, (data or {}).get('errors', {})


def refresh_host_ip(log=None):
    """Cap nhat HOST_IP (dung chung moi tab) theo lease; tra ve so host da doi IP."""
    m, age, errors = resolve()
    if age is None:
        log and log('  [i] Chua co bang lease tu NetOps Bot - dung IP ghi cung.\n', 'info')
    elif age > MAX_AGE:
        log and log('  [!] Bang lease cu {:.0f} phut (> {} phut) - dung IP ghi cung.\n'.format(
            age / 60, MAX_AGE // 60), 'err')
    changed = 0
    for host, r in m.items():
        if HOST_IP.get(host) != r['ip']:
            if log:
                log('  [i] {:<22} {} -> {} ({})\n'.format(host, HOST_IP.get(host), r['ip'],
                                                         r['source'] or 'IP ghi cung'), 'info')
            HOST_IP[host] = r['ip']
            changed += 1
    if log and age is not None and age <= MAX_AGE:
        found = sum(1 for r in m.values() if r['source'])
        log('  [i] IP theo lease DHCP (bot, {:.0f} phut truoc): {}/{} PC tim thay{}.\n'.format(
            age / 60, found, len(m), '; nguon loi: ' + ', '.join(errors) if errors else ''), 'info')
    return changed


def summary():
    """Cho GET /api/leases: bang host -> IP lease / IP ghi cung."""
    m, age, errors = resolve()
    data = load() or {}
    return {'age_s': None if age is None else round(age), 'max_age_s': MAX_AGE,
            'collected_at': data.get('collected_at', ''), 'errors': errors,
            'received': datetime.fromtimestamp(data['received_at']).strftime('%d/%m %H:%M:%S') if data else '',
            'hosts': [dict(host=h, site=HOST_SITE.get(h, ''), **r) for h, r in sorted(m.items())]}
