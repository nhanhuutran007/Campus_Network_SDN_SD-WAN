# =====================================================================
#  campus_noc_monitor.py - Campus SDN Console (Ryu / OpenFlow 1.3)
#  Do an: Campus Network ket hop SDN + SD-WAN (EVE-NG)
#  Phien ban 2 (10/2026): giao dien TAP TRUNG cho do dac & danh gia SDN
#  campus chinh (Site 100). Lien site do SD-WAN dam nhiem.
#
#  Muc tieu danh gia (de bai) -> tab giao dien:
#     Tong quan    : KPI, bang thong tong, su kien moi
#     Topology     : do thi lien ket, cay du lieu, mo phong cat lien ket
#     Khoi phuc    : thoi gian hoi tu (controller) + mat goi (ping lien tuc)
#     Luu luong    : bang thong/% su dung tung cong (PortStats)
#     VLAN, Chinh sach, Tai thiet bi, Hieu nang: cac giai doan tiep theo
#
#  Khong dung CDN (VLAN 99 khong ra Internet): bieu do ve bang canvas.
#  Du lieu dieu khien lay truc tiep tu app CampusSwitch13 (cung tien trinh).
#
#  Truy cap: http://10.1.99.10:8080/   (PC-Management VLAN 99)
#  REST:
#     GET  /noc/switches|ports|congestion|topology|summary|history  (giu nhu cu)
#     GET  /campus/topology            do thi + cay + trang thai lien ket
#     GET  /campus/events?since=N      su kien (co thoi gian hoi tu)
#     POST /campus/linktest            {"link":"A1-D1","action":"down|up","mode":"silent|admin"}
#     GET  /campus/pinger              thong ke ping lien tuc
#     POST /campus/pinger              {"target":"10.1.40.102","action":"start|stop|reset","interval":0.2}
#     GET  /campus/export/events.csv   |  /campus/export/pinger.csv?target=IP
# =====================================================================

import json
import os
import random
import socket
import struct
import time
import collections

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
# Ban Ryu tren controller la phien ban cu -> WSGI nam o ryu.app.wsgi
from ryu.app.wsgi import WSGIApplication, ControllerBase, Response

SWITCH_INFO = {
    5:  {'name': 'Dist-SW1',  'role': 'Distribution'},
    8:  {'name': 'Dist-SW2',  'role': 'Distribution'},
    68: {'name': 'Access-SW1', 'role': 'Access'},
    66: {'name': 'Access-SW2', 'role': 'Access'},
    70: {'name': 'Access-SW3', 'role': 'Access'},
    69: {'name': 'Access-SW4', 'role': 'Access'},
}
POLL_INTERVAL = 5           # giay giua 2 lan PortStats
HISTORY_LEN = 600           # mau lich su (1 mau/giay)
MIN_PORT_SPEED = 100 * 1000 * 1000
CONGEST_LOW = 70.0
CONGEST_HIGH = 90.0
SWITCH_APP = 'CampusSwitch13'
# Cong OVS noi Core (dem luu luong qua Core khi Core la IOL khong OpenFlow)
CORE_UPLINKS = {'Core-SW1': [(5, 'ens9'), (8, 'ens10')], 'Core-SW2': [(5, 'ens10'), (8, 'ens9')]}
PERF_FILE = '/root/ryu-app/metrics/perf.json'   # ket qua do hieu nang VLAN (giu qua khoi dong)
SNMP_CFG = '/root/ryu-app/state/snmp.json'   # {"community": "...", "targets": {"Core-SW1": "10.1.99.1", ...}}
SNMP_CPU_OID = '1.3.6.1.4.1.9.9.109.1.1.1.1.6.1'   # cpmCPUTotal5secRev (Cisco)
REPLY_TIMEOUT = 1.0         # ping: qua thoi gian nay coi la mat


# =====================================================================
#  Ping lien tuc tu controller (ICMP raw socket) - do mat goi phia du lieu
# =====================================================================
def _icmp_checksum(data):
    if len(data) % 2:
        data += b'\0'
    s = sum(struct.unpack('!%dH' % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16
    return (~s) & 0xffff


class PingTarget(object):
    def __init__(self, ip, interval):
        self.ip = ip
        self.interval = max(0.05, float(interval))
        self.running = False
        self.samples = collections.deque(maxlen=6000)   # (ts, rtt_ms|None)
        self.reset()

    def reset(self):
        self.samples.clear()
        self.sent = self.recv = 0
        self.cur_lost = 0
        self.cur_start = None
        self.outages = []           # {'start','end','lost','duration_ms'}

    def record(self, ts, rtt):
        self.sent += 1
        self.samples.append((ts, rtt))
        if rtt is None:
            if self.cur_lost == 0:
                self.cur_start = ts
            self.cur_lost += 1
        else:
            self.recv += 1
            if self.cur_lost:
                self.outages.append({
                    'start': self.cur_start, 'end': ts, 'lost': self.cur_lost,
                    'duration_ms': round((ts - self.cur_start) * 1000, 1)})
                self.outages = self.outages[-50:]
            self.cur_lost = 0

    def stats(self, tail=300):
        rtts = [r for _, r in self.samples if r is not None]
        jit = 0.0
        if len(rtts) > 1:
            jit = sum(abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))) / (len(rtts) - 1)
        return {
            'target': self.ip, 'running': self.running, 'interval': self.interval,
            'sent': self.sent, 'recv': self.recv,
            'loss_pct': round(100.0 * (self.sent - self.recv) / self.sent, 2) if self.sent else 0,
            'rtt_avg': round(sum(rtts) / len(rtts), 2) if rtts else None,
            'rtt_min': round(min(rtts), 2) if rtts else None,
            'rtt_max': round(max(rtts), 2) if rtts else None,
            'jitter': round(jit, 2),
            'current_outage': self.cur_lost,
            'outages': list(self.outages),
            'samples': [[round(t, 3), r] for t, r in list(self.samples)[-tail:]],
        }


