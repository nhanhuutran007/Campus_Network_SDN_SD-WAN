#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdwan_monitor.py  –  Lay du lieu THAT tu thiet bi qua vManage REST API
================================================================
Ban web KHONG con dung console/SSH vao host EVE-NG (10.215.28.26). Moi so lieu
lay dung kieu van hanh thuc te: vEdge day trang thai len vManage, NOC goi
REST API cua vManage theo IP cua vManage (mac dinh 10.9.0.10):
  * /device, /device/bfd/sessions, /device/control/connections   -> tong quan
  * /device/interface (rx/tx-octets)                              -> thong luong
  * /device/tools/nping, /device/tools/traceroute                 -> vEdge tu
    ping / traceroute trong VPN 1 (giong Monitor > Troubleshooting tren GUI)
  * /device/policy/*filter, /device/omp/routes/received           -> chinh sach
  * /system/device/vedges, /device/orchestrator/validvedges       -> whitelist
Ping "tu may chay web" thi chay lenh ping cua chinh may do toi IP thiet bi.

Cac tab chi DO / KIEM CHUNG, khong sua cau hinh thiet bi (ngoai le duy nhat:
day lai whitelist vEdge qua API vManage = nut "Send to Controllers").
"""
import csv, ipaddress, json, os, re, ssl, threading, time
import http.cookiejar, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from campus_ping_tool import (
    HOST_IP, SITE_VEDGES, LOG_DIR, HAS_MPL,
    PingResult, ChartEngine, ping_host, site_of_ip, CYAN, PURPLE, RED, YELLOW, GREEN,
)

VMANAGE_DEFAULT = '10.9.0.10'
VEDGE_NAMES = {ip: n for d in SITE_VEDGES.values() for ip, n in d.items()}
NAME_TO_SYSIP = {n: ip for ip, n in VEDGE_NAMES.items()}
SITE_OF_SYSIP = {ip: sid for sid, d in SITE_VEDGES.items() for ip in d}
TOOL_GAP = 0.3          # giay nghi giua 2 lenh nping lien tiep (vManage xu ly tuan tu)


class VManageError(Exception):
    pass


# =========================================================
#  vMANAGE REST CLIENT  (HTTPS truc tiep toi IP vManage)
# =========================================================
class VManage:
    def __init__(self, host, user, password, timeout=40):
        self.host, self.user, self.password, self.timeout = host, user, password, timeout
        self.base = 'https://{}'.format(host)
        self._op, self._token = None, None
        self._lock = threading.Lock()

    def login(self):
        with self._lock:
            op = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            data = urllib.parse.urlencode({'j_username': self.user, 'j_password': self.password}).encode()
            try:
                body = op.open(self.base + '/j_security_check', data, timeout=10).read()
            except (urllib.error.URLError, OSError) as e:
                raise VManageError('Khong toi duoc vManage {} ({})'.format(self.host, getattr(e, 'reason', e)))
            if b'<html' in body.lower():          # vManage tra lai trang login = sai user/pass
                raise VManageError('Dang nhap vManage {} that bai (sai user/pass?)'.format(self.host))
            self._op, self._token = op, None
            try:                                   # vManage >= 19.2 can XSRF token cho POST
                tok = op.open(self.base + '/dataservice/client/token', timeout=10).read().decode().strip()
                if tok and '<' not in tok:
                    self._token = tok
            except urllib.error.HTTPError:
                pass                               # ban cu khong co token
        return self

    def _request(self, path, body=None, timeout=None, retry=True):
        if self._op is None:
            self.login()
        headers = {'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
            if self._token:
                headers['X-XSRF-TOKEN'] = self._token
        req = urllib.request.Request(self.base + '/dataservice/' + path.lstrip('/'), data=data, headers=headers)
        try:
            raw = self._op.open(req, timeout=timeout or self.timeout).read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and retry:
                self.login()
                return self._request(path, body, timeout, False)
            msg = e.read().decode('utf-8', 'replace')[:300]
            raise VManageError('vManage {} {}: HTTP {} {}'.format('POST' if body is not None else 'GET',
                                                                 path, e.code, msg))
        except (urllib.error.URLError, OSError) as e:
            raise VManageError('vManage {}: {}'.format(path, getattr(e, 'reason', e)))
        if raw.lstrip().startswith('<'):           # het phien -> trang login
            if retry:
                self.login()
                return self._request(path, body, timeout, False)
            raise VManageError('vManage tra ve HTML cho {} (het phien dang nhap?)'.format(path))
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError:
            return {'raw': raw}

    def get(self, path, timeout=None):
        return self._request(path, timeout=timeout)

    def rows(self, path, timeout=None):
        d = self.get(path, timeout)
        return d.get('data', []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

    def post(self, path, body=None, timeout=None):
        return self._request(path, body if body is not None else {}, timeout)

    # ---- tien ich hay dung ----
    def devices(self):
        return self.rows('device')

    def vedges(self):
        return [d for d in self.devices() if d.get('personality') == 'vedge' or d.get('device-type') == 'vedge']

    def bfd(self, sysip):
        return self.rows('device/bfd/sessions?deviceId=' + sysip)

    def control(self, sysip):
        return self.rows('device/control/connections?deviceId=' + sysip)

    def interfaces(self, sysip):
        return self.rows('device/interface?deviceId=' + sysip)


# =========================================================
#  PING / TRACEROUTE TU vEDGE (vManage Troubleshooting tools)
# =========================================================
_SRC_CACHE = {}


def lan_source(vm, sysip, vpn=1):
    """Interface LAN (vpn 1) dang up co IP cua vEdge -> (ifname, ip). Lam nguon cho nping de
    goi tin di dung duong du lieu that (vpn 1 -> overlay -> site dich)."""
    key = (vm.host, sysip, vpn)
    if key in _SRC_CACHE:
        return _SRC_CACHE[key]
    best = None
    for r in vm.interfaces(sysip):
        if str(r.get('vpn-id')) != str(vpn):
            continue
        ip = str(r.get('ip-address', '')).split('/')[0]
        if not ip or ip.startswith('0.') or ip == '-':
            continue
        up = str(r.get('if-oper-status', '')).lower() == 'up'
        name = r.get('ifname', '')
        score = (up, name.startswith('ge'), not name.startswith('loopback'))
        if best is None or score > best[0]:
            best = (score, name, ip)
    if best is None:
        raise VManageError('{} khong co interface vpn {} co IP'.format(VEDGE_NAMES.get(sysip, sysip), vpn))
    _SRC_CACHE[key] = (best[1], best[2])
    return _SRC_CACHE[key]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_nping(resp, count):
    """Ket qua /device/tools/nping -> PingResult. Uu tien so trong rawOutput (nping in
    'Max rtt: x | Min rtt: y | Avg rtt: z', 'Raw packets sent: n | Rcvd: m | Lost: k (p%)');
    jitter = TB |RTT_i - RTT_(i-1)| tinh tu cap dong SENT/RCVD."""
    r = PingResult()
    lines = resp.get('rawOutput') or []
    if isinstance(lines, str):
        lines = lines.splitlines()
    raw = '\n'.join(str(l) for l in lines)
    r.raw = raw or json.dumps(resp)[:500]
    m = re.search(r'Max rtt:\s*([\d.]+)ms\s*\|\s*Min rtt:\s*([\d.]+)ms\s*\|\s*Avg rtt:\s*([\d.]+)ms', raw)
    if m:
        r.max_latency, r.min_latency, r.avg_latency = map(float, m.groups())
        r.success = True
    m2 = re.search(r'Rcvd:\s*(\d+).*?Lost:\s*(\d+)\s*\(([\d.]+)%\)', raw)
    if m2:
        r.loss = float(m2.group(3))
        r.success = r.success and int(m2.group(1)) > 0
    else:                                    # khong co rawOutput chuan -> doc truong JSON
        tx, rx = _f(resp.get('packetsTransmitted')), _f(resp.get('packetsReceived'))
        loss = _f(resp.get('lossPercentage'))
        if loss is None and tx:
            loss = (tx - (rx or 0)) / tx * 100
        r.loss = loss if loss is not None else 100.0
        if not m and rx:
            r.min_latency = _f(resp.get('minRoundTrip')) or 0.0
            r.avg_latency = _f(resp.get('avgRoundTrip')) or 0.0
            r.max_latency = _f(resp.get('maxRoundTrip')) or 0.0
            r.success = True
    # RTT tung goi: dong SENT (t) ... RCVD (t') lien tiep
    rtts, sent = [], None
    for l in lines:
        ms = re.match(r'\s*(SENT|RCVD)\s*\(([\d.]+)s\)', str(l))
        if not ms:
            continue
        if ms.group(1) == 'SENT':
            sent = float(ms.group(2))
        elif sent is not None:
            rtts.append((float(ms.group(2)) - sent) * 1000)
            sent = None
    if len(rtts) >= 2:
        r.jitter = round(sum(abs(a - b) for a, b in zip(rtts[1:], rtts)) / (len(rtts) - 1), 3)
    elif r.success:
        r.jitter = round(r.max_latency - r.min_latency, 3)
    else:
        r.jitter = 0.0
    if not r.success:
        r.loss = 100.0 if r.loss is None else r.loss
    return r


def vedge_ping(vm, sysip, dst, count=5, vpn=1, source=None, probe='icmp', port=None, size=None):
    """vEdge `sysip` ping `dst` trong VPN `vpn` (mac dinh nguon = interface LAN vpn 1)."""
    if source is None:
        source = lan_source(vm, sysip, vpn)[0] if str(vpn) != '0' else ''
    body = {'host': dst, 'vpn': str(vpn), 'source': source, 'probeType': probe, 'count': str(count),
            'size': str(size or ''), 'df': 'false', 'rapid': 'false'}
    if port:
        body['destPort'] = str(port)
    resp = vm.post('device/tools/nping/' + sysip, body, timeout=count * 3 + 30)
    r = parse_nping(resp if isinstance(resp, dict) else {}, count)
    r.raw = '[vManage nping {} vpn {} src {}] -> {}\n{}'.format(
        VEDGE_NAMES.get(sysip, sysip), vpn, source or '-', dst, r.raw)
    return r


def vedge_traceroute(vm, sysip, dst, vpn=1):
    source = lan_source(vm, sysip, vpn)[0]
    resp = vm.post('device/tools/traceroute/' + sysip, {'host': dst, 'vpn': str(vpn), 'source': source},
                   timeout=90)
    lines = resp.get('rawOutput') if isinstance(resp, dict) else None
    if isinstance(lines, str):
        lines = lines.splitlines()
    return [str(l) for l in (lines or [])]


def site_vedges(site_id, vm=None):
    """system-ip vEdge cua 1 site (theo SITE_VEDGES); co vm thi uu tien vEdge reachable."""
    ips = sorted(SITE_VEDGES.get(site_id, {}))
    if vm is not None:
        reach = {d.get('system-ip') for d in vm.vedges() if d.get('reachability') == 'reachable'}
        ips = [i for i in ips if i in reach] + [i for i in ips if i not in reach]
    return ips


def _metrics(ctx, r):
    if r.success:
        ctx._update_metric('avg_lat', '{:.2f} ms'.format(r.avg_latency))
        ctx._update_metric('loss', '{:.1f} %'.format(r.loss))
        ctx._update_metric('jitter', '{:.2f} ms'.format(r.jitter))
        ctx._update_metric('min_lat', '{:.2f} ms'.format(r.min_latency))
        ctx._update_metric('max_lat', '{:.2f} ms'.format(r.max_latency))
    else:
        for k in ('avg_lat', 'jitter', 'min_lat', 'max_lat'):
            ctx._update_metric(k, '--')
        ctx._update_metric('loss', '100.0 %')


def _grade(r):
    if r.loss == 0 and r.avg_latency < 50 and r.jitter < 10:
        return 'TOT', 'ok'
    if r.loss < 5 and r.avg_latency < 150:
        return 'TRUNG BINH', 'info'
    return 'KEM', 'err'


def probe(ctx, vm, src, dst_ip, count, timeout=2):
    """src = system-ip vEdge (ping qua vManage) hoac 'local' (ping tu may chay web)."""
    if src == 'local':
        r = ping_host(dst_ip, count=count, timeout_sec=timeout)
        r.raw = '[ping tu may chay web] -> {}\n{}'.format(dst_ip, r.raw)
        return r
    return vedge_ping(vm, src, dst_ip, count)


def _src_label(src):
    return 'may chay web' if src == 'local' else VEDGE_NAMES.get(src, src)


# =========================================================
#  DO LUONG: ping 1 lan / lien tuc / batch cases
# =========================================================
def ping_job(ctx, vm, src, dst_name, dst_ip, count, timeout):
    log = ctx._log
    ctx._set_status('Ping {} -> {}...'.format(_src_label(src), dst_name), True)
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[PING] {} -> {} ({}) x{} goi\n'.format(_src_label(src), dst_name, dst_ip, count), 'hdr')
    r = probe(ctx, vm, src, dst_ip, count, timeout)
    log('+ Output:\n', 'info')
    for line in r.raw.strip().splitlines():
        log('  {}\n'.format(line), 'data')
    if r.success:
        g, tag = _grade(r)
        log('[OK] Avg {:.3f} ms | Loss {:.1f} % | Jitter {:.3f} ms | Min {:.3f} | Max {:.3f} -> {}\n'.format(
            r.avg_latency, r.loss, r.jitter, r.min_latency, r.max_latency, g), tag)
    else:
        log('[FAIL] {} ({}) khong phan hoi\n'.format(dst_name, dst_ip), 'err')
    _metrics(ctx, r)


def ping_loop_job(ctx, vm, src, dst_name, dst_ip, timeout):
    log, stop = ctx._log, ctx._stop_event
    log('\n[PING LIEN TUC] {} -> {} ({}) | bam Dung de ngung\n'.format(_src_label(src), dst_name, dst_ip), 'hdr')
    ctx._set_status('Ping lien tuc -> {}'.format(dst_name), True)
    seq = 0
    while not stop.is_set():
        seq += 1
        try:
            r = probe(ctx, vm, src, dst_ip, 4, timeout)
        except Exception as e:
            log('  #{:04d}  loi: {}\n'.format(seq, e), 'err')
            stop.wait(3)
            continue
        if r.success:
            log('  #{:04d}  Lat={:7.2f} ms  Loss={:5.1f}%  Jitter={:6.2f} ms\n'.format(
                seq, r.avg_latency, r.loss, r.jitter), 'ok' if r.loss == 0 else 'err')
        else:
            log('  #{:04d}  TIMEOUT - khong phan hoi\n'.format(seq), 'err')
        _metrics(ctx, r)
        stop.wait(1)
    log('[DUNG ping lien tuc]\n', 'info')


# Tuyen do: (site nguon, host dich). Nguon la vEdge cua site do (vpn 1).
INTRA_ROUTES = [(100, 'PC-CNTT-S100-1'), (100, 'PC-TTK-S100-1'), (100, 'PC-Luat-S100-1'),
                (100, 'WebServer'), (100, 'DHCP-Server'),
                (200, 'PC-NongNghiep-S200-1'), (200, 'PC-YTe-S200'),
                (300, 'PC-DuLich-S300-1'), (300, 'PC-TaiChinh-S300'),
                (400, 'PC-ThuySan-S400-1'), (400, 'PC-LuHanh-S400')]
INTER_ROUTES = [(100, 'PC-NongNghiep-S200-1'), (100, 'PC-TaiChinh-S300'), (100, 'PC-LuHanh-S400-2'),
                (200, 'PC-CNTT-S100-1'), (200, 'PC-TaiChinh-S300'), (200, 'PC-LuHanh-S400-2'),
                (300, 'PC-CNTT-S100-1'), (300, 'PC-LuHanh-S400-2'),
                (400, 'PC-CNTT-S100-1'), (400, 'WebServer')]
CASE_NAMES = ['Ping noi bo tung site (vEdge -> host cung site)',
              'Ping lien chi nhanh qua overlay SD-WAN',
              'Bieu do Avg Latency', 'Bieu do Avg Loss (%)', 'Bieu do Avg Jitter', 'Dashboard tong hop (PNG)']


def _save_case_csv(ctx, name, data):
    path = os.path.join(LOG_DIR, '{}.csv'.format(name))
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Tuyen_Duong', 'Nguon_vEdge', 'Dich_IP', 'Avg_Latency_ms', 'Avg_Loss_pct',
                    'Avg_Jitter_ms', 'Min_RTT_ms', 'Max_RTT_ms', 'Thoi_gian'])
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for r in data:
            w.writerow([r['label'], r['src'], r['dst'], round(r['latency'], 3), round(r['loss'], 2),
                        round(r['jitter'], 3), round(r['min'], 3), round(r['max'], 3), ts])
    ctx._log('  [OK] CSV: {}\n'.format(path), 'ok')


def _run_routes(ctx, vm, routes, count):
    data, stop = [], ctx._stop_event
    srcs = {}
    for sid, host in routes:
        if stop.is_set():
            break
        if sid not in srcs:
            cands = site_vedges(sid, vm)
            srcs[sid] = cands[0] if cands else None
        src, ip = srcs[sid], HOST_IP[host]
        label = '{}>{}'.format(VEDGE_NAMES.get(src, 'S{}'.format(sid)), host)
        row = {'label': label, 'src': VEDGE_NAMES.get(src, ''), 'dst': ip,
               'latency': 0.0, 'loss': 100.0, 'jitter': 0.0, 'min': 0.0, 'max': 0.0}
        try:
            if src is None:
                raise VManageError('site {} khong co vEdge'.format(sid))
            r = vedge_ping(vm, src, ip, count)
            if r.success:
                row.update(latency=r.avg_latency, loss=r.loss, jitter=r.jitter, min=r.min_latency, max=r.max_latency)
                ctx._log('  OK   {:<40} Lat={:7.2f}ms Loss={:5.1f}% Jitter={:6.2f}ms\n'.format(
                    label, r.avg_latency, r.loss, r.jitter), 'ok')
            else:
                ctx._log('  FAIL {:<40} ({}) khong phan hoi\n'.format(label, ip), 'err')
        except Exception as e:
            ctx._log('  FAIL {:<40} {}\n'.format(label, e), 'err')
        data.append(row)
        time.sleep(TOOL_GAP)
    return data


def cases_job(ctx, vm, cases, count):
    log = ctx._log
    ctx._set_status('Batch cases {}...'.format(cases), True)
    log('\n' + '=' * 55 + '\n', 'sep')
    log('BATCH REPORT (vEdge ping qua vManage API) - Cases: {}\n'.format(cases), 'hdr')
    cache = {}

    def need(key, routes):
        if key not in cache:
            cache[key] = _run_routes(ctx, vm, routes, count)
        return cache[key]

    def bar(data, field, title, ylabel, fname, color, horiz=False):
        if HAS_MPL and data:
            ChartEngine.bar_chart([r['label'] for r in data], [r[field] for r in data], title, ylabel,
                                  os.path.join(LOG_DIR, fname), color=color, horiz=horiz)
            log('  [OK] PNG: {}\n'.format(fname), 'ok')

    for c in cases:
        if ctx._stop_event.is_set():
            log('  [i] Dung theo yeu cau.\n', 'info')
            break
        log('\n' + '-' * 40 + '\nCase {} - {}\n'.format(c, CASE_NAMES[c - 1]), 'info')
        try:
            if c == 1:
                d = need('intra', INTRA_ROUTES)
                bar(d, 'latency', 'Case 1 - Avg Latency noi bo tung site (ms)', 'ms', 'case1_intra_latency.png', CYAN)
                _save_case_csv(ctx, 'case1_intra', d)
            elif c == 2:
                d = need('inter', INTER_ROUTES)
                bar(d, 'latency', 'Case 2 - Avg Latency lien chi nhanh SD-WAN (ms)', 'ms', 'case2_inter_latency.png', PURPLE)
                _save_case_csv(ctx, 'case2_inter', d)
            else:
                d = need('intra', INTRA_ROUTES) + need('inter', INTER_ROUTES)
                if c == 3:
                    bar(d, 'latency', 'Case 3 - Avg Latency toan mang (ms)', 'ms', 'case3_latency.png', CYAN, True)
                elif c == 4:
                    bar(d, 'loss', 'Case 4 - Avg Loss % toan mang', '%', 'case4_loss.png', RED)
                elif c == 5:
                    bar(d, 'jitter', 'Case 5 - Avg Jitter toan mang (ms)', 'ms', 'case5_jitter.png', YELLOW)
                elif HAS_MPL:
                    ChartEngine.dashboard(d, os.path.join(LOG_DIR, 'case6_dashboard.png'))
                    log('  [OK] PNG: case6_dashboard.png\n', 'ok')
                _save_case_csv(ctx, 'case{}_{}'.format(c, ['latency', 'loss', 'jitter', 'dashboard'][c - 3]), d)
        except Exception as e:
            log('  [!] Loi Case {}: {}\n'.format(c, e), 'err')
    log('\n' + '=' * 55 + '\nHOAN THANH. Bieu do & CSV: {}\n'.format(LOG_DIR), 'ok')


# =========================================================
#  TONG QUAN FABRIC
# =========================================================
def _uptime(d):
    v = d.get('uptime-date')
    try:
        s = time.time() - int(v) / 1000
    except (TypeError, ValueError):
        return ''
    days, rem = divmod(int(s), 86400)
    return '{}d {}h'.format(days, rem // 3600) if days else '{}h {}m'.format(rem // 3600, rem % 3600 // 60)


def overview(vm):
    """Danh sach thiet bi + so phien BFD/control cua tung vEdge (goi song song)."""
    devs = vm.devices()
    out = []
    for d in devs:
        out.append({'host': d.get('host-name', ''), 'sysip': d.get('system-ip', ''),
                    'type': d.get('personality') or d.get('device-type', ''),
                    'site': d.get('site-id', ''), 'reach': d.get('reachability', ''),
                    'version': d.get('version', ''), 'uptime': _uptime(d),
                    'bfd_up': None, 'bfd_total': None, 'ctrl_up': None})
    edges = [o for o in out if o['type'] == 'vedge' and o['reach'] == 'reachable']

    def fill(o):
        try:
            b = vm.bfd(o['sysip'])
            o['bfd_total'] = len(b)
            o['bfd_up'] = sum(1 for s in b if s.get('state') == 'up')
            c = vm.control(o['sysip'])
            o['ctrl_up'] = sum(1 for s in c if s.get('state') == 'up')
        except Exception as e:
            o['error'] = str(e)[:120]
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(fill, edges))
    order = {'vmanage': 0, 'vsmart': 1, 'vbond': 2, 'vedge': 3}
    out.sort(key=lambda o: (order.get(o['type'], 9), str(o['site']), o['host']))
    return out


def vedge_detail(vm, sysip):
    bfd = [{'peer': VEDGE_NAMES.get(s.get('system-ip'), s.get('system-ip', '')), 'site': s.get('site-id', ''),
            'state': s.get('state', ''), 'local': s.get('local-color', ''), 'remote': s.get('color', ''),
            'src': s.get('src-ip', ''), 'dst': s.get('dst-ip', ''), 'uptime': s.get('uptime', ''),
            'trans': s.get('transitions', '')} for s in vm.bfd(sysip)]
    ctrl = [{'peer': s.get('peer-type', ''), 'sysip': s.get('system-ip', ''), 'state': s.get('state', ''),
             'color': s.get('local-color', ''), 'uptime': s.get('uptime', '')} for s in vm.control(sysip)]
    ifs = [{'vpn': r.get('vpn-id', ''), 'ifname': r.get('ifname', ''), 'ip': r.get('ip-address', ''),
            'admin': r.get('if-admin-status', ''), 'oper': r.get('if-oper-status', ''),
            'rx': r.get('rx-packets', ''), 'tx': r.get('tx-packets', '')}
           for r in vm.interfaces(sysip) if str(r.get('af-type', 'ipv4')) == 'ipv4']
    return {'bfd': bfd, 'control': ctrl, 'interfaces': ifs}


# =========================================================
#  FAILOVER (CHI DO): nguoi lam tu cat link, tool do RTO
# =========================================================
def failover_job(ctx, vm, opts):
    """opts: watch (sysip vEdge bi cat), probe (sysip vEdge do), target, wait_cut, duration.
    2 luong song song: (1) vEdge do nping 1 goi lien tuc toi target, (2) doc phien BFD cua
    vEdge bi cat. Moc CUT = BFD giam hoac mat goi dau tien; RECOVER = goi tra loi dau tien
    sau chuoi mat goi. RTO = RECOVER - CUT (do phan giai ~ thoi gian 1 lan nping)."""
    log, stop = ctx._log, ctx._stop_event
    watch, src, target = opts['watch'], opts['probe'], opts['target']
    wname, sname = VEDGE_NAMES.get(watch, watch), VEDGE_NAMES.get(src, src)
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[FAILOVER] Theo doi {} | do bang nping tu {} -> {}\n'.format(wname, sname, target), 'hdr')
    ctx._set_status('Failover: lay moc ban dau...', True)

    base = vm.bfd(watch)
    up0 = sum(1 for s in base if s.get('state') == 'up')
    log('  [*] BFD {} ban dau: {}/{} up ({})\n'.format(wname, up0, len(base), ', '.join(sorted(
        {s.get('local-color', '?') for s in base if s.get('state') == 'up'})) or '-'), 'info')
    r0 = vedge_ping(vm, src, target, 3)
    if not r0.success:
        log('  [!] {} chua ping duoc {} truoc khi cat -> chon dich khac / kiem tra host dich.\n'.format(
            sname, target), 'err')
        return
    log('  [*] Ping moc ban dau OK: {:.2f} ms\n'.format(r0.avg_latency), 'ok')
    log('  >>> BAY GIO hay cat link WAN tren {} (shutdown interface tren vEdge hoac ngat link '
        'trong lab). Tool cho toi {} s. <<<\n'.format(wname, opts['wait_cut']), 'hdr')

    t0 = time.time()
    pings, bfds = [], []            # (t, ok, rtt) | (t, up, total)
    halt = threading.Event()

    def pinger():
        while not halt.is_set():
            ts = time.time() - t0
            try:
                r = vedge_ping(vm, src, target, 1)
                pings.append((round(ts, 2), r.success, r.avg_latency if r.success else None))
            except Exception as e:
                pings.append((round(ts, 2), False, None))
                log('    [!] nping loi: {}\n'.format(str(e)[:100]), 'err')
                halt.wait(1)

    def bfd_watch():
        last = up0
        while not halt.is_set():
            try:
                b = vm.bfd(watch)
                up = sum(1 for s in b if s.get('state') == 'up')
                ts = round(time.time() - t0, 2)
                bfds.append((ts, up, len(b)))
                if up != last:
                    down = sorted({s.get('local-color', '?') for s in b if s.get('state') != 'up'})
                    log('    t={:6.1f}s  BFD {} {}/{} up{}\n'.format(ts, wname, up, len(b),
                        ' | down: ' + ', '.join(down) if down else ''), 'info' if up < last else 'ok')
                    last = up
            except Exception as e:
                log('    [!] doc BFD loi: {}\n'.format(str(e)[:100]), 'err')
            halt.wait(2)

    th = [threading.Thread(target=pinger, daemon=True), threading.Thread(target=bfd_watch, daemon=True)]
    for t in th:
        t.start()
    cut_t = rec_t = None
    shown = 0
    try:
        while not stop.is_set():
            now = time.time() - t0
            for ts, ok, rtt in pings[shown:]:
                log('    t={:6.1f}s  {}\n'.format(ts, '{:.2f} ms'.format(rtt) if ok else 'MAT GOI'),
                    'data' if ok else 'err')
            shown = len(pings)
            if cut_t is None:
                cands = [ts for ts, ok, _ in pings if not ok] + [ts for ts, up, _ in bfds if up < up0]
                if cands:
                    cut_t = min(cands)
                    log('  [CUT] Phat hien su co tai t={:.1f}s\n'.format(cut_t), 'hdr')
                elif now > opts['wait_cut']:
                    log('  [!] Het {} s ma khong thay link bi cat (BFD van {}/{} up, ping khong mat).\n'.format(
                        opts['wait_cut'], up0, len(base)), 'err')
                    break
            else:
                if rec_t is None:
                    # RECOVER = goi OK dau tien ngay sau 1 goi mat (tinh tu moc CUT)
                    seq = [(ts, ok) for ts, ok, _ in pings if ts >= cut_t]
                    for i in range(1, len(seq)):
                        if seq[i][1] and not seq[i - 1][1]:
                            rec_t = seq[i][0]
                            break
                    if rec_t is None and all(ok for _, ok in seq) and len(seq) >= 3:
                        rec_t = cut_t          # khong mat goi nao o do phan giai hien tai
                    if rec_t is not None:
                        log('  [RECOVER] Ping thong lai tai t={:.1f}s -> RTO ~ {:.1f} s\n'.format(
                            rec_t, rec_t - cut_t), 'ok')
                if now - cut_t > opts['duration']:
                    break
            ctx._set_status('Failover t={:.0f}s{}'.format(now, '' if cut_t is None else
                            ' (sau cat {:.0f}/{}s)'.format(now - cut_t, opts['duration'])), True)
            stop.wait(0.5)
    finally:
        halt.set()
        for t in th:
            t.join(5)

    if stop.is_set():
        log('  [i] Dung theo yeu cau.\n', 'info')
    if not pings:
        log('=' * 55 + '\n\n', 'sep')
        return
    sent = [p for p in pings if cut_t is None or p[0] >= cut_t]
    lost = sum(1 for p in sent if not p[1])
    rto = None if cut_t is None or rec_t is None else round(rec_t - cut_t, 2)
    step = round((pings[-1][0] - pings[0][0]) / max(1, len(pings) - 1), 2) if len(pings) > 1 else None
    log('  ---- Ket qua ----\n', 'hdr')
    log('    RTO: {}\n'.format('{} s'.format(rto) if rto is not None else 'khong xac dinh'), 'ok' if rto is not None else 'err')
    log('    Goi mat sau CUT: {}/{} | do phan giai ~{} s/goi\n'.format(lost, len(sent), step), 'info')

    base_name = 'failover_{}_{}'.format(wname, datetime.now().strftime('%Y%m%d_%H%M%S'))
    path = os.path.join(LOG_DIR, base_name + '.csv')
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['t_s', 'ping_ok', 'rtt_ms', 'event'])
        for ts, ok, rtt in pings:
            ev = 'CUT' if ts == cut_t else 'RECOVER' if ts == rec_t else ''
            w.writerow([ts, int(ok), '' if rtt is None else round(rtt, 3), ev])
        w.writerow([])
        w.writerow(['t_s', 'bfd_up', 'bfd_total'])
        for row in bfds:
            w.writerow(row)
        w.writerow([])
        w.writerow(['watch', wname, 'probe', sname, 'target', target, 'RTO_s', rto, 'lost', lost, 'sent', len(sent)])
    log('  [OK] CSV: {}\n'.format(path), 'ok')
    if HAS_MPL:
        png = os.path.join(LOG_DIR, base_name + '.png')
        ChartEngine.timeseries_chart([p[0] for p in pings], [p[2] or 0 for p in pings],
                                     [0 if p[1] else 100 for p in pings], cut_t, rec_t,
                                     'Failover {} (nping {} -> {})'.format(wname, sname, target), png)
        log('  [OK] PNG: {}\n'.format(png), 'ok')
    log('=' * 55 + '\n\n', 'sep')


# =========================================================
#  THONG LUONG: bo dem interface vEdge doc qua vManage
# =========================================================
class VManageCounterReader:
    """Cung giao dien VedgeCounterReader (campus_throughput): read() -> (t, {(vpn, if): (rx, tx)}, raw)."""

    def __init__(self, vm, sysip):
        self.vm, self.sysip = vm, sysip

    def read(self):
        rows = self.vm.interfaces(self.sysip)
        t = time.time()
        out = {}
        for r in rows:
            if str(r.get('af-type', 'ipv4')) != 'ipv4':
                continue
            try:
                out[(int(r.get('vpn-id')), r.get('ifname'))] = (int(r.get('rx-octets')), int(r.get('tx-octets')))
            except (TypeError, ValueError):
                pass
        return t, out, json.dumps(rows[:2])[:600]

    def close(self):
        pass


# =========================================================
#  CHINH SACH TAP TRUNG (doc counter + route + whitelist)
# =========================================================
POLICY_COLS = ['timestamp', 'test_id', 'policy', 'check', 'scope', 'value', 'detail', 'result']
REJOIN_TIMEOUT = 150


def _snapshot(vm, edges):
    d = {}
    for e in edges:
        for kind in ('datapolicyfilter', 'approutepolicyfilter'):
            try:
                rows = vm.rows('device/policy/{}?deviceId={}'.format(kind, e))
            except VManageError:
                continue
            for r in rows:
                if r.get('counter-name'):
                    try:
                        d[(e, r.get('policy-name', ''), r['counter-name'])] = int(r.get('packets') or 0)
                    except ValueError:
                        pass
    return d


def policy_job(ctx, vm, opts):
    log, stop = ctx._log, ctx._stop_event
    groups = opts['groups']
    rows = []

    def rec(tid, pol, check, scope, value, detail, ok):
        rows.append({'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'test_id': tid, 'policy': pol,
                     'check': check, 'scope': scope, 'value': value, 'detail': detail,
                     'result': 'PASS' if ok else ('INFO' if ok is None else 'FAIL')})
        log('    [{}] {} {} {} = {} {}\n'.format(rows[-1]['result'], tid, '' if scope in ('-', 'all') else scope,
                                                check, value,
                                             '({})'.format(detail) if detail else ''),
            'ok' if ok else ('info' if ok is None else 'err'))

    log('\n' + '=' * 55 + '\n', 'sep')
    log('[POLICY] Kiem chung chinh sach tap trung (vManage API): {}\n'.format(' '.join(sorted(groups))), 'hdr')

    if 'W' in groups:
        log('  [W] Doi chieu whitelist vManage <-> vBond...\n', 'info')
        valid = {r.get('serialNumber'): r.get('host-name') for r in vm.rows('system/device/vedges')
                 if r.get('validity') == 'valid' and r.get('serialNumber')}
        vbond = next((d.get('system-ip') for d in vm.devices() if d.get('personality') == 'vbond'), None)
        if not vbond:
            rec('W-1', 'whitelist', 'vbond', '-', 0, 'vManage khong thay vBond', False)
        else:
            onbond = {r.get('serial-number') for r in vm.rows('device/orchestrator/validvedges?deviceId=' + vbond)}
            missing = {s: n for s, n in valid.items() if s not in onbond}
            log('      vManage valid={} | vBond co={} | thieu: {}\n'.format(
                len(valid), len(onbond), ', '.join(sorted(str(n) for n in missing.values())) or 'khong'), 'info')
            if not missing:
                rec('W-1', 'whitelist', 'missing', vbond, 0, '', True)
            elif not opts.get('push'):
                rec('W-1', 'whitelist', 'missing', vbond, len(missing), 'bat "Tu day lai" de sua', False)
            else:
                log('  [W] Day whitelist tu vManage (Send to Controllers)...\n', 'info')
                t0 = time.time()
                vm.post('certificate/vedge/list?action=push', {})
                pending = {str(n) for n in missing.values()}
                while pending and time.time() - t0 < REJOIN_TIMEOUT and not stop.is_set():
                    stop.wait(10)
                    up = {d.get('host-name') for d in vm.devices() if d.get('reachability') == 'reachable'}
                    for n in sorted(pending & up):
                        log('      {} reachable sau {:.0f}s\n'.format(n, time.time() - t0), 'ok')
                    pending -= up
                rec('W-1', 'whitelist', 'rejoin_s', vbond, round(time.time() - t0, 1),
                    'chua len: ' + ','.join(sorted(pending)) if pending else '', not pending)

    if 'CP' in groups:
        log('  [CP] Route OMP 10.1.0.0/16 tren vEdge chi nhanh (PREFER-VE1)...\n', 'info')
        for sid in (200, 300, 400):
            for e in sorted(SITE_VEDGES[sid]):
                try:
                    routes = {r.get('originator'): r.get('status', '')
                              for r in vm.rows('device/omp/routes/received?deviceId=' + e)
                              if r.get('prefix') == '10.1.0.0/16'}
                except VManageError as ex:
                    rec('CP-1', 'PREFER-VE1', 'status', VEDGE_NAMES[e], '-', str(ex)[:80], False)
                    continue
                ve1, ve2 = routes.get('10.200.100.1', ''), routes.get('10.200.100.2', '')
                rec('CP-1', 'PREFER-VE1', 'status', VEDGE_NAMES[e], 've1=[{}] ve2=[{}]'.format(ve1 or '-', ve2 or '-'),
                    '', 'C' in ve1 and 'C' not in ve2)

    if 'CNT' in groups and not stop.is_set():
        edges = sorted(ip for sid, d in SITE_VEDGES.items() for ip in d)
        win = opts['window']
        log('  [CNT] Chup counter data-policy / app-route tren {} vEdge, cho {} s...\n'.format(len(edges), win), 'info')
        log('        (trong luc cho, tao traffic THAT tu PC chi nhanh: telnet {} / ssh {} / ping lien site)\n'.format(
            opts['farm'], opts['dmz']), 'info')
        before = _snapshot(vm, edges)
        if not before:
            log('      [!] Khong doc duoc counter nao (vSmart chua day policy?).\n', 'err')
        t0 = time.time()
        while time.time() - t0 < win and not stop.is_set():
            ctx._set_status('Doc counter policy {:.0f}/{}s'.format(time.time() - t0, win), True)
            stop.wait(1)
        after = _snapshot(vm, edges)
        agg = {}
        for k, v in after.items():
            dv = v - before.get(k, 0)
            a = agg.setdefault((k[1], k[2]), [0, []])
            a[0] += max(dv, 0)
            if dv > 0:
                a[1].append('{}+{}'.format(VEDGE_NAMES.get(k[0], k[0]), dv))
        for (pol, cnt), (total, parts) in sorted(agg.items()):
            rec('CNT', pol, cnt, 'all', total, ' '.join(parts), None if total == 0 else True)

    if not rows:
        log('=' * 55 + '\n\n', 'sep')
        return
    path = os.path.join(LOG_DIR, 'policy_{}.csv'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=POLICY_COLS)
        w.writeheader()
        w.writerows(rows)
    log('  [OK] CSV: {}\n'.format(path), 'ok')
    cnt = [r for r in rows if r['test_id'] == 'CNT' and r['value']]
    if HAS_MPL and cnt:
        png = path[:-4] + '.png'
        ChartEngine.bar_chart(['{} {}'.format(r['policy'], r['check']) for r in cnt], [r['value'] for r in cnt],
                              'Counter chinh sach SD-WAN tang trong {} s'.format(opts['window']), 'goi', png,
                              horiz=True, color=GREEN)
        log('  [OK] PNG: {}\n'.format(png), 'ok')
    log('=' * 55 + '\n\n', 'sep')


# =========================================================
#  KIEM CHUNG VLAN / SUBNET MOI (khong cau hinh Core-SW)
# =========================================================
def vlan_verify_job(ctx, vm, opts):
    """Nguoi quan tri tu tao VLAN/SVI tren Core-SW. Tool tu cac vEdge chi nhanh:
    (1) xem OMP co route phu subnet do khong, (2) nping toi gateway moi theo chu ky cho den
    khi thong -> thoi gian hoi tu, (3) traceroute de thay duong di qua vEdge."""
    log, stop = ctx._log, ctx._stop_event
    net, gw = opts['net'], opts['gw']
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[VLAN] Kiem chung subnet {} (gateway {}) tu cac chi nhanh\n'.format(net, gw), 'hdr')
    home = site_of_ip(gw)
    srcs = [ip for sid in opts['sites'] for ip in site_vedges(sid, vm)[:1]]
    if not srcs:
        log('  [!] Khong co vEdge nguon.\n', 'err')
        return
    rows = []
    for e in srcs:
        name = VEDGE_NAMES.get(e, e)
        try:
            cover = []
            for r in vm.rows('device/omp/routes/received?deviceId=' + e):
                try:
                    p = ipaddress.ip_network(r.get('prefix', ''), strict=False)
                except ValueError:
                    continue
                if net.subnet_of(p) and 'C' in str(r.get('status', '')):
                    cover.append((p.prefixlen, str(p), VEDGE_NAMES.get(r.get('originator'), r.get('originator'))))
            cover.sort(reverse=True)
            if cover:
                log('  [OMP] {}: route {} tu {}\n'.format(name, cover[0][1], ', '.join(sorted({c[2] for c in cover
                    if c[1] == cover[0][1]}))), 'ok')
            else:
                log('  [OMP] {}: KHONG co route OMP nao phu {}\n'.format(name, net), 'err')
            rows.append({'vedge': name, 'omp': cover[0][1] if cover else '', 'reach_s': None})
        except VManageError as ex:
            log('  [OMP] {}: loi {}\n'.format(name, ex), 'err')
            rows.append({'vedge': name, 'omp': '', 'reach_s': None})
    log('  [*] Ping {} tu {} moi {} s, toi da {} s (tao VLAN tren Core-SW ngay bay gio neu chua tao)...\n'.format(
        gw, ', '.join(r['vedge'] for r in rows), opts['interval'], opts['timeout']), 'info')
    t0 = time.time()
    pending = dict(zip(srcs, rows))
    while pending and time.time() - t0 < opts['timeout'] and not stop.is_set():
        for e, row in list(pending.items()):
            try:
                r = vedge_ping(vm, e, gw, 2)
            except VManageError as ex:
                log('    {} loi: {}\n'.format(row['vedge'], str(ex)[:100]), 'err')
                continue
            if r.success:
                row['reach_s'] = round(time.time() - t0, 1)
                row['rtt'] = round(r.avg_latency, 2)
                log('    {} -> {} THONG sau {} s ({:.2f} ms)\n'.format(row['vedge'], gw, row['reach_s'], r.avg_latency), 'ok')
                pending.pop(e)
        ctx._set_status('Kiem chung VLAN {:.0f}/{}s'.format(time.time() - t0, opts['timeout']), True)
        if pending:
            stop.wait(opts['interval'])
    for e, row in pending.items():
        log('    {} -> {} CHUA THONG sau {} s\n'.format(row['vedge'], gw, opts['timeout']), 'err')
    if opts.get('trace') and srcs and not stop.is_set():
        e = srcs[0]
        log('  [TRACE] {} -> {}\n'.format(VEDGE_NAMES.get(e, e), gw), 'info')
        try:
            for l in vedge_traceroute(vm, e, gw):
                log('      {}\n'.format(l), 'data')
        except VManageError as ex:
            log('      loi: {}\n'.format(ex), 'err')
    path = os.path.join(LOG_DIR, 'vlan_verify.csv')
    new = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['timestamp', 'subnet', 'gateway', 'home_site', 'vedge', 'omp_route', 'reach_s', 'rtt_ms'])
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for row in rows:
            w.writerow([ts, str(net), gw, home, row['vedge'], row['omp'],
                        '' if row['reach_s'] is None else row['reach_s'], row.get('rtt', '')])
    log('  [OK] CSV: {}\n'.format(path), 'ok')
    log('=' * 55 + '\n\n', 'sep')
