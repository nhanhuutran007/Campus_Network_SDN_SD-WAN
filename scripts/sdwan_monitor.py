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
Ping "tu may chay web" thi chay lenh ping cua chinh may do toi IP thiet bi.

Cac tab chi DO / KIEM CHUNG, khong sua cau hinh thiet bi.
"""
import csv, json, os, re, ssl, threading, time
import http.cookiejar, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from campus_ping_tool import (
    HOST_IP, SITE_VEDGES, SITES, WAN_IFACE, LOG_DIR, HAS_MPL,
    PingResult, ChartEngine, ping_host, site_of_ip, CYAN, PURPLE, RED, YELLOW, GREEN, ORANGE,
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

    def _request(self, path, body=None, timeout=None, retry=True, method=None, busy=0):
        if self._op is None:
            self.login()
        headers = {'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
            if self._token:
                headers['X-XSRF-TOKEN'] = self._token
        req = urllib.request.Request(self.base + '/dataservice/' + path.lstrip('/'), data=data, headers=headers,
                                     method=method)
        try:
            raw = self._op.open(req, timeout=timeout or self.timeout).read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and retry:
                self.login()
                return self._request(path, body, timeout, False, method)
            if e.code in (502, 503, 504) and body is None and method is None and busy < 3:
                time.sleep(5)                       # vManage ban tam thoi (host lab tai cao) -> GET thu lai
                return self._request(path, body, timeout, retry, method, busy + 1)
            msg = e.read().decode('utf-8', 'replace')
            if '<html' in msg.lower():              # trang loi HTML cua vManage -> chi giu <title>
                t = re.search(r'<title>(.*?)</title>', msg, re.S | re.I)
                msg = '(trang HTML{}){}'.format(': ' + t.group(1).strip() if t else '',
                                                ' - vManage dang qua tai / khoi dong lai dich vu'
                                                if e.code in (502, 503, 504) else '')
            else:                                   # {"error":{"message":..,"details":..}} -> doc duoc ngay
                try:
                    err = json.loads(msg).get('error') or {}
                    msg = ' - '.join(str(err[k]) for k in ('message', 'details') if err.get(k)) or msg
                except (ValueError, AttributeError):
                    pass
            msg = msg[:300]
            raise VManageError('vManage {} {}: HTTP {} {}'.format(method or ('POST' if body is not None else 'GET'),
                                                                 path, e.code, msg))
        except (urllib.error.URLError, OSError) as e:
            raise VManageError('vManage {}: {}'.format(path, getattr(e, 'reason', e)))
        if raw.lstrip().startswith('<'):           # het phien -> trang login
            if retry:
                self.login()
                return self._request(path, body, timeout, False, method)
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

    def put(self, path, body=None, timeout=None):
        return self._request(path, body if body is not None else {}, timeout, method='PUT')

    # ---- tien ich hay dung ----
    def devices(self):
        return self.rows('device')

    def vedges(self):
        return [d for d in self.devices() if d.get('personality') == 'vedge' or d.get('device-type') == 'vedge']

    def bfd(self, sysip, timeout=None):
        return self.rows('device/bfd/sessions?deviceId=' + sysip, timeout)

    def control(self, sysip, timeout=None):
        return self.rows('device/control/connections?deviceId=' + sysip, timeout)

    def interfaces(self, sysip):
        return self.rows('device/interface?deviceId=' + sysip)


# =========================================================
#  PING / TRACEROUTE TU vEDGE (vManage Troubleshooting tools)
# =========================================================
_SRC_CACHE = {}


def lan_sources(vm, sysip, vpn=1):
    """Moi interface vpn `vpn` co IP cua vEdge, xep uu tien (up, ge*, khong phai loopback)
    -> [(ifname, ip)]. Phan tu dau la nguon mac dinh cho nping."""
    key = (vm.host, sysip, vpn)
    if key in _SRC_CACHE:
        return _SRC_CACHE[key]
    found = {}
    for r in vm.interfaces(sysip):
        if str(r.get('vpn-id')) != str(vpn):
            continue
        ip = str(r.get('ip-address', '')).split('/')[0]
        if not ip or ip.startswith('0.') or ip == '-':
            continue
        up = str(r.get('if-oper-status', '')).lower() == 'up'
        name = r.get('ifname', '')
        score = (up, name.startswith('ge'), not name.startswith('loopback'))
        if name not in found or score > found[name][0]:
            found[name] = (score, name, ip)
    if not found:
        raise VManageError('{} khong co interface vpn {} co IP'.format(VEDGE_NAMES.get(sysip, sysip), vpn))
    _SRC_CACHE[key] = [(n, ip) for _, n, ip in sorted(found.values(), key=lambda x: (x[0], x[1]), reverse=True)]
    return _SRC_CACHE[key]


def lan_source(vm, sysip, vpn=1):
    """Interface LAN (vpn 1) dang up co IP cua vEdge -> (ifname, ip). Lam nguon cho nping de
    goi tin di dung duong du lieu that (vpn 1 -> overlay -> site dich)."""
    return lan_sources(vm, sysip, vpn)[0]


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


NPING_STYLES = [
    {'size': '64', 'df': 'false', 'rapid': 'false'},
    {'df': 'false', 'rapid': 'false'},
    {'size': '64'},
    {},
]
_NPING_STYLE = None     # chi so kieu body nping vManage da chap nhan


def vedge_ping(vm, sysip, dst, count=5, vpn=1, source=None, probe='icmp', port=None, size=None):
    """vEdge `sysip` ping `dst` trong VPN `vpn` (mac dinh nguon = interface LAN vpn 1)."""
    if source is None:
        source = lan_source(vm, sysip, vpn)[0] if str(vpn) != '0' else ''
    global _NPING_STYLE
    base = {'host': dst, 'vpn': str(vpn), 'source': source, 'probeType': probe, 'count': str(count)}
    if port:
        base['destPort'] = str(port)
    # 20.10 tra HTTP 400 "Invalid data length value" voi size '' -> thu lan luot cac kieu body,
    # nho kieu chay duoc de cac lan ping sau (do RTO) chi goi 1 lan
    styles = [{'size': str(size)}] if size else NPING_STYLES
    order = list(range(len(styles)))
    if not size and _NPING_STYLE is not None:
        order.remove(_NPING_STYLE)
        order.insert(0, _NPING_STYLE)
    tried = []
    for i in order:
        body = dict(base, **styles[i])
        try:
            resp = vm.post('device/tools/nping/' + sysip, body, timeout=count * 3 + 30)
        except VManageError as e:
            if 'data length' not in str(e).lower():
                raise
            tried.append(json.dumps(body))
            continue
        if not size:
            _NPING_STYLE = i
        break
    else:
        raise VManageError('nping: vManage tu choi moi kieu body ("Invalid data length value"). Da gui: '
                           + ' | '.join(tried))
    r = parse_nping(resp if isinstance(resp, dict) else {}, count)
    r.raw = '[vManage nping {} vpn {} src {}] -> {}\n{}'.format(
        VEDGE_NAMES.get(sysip, sysip), vpn, source or '-', dst, r.raw)
    return r


def vedge_ping_any(vm, sysip, dst, count=5, vpn=1):
    """Nhu vedge_ping nhung mat het goi thi thu lan luot cac interface vpn 1 khac lam nguon
    (vd ge0/0 phia FW, ge0/3 phia vEdge cung site) -> (PingResult, interface da dung, cac nguon
    da thu) - PingResult co __slots__ nen khong gan them thuoc tinh."""
    r, src, tried = None, '', []
    srcs = lan_sources(vm, sysip, vpn)
    for ifname, ip in srcs:
        r, src = vedge_ping(vm, sysip, dst, count, vpn, source=ifname), ifname
        tried.append('{}({})'.format(ifname, ip))
        if r.success:
            return r, src, tried
        time.sleep(TOOL_GAP)
    # 25/10/2026: nping cua vManage (ca ICMP lan UDP) toi LAN CUNG site mat 100% o moi site,
    # trong khi `ping vpn 1 source ge0/0 10.2.60.100` tren console vEdge1-S200 OK 4/4 va
    # traceroute OK -> loi o cong cu nping, khong phai mang. Du phong: API traceroute, lay RTT
    # 3 probe cua hop co IP = dich (RTT traceroute UDP thuong cao hon ping ICMP).
    try:
        t = traceroute_probe(vm, sysip, dst, count, vpn)
        tried.append('traceroute')
        if t.success:
            return t, '{} (traceroute)'.format(srcs[0][0]), tried
    except VManageError as e:
        tried.append('traceroute loi: {}'.format(str(e)[:60]))
    return r, src, tried


def traceroute_probe(vm, sysip, dst, count=6, vpn=1):
    """Do RTT/loss toi `dst` bang API traceroute: moi lan chay cho 3 probe o hop cuoi; chay
    toi khi du >= count probe. Probe '*' o hop dich = mat goi."""
    rtts, sent = [], 0
    raw = []
    hop = re.compile(r'^\s*\d+\s+(.*)$')
    while sent < count:
        lines = vedge_traceroute(vm, sysip, dst, vpn)
        raw += lines
        last = [hop.match(l).group(1) for l in lines if hop.match(l)]
        if not last:
            break
        tail = last[-1]
        times = [float(x) for x in re.findall(r'([\d.]+)\s*ms', tail)] if dst in tail else []
        probes = 3
        sent += probes
        rtts += times[:probes]
        time.sleep(TOOL_GAP)
    r = PingResult()
    r.raw = '[vManage traceroute {} vpn {}] -> {}\n{}'.format(VEDGE_NAMES.get(sysip, sysip), vpn, dst,
                                                                '\n'.join(raw[-6:]))
    if not sent:
        return r
    r.loss = round((sent - len(rtts)) / sent * 100, 2)
    if rtts:
        r.success = True
        r.avg_latency = sum(rtts) / len(rtts)
        r.min_latency, r.max_latency = min(rtts), max(rtts)
        r.jitter = round(sum(abs(a - b) for a, b in zip(rtts[1:], rtts)) / (len(rtts) - 1), 3) if len(rtts) > 1 else 0.0
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


# =========================================================
#  SO SANH CAMPUS CHINH - CHI NHANH: Delay / Jitter / Packet Loss / Throughput
#  Moi site do 2 loai duong (nguon = vEdge cua site, vpn 1):
#    LAN : vEdge -> host cung site (chat luong mang noi bo)
#    WAN : chi nhanh -> Campus chinh, Campus chinh -> chi nhanh (qua overlay SD-WAN)
#  Throughput: doc bo dem cong WAN (vpn 0) moi vEdge cua tung site cung luc, theo chu ky.
# =========================================================
LAN_ROUTES = [(100, 'PC-CNTT-S100-1'), (100, 'PC-TTK-S100-1'), (100, 'PC-Luat-S100-1'),
              (100, 'WebServer'), (100, 'DHCP-Server'),
              (200, 'PC-NongNghiep-S200-1'), (200, 'PC-YTe-S200'),
              (300, 'PC-DuLich-S300-1'), (300, 'PC-TaiChinh-S300'),
              (400, 'PC-ThuySan-S400-1'), (400, 'PC-LuHanh-S400')]
WAN_ROUTES = [(100, 'PC-NongNghiep-S200-1'), (100, 'PC-TaiChinh-S300'), (100, 'PC-LuHanh-S400-2'),
              (200, 'PC-CNTT-S100-1'), (200, 'WebServer'),
              (300, 'PC-CNTT-S100-1'), (300, 'WebServer'),
              (400, 'PC-CNTT-S100-1'), (400, 'WebServer')]
SITE_IDS = sorted(SITE_VEDGES)
SITE_LABEL = {sd['site_id']: 'S{} {}'.format(sd['site_id'], sn.split(' - ', 1)[-1]) for sn, sd in SITES.items()}
CASE_NAMES = ['Delay (Avg RTT) - Campus chinh vs chi nhanh',
              'Jitter - Campus chinh vs chi nhanh',
              'Packet Loss - Campus chinh vs chi nhanh',
              'Throughput WAN - Campus chinh vs chi nhanh',
              'Tong hop 4 tieu chi (dashboard PNG + CSV)']
# nguong danh gia (giong chu thich tren web): (tot, trung binh)
GRADE = {'delay': (50, 150), 'jitter': (10, 30), 'loss': (0, 5)}
METRIC = {'delay': ('Delay (Avg RTT)', 'ms'), 'jitter': ('Jitter', 'ms'), 'loss': ('Packet Loss', '%')}


def _run_routes(ctx, vm, routes, count, kind):
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
        # tuyen chet: latency/jitter = None (khong phai 0 ms), ly do ghi vao 'note'
        row = {'site': sid, 'kind': kind, 'label': label, 'src': VEDGE_NAMES.get(src, ''), 'src_if': '',
               'dst': ip, 'latency': None, 'loss': 100.0, 'jitter': None, 'min': None, 'max': None, 'note': ''}
        try:
            if src is None:
                raise VManageError('site {} khong co vEdge reachable'.format(sid))
            r, row['src_if'], tried = vedge_ping_any(vm, src, ip, count)
            if r.success:
                row.update(latency=r.avg_latency, loss=r.loss, jitter=r.jitter, min=r.min_latency, max=r.max_latency)
                ctx._log('  OK   {} {:<38} Lat={:7.2f}ms Loss={:5.1f}% Jitter={:6.2f}ms (src {})\n'.format(
                    kind, label, r.avg_latency, r.loss, r.jitter, row['src_if']), 'ok')
            else:
                row['note'] = 'mat het goi, da thu nguon ' + ', '.join(tried)
                ctx._log('  FAIL {} {:<38} ({}) khong phan hoi - {}\n'.format(kind, label, ip, row['note']), 'err')
                for l in [l for l in r.raw.strip().splitlines() if l.strip()][-3:]:
                    ctx._log('         {}\n'.format(l.strip()[:120]), 'data')
        except Exception as e:
            row['note'] = str(e)[:150]
            ctx._log('  FAIL {} {:<38} {}\n'.format(kind, label, e), 'err')
        data.append(row)
        time.sleep(TOOL_GAP)
    return data


def _mean(v):
    return sum(v) / len(v) if v else None


def site_summary(rows):
    """{site: {'LAN'|'WAN': {'delay','jitter','loss','ok','n'}}}. Delay/jitter chi tinh tuyen
    co tra loi; loss tinh tren moi tuyen (tuyen chet = 100%)."""
    out = {}
    for sid in SITE_IDS:
        out[sid] = {}
        for kind in ('LAN', 'WAN'):
            rs = [r for r in rows if r['site'] == sid and r['kind'] == kind]
            ok = [r for r in rs if r['loss'] < 100]
            out[sid][kind] = {'delay': _mean([r['latency'] for r in ok]), 'jitter': _mean([r['jitter'] for r in ok]),
                              'loss': _mean([r['loss'] for r in rs]), 'ok': len(ok), 'n': len(rs)}
    return out


def _grade_val(metric, v):
    if v is None:
        return 'KHONG DO DUOC', 'err'
    good, mid = GRADE[metric]
    if (v <= good) if metric == 'loss' else (v < good):
        return 'TOT', 'ok'
    return ('TRUNG BINH', 'info') if v < mid else ('KEM', 'err')


def _fmt(v, nd=2):
    return '--' if v is None else '{:.{}f}'.format(v, nd)


def _log_compare(log, summ, metric):
    name, unit = METRIC[metric]
    log('  {} ({}) theo site - LAN noi bo / WAN qua SD-WAN, chenh lech WAN so voi Campus chinh:\n'.format(name, unit), 'hdr')
    log('  {:<22} {:>9} {:>9} {:>12}  {}\n'.format('Site', 'LAN', 'WAN', 'WAN-vs-S100', 'Danh gia WAN'), 'data')
    base = summ[100]['WAN'][metric]
    for sid in SITE_IDS:
        lan, wan = summ[sid]['LAN'][metric], summ[sid]['WAN'][metric]
        diff = '' if sid == 100 or wan is None or base is None else '{:+.2f}'.format(wan - base)
        g, tag = _grade_val(metric, wan)
        log('  {:<22} {:>9} {:>9} {:>12}  {} ({}/{} tuyen)\n'.format(
            SITE_LABEL[sid], _fmt(lan), _fmt(wan), diff, g, summ[sid]['WAN']['ok'], summ[sid]['WAN']['n']), tag)


def _wan_keys(sysip, counters):
    names = set(WAN_IFACE.get(VEDGE_NAMES.get(sysip, ''), {}).values())
    return [k for k in counters if k[0] == 0 and (k[1] in names if names else str(k[1]).startswith('ge'))]


def site_throughput(ctx, vm, window, interval):
    """Doc bo dem cong WAN (vpn 0) cua moi vEdge reachable cung luc moi `interval` s trong
    `window` s -> Mbps RX/TX cua tung site (tong cac vEdge). Chi do traffic DANG chay."""
    log, stop = ctx._log, ctx._stop_event
    reach = {d.get('system-ip') for d in vm.vedges() if d.get('reachability') == 'reachable'}
    edges = {sid: [ip for ip in SITE_VEDGES[sid] if ip in reach] for sid in SITE_IDS}
    readers = {ip: VManageCounterReader(vm, ip) for ips in edges.values() for ip in ips}
    for sid in SITE_IDS:
        if not edges[sid]:
            log('  [!] {}: khong co vEdge reachable - bo qua throughput\n'.format(SITE_LABEL[sid]), 'err')

    def safe(ip):
        try:
            t, c, _ = readers[ip].read()
            return t, c
        except Exception as e:
            log('  [!] doc bo dem {}: {}\n'.format(VEDGE_NAMES.get(ip, ip), str(e)[:100]), 'err')
            return None

    def read_all():
        if not readers:
            return {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            return dict(zip(readers, ex.map(safe, readers)))

    samples = {sid: [] for sid in SITE_IDS}
    prev = {ip: v for ip, v in read_all().items() if v}
    t0 = time.time()
    log('  Lay mau moi {}s trong {}s (Mbps = delta octet x 8 / delta t, cong WAN vpn 0)\n'.format(interval, window), 'info')
    while readers and time.time() - t0 < window and not stop.is_set():
        stop.wait(interval)
        cur = {ip: v for ip, v in read_all().items() if v}
        parts = []
        for sid in SITE_IDS:
            rx = tx = 0.0
            got = False
            for ip in edges[sid]:
                a, b = prev.get(ip), cur.get(ip)
                if not a or not b or b[0] <= a[0]:
                    continue
                dt = b[0] - a[0]
                for k in _wan_keys(ip, b[1]):
                    if k not in a[1]:
                        continue
                    drx, dtx = b[1][k][0] - a[1][k][0], b[1][k][1] - a[1][k][1]
                    if drx < 0 or dtx < 0:          # vEdge reboot / bo dem reset
                        continue
                    rx += drx * 8 / dt / 1e6
                    tx += dtx * 8 / dt / 1e6
                    got = True
            if got:
                samples[sid].append((rx, tx))
                parts.append('S{} {:.3f}/{:.3f}'.format(sid, rx, tx))
        log('  +{:>4.0f}s  RX/TX Mbps: {}\n'.format(time.time() - t0, '  '.join(parts) or '(chua co mau)'), 'data')
        prev.update(cur)
    out = {}
    for sid in SITE_IDS:
        s = samples[sid]
        out[sid] = {'rx': _mean([x[0] for x in s]), 'tx': _mean([x[1] for x in s]),
                    'peak': max((x[0] + x[1] for x in s), default=None), 'n': len(s), 'edges': len(edges[sid])}
    return out


def _log_throughput(log, tp):
    log('  Luu luong WAN thuc te theo site (Mbps, trung binh cua cac mau):\n', 'hdr')
    log('  {:<22} {:>9} {:>9} {:>9} {:>8}\n'.format('Site', 'RX TB', 'TX TB', 'Dinh', 'Mau'), 'data')
    for sid in SITE_IDS:
        t = tp[sid]
        log('  {:<22} {:>9} {:>9} {:>9} {:>8}\n'.format(SITE_LABEL[sid], _fmt(t['rx'], 3), _fmt(t['tx'], 3),
                                                       _fmt(t['peak'], 3), t['n']), 'ok' if t['n'] else 'err')
    log('  (Day la luu luong DANG chay luc do - khong bom tai thi chi la traffic nen BFD/OMP/control, KHONG phai\n'
        '   throughput/nang luc duong truyen. Muon do throughput: chay iperf/tai cung muc o moi site trong luc do.)\n',
        'info')


def _grouped(ax, series, title, ylabel, colors):
    """Cot nhom theo site: series = [(ten, [gia tri theo SITE_IDS])]."""
    ChartEngine._dark(ax, title)
    n, w = len(series), 0.8 / len(series)
    for i, (name, vals) in enumerate(series):
        xs = [k + (i - (n - 1) / 2) * w for k in range(len(SITE_IDS))]
        bars = ax.bar(xs, [v or 0 for v in vals], w, label=name, color=colors[i],
                      edgecolor=ChartEngine.EDGE, linewidth=0.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), 'n/a' if v is None else '{:.2f}'.format(v),
                    ha='center', va='bottom', color=ChartEngine.TXT, fontsize=7)
    ax.set_xticks(range(len(SITE_IDS)))
    ax.set_xticklabels([SITE_LABEL[s] for s in SITE_IDS], color=ChartEngine.TXT, fontsize=8)
    ax.set_ylabel(ylabel, color=ChartEngine.TXT)
    ax.legend(facecolor=ChartEngine.BG_DARK2, edgecolor=ChartEngine.EDGE, labelcolor=ChartEngine.TXT, fontsize=8)


def _metric_series(summ, metric):
    return [('LAN noi bo', [summ[s]['LAN'][metric] for s in SITE_IDS]),
            ('WAN qua SD-WAN', [summ[s]['WAN'][metric] for s in SITE_IDS])]


def _tp_series(tp):
    return [('RX', [tp[s]['rx'] for s in SITE_IDS]), ('TX', [tp[s]['tx'] for s in SITE_IDS])]


def _save_png(path, draw, size=(10, 5)):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=size)
    fig.patch.set_facecolor(ChartEngine.BG_DARK)
    draw(fig)
    plt.tight_layout()
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close('all')


def _save_compare_csv(ctx, name, summ=None, tp=None, routes=None):
    path = os.path.join(LOG_DIR, name + '.csv')
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    r = lambda v, nd=3: '' if v is None else round(v, nd)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Site', 'Ten', 'Delay_LAN_ms', 'Delay_WAN_ms', 'Jitter_LAN_ms', 'Jitter_WAN_ms',
                    'Loss_LAN_pct', 'Loss_WAN_pct', 'Tuyen_LAN_ok', 'Tuyen_WAN_ok', 'Thr_RX_Mbps', 'Thr_TX_Mbps',
                    'Thr_Dinh_Mbps', 'Thoi_gian'])
        for sid in SITE_IDS:
            s = summ[sid] if summ else None
            t = tp[sid] if tp else None
            w.writerow([sid, SITE_LABEL[sid]] +
                       ([r(s['LAN']['delay']), r(s['WAN']['delay']), r(s['LAN']['jitter']), r(s['WAN']['jitter']),
                         r(s['LAN']['loss'], 2), r(s['WAN']['loss'], 2), '{}/{}'.format(s['LAN']['ok'], s['LAN']['n']),
                         '{}/{}'.format(s['WAN']['ok'], s['WAN']['n'])]
                        if s else [''] * 8) +
                       ([r(t['rx']), r(t['tx']), r(t['peak'])] if t else [''] * 3) + [ts])
        if routes:
            w.writerow([])
            w.writerow(['Site', 'Loai', 'Tuyen_Duong', 'Nguon_vEdge', 'Nguon_IF', 'Dich_IP', 'Avg_Latency_ms',
                        'Loss_pct', 'Jitter_ms', 'Min_RTT_ms', 'Max_RTT_ms', 'Ghi_chu'])
            for x in routes:
                w.writerow([x['site'], x['kind'], x['label'], x['src'], x.get('src_if', ''), x['dst'],
                            r(x['latency']), r(x['loss'], 2), r(x['jitter']), r(x['min']), r(x['max']),
                            x.get('note', '')])
    ctx._log('  [OK] CSV: {}\n'.format(path), 'ok')


def cases_job(ctx, vm, cases, count, tp_window=60, tp_interval=10):
    log = ctx._log
    ctx._set_status('So sanh site - cases {}...'.format(cases), True)
    log('\n' + '=' * 55 + '\n', 'sep')
    log('SO SANH CAMPUS CHINH - CHI NHANH (vManage API) - Cases: {}\n'.format(cases), 'hdr')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    cache = {}

    def ping_rows():
        if 'rows' not in cache:
            log('  Do ping LAN + WAN ({} goi/tuyen)...\n'.format(count), 'info')
            cache['rows'] = _run_routes(ctx, vm, LAN_ROUTES, count, 'LAN') + \
                _run_routes(ctx, vm, WAN_ROUTES, count, 'WAN')
            cache['summ'] = site_summary(cache['rows'])
        return cache['rows'], cache['summ']

    def throughput():
        if 'tp' not in cache:
            ctx._set_status('Do throughput WAN cac site ({}s)...'.format(tp_window), True)
            cache['tp'] = site_throughput(ctx, vm, tp_window, tp_interval)
        return cache['tp']

    colors_m, colors_t = (CYAN, PURPLE), (GREEN, ORANGE)
    for c in cases:
        if ctx._stop_event.is_set():
            log('  [i] Dung theo yeu cau.\n', 'info')
            break
        log('\n' + '-' * 40 + '\nCase {} - {}\n'.format(c, CASE_NAMES[c - 1]), 'info')
        try:
            if c in (1, 2, 3):
                metric = ('delay', 'jitter', 'loss')[c - 1]
                rows, summ = ping_rows()
                _log_compare(log, summ, metric)
                name, unit = METRIC[metric]
                fname = 'so_sanh_{}_{}'.format(metric, stamp)
                if HAS_MPL:
                    _save_png(os.path.join(LOG_DIR, fname + '.png'), lambda fig: _grouped(
                        fig.add_subplot(111), _metric_series(summ, metric),
                        'Case {} - {} theo site: Campus chinh vs chi nhanh'.format(c, name), unit, colors_m))
                    log('  [OK] PNG: {}.png\n'.format(fname), 'ok')
                _save_compare_csv(ctx, fname, summ=summ, routes=rows)
            elif c == 4:
                tp = throughput()
                _log_throughput(log, tp)
                fname = 'so_sanh_throughput_{}'.format(stamp)
                if HAS_MPL:
                    _save_png(os.path.join(LOG_DIR, fname + '.png'), lambda fig: _grouped(
                        fig.add_subplot(111), _tp_series(tp),
                        'Case 4 - Luu luong WAN thuc te theo site (Mbps, {}s, khong bom tai)'.format(tp_window), 'Mbps', colors_t))
                    log('  [OK] PNG: {}.png\n'.format(fname), 'ok')
                _save_compare_csv(ctx, fname, tp=tp)
            else:
                rows, summ = ping_rows()
                tp = throughput()
                for m in ('delay', 'jitter', 'loss'):
                    _log_compare(log, summ, m)
                _log_throughput(log, tp)
                fname = 'so_sanh_tong_hop_{}'.format(stamp)
                if HAS_MPL:
                    def draw(fig):
                        fig.suptitle('SO SANH CAMPUS CHINH - CHI NHANH: Delay / Jitter / Packet Loss / Throughput',
                                     color=CYAN, fontsize=13, fontweight='bold')
                        for i, m in enumerate(('delay', 'jitter', 'loss')):
                            _grouped(fig.add_subplot(2, 2, i + 1), _metric_series(summ, m),
                                     '{} ({})'.format(*METRIC[m]), METRIC[m][1], colors_m)
                        _grouped(fig.add_subplot(2, 2, 4), _tp_series(tp),
                                 'Luu luong WAN thuc te (Mbps, {}s, khong bom tai)'.format(tp_window), 'Mbps', colors_t)
                    _save_png(os.path.join(LOG_DIR, fname + '.png'), draw, size=(16, 10))
                    log('  [OK] PNG: {}.png\n'.format(fname), 'ok')
                _save_compare_csv(ctx, fname, summ=summ, tp=tp, routes=rows)
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


OVERVIEW_RT_TIMEOUT = 20   # moi lenh realtime (vManage hoi vEdge qua NETCONF) - vEdge treo khong giu ca bang


def overview(vm, quick=False):
    """Danh sach thiet bi + so phien BFD/control cua tung vEdge (goi song song).
    quick=True: chi /device (nhanh) de web ve bang ngay, BFD/control dien sau."""
    devs = vm.devices()
    out = []
    for d in devs:
        out.append({'host': d.get('host-name', ''), 'sysip': d.get('system-ip', ''),
                    'type': d.get('personality') or d.get('device-type', ''),
                    'site': d.get('site-id', ''), 'reach': d.get('reachability', ''),
                    'version': d.get('version', ''), 'uptime': _uptime(d),
                    'bfd_up': None, 'bfd_total': None, 'ctrl_up': None})
    edges = [] if quick else [o for o in out if o['type'] == 'vedge' and o['reach'] == 'reachable']

    def fill(o):
        try:
            b = vm.bfd(o['sysip'], OVERVIEW_RT_TIMEOUT)
            o['bfd_total'] = len(b)
            o['bfd_up'] = sum(1 for s in b if s.get('state') == 'up')
            c = vm.control(o['sysip'], OVERVIEW_RT_TIMEOUT)
            o['ctrl_up'] = sum(1 for s in c if s.get('state') == 'up')
        except Exception as e:
            o['error'] = str(e)[:120]
    with ThreadPoolExecutor(max_workers=8) as ex:
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
AFTER_RECOVER_S = 4     # sau RECOVER chi theo doi them chung nay giay roi dung (khong cho het duration)


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

    try:
        base = vm.bfd(watch)
    except VManageError as e:
        if 'not connected' not in str(e).lower():
            raise
        log('  [!] {} dang mat ket noi vManage TRUOC khi test (link con bi cat tu lan truoc?). '
            'no shutdown cong WAN, cho control connection len lai roi chay lai.\n'.format(wname), 'err')
        return
    up0 =sum(1 for s in base if s.get('state') == 'up')
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
                if rec_t is not None and now - rec_t >= AFTER_RECOVER_S:
                    log('  [i] Da thong lai, theo doi them {} s on dinh -> ket thuc som.\n'.format(
                        AFTER_RECOVER_S), 'info')
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
    # PRR tinh trong cua so co dinh [CUT, RECOVER + AFTER_RECOVER_S] -> khong phu thuoc do dai
    # lan do (truoc day tinh toi luc dung -> do cang lau PRR cang cao, khong so sanh duoc)
    win_end = rec_t + AFTER_RECOVER_S if rec_t is not None else float('inf')
    sent = [p for p in pings if (cut_t is None or p[0] >= cut_t) and p[0] <= win_end]
    lost = sum(1 for p in sent if not p[1])
    rto = None if cut_t is None or rec_t is None else round(rec_t - cut_t, 2)
    step = round((pings[-1][0] - pings[0][0]) / max(1, len(pings) - 1), 2) if len(pings) > 1 else None
    log('  ---- Ket qua ----\n', 'hdr')
    log('    RTO: {}\n'.format('{} s'.format(rto) if rto is not None else 'khong xac dinh'), 'ok' if rto is not None else 'err')
    prr = round((len(sent) - lost) / len(sent) * 100, 2) if sent else None
    log('    Goi mat trong cua so CUT -> RECOVER+{}s: {}/{} | do phan giai ~{} s/goi (sai so RTO +-{} s)\n'.format(
        AFTER_RECOVER_S, lost, len(sent), step, step), 'info')
    log('    Packet Recovery Rate: {}\n'.format('{} %'.format(prr) if prr is not None else '--'),
        'ok' if prr == 100 else 'info')

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
        w.writerow(['watch', wname, 'probe', sname, 'target', target, 'RTO_s', rto, 'lost', lost, 'sent', len(sent),
                    'PRR_pct', prr, 'step_s', step, 'prr_after_recover_s', AFTER_RECOVER_S])
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