class Pinger(object):
    def __init__(self, logger):
        self.logger = logger
        self.targets = collections.OrderedDict()
        self.ident = random.randint(1, 0xfffe)

    def start(self, ip, interval=0.2):
        socket.inet_aton(ip)        # kiem tra dinh dang
        t = self.targets.get(ip)
        if t is None:
            t = PingTarget(ip, interval)
            self.targets[ip] = t
        t.interval = max(0.05, float(interval))
        if not t.running:
            t.running = True
            hub.spawn(self._run, t)
        return t

    def stop(self, ip):
        t = self.targets.get(ip)
        if t:
            t.running = False

    def _run(self, t):
        """Gui DEU theo chu ky (khong cho tra loi) + nhan o luong rieng.
        Goi khong co tra loi sau REPLY_TIMEOUT -> mat. Do phan giai = chu ky."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sock.settimeout(0.2)
        except Exception as e:
            self.logger.warning('PINGER: khong mo duoc raw socket: %s', e)
            t.running = False
            return
        ident = (self.ident + len(self.targets)) & 0xffff
        pending = collections.OrderedDict()     # seq -> [t_gui, rtt|None] (thu tu gui)
        state = {'stop': False}

        def receiver():
            while not state['stop']:
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except Exception:
                    break
                if addr[0] != t.ip or len(data) < 28:
                    continue
                ihl = (data[0] & 0x0f) * 4
                typ, _c, _ck, rid, rseq = struct.unpack('!BBHHH', data[ihl:ihl + 8])
                if typ == 0 and rid == ident and rseq in pending:
                    ent = pending[rseq]
                    ent[1] = (time.time() - ent[0]) * 1000.0

        hub.spawn(receiver)
        seq = 0
        try:
            while t.running:
                seq = (seq + 1) & 0xffff
                payload = struct.pack('!d', time.time()) + b'campus-sdn'
                hdr = struct.pack('!BBHHH', 8, 0, 0, ident, seq)
                pkt = struct.pack('!BBHHH', 8, 0, _icmp_checksum(hdr + payload),
                                  ident, seq) + payload
                t0 = time.time()
                pending[seq] = [t0, None]
                try:
                    sock.sendto(pkt, (t.ip, 0))
                except Exception as e:
                    self.logger.debug('PINGER %s: %s', t.ip, e)
                # Ghi ket qua THEO THU TU GUI: goi dau hang da co tra loi -> ghi RTT;
                # qua REPLY_TIMEOUT ma chua co -> ghi mat; con lai -> doi.
                for s_, (ts, rtt) in list(pending.items()):
                    if rtt is not None:
                        pending.pop(s_, None)
                        t.record(ts, rtt)
                    elif t0 - ts >= REPLY_TIMEOUT:
                        pending.pop(s_, None)
                        t.record(ts, None)
                    else:
                        break
                hub.sleep(max(0.0, t.interval - (time.time() - t0)))
        finally:
            state['stop'] = True
            hub.sleep(0.3)
            sock.close()


# =====================================================================
#  SNMP v2c GET toi thieu (khong can thu vien ngoai - node 9 khong ra Internet)
# =====================================================================
def _ber_len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(b)]) + b


def _tlv(t, v):
    return bytes([t]) + _ber_len(len(v)) + v


def _ber_int(i):
    return _tlv(0x02, i.to_bytes(max(1, (i.bit_length() + 8) // 8), 'big', signed=True))


def _ber_oid(oid):
    parts = [int(x) for x in oid.split('.')]
    out = bytes([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        enc = [p & 0x7f]
        p >>= 7
        while p:
            enc.insert(0, 0x80 | (p & 0x7f))
            p >>= 7
        out += bytes(enc)
    return _tlv(0x06, out)


def _ber_parse(data, i=0):
    t = data[i]
    l = data[i + 1]
    i += 2
    if l & 0x80:
        n = l & 0x7f
        l = int.from_bytes(data[i:i + n], 'big')
        i += n
    return t, data[i:i + l], i + l


def snmp_get(host, community, oids, timeout=1.5):
    """SNMPv2c GET -> {oid: int|bytes|None}. Chi doc (RO)."""
    rid = random.randint(1, 0x7fffffff)
    vbl = b''.join(_tlv(0x30, _ber_oid(o) + b'\x05\x00') for o in oids)
    pdu = _tlv(0xa0, _ber_int(rid) + _ber_int(0) + _ber_int(0) + _tlv(0x30, vbl))
    msg = _tlv(0x30, _ber_int(1) + _tlv(0x04, community.encode()) + pdu)
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sk.settimeout(timeout)
    try:
        sk.sendto(msg, (host, 161))
        data, _ = sk.recvfrom(4096)
    finally:
        sk.close()
    _, body, _ = _ber_parse(data)
    _, _, i = _ber_parse(body)             # version
    _, _, i = _ber_parse(body, i)          # community
    _, pdu, _ = _ber_parse(body, i)
    _, _, j = _ber_parse(pdu)              # request-id
    _, _, j = _ber_parse(pdu, j)           # error-status
    _, _, j = _ber_parse(pdu, j)           # error-index
    _, vbl, _ = _ber_parse(pdu, j)
    out, k = {}, 0
    for o in oids:
        _, vb, k = _ber_parse(vbl, k)
        _, _, m = _ber_parse(vb)
        t, val, _ = _ber_parse(vb, m)
        out[o] = int.from_bytes(val, 'big') if t in (0x02, 0x41, 0x42, 0x43, 0x46) else (
            None if t in (0x80, 0x81, 0x82) else val)
    return out


def _read_proc():
    """CPU % toan node + RSS/CPU tien trinh Ryu (doc /proc, khong can psutil)."""
    with open('/proc/stat') as f:
        cpu = [int(x) for x in f.readline().split()[1:]]
    with open('/proc/meminfo') as f:
        mem = dict((l.split(':')[0], int(l.split()[1])) for l in f if ':' in l)
    with open('/proc/self/stat') as f:
        st = f.read().rsplit(')', 1)[1].split()
    return {'cpu_total': sum(cpu), 'cpu_idle': cpu[3] + cpu[4],
            'mem_total_kb': mem.get('MemTotal', 0), 'mem_avail_kb': mem.get('MemAvailable', 0),
            'proc_ticks': int(st[11]) + int(st[12]), 'proc_rss_kb': int(st[21]) * 4,
            'ncpu': os.cpu_count() or 1}


# =====================================================================
class CampusNocMonitor(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(CampusNocMonitor, self).__init__(*args, **kwargs)
        self.switches = {}
        self.up_time = {}
        self.port_name = {}
        self.port_speed = {}
        self.port_prev = {}
        self.prev_ts = {}
        self.rate = {}
        self.congestion = {}
        self.history = collections.deque(maxlen=HISTORY_LEN)
        self.pinger = Pinger(self.logger)
        self.table_stats = {}       # dpid -> {table: {'active':, 'lookup':, 'matched':}}
        self.load_hist = collections.deque(maxlen=HISTORY_LEN)
        self._load_prev = None
        self.snmp = {}              # 'Core-SW1' -> {'cpu':, 'ts':, 'error':}
        self.perf_runs = []         # ket qua do ma tran VLAN (moi lan 1 phan tu)
        try:
            with open(PERF_FILE) as f:
                self.perf_runs = json.load(f)[-30:]
        except (IOError, OSError, ValueError):
            pass
        wsgi = kwargs['wsgi']
        try:
            mapper = wsgi.mapper
            wsgi.registory['NocController'] = {'monitor': self}
            g = dict(controller=NocController, conditions=dict(method=['GET']))
            p = dict(controller=NocController, conditions=dict(method=['POST']))
            for path, act in [('/noc/switches', 'switches'), ('/noc/ports', 'ports'),
                              ('/noc/congestion', 'congestion'), ('/noc/topology', 'topology'),
                              ('/noc/summary', 'summary'), ('/noc/history', 'history'),
                              ('/campus/topology', 'c_topology'), ('/campus/events', 'c_events'),
                              ('/campus/pinger', 'c_pinger_get'),
                              ('/campus/vlans', 'c_vlans'),
                              ('/campus/policies', 'c_policies'),
                              ('/campus/load', 'c_load'),
                              ('/campus/perf', 'c_perf'),
                              ('/campus/export/events.csv', 'c_export_events'),
                              ('/campus/export/pinger.csv', 'c_export_pinger'),
                              ('/', 'index')]:
                mapper.connect('noc', path, action=act, **g)
            mapper.connect('noc', '/campus/linktest', action='c_linktest', **p)
            mapper.connect('noc', '/campus/pinger', action='c_pinger_post', **p)
            mapper.connect('noc', '/campus/vlan', action='c_vlan_post', **p)
            mapper.connect('noc', '/campus/policy', action='c_policy_post', **p)
            mapper.connect('noc', '/campus/perf', action='c_perf_post', **p)
            self.logger.info('NOC: routes registered')
        except Exception as e:
            self.logger.warning('NOC: wsgi register fail: %s', e)
        hub.spawn(self._poll_loop)
        hub.spawn(self._history_loop)
        hub.spawn(self._load_loop)

    def sw(self):
        return app_manager.lookup_service_brick(SWITCH_APP)

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        dp = ev.msg.datapath
        self.switches[dp.id] = dp
        self.up_time[dp.id] = time.time()
        for m in (self.port_name, self.port_speed, self.port_prev, self.rate, self.congestion):
            m[dp.id] = {}
        dp.send_msg(dp.ofproto_parser.OFPPortDescStatsRequest(datapath=dp, flags=0))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc_stats_handler(self, ev):
        dpid = ev.msg.datapath.id
        if dpid not in self.switches:
            return
        for p in ev.msg.body:
            name = p.name.decode('utf-8', 'replace') if isinstance(p.name, bytes) else p.name
            self.port_name[dpid][p.port_no] = name
            kbps = getattr(p, 'curr_speed', 0) or getattr(p, 'max_speed', 0)
            self.port_speed[dpid][p.port_no] = (kbps or MIN_PORT_SPEED / 1000) * 1000.0

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        if ev.state == DEAD_DISPATCHER and ev.datapath.id in self.switches:
            if self.switches[ev.datapath.id] is not ev.datapath:
                return
            for m in (self.switches, self.up_time, self.port_name, self.port_speed,
                      self.prev_ts, self.port_prev, self.rate, self.congestion):
                m.pop(ev.datapath.id, None)

    def _poll_loop(self):
        while True:
            for dp in list(self.switches.values()):
                try:
                    dp.send_msg(dp.ofproto_parser.OFPPortStatsRequest(
                        datapath=dp, flags=0, port_no=dp.ofproto.OFPP_ANY))
                    dp.send_msg(dp.ofproto_parser.OFPTableStatsRequest(dp, 0))
                except Exception:
                    pass
            hub.sleep(POLL_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_handler(self, ev):
        dpid = ev.msg.datapath.id
        if dpid not in self.switches:
            return
        now = time.time()
        prev_ts = self.prev_ts.get(dpid)
        prev = self.port_prev.get(dpid, {})
        for p in ev.msg.body:
            if p.port_no >= 0xffff0000:
                continue
            pr = prev.get(p.port_no)
            dt = (now - prev_ts) if prev_ts else 0
            def r(cur, old):
                return max(0.0, (cur - old) / dt) if (pr is not None and dt > 0) else 0.0
            rate = {
                'rx': r(p.rx_bytes, pr.rx_bytes if pr else 0) * 8,
                'tx': r(p.tx_bytes, pr.tx_bytes if pr else 0) * 8,
                'rxpkt': r(p.rx_packets, pr.rx_packets if pr else 0),
                'txpkt': r(p.tx_packets, pr.tx_packets if pr else 0),
                'rxdrop': r(p.rx_dropped, pr.rx_dropped if pr else 0),
                'txdrop': r(p.tx_dropped, pr.tx_dropped if pr else 0),
                'rxerr': r(p.rx_errors, pr.rx_errors if pr else 0),
            }
            self.rate[dpid][p.port_no] = rate
            speed = self.port_speed.get(dpid, {}).get(p.port_no) or MIN_PORT_SPEED
            util = (rate['rx'] + rate['tx']) / speed * 100.0
            level = 'HIGH' if util >= CONGEST_HIGH else ('WARN' if util >= CONGEST_LOW else 'OK')
            self.congestion[dpid][p.port_no] = {'util': round(util, 2), 'level': level, 'ts': now}
        self.port_prev[dpid] = {p.port_no: p for p in ev.msg.body if p.port_no < 0xffff0000}
        self.prev_ts[dpid] = now

    @set_ev_cls(ofp_event.EventOFPTableStatsReply, MAIN_DISPATCHER)
    def _table_stats_handler(self, ev):
        d = {}
        for t in ev.msg.body:
            if t.active_count or t.table_id in (0, 1):
                d[t.table_id] = {'active': t.active_count, 'lookup': t.lookup_count,
                                 'matched': t.matched_count}
        self.table_stats[ev.msg.datapath.id] = d

    def _load_loop(self):
        """Moi 5 s: tai tung switch (Mbps, pps, packet-in/s, so flow), tai Core qua
        uplink OVS (+ CPU qua SNMP neu cau hinh), CPU/RAM controller."""
        while True:
            hub.sleep(POLL_INTERVAL)
            try:
                self._load_sample()
            except Exception as e:
                self.logger.debug('load sample: %s', e)

    def _load_sample(self):
        now = time.time()
        s = self.sw()
        cnt = s.api_counters() if s else {'pktin': {}}
        proc = _read_proc()
        prev = self._load_prev
        self._load_prev = {'ts': now, 'pktin': dict(cnt['pktin']), 'proc': proc,
                           'lookup': {d: sum(t['lookup'] for t in v.values())
                                      for d, v in self.table_stats.items()}}
        if prev is None:
            return
        dt = now - prev['ts']
        sw = {}
        for dpid in SWITCH_INFO:
            r = self.rate.get(dpid, {})
            ts = self.table_stats.get(dpid, {})
            lk = self._load_prev['lookup'].get(dpid, 0) - prev['lookup'].get(dpid, 0)
            sw[dpid] = {
                'name': SWITCH_INFO[dpid]['name'], 'role': SWITCH_INFO[dpid]['role'],
                'connected': dpid in self.switches,
                'mbps': round(sum(v['rx'] + v['tx'] for v in r.values()) / 1e6, 3),
                'pps': round(sum(v['rxpkt'] + v['txpkt'] for v in r.values()), 1),
                'drop_pps': round(sum(v['rxdrop'] + v['txdrop'] for v in r.values()), 2),
                'pktin_ps': round((cnt['pktin'].get(dpid, 0) - prev['pktin'].get(dpid, 0)) / dt, 2),
                'flows_t0': ts.get(0, {}).get('active', 0), 'flows_t1': ts.get(1, {}).get('active', 0),
                'lookup_ps': round(max(lk, 0) / dt, 1),
            }
        core = {}
        for name, ends in CORE_UPLINKS.items():
            mb = pp = 0.0
            for dpid, pname in ends:
                pno = next((k for k, v in self.port_name.get(dpid, {}).items() if v == pname), None)
                r = self.rate.get(dpid, {}).get(pno, {})
                mb += (r.get('rx', 0) + r.get('tx', 0)) / 1e6
                pp += r.get('rxpkt', 0) + r.get('txpkt', 0)
            core[name] = {'uplink_mbps': round(mb, 3), 'uplink_pps': round(pp, 1),
                          'cpu': self.snmp.get(name, {}).get('cpu'),
                          'snmp_error': self.snmp.get(name, {}).get('error')}
        p0, p1 = prev['proc'], proc
        dtot = p1['cpu_total'] - p0['cpu_total']
        ctl = {'cpu_pct': round(100.0 * (1 - (p1['cpu_idle'] - p0['cpu_idle']) / dtot), 1) if dtot else 0,
               'ryu_cpu_pct': round(100.0 * (p1['proc_ticks'] - p0['proc_ticks']) * p1['ncpu'] / dtot, 1)
               if dtot else 0,
               'mem_used_pct': round(100.0 * (1 - p1['mem_avail_kb'] / float(p1['mem_total_kb'] or 1)), 1),
               'ryu_rss_mb': round(p1['proc_rss_kb'] / 1024.0, 1),
               'pktin_ps_total': round(sum(v['pktin_ps'] for v in sw.values()), 1)}
        self.load_hist.append({'ts': now, 'sw': sw, 'core': core, 'ctl': ctl})
        self._snmp_poll()

    def _snmp_poll(self):
        try:
            with open(SNMP_CFG) as f:
                cfg = json.load(f)
        except (IOError, OSError, ValueError):
            return          # SNMP chua cau hinh -> chi dung luu luong uplink
        for name, host in cfg.get('targets', {}).items():
            try:
                v = snmp_get(host, cfg['community'], [SNMP_CPU_OID])
                self.snmp[name] = {'cpu': v.get(SNMP_CPU_OID), 'ts': time.time(), 'error': None}
            except Exception as e:
                self.snmp[name] = {'cpu': None, 'ts': time.time(), 'error': str(e)[:60]}

    def add_perf(self, run):
        """Nhan ket qua do tu script lab (VPC <-> VPC). Tinh tom tat trong/khac VLAN."""
        rows = run.get('rows') or []
        for r in rows:
            r['same_vlan'] = r.get('src_vlan') == r.get('dst_vlan')
        def agg(sel):
            ok = [r for r in sel if r.get('avg') is not None]
            sent = sum(r.get('sent', 0) for r in sel)
            recv = sum(r.get('recv', 0) for r in sel)
            return {'pairs': len(sel),
                    'rtt_avg': round(sum(r['avg'] for r in ok) / len(ok), 2) if ok else None,
                    'jitter': round(sum(r.get('jitter') or 0 for r in ok) / len(ok), 2) if ok else None,
                    'loss_pct': round(100.0 * (sent - recv) / sent, 2) if sent else None}
        run['ts'] = run.get('ts') or time.time()
        run['summary'] = {'intra_vlan': agg([r for r in rows if r['same_vlan']]),
                          'inter_vlan': agg([r for r in rows if not r['same_vlan']])}
        self.perf_runs.append(run)
        self.perf_runs = self.perf_runs[-30:]
        try:
            with open(PERF_FILE, 'w') as f:
                json.dump(self.perf_runs, f)
        except (IOError, OSError):
            pass
        return run['summary']

    def get_load(self, n=120):
        h = list(self.load_hist)
        return {'latest': h[-1] if h else None, 'history': h[-n:],
                'snmp_configured': os.path.exists(SNMP_CFG)}

    def _history_loop(self):
        while True:
            rx = tx = 0.0
            per = {}
            for dpid in list(self.switches):
                d = self.rate.get(dpid, {})
                srx = sum(v['rx'] for v in d.values())
                stx = sum(v['tx'] for v in d.values())
                per[dpid] = round(srx + stx)
                rx += srx
                tx += stx
            self.history.append({'ts': time.time(), 'total_rx': rx, 'total_tx': tx,
                                 'per_switch': per})
            hub.sleep(1)

    # -----------------------------------------------------------------
    #  Du lieu cho REST
    # -----------------------------------------------------------------
    def get_switches(self):
        out = []
        for dpid in sorted(self.switches):
            info = SWITCH_INFO.get(dpid, {'name': str(dpid), 'role': '?'})
            out.append({'dpid': dpid, 'name': info['name'], 'role': info['role'],
                        'connected': True,
                        'uptime': round(time.time() - self.up_time.get(dpid, time.time()), 1),
                        'ports': len(self.port_name.get(dpid, {}))})
        return out

    def get_ports(self, dpid=None):
        out = []
        for did in ([dpid] if dpid else sorted(self.switches)):
            for pno, name in sorted(self.port_name.get(did, {}).items()):
                if pno >= 0xffff0000:
                    continue
                r = self.rate.get(did, {}).get(pno, {})
                c = self.congestion.get(did, {}).get(pno, {})
                out.append({'dpid': did, 'switch': SWITCH_INFO.get(did, {}).get('name', did),
                            'port': pno, 'name': name,
                            'speed': self.port_speed.get(did, {}).get(pno, 0),
                            'rx': r.get('rx', 0), 'tx': r.get('tx', 0),
                            'rxpkt': r.get('rxpkt', 0), 'txpkt': r.get('txpkt', 0),
                            'rxdrop': r.get('rxdrop', 0), 'txdrop': r.get('txdrop', 0),
                            'util': c.get('util', 0), 'level': c.get('level', 'OK')})
        return out

    def get_congestion(self):
        return [p for p in self.get_ports() if p['level'] in ('HIGH', 'WARN')]

    def get_summary(self):
        ports = self.get_ports()
        s = self.sw()
        evs = s.api_events() if s else []
        conv = [e['converge_ms'] for e in evs if e.get('converge_ms') is not None
                and e['kind'] in ('link_down', 'link_up', 'tree_change')]
        topo = s.api_topology() if s else {}
        return {
            'switches_up': len(self.switches), 'switches_total': len(SWITCH_INFO),
            'total_rx': sum(p['rx'] for p in ports), 'total_tx': sum(p['tx'] for p in ports),
            'congestion_high': len([p for p in ports if p['level'] == 'HIGH']),
            'congestion_warn': len([p for p in ports if p['level'] == 'WARN']),
            'links_up': len([l for l in topo.get('links', []) if l['up']]),
            'links_total': len(topo.get('links', [])),
            'root': topo.get('root'), 'tree_version': topo.get('tree_version'),
            'vlans': len(topo.get('vlans', [])),
            'events': len(evs),
            'last_converge_ms': conv[-1] if conv else None,
            'avg_converge_ms': round(sum(conv) / len(conv), 1) if conv else None,
        }


class NocController(ControllerBase):
    def __init__(self, req, resp, data, **kwargs):
        super(NocController, self).__init__(req, resp, data, **kwargs)
        self.m = data['monitor']

    # ---- cu (giu tuong thich) ----
    def switches(self, req, **kw):
        return _json(self.m.get_switches())

    def ports(self, req, **kw):
        try:
            d = int(req.GET.get('dpid') or 0) or None
        except ValueError:
            d = None
        return _json(self.m.get_ports(d))

    def congestion(self, req, **kw):
        return _json(self.m.get_congestion())

    def topology(self, req, **kw):
        s = self.m.sw()
        return _json(s.api_topology() if s else {})

    def summary(self, req, **kw):
        return _json(self.m.get_summary())

    def history(self, req, **kw):
        return _json(list(self.m.history))

    # ---- campus ----
    def c_topology(self, req, **kw):
        s = self.m.sw()
        if s is None:
            return _err('app CampusSwitch13 chua chay', 503)
        return _json(s.api_topology())

    def c_events(self, req, **kw):
        s = self.m.sw()
        try:
            since = int(req.GET.get('since') or 0)
        except ValueError:
            since = 0
        return _json(s.api_events(since) if s else [])

    def c_linktest(self, req, **kw):
        s = self.m.sw()
        try:
            body = json.loads(req.body.decode('utf-8') if req.body else '{}')
            return _json(s.api_link_test(body.get('link'), body.get('action'),
                                         body.get('mode', 'silent')))
        except Exception as e:
            return _err(str(e))

    def c_vlans(self, req, **kw):
        s = self.m.sw()
        return _json(s.api_vlans() if s else {})

    def c_vlan_post(self, req, **kw):
        s = self.m.sw()
        try:
            b = json.loads(req.body.decode('utf-8') if req.body else '{}')
            return _json(s.api_vlan_apply(b.get('action', 'add'), b.get('vid'),
                                          b.get('name', ''), b.get('ports') or []))
        except Exception as e:
            return _err(str(e))

    def c_policies(self, req, **kw):
        s = self.m.sw()
        return _json(s.api_policies() if s else [])

    def c_policy_post(self, req, **kw):
        s = self.m.sw()
        try:
            b = json.loads(req.body.decode('utf-8') if req.body else '{}')
            return _json(s.api_policy_apply(b.get('action', 'add'), b.get('rule'), b.get('id')))
        except Exception as e:
            return _err(str(e))

    def c_load(self, req, **kw):
        try:
            n = int(req.GET.get('n') or 120)
        except ValueError:
            n = 120
        return _json(self.m.get_load(n))

    def c_perf(self, req, **kw):
        return _json(self.m.perf_runs)

    def c_perf_post(self, req, **kw):
        try:
            return _json(self.m.add_perf(json.loads(req.body.decode('utf-8'))))
        except Exception as e:
            return _err(str(e))

    def c_pinger_get(self, req, **kw):
        return _json([t.stats() for t in self.m.pinger.targets.values()])

    def c_pinger_post(self, req, **kw):
        try:
            body = json.loads(req.body.decode('utf-8') if req.body else '{}')
            ip = (body.get('target') or '').strip()
            act = body.get('action', 'start')
            if act == 'start':
                self.m.pinger.start(ip, body.get('interval', 0.2))
            elif act == 'stop':
                self.m.pinger.stop(ip)
            elif act == 'reset' and ip in self.m.pinger.targets:
                self.m.pinger.targets[ip].reset()
            elif act == 'remove':
                self.m.pinger.stop(ip)
                self.m.pinger.targets.pop(ip, None)
            return _json({'ok': True, 'target': ip, 'action': act})
        except Exception as e:
            return _err(str(e))

    def c_export_events(self, req, **kw):
        s = self.m.sw()
        cols = ['id', 'time', 'kind', 'detail', 'link', 'trigger', 'detect_ms',
                'converge_ms', 'total_ms', 'switches', 'flow_mods', 'tree_version', 'root']
        lines = [','.join(cols)]
        for e in (s.api_events() if s else []):
            row = dict(e)
            row['time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e['ts']))
            lines.append(','.join('"%s"' % str(row.get(c, '')).replace('"', "'") for c in cols))
        return Response(content_type='text/csv', charset='utf-8',
                        body=('\n'.join(lines) + '\n').encode('utf-8'))

    def c_export_pinger(self, req, **kw):
        ip = req.GET.get('target', '')
        t = self.m.pinger.targets.get(ip)
        lines = ['time,target,rtt_ms']
        if t:
            for ts, rtt in list(t.samples):
                lines.append('%s,%s,%s' % (time.strftime('%H:%M:%S', time.localtime(ts)) +
                                           ('%.3f' % (ts % 1))[1:], ip,
                                           '' if rtt is None else '%.2f' % rtt))
        return Response(content_type='text/csv', charset='utf-8',
                        body=('\n'.join(lines) + '\n').encode('utf-8'))

    def index(self, req, **kw):
        return Response(content_type='text/html', charset='utf-8',
                        body=DASHBOARD_HTML.encode('utf-8'))


def _json(obj):
    return Response(content_type='application/json', charset='utf-8',
                    body=json.dumps(obj, default=str).encode('utf-8'))


def _err(msg, status=400):
    return Response(content_type='application/json', charset='utf-8', status=status,
                    body=json.dumps({'error': msg}).encode('utf-8'))


# =====================================================================
#  GIAO DIEN (self-contained, khong CDN)
# =====================================================================
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Campus SDN Console</title>
<style>
:root{--bg:#0b1220;--panel:#111a2e;--panel2:#0e1627;--border:#22304d;--text:#d3ddf3;--muted:#7f8db0;
--accent:#3aa0ff;--ok:#22c55e;--warn:#f59e0b;--bad:#ef4444;--idle:#64748b}
*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;background:var(--bg);color:var(--text);font-size:14px}
header{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;border-bottom:1px solid var(--border);background:#0d1628}
header h1{margin:0;font-size:17px}header .sub{color:var(--muted);font-size:12px}
nav{display:flex;gap:4px;padding:0 20px;border-bottom:1px solid var(--border);background:#0d1628;flex-wrap:wrap}
nav button{background:none;border:0;color:var(--muted);padding:11px 14px;cursor:pointer;font-size:13px;border-bottom:2px solid transparent}
nav button.on{color:var(--text);border-bottom-color:var(--accent)}nav button .soon{font-size:10px;color:var(--idle)}
main{padding:18px 20px}.tab{display:none}.tab.on{display:block}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g2{grid-template-columns:1fr 1fr}
@media(max-width:900px){.g4,.g2{grid-template-columns:1fr 1fr}}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:14px}
.card h2{margin:0 0 10px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.kpi .v{font-size:24px;font-weight:700;margin-top:4px}.kpi .s{font-size:11px;color:var(--muted);margin-top:3px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-size:11px;text-transform:uppercase;font-weight:600}td.num{text-align:right;font-variant-numeric:tabular-nums}
.b{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700}
.b-ok{background:rgba(34,197,94,.15);color:var(--ok)}.b-warn{background:rgba(245,158,11,.15);color:var(--warn)}
.b-bad{background:rgba(239,68,68,.15);color:var(--bad)}.b-idle{background:rgba(100,116,139,.2);color:#a8b3c9}.b-acc{background:rgba(58,160,255,.15);color:var(--accent)}
button.act{background:#1b2a47;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 10px;cursor:pointer;font-size:12px}
button.act:hover{border-color:var(--accent)}button.red{border-color:rgba(239,68,68,.5)}button.green{border-color:rgba(34,197,94,.5)}
input,select{background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:13px}
canvas{width:100%;display:block}.muted{color:var(--muted)}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
svg text{fill:var(--text);font-size:12px}.legend span{margin-right:14px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:5px}
#toast{position:fixed;right:16px;bottom:16px;background:#1b2a47;border:1px solid var(--border);padding:10px 14px;border-radius:8px;display:none}
</style></head><body>
<header><div><h1>Campus SDN Console &mdash; Site 100</h1><div class="sub">Ryu OpenFlow 1.3 &middot; Dist-SW1/2 + Access-SW1..4 &middot; goc cay: <b id="hdr-root">-</b> &middot; phien ban cay <b id="hdr-ver">-</b></div></div>
<div class="sub" id="hdr-time"></div></header>
<nav id="nav"></nav>
<main>
<section class="tab" id="t-overview">
 <div class="grid g4">
  <div class="card kpi"><h2>Switch OpenFlow</h2><div class="v" id="k-sw">-</div><div class="s">dang ket noi controller</div></div>
  <div class="card kpi"><h2>Lien ket song</h2><div class="v" id="k-link">-</div><div class="s">tham do chu dong</div></div>
  <div class="card kpi"><h2>Hoi tu gan nhat</h2><div class="v" id="k-conv">-</div><div class="s" id="k-conv2">-</div></div>
  <div class="card kpi"><h2>Bang thong tong</h2><div class="v" id="k-bw">-</div><div class="s" id="k-cong">-</div></div>
 </div>
 <div class="card"><h2>Bang thong tong theo thoi gian (Mbps)</h2><canvas id="c-bw" height="190"></canvas></div>
 <div class="card"><h2>Su kien gan day</h2><table id="tb-ev-mini"></table></div>
</section>
<section class="tab" id="t-topo">
 <div class="card"><h2>Do thi lien ket &amp; cay du lieu</h2>
  <div class="legend"><span><i style="background:var(--ok)"></i>thuoc cay</span><span><i style="background:var(--idle)"></i>du phong (song)</span><span><i style="background:var(--bad)"></i>chet</span><span><i style="background:var(--warn)"></i>dang mo phong cat</span></div>
  <svg id="svg-topo" viewBox="0 0 900 360" style="width:100%;max-height:420px"></svg></div>
 <div class="card"><h2>Lien ket</h2><div class="row muted" style="margin-bottom:8px">Che do mo phong:
   <select id="sel-mode"><option value="silent">silent - drop 2 dau (giong dut cap)</option><option value="admin">admin - PortMod down 1 dau</option></select></div>
  <table id="tb-links"></table></div>
</section>
<section class="tab" id="t-recovery">
 <div class="grid g2">
  <div class="card"><h2>Ping lien tuc tu controller (do mat goi)</h2>
   <div class="row"><input id="in-target" value="10.1.40.102" size="14"/> chu ky <select id="in-int"><option>0.1</option><option selected>0.2</option><option>0.5</option><option>1</option></select>s
   <button class="act green" onclick="ping('start')">Bat dau</button><button class="act" onclick="ping('stop')">Dung</button><button class="act" onclick="ping('reset')">Xoa so lieu</button>
   <a class="act" id="a-pcsv" href="#" style="text-decoration:none"><button class="act">CSV</button></a></div>
   <table id="tb-ping" style="margin-top:8px"></table></div>
  <div class="card"><h2>Thoi gian hoi tu (ms) - moi su kien mat/co lien ket</h2><canvas id="c-conv" height="190"></canvas></div>
 </div>
 <div class="card"><h2>RTT (ms) - o trong = mat goi</h2><canvas id="c-rtt" height="200"></canvas></div>
 <div class="card"><h2>Su kien hoi tu <a href="/campus/export/events.csv"><button class="act" style="float:right">Xuat CSV</button></a></h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">detect = moc phat hien - moc kich hoat (lan cuoi thay probe / luc bam mo phong); converge = moc phat hien -> barrier cua moi switch; total = tong.</div>
  <table id="tb-ev"></table></div>
</section>
<section class="tab" id="t-traffic">
 <div class="card"><h2>Bang thong tung switch (Mbps)</h2><canvas id="c-sw" height="200"></canvas></div>
 <div class="card"><h2>Cong</h2><table id="tb-ports"></table></div>
</section>
<section class="tab" id="t-vlan">
 <div class="grid g2">
  <div class="card"><h2>Them VLAN / khu vuc mang (1 lenh API cho toan bo OVS)</h2>
   <div class="row">VLAN <input id="v-vid" size="4" placeholder="50"/> Ten <input id="v-name" size="16" placeholder="Phong Lab"/></div>
   <div class="muted" style="margin:8px 0 4px;font-size:12px">Cong access tren Access (VLAN hien tai trong ngoac):</div>
   <div id="v-ports" class="row"></div>
   <div class="row" style="margin-top:10px"><button class="act green" onclick="vlanDo('add')">Them VLAN</button>
    <button class="act" onclick="vlanDo('ports')">Cap nhat cong cho VLAN</button></div>
   <div id="v-result" style="margin-top:10px"></div></div>
  <div class="card"><h2>Cau hinh Core-SW1/2 can lam (switch truyen thong, ngoai OpenFlow)</h2>
   <div class="muted" style="font-size:12px">Controller tu sinh theo quy uoc 10.1.&lt;VLAN&gt;.0/24, VRRP .1, Core-SW1 .2 (150) / Core-SW2 .3, ip helper DHCP 10.1.90.10. Con can: scope DHCP tren DHCP-Server 72.</div>
   <pre id="v-core" style="background:#0e1627;border:1px solid var(--border);border-radius:6px;padding:8px;font-size:12px;max-height:300px;overflow:auto">-</pre>
   <button class="act" onclick="navigator.clipboard&&navigator.clipboard.writeText($('v-core').textContent);toast('Da sao chep')">Sao chep</button></div>
 </div>
 <div class="card"><h2>VLAN hien co</h2><table id="tb-vlan"></table></div>
 <div class="card"><h2>Lich su trien khai VLAN - so sanh SDN va cau hinh truyen thong</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">SDN: thoi gian tu luc goi API toi khi moi OVS bi anh huong tra barrier. Truyen thong (uoc tinh cung thay doi): moi Access + 2 Dist + 2 Core cau hinh tay qua CLI (vlan, name, trunk allowed tren moi trunk, cong access).</div>
  <table id="tb-vlanev"></table></div>
</section>
<section class="tab" id="t-policy">
 <div class="card"><h2>Them luat (ap dong thoi len 4 Access, bang 0 OpenFlow)</h2>
  <div class="row" style="font-size:12px">Mau nhanh:
   <button class="act" onclick="preset('deny','vlan:10','vlan:40','icmp','',1,'Cach ly CNTT - Hanh chinh (ICMP)')">Cach ly VLAN10-40 (ICMP)</button>
   <button class="act" onclick="preset('deny','vlan:20','vlan:30','ip','',1,'Cach ly Toan-TK - Luat')">Cach ly VLAN20-30</button>
   <button class="act" onclick="preset('deny','any','10.1.90.0/24','tcp','22',0,'Chan SSH vao Server Farm')">Chan SSH -> Server Farm</button>
   <button class="act" onclick="preset('deny','vlan:40','any','tcp','23',0,'Chan Telnet tu Hanh chinh')">Chan Telnet tu VLAN40</button></div>
  <div class="row" style="margin-top:8px">
   <select id="p-act"><option value="deny">deny</option><option value="allow">allow</option></select>
   nguon <input id="p-src" size="14" value="vlan:10"/> dich <input id="p-dst" size="14" value="vlan:40"/>
   <select id="p-proto"><option>ip</option><option selected>icmp</option><option>tcp</option><option>udp</option></select>
   cong <input id="p-dport" size="5"/> uu tien <input id="p-prio" size="4" value="100"/>
   <label><input type="checkbox" id="p-bidir" checked/> hai chieu</label>
   ten <input id="p-name" size="22"/>
   <button class="act green" onclick="polAdd()">Ap dung</button></div>
  <div class="muted" style="font-size:12px;margin-top:6px">Dia chi: any | vlan:N (= 10.1.N.0/24) | CIDR | IP. Uu tien lon hon thang (allow uu tien cao lam ngoai le cho deny). Luat khop IP tren Access: moi luong cua host deu di qua Access.</div></div>
 <div class="card"><h2>Luat dang ap</h2><table id="tb-pol"></table></div>
 <div class="card"><h2>Lich su ap chinh sach - thoi gian trien khai toan campus</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">SDN: 1 lenh API -> 4 Access xac nhan (barrier). Truyen thong (uoc tinh): ACL dat tren SVI cua 2 Core (L3) hoac VACL tren tung switch: moi luat x moi thiet bi = nhieu lenh CLI.</div>
  <table id="tb-polev"></table></div>
</section>
<section class="tab" id="t-load">
 <div class="grid g4" id="ld-cards"></div>
 <div class="grid g2">
  <div class="card"><h2>Distribution - Mbps theo thoi gian</h2><canvas id="c-ld-dist" height="190"></canvas></div>
  <div class="card"><h2>Packet-in/s len controller (tai dieu khien)</h2><canvas id="c-ld-pktin" height="190"></canvas></div>
  <div class="card"><h2>Core-SW1/2 - luu luong qua uplink tu OVS (Mbps)</h2><canvas id="c-ld-core" height="190"></canvas><div class="muted" id="ld-snmp" style="font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Controller (node 9) - CPU %</h2><canvas id="c-ld-ctl" height="190"></canvas></div>
 </div>
 <div class="card"><h2>Chi tiet tung switch (mau 5 s gan nhat)</h2><table id="tb-ld"></table></div>
</section>
<section class="tab" id="t-perf">
 <div class="grid g4" id="pf-cards"></div>
 <div class="card"><h2>Ma tran RTT trung binh (ms) giua cac VLAN - lan do gan nhat <span class="muted" id="pf-when"></span></h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">Hang = VLAN nguon, cot = VLAN dich. Duong cheo = cung VLAN (chuyen mach L2 qua OVS); ngoai duong cheo = dinh tuyen qua Core-SW1 (SVI/VRRP). Ket qua do script lab (VPC &harr; VPC) day len /campus/perf.</div>
  <table id="tb-pf-matrix"></table></div>
 <div class="grid g2">
  <div class="card"><h2>Chi tiet tung cap</h2><table id="tb-pf-pairs"></table></div>
  <div class="card"><h2>Lich su: trong VLAN vs khac VLAN (ms)</h2><canvas id="c-pf-hist" height="200"></canvas>
   <div class="row" style="margin-top:8px;font-size:12px">Ping lien tuc tu controller toi 1 may moi VLAN:
    <button class="act" onclick="perfPing()">Bat cho cac VLAN</button> (xem tab Khoi phuc)</div></div>
 </div>
</section>
</main><div id="toast"></div>
<script>
const TABS=[['overview','Tong quan'],['topo','Topology'],['recovery','Khoi phuc'],['traffic','Luu luong'],
 ['vlan','VLAN'],['policy','Chinh sach'],['load','Tai thiet bi'],['perf','Hieu nang']];
const SOON={};
let cur=localStorage.getItem('tab')||'overview';
const nav=document.getElementById('nav');
TABS.forEach(([id,l])=>{const b=document.createElement('button');b.id='nb-'+id;
 b.innerHTML=l+(SOON[id]?' <span class="soon">('+SOON[id]+')</span>':'');b.onclick=()=>show(id);nav.appendChild(b)});
function show(id){cur=id;try{localStorage.setItem('tab',id)}catch(e){}
 document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.id==='t-'+id));
 document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.id==='nb-'+id));refresh()}
const $=id=>document.getElementById(id);
async function J(u,o){const r=await fetch(u,o);return r.json()}
function toast(m){const t=$('toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3500)}
function mbps(b){return (b/1e6).toFixed(b<1e6?3:2)}
function fmt(v,d){return v==null?'-':(+v).toFixed(d==null?1:d)}
function tstr(ts){const d=new Date(ts*1000);return d.toLocaleTimeString('vi-VN')}
// ---- bieu do canvas don gian ----
function chart(cv,series,opt){opt=opt||{};const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=cv.height;
 cv.width=W*dpr;cv.height=H*dpr;cv.style.height=H+'px';const g=cv.getContext('2d');g.scale(dpr,dpr);
 const L=46,R=10,T=10,B=22;g.fillStyle='#0e1627';g.fillRect(0,0,W,H);
 let xs=[],ys=[];series.forEach(s=>s.pts.forEach(p=>{xs.push(p[0]);if(p[1]!=null)ys.push(p[1])}));
 if(!xs.length){g.fillStyle='#7f8db0';g.fillText('chua co du lieu',L,H/2);return}
 let x0=Math.min(...xs),x1=Math.max(...xs);if(x1===x0)x1=x0+1;let y1=Math.max(opt.ymin||0,...ys)*1.15||1,y0=0;
 const X=x=>L+(x-x0)/(x1-x0)*(W-L-R),Y=y=>H-B-(y-y0)/(y1-y0)*(H-T-B);
 g.strokeStyle='#22304d';g.fillStyle='#7f8db0';g.font='11px Segoe UI';g.lineWidth=1;
 for(let i=0;i<=4;i++){const yv=y0+(y1-y0)*i/4,yy=Y(yv);g.beginPath();g.moveTo(L,yy);g.lineTo(W-R,yy);g.stroke();g.fillText(yv.toFixed(yv<10?2:0),4,yy+4)}
 if(opt.timeAxis){[x0,(x0+x1)/2,x1].forEach((xv,i)=>{g.fillText(tstr(xv),Math.min(X(xv)-(i?24:0),W-60),H-6)})}
 series.forEach(s=>{g.strokeStyle=s.color;g.fillStyle=s.color;g.lineWidth=1.6;
  if(s.bar){const bw=Math.max(3,(W-L-R)/Math.max(8,s.pts.length)*0.6);s.pts.forEach(p=>{if(p[1]!=null)g.fillRect(X(p[0])-bw/2,Y(p[1]),bw,H-B-Y(p[1]))});return}
  g.beginPath();let pen=false;s.pts.forEach(p=>{if(p[1]==null){pen=false;if(s.gapMark){g.save();g.fillStyle='rgba(239,68,68,.55)';g.fillRect(X(p[0])-1,T,2,H-T-B);g.restore()}return}
   const xx=X(p[0]),yy=Y(p[1]);pen?g.lineTo(xx,yy):g.moveTo(xx,yy);pen=true});g.stroke()});
 if(series.length>1){let lx=L+6;series.forEach(s=>{g.fillStyle=s.color;g.fillRect(lx,T+2,10,3);g.fillStyle='#d3ddf3';g.fillText(s.name,lx+14,T+8);lx+=g.measureText(s.name).width+30})}}
const COLORS=['#3aa0ff','#22c55e','#f59e0b','#a78bfa','#f472b6','#2dd4bf','#ef4444'];
// ---- Topology SVG ----
const POS={'C1':[300,40],'C2':[600,40],'Dist-SW1':[300,170],'Dist-SW2':[600,170],
 'Access-SW1':[120,310],'Access-SW2':[340,310],'Access-SW3':[560,310],'Access-SW4':[780,310]};
const NAME={5:'Dist-SW1',8:'Dist-SW2',68:'Access-SW1',66:'Access-SW2',70:'Access-SW3',69:'Access-SW4',C1:'C1',C2:'C2'};
function drawTopo(t){const s=$('svg-topo');let h='';
 t.links.forEach(l=>{const a=POS[NAME[l.a[0]]],b=POS[NAME[l.b[0]]];if(!a||!b)return;
  const col=l.test_cut?'#f59e0b':(!l.up?'#ef4444':(l.in_tree?'#22c55e':'#64748b'));
  const w=l.in_tree?4:2,dash=(!l.up||l.test_cut)?'6 5':'';
  h+=`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${col}" stroke-width="${w}" stroke-dasharray="${dash}"><title>${l.id}: ${l.a_name}.${l.a[1]} - ${l.b_name}.${l.b[1]}</title></line>`;
  const mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2;h+=`<text x="${mx+4}" y="${my-4}" style="font-size:10px;fill:#7f8db0">${l.id}</text>`});
 t.nodes.forEach(n=>{const key=n.id==='C1'||n.id==='C2'?n.id:n.name,p=POS[key];if(!p)return;
  const core=n.role==='Core',col=core?'#3aa0ff':(n.connected?'#22c55e':'#ef4444');
  h+=`<rect x="${p[0]-62}" y="${p[1]-17}" width="124" height="34" rx="7" fill="#111a2e" stroke="${col}" stroke-width="2"/>`;
  h+=`<text x="${p[0]}" y="${p[1]+4}" text-anchor="middle">${n.name}${core&&t.root===n.name?' (goc)':''}</text>`});
 s.innerHTML=h}
function linkRows(t){let h='<tr><th>Lien ket</th><th>Dau A</th><th>Dau B</th><th>Trang thai</th><th>Cay</th><th class="num">Probe gan nhat (s)</th><th class="num">On dinh (s)</th><th>Mo phong</th></tr>';
 t.links.forEach(l=>{const st=l.test_cut?'<span class="b b-warn">cat ('+l.test_cut+')</span>':(l.up?'<span class="b b-ok">song</span>':'<span class="b b-bad">chet</span>');
  h+=`<tr><td><b>${l.id}</b></td><td>${l.a_name}.${l.a[1]}</td><td>${l.b_name}.${l.b[1]}</td><td>${st}</td><td>${l.in_tree?'<span class="b b-acc">active</span>':'<span class="b b-idle">standby</span>'}</td>
  <td class="num">${fmt(l.probe_age,2)}</td><td class="num">${fmt(l.since,0)}</td>
  <td>${l.test_cut?`<button class="act green" onclick="cut('${l.id}','up')">Khoi phuc</button>`:`<button class="act red" onclick="cut('${l.id}','down')">Cat</button>`}</td></tr>`});
 $('tb-links').innerHTML=h}
async function cut(id,action){const r=await J('/campus/linktest',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({link:id,action:action,mode:$('sel-mode').value})});toast(r.error?('Loi: '+r.error):(action==='down'?'Da cat ':'Da khoi phuc ')+id);refresh()}
async function ping(action){const ip=$('in-target').value.trim();const r=await J('/campus/pinger',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({target:ip,action:action,interval:+$('in-int').value})});if(r.error)toast('Loi: '+r.error);refresh()}
function evRows(evs,full){let h='<tr><th>#</th><th>Gio</th><th>Loai</th><th>Mo ta</th>'+(full?'<th class="num">detect</th><th class="num">converge</th><th class="num">total</th><th class="num">switch</th><th class="num">flow-mod</th><th>cay</th>':'<th class="num">converge (ms)</th>')+'</tr>';
 evs.slice().reverse().forEach(e=>{const k={link_down:'b-bad',link_up:'b-ok',switch_down:'b-bad',switch_up:'b-ok',tree_change:'b-acc',test_inject:'b-warn',test_restore:'b-warn'}[e.kind]||'b-idle';
  h+=`<tr><td>${e.id}</td><td>${tstr(e.ts)}</td><td><span class="b ${k}">${e.kind}</span></td><td>${e.detail}</td>`+
  (full?`<td class="num">${fmt(e.detect_ms)}</td><td class="num">${fmt(e.converge_ms)}</td><td class="num">${fmt(e.total_ms)}</td><td class="num">${e.switches==null?'-':e.switches}</td><td class="num">${e.flow_mods==null?'-':e.flow_mods}</td><td>v${e.tree_version==null?'-':e.tree_version}</td>`:`<td class="num">${fmt(e.converge_ms)}</td>`)+'</tr>'});return h}
// ---- VLAN ----
let VLANS=null;
function vlanForm(v){const box=$('v-ports');if(box.dataset.ready)return;let h='';
 Object.keys(v.access_ports).forEach(sw=>v.access_ports[sw].forEach(p=>{const id=sw+'.'+p;
  const cur=(v.vlans.find(x=>x.ports.includes(id))||{}).vid;h+=`<label style="margin-right:10px;font-size:12px"><input type="checkbox" value="${id}" class="v-pc"/> ${id} <span class="muted">(${cur||'-'})</span></label>`}));
 box.innerHTML=h;box.dataset.ready=1}
async function vlanDo(action,vid){const body={action:action,vid:vid||+$('v-vid').value,name:$('v-name').value,
  ports:[...document.querySelectorAll('.v-pc:checked')].map(x=>x.value)};
 if(action==='delete'&&!confirm('Xoa VLAN '+body.vid+'? Cong se ve VLAN goc.'))return;
 const r=await J('/campus/vlan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.error){toast('Loi: '+r.error);return}
 $('v-core').textContent=Object.entries(r.core_config).map(([k,v])=>'! ===== '+k+' =====\n'+v).join('\n\n');
 $('v-result').innerHTML='<span class="b b-ok">'+r.kind+'</span> '+r.detail+' &mdash; dang cho barrier...';
 $('v-ports').dataset.ready='';setTimeout(refresh,800);toast(r.kind+' VLAN '+body.vid)}
function vlanTables(v){let h='<tr><th>VLAN</th><th>Ten</th><th>Mang</th><th>Cong access (OVS)</th><th></th></tr>';
 v.vlans.forEach(x=>{h+=`<tr><td><b>${x.vid}</b></td><td>${x.name}</td><td>${x.subnet}</td><td>${x.ports.join(', ')||'-'}</td><td>${x.base?'<span class="b b-idle">goc</span>':`<button class="act red" onclick="vlanDo('delete',${x.vid})">Xoa</button>`}</td></tr>`});
 $('tb-vlan').innerHTML=h;
 const ve=EV.filter(e=>e.kind&&e.kind.indexOf('vlan_')===0);
 let g='<tr><th>Gio</th><th>Thao tac</th><th>Mo ta</th><th class="num">SDN (ms)</th><th class="num">OVS</th><th class="num">flow-mod</th><th class="num">Thiet bi CLI (truyen thong)</th><th class="num">Lenh CLI uoc tinh</th></tr>';
 ve.slice().reverse().forEach(e=>{const nPorts=(e.detail.split('cong: ')[1]||'').split(',').filter(x=>x.trim()&&x.trim()!=='-').length;
  const acc=new Set((e.detail.split('cong: ')[1]||'').split(',').map(x=>x.trim().split('.')[0]).filter(x=>x&&x!=='-')).size;
  const devs=2+2+acc, cli=(e.core_commands||34)+2*(2+6)+acc*2+nPorts*2;
  const last=[...ve].reverse().find(x=>x.id===e.id);
  g+=`<tr><td>${tstr(e.ts)}</td><td><span class="b b-acc">${e.kind}</span></td><td>${e.detail}</td><td class="num">${fmt(e.converge_ms)}</td><td class="num">${e.switches==null?'-':e.switches}</td><td class="num">${e.flow_mods==null?'-':e.flow_mods}</td><td class="num">${devs}</td><td class="num">${cli}</td></tr>`});
 $('tb-vlanev').innerHTML=g}
// ---- CHINH SACH ----
function preset(a,s,d,pr,po,bi,n){$('p-act').value=a;$('p-src').value=s;$('p-dst').value=d;$('p-proto').value=pr;$('p-dport').value=po;$('p-bidir').checked=!!bi;$('p-name').value=n}
async function polPost(body){const r=await J('/campus/policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.error)toast('Loi: '+r.error);else toast(r.kind+' '+r.detail);setTimeout(refresh,700)}
function polAdd(){polPost({action:'add',rule:{action:$('p-act').value,src:$('p-src').value,dst:$('p-dst').value,proto:$('p-proto').value,
 dport:$('p-dport').value||null,prio:+$('p-prio').value||100,bidir:$('p-bidir').checked,name:$('p-name').value}})}
function polTables(P){let h='<tr><th>#</th><th>Ten</th><th>Hanh dong</th><th>Nguon</th><th>Dich</th><th>Proto</th><th>Cong</th><th>2 chieu</th><th class="num">Uu tien</th><th class="num">Goi khop</th><th>Trang thai</th><th></th></tr>';
 P.forEach(r=>{h+=`<tr><td>${r.id}</td><td>${r.name}</td><td><span class="b ${r.action==='deny'?'b-bad':'b-ok'}">${r.action}</span></td><td>${r.src}</td><td>${r.dst}</td><td>${r.proto}</td><td>${r.dport||'-'}</td><td>${r.bidir?'co':'-'}</td><td class="num">${r.prio}</td><td class="num">${r.packets||0}</td>
  <td>${r.enabled?'<span class="b b-ok">bat</span>':'<span class="b b-idle">tat</span>'}</td>
  <td><button class="act" onclick="polPost({action:'${r.enabled?'disable':'enable'}',id:${r.id}})">${r.enabled?'Tat':'Bat'}</button> <button class="act red" onclick="if(confirm('Xoa luat #${r.id}?'))polPost({action:'delete',id:${r.id}})">Xoa</button></td></tr>`});
 if(!P.length)h+='<tr><td colspan="12" class="muted">Chua co luat</td></tr>';$('tb-pol').innerHTML=h;
 const pe=EV.filter(e=>e.kind&&e.kind.indexOf('policy_')===0);
 let g='<tr><th>Gio</th><th>Thao tac</th><th>Luat</th><th class="num">SDN (ms)</th><th class="num">Switch</th><th class="num">flow-mod</th><th class="num">Thiet bi CLI (truyen thong)</th></tr>';
 pe.slice().reverse().forEach(e=>{g+=`<tr><td>${tstr(e.ts)}</td><td><span class="b b-acc">${e.kind}</span></td><td>${e.detail}</td><td class="num">${fmt(e.converge_ms)}</td><td class="num">${e.switches==null?'-':e.switches}</td><td class="num">${e.flow_mods==null?'-':e.flow_mods}</td><td class="num">2 Core + 6 switch</td></tr>`});
 $('tb-polev').innerHTML=g}
// ---- TAI THIET BI ----
function loadView(L){const h=L.history||[],x=L.latest;if(!x){$('ld-cards').innerHTML='<div class="card muted">dang thu mau (5 s)...</div>';return}
 const d5=x.sw[5]||{},d8=x.sw[8]||{},c1=x.core['Core-SW1']||{},c2=x.core['Core-SW2']||{};
 const card=(t,v,s)=>`<div class="card kpi"><h2>${t}</h2><div class="v">${v}</div><div class="s">${s}</div></div>`;
 $('ld-cards').innerHTML=card('Dist-SW1',fmt(d5.mbps,2)+' Mbps',fmt(d5.pps,0)+' pps, '+d5.flows_t0+'+'+d5.flows_t1+' flow, '+fmt(d5.pktin_ps,1)+' pkt-in/s')+
  card('Dist-SW2',fmt(d8.mbps,2)+' Mbps',fmt(d8.pps,0)+' pps, '+d8.flows_t0+'+'+d8.flows_t1+' flow, '+fmt(d8.pktin_ps,1)+' pkt-in/s')+
  card('Core-SW1 / Core-SW2',fmt(c1.uplink_mbps,2)+' / '+fmt(c2.uplink_mbps,2)+' Mbps','uplink OVS'+(c1.cpu!=null?' &middot; CPU '+c1.cpu+'% / '+(c2.cpu==null?'-':c2.cpu)+'%':''))+
  card('Controller',fmt(x.ctl.cpu_pct,1)+' % CPU','Ryu '+fmt(x.ctl.ryu_cpu_pct,1)+'% CPU, '+x.ctl.ryu_rss_mb+' MB, RAM '+x.ctl.mem_used_pct+'%');
 chart($('c-ld-dist'),[5,8].map((d,i)=>({name:NAME[d],color:COLORS[i],pts:h.map(p=>[p.ts,(p.sw[d]||{}).mbps])})),{timeAxis:1});
 chart($('c-ld-pktin'),[5,8,68,66,70,69].map((d,i)=>({name:NAME[d],color:COLORS[i],pts:h.map(p=>[p.ts,(p.sw[d]||{}).pktin_ps])})),{timeAxis:1});
 chart($('c-ld-core'),['Core-SW1','Core-SW2'].map((c,i)=>({name:c,color:COLORS[i+2],pts:h.map(p=>[p.ts,(p.core[c]||{}).uplink_mbps])})),{timeAxis:1});
 chart($('c-ld-ctl'),[{name:'node 9',color:COLORS[0],pts:h.map(p=>[p.ts,p.ctl.cpu_pct])},{name:'Ryu',color:COLORS[2],pts:h.map(p=>[p.ts,p.ctl.ryu_cpu_pct])}],{timeAxis:1});
 $('ld-snmp').textContent=L.snmp_configured?('SNMP: Core-SW1 '+(c1.snmp_error||'OK')+', Core-SW2 '+(c2.snmp_error||'OK')):'SNMP chua cau hinh (state/snmp.json) - CPU Core chua do; tai Core tinh qua luu luong uplink OVS.';
 let t='<tr><th>Switch</th><th>Vai tro</th><th class="num">Mbps</th><th class="num">pps</th><th class="num">drop/s</th><th class="num">packet-in/s</th><th class="num">flow bang 0</th><th class="num">flow bang 1</th><th class="num">lookup/s</th></tr>';
 [5,8,68,66,70,69].forEach(d=>{const v=x.sw[d]||{};t+=`<tr><td>${v.name}${v.connected?'':' <span class="b b-bad">mat ket noi</span>'}</td><td>${v.role}</td><td class="num">${fmt(v.mbps,3)}</td><td class="num">${fmt(v.pps,0)}</td><td class="num">${fmt(v.drop_pps,2)}</td><td class="num">${fmt(v.pktin_ps,1)}</td><td class="num">${v.flows_t0}</td><td class="num">${v.flows_t1}</td><td class="num">${fmt(v.lookup_ps,0)}</td></tr>`});
 $('tb-ld').innerHTML=t}
// ---- HIEU NANG ----
function heat(v){if(v==null)return '';const t=Math.min(1,v/20);return `background:rgba(${Math.round(58+180*t)},${Math.round(160-100*t)},${Math.round(255-200*t)},.25)`}
async function perfPing(){const runs=await J('/campus/perf');const last=runs[runs.length-1];if(!last){toast('Chua co lan do');return}
 const seen={};last.rows.forEach(r=>{if(!seen[r.dst_vlan])seen[r.dst_vlan]=r.dst});
 for(const v in seen){await J('/campus/pinger',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:seen[v],action:'start',interval:0.5})})}
 toast('Da bat ping toi '+Object.values(seen).join(', '))}
function perfView(runs){const last=runs[runs.length-1];
 if(!last){$('pf-cards').innerHTML='<div class="card muted">Chua co ket qua - chay scripts/lab/sdn_perf_test.py</div>';return}
 const S=last.summary,card=(t,v,s)=>`<div class="card kpi"><h2>${t}</h2><div class="v">${v}</div><div class="s">${s}</div></div>`;
 $('pf-cards').innerHTML=card('Trong VLAN (L2)',fmt(S.intra_vlan.rtt_avg,2)+' ms','jitter '+fmt(S.intra_vlan.jitter,2)+' ms, mat '+fmt(S.intra_vlan.loss_pct,1)+'%, '+S.intra_vlan.pairs+' cap')+
  card('Khac VLAN (qua Core)',fmt(S.inter_vlan.rtt_avg,2)+' ms','jitter '+fmt(S.inter_vlan.jitter,2)+' ms, mat '+fmt(S.inter_vlan.loss_pct,1)+'%, '+S.inter_vlan.pairs+' cap')+
  card('So lan do',runs.length,'goi moi cap: '+(last.count||'-'))+card('Lan gan nhat',tstr(last.ts),new Date(last.ts*1000).toLocaleDateString('vi-VN'));
 $('pf-when').textContent='('+new Date(last.ts*1000).toLocaleString('vi-VN')+')';
 const vl=[...new Set(last.rows.map(r=>r.src_vlan).concat(last.rows.map(r=>r.dst_vlan)))].sort((a,b)=>a-b);
 let h='<tr><th>nguon / dich</th>'+vl.map(v=>'<th class="num">VLAN '+v+'</th>').join('')+'</tr>';
 vl.forEach(a=>{h+='<tr><td><b>VLAN '+a+'</b></td>'+vl.map(b=>{const c=last.rows.filter(r=>r.src_vlan===a&&r.dst_vlan===b&&r.avg!=null);
  if(!c.length)return '<td class="num muted">-</td>';const m=c.reduce((x,r)=>x+r.avg,0)/c.length;return `<td class="num" style="${heat(m)}">${m.toFixed(2)}</td>`}).join('')+'</tr>'});
 $('tb-pf-matrix').innerHTML=h;
 let t='<tr><th>Nguon</th><th>Dich</th><th class="num">RTT tb</th><th class="num">min</th><th class="num">max</th><th class="num">jitter</th><th class="num">mat %</th></tr>';
 last.rows.forEach(r=>{t+=`<tr><td>${r.src} (V${r.src_vlan})</td><td>${r.dst} (V${r.dst_vlan})</td><td class="num">${fmt(r.avg,2)}</td><td class="num">${fmt(r.min,2)}</td><td class="num">${fmt(r.max,2)}</td><td class="num">${fmt(r.jitter,2)}</td><td class="num">${r.sent?fmt(100*(r.sent-r.recv)/r.sent,1):'-'}</td></tr>`});
 $('tb-pf-pairs').innerHTML=t;
 chart($('c-pf-hist'),[{name:'trong VLAN',color:COLORS[1],pts:runs.map(r=>[r.ts,r.summary.intra_vlan.rtt_avg])},{name:'khac VLAN',color:COLORS[2],pts:runs.map(r=>[r.ts,r.summary.inter_vlan.rtt_avg])}],{timeAxis:1})}
// ---- refresh ----
let EV=[];
async function refresh(){try{
 $('hdr-time').textContent=new Date().toLocaleString('vi-VN');
 const [sum,topo]=await Promise.all([J('/noc/summary'),J('/campus/topology')]);
 $('hdr-root').textContent=topo.root||'-';$('hdr-ver').textContent=topo.tree_version;
 EV=await J('/campus/events');
 if(cur==='overview'){$('k-sw').textContent=sum.switches_up+' / '+sum.switches_total;$('k-link').textContent=sum.links_up+' / '+sum.links_total;
  $('k-conv').textContent=sum.last_converge_ms==null?'-':sum.last_converge_ms+' ms';$('k-conv2').textContent='trung binh '+fmt(sum.avg_converge_ms)+' ms';
  $('k-bw').textContent=mbps(sum.total_rx+sum.total_tx)+' Mbps';$('k-cong').textContent=sum.congestion_high+' HIGH / '+sum.congestion_warn+' WARN';
  const hi=await J('/noc/history');chart($('c-bw'),[{name:'Rx',color:COLORS[0],pts:hi.map(x=>[x.ts,x.total_rx/1e6])},{name:'Tx',color:COLORS[1],pts:hi.map(x=>[x.ts,x.total_tx/1e6])}],{timeAxis:1});
  $('tb-ev-mini').innerHTML=evRows(EV.slice(-8),false)}
 if(cur==='topo'){drawTopo(topo);linkRows(topo)}
 if(cur==='recovery'){const P=await J('/campus/pinger');let h='<tr><th>Dich</th><th>TT</th><th class="num">Gui</th><th class="num">Mat %</th><th class="num">RTT tb</th><th class="num">Jitter</th><th class="num">Dang mat</th><th>Lan mat gan nhat</th><th></th></tr>';
  P.forEach(p=>{const o=p.outages.length?p.outages[p.outages.length-1]:null;h+=`<tr><td>${p.target}</td><td>${p.running?'<span class="b b-ok">chay</span>':'<span class="b b-idle">dung</span>'}</td><td class="num">${p.sent}</td><td class="num">${p.loss_pct}</td><td class="num">${fmt(p.rtt_avg,2)}</td><td class="num">${fmt(p.jitter,2)}</td><td class="num">${p.current_outage}</td><td>${o?o.lost+' goi / '+o.duration_ms+' ms ('+tstr(o.start)+')':'-'}</td><td><button class="act" onclick="$('in-target').value='${p.target}';ping('remove')">x</button></td></tr>`});
  $('tb-ping').innerHTML=h;$('a-pcsv').href='/campus/export/pinger.csv?target='+encodeURIComponent($('in-target').value.trim());
  chart($('c-rtt'),P.map((p,i)=>({name:p.target,color:COLORS[i%7],gapMark:1,pts:p.samples})),{timeAxis:1});
  const cv=EV.filter(e=>e.converge_ms!=null&&['link_down','link_up','tree_change'].includes(e.kind));
  chart($('c-conv'),[{name:'converge',color:COLORS[0],bar:1,pts:cv.map(e=>[e.ts,e.converge_ms])},{name:'total',color:COLORS[2],bar:1,pts:cv.filter(e=>e.total_ms!=null).map(e=>[e.ts+0.3,e.total_ms])}],{timeAxis:1});
  $('tb-ev').innerHTML=evRows(EV.slice(-60),true)}
 if(cur==='traffic'){const ports=await J('/noc/ports'),hi=await J('/noc/history');const ids=[5,8,68,66,70,69];
  chart($('c-sw'),ids.map((d,i)=>({name:NAME[d],color:COLORS[i],pts:hi.map(x=>[x.ts,(x.per_switch[d]||0)/1e6])})),{timeAxis:1});
  let h='<tr><th>Switch</th><th>Cong</th><th class="num">Rx Mbps</th><th class="num">Tx Mbps</th><th class="num">Rx pps</th><th class="num">Tx pps</th><th class="num">Drop</th><th class="num">%</th><th>Muc</th></tr>';
  ports.forEach(p=>{h+=`<tr><td>${p.switch}</td><td>${p.name}</td><td class="num">${mbps(p.rx)}</td><td class="num">${mbps(p.tx)}</td><td class="num">${fmt(p.rxpkt,0)}</td><td class="num">${fmt(p.txpkt,0)}</td><td class="num">${fmt(p.rxdrop+p.txdrop,0)}</td><td class="num">${fmt(p.util,2)}</td><td><span class="b ${p.level==='OK'?'b-ok':p.level==='WARN'?'b-warn':'b-bad'}">${p.level}</span></td></tr>`});
  $('tb-ports').innerHTML=h}
 if(cur==='vlan'){VLANS=await J('/campus/vlans');vlanForm(VLANS);vlanTables(VLANS)}
 if(cur==='policy'){polTables(await J('/campus/policies'))}
 if(cur==='load'){loadView(await J('/campus/load'))}
 if(cur==='perf'){perfView(await J('/campus/perf'))}
}catch(e){console.log(e)}}
show(cur);setInterval(refresh,2000);
</script></body></html>"""
