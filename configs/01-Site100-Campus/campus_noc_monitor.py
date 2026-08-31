# =====================================================================
#  campus_noc_monitor.py - NOC Monitoring app (Ryu / OpenFlow 1.3)
#  Do an: Campus Network ket hop SDN + SD-WAN (EVE-NG)
#
#  Muc dich: giam sat luu luong mang campus theo chuan NOC - do bang
#  thong thuc te, phat hien tac nghen (congestion) va cung cap lich su
#  de ve dashboard truc quan. Lay du lieu thuan qua OpenFlow (khong
#  can agent tren switch):
#     - PortStatsRequest  : dem byte/loi/got tren moi port
#     - PortDescStats     : ten port + toc do (cur_speed)
#     - FlowStatsRequest  : dem flow (bo sung - tuy chon)
#
#  Cac switch duoc quan ly (datapath-id = node-id):
#     5  = Dist-SW1       8  = Dist-SW2
#     68 = Access-SW1     66 = Access-SW2   70 = Access-SW3   69 = Access-SW4
#
#  Web Dashboard NOC (truy cap tu PC-Management / may quan ly qua IP):
#     http://<controller-ip>:8080/
#       vi du:  http://10.1.99.10:8080/
#  (cung port 8080 voi ofctl_rest - ca hai app dung chung WSGI cua Ryu,
#   cac endpoint /noc/* va /stats/* deu nam tren 8080)
#  REST API NOC (JSON, northbound - dung cho kha cau / branch):
#     GET /noc/switches      -> danh sach switch + trang thai ket noi
#     GET /noc/ports         -> chi tiet port: rate rxpkt/txbytes..., %util
#     GET /noc/congestion    -> danh sach canh bao tac nghen
#     GET /noc/topology      -> topo campless the de ve (port noi nao dau)
#     GET /noc/summary       -> tong hop (switch up, tong BW, so canh bao)
#     GET /noc/history       -> lich su mau (bao cho bieu do theo thoi gian)
#
#  Chay chung voi app chinh va ofctl_rest:
#     ryu-manager --ofp-tcp-listen-port 6653 \
#         /root/ryu-app/campus_switch_13.py \
#         /root/ryu-app/campus_noc_monitor.py \
#         ryu.app.ofctl_rest
#  (Dashboard + REST NOC nam tren port 8080 chung voi ofctl_rest)
# =====================================================================

import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
# Ban Ryu tren controller la phien ban cu -> WSGI nam o ryu.app.wsgi
# (khong phai ryu.lib.wsgi). Dang ky route bang mapper.connect nhu ofctl_rest.
from ryu.app.wsgi import (
    WSGIApplication, ControllerBase, Response,
)

# Ten + vai tro switch cho dashboard (khong thu topo .unl)
SWITCH_INFO = {
    5:  {'name': 'Dist-SW1',  'role': 'Distribution', 'datacenter': 'Site100'},
    8:  {'name': 'Dist-SW2',  'role': 'Distribution', 'datacenter': 'Site100'},
    68: {'name': 'Access-SW1', 'role': 'Access',      'datacenter': 'Site100'},
    66: {'name': 'Access-SW2', 'role': 'Access',      'datacenter': 'Site100'},
    70: {'name': 'Access-SW3', 'role': 'Access',      'datacenter': 'Site100'},
    69: {'name': 'Access-SW4', 'role': 'Access',      'datacenter': 'Site100'},
}

# Thoi gian poll (giay) - dieu chinh cho phu hop tan suat
POLL_INTERVAL = 5
# Lich su gio lai bao nhieu mau (POLL_INTERVAL * HISTORY_LEN giay)
HISTORY_LEN = 300

# Cong suat port duoi 1 Gbps bi xem la "toc do thap" (bit/s) - chi de chuan hoa
MIN_PORT_SPEED = 100 * 1000 * 1000  # 100 Mbps

# Nguong tac nghen (ly thuyet dem demo): %su dung BW >= CONGEST_LOW
CONGEST_LOW = 70.0
CONGEST_HIGH = 90.0


class CampusNocMonitor(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(CampusNocMonitor, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        try:
            mapper = wsgi.mapper
            wsgi.registory['NocController'] = {'monitor': self}
            _r = dict(controller=NocController, conditions=dict(method=['GET']))
            mapper.connect('noc', '/noc/switches', action='switches', **_r)
            mapper.connect('noc', '/noc/ports', action='ports', **_r)
            mapper.connect('noc', '/noc/congestion', action='congestion', **_r)
            mapper.connect('noc', '/noc/topology', action='topology', **_r)
            mapper.connect('noc', '/noc/summary', action='summary', **_r)
            mapper.connect('noc', '/noc/history', action='history', **_r)
            mapper.connect('noc', '/', action='index', **_r)
            self.logger.info('NOC: WSGI routes registered on ryu.app.wsgi')
        except Exception as e:
            self.logger.warning('NOC: wsgi register fail: %s', e)

        # Trang thai switch
        self.switches = {}      # dpid -> datapath
        self.up_time = {}       # dpid -> thoi diem ket noi (monotonic)

        # Du lieu port dang thu thap
        self.port_name = {}     # dpid -> {port_no: name}
        self.port_speed = {}    # dpid -> {port_no: speed bit/s}
        self.port_stats = {}    # dpid -> {port_no: OFPPortStats (gan nhat)}
        self.prev_ts = {}       # dpid -> time.time() cua lan poll truoc
        self.port_prev = {}     # dpid -> {port_no: OFPPortStats (lan truoc)}
        self.rate = {}          # dpid -> {port_no: {'rx': bps-bps, 'tx': bps-bps, 'rxpkt':, 'txpkt':, 'rxerr':, 'txerr':, 'rxdrop':, 'txdrop':}}

        # Lich su (moi phan tu la snapshot toan bo)
        self.history = []       # list of {'ts':, 'switches': {dpid: {'rx':total-rx-bps, 'tx':total-tx-bps, 'ports':N}}}

        self.congestion = {}    # dpid -> {port_no: {'util':%, 'level':, 'ts':, 'name':}}

        # Lock de dat du lieu an toan vao history
        self._lock = hub.semaphore.Semaphore(1) if hasattr(hub, 'semaphore') else hub.Semaphore(1)

        self.monitor_thread = hub.spawn(self._monitor)

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        self.logger.info('NOC: switch %s ket noi', dpid)
        if dpid in self.switches:
            self.logger.warning('NOC: switch %s da ton tai, bo qua', dpid)
            return
        self.switches[dpid] = dp
        self.up_time[dpid] = time.time()
        self.port_name.setdefault(dpid, {})
        self.port_speed.setdefault(dpid, {})
        self.port_stats.setdefault(dpid, {})
        self.port_prev.setdefault(dpid, {})
        self.rate.setdefault(dpid, {})
        self.congestion.setdefault(dpid, {})

        parser = dp.ofproto_parser
        req = parser.OFPPortDescStatsRequest(datapath=dp, flags=0)
        dp.send_msg(req)
        # poll port stats ngay
        self._request_port_stats(dp)

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc_stats_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        if dpid not in self.switches:
            return
        for p in ev.msg.body:
            pno = p.port_no
            # (port_no tu xau khi khong tiep nhan: p.name bytes)
            self.port_name[dpid][pno] = self._pname(p.name)
            # Toc do port: ban Ryu cu dung 'curr_speed' (kbps), ban moi dung 'cur_speed'.
            # Lay field nao co san, don vi kbps -> *1000 = bit/s.
            # Neu switch khong bao (0) -> dung max_speed, roi toi MIN_PORT_SPEED (1Gbps).
            speed_kbps = getattr(p, 'curr_speed', None)
            if not speed_kbps:
                speed_kbps = getattr(p, 'cur_speed', None)
            if not speed_kbps:
                speed_kbps = getattr(p, 'max_speed', 0)
            self.port_speed[dpid][pno] = (speed_kbps or (MIN_PORT_SPEED / 1000)) * 1000.0
        self.logger.info('NOC: PORTDESC %s: %d port', dpid, len(ev.msg.body))

    def _pname(self, name):
        if isinstance(name, bytes):
            return name.decode('utf-8', 'replace')
        return name

    # -----------------------------------------------------------------
    def _request_port_stats(self, dp):
        parser = dp.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath=dp, flags=0, port_no=dp.ofproto.OFPP_ANY)
        dp.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        if dpid not in self.switches:
            return
        now = time.time()
        prev_ts = self.prev_ts.get(dpid)
        for p in ev.msg.body:
            pno = p.port_no
            if pno >= 0xffff0000:   # bo cac port ao (LOCAL)
                continue
            pname = self.port_name.get(dpid, {}).get(pno, str(pno))
            # tinh rate khac lan truoc
            pr = self.port_prev.get(dpid, {}).get(pno)
            rate = {'rx': 0, 'tx': 0, 'rxpkt': 0, 'txpkt': 0,
                    'rxerr': 0, 'txerr': 0, 'rxdrop': 0, 'txdrop': 0}
            rate['rx'] = max(0, self._rate(p.rx_bytes, pr.rx_bytes if pr else None, prev_ts, now))
            rate['tx'] = max(0, self._rate(p.tx_bytes, pr.tx_bytes if pr else None, prev_ts, now))
            rate['rxpkt'] = max(0, self._rate(p.rx_packets, pr.rx_packets if pr else None, prev_ts, now))
            rate['txpkt'] = max(0, self._rate(p.tx_packets, pr.tx_packets if pr else None, prev_ts, now))
            rate['rxerr'] = max(0, self._rate(p.rx_errors, pr.rx_errors if pr else None, prev_ts, now))
            rate['txerr'] = max(0, self._rate(p.tx_errors, pr.tx_errors if pr else None, prev_ts, now))
            rate['rxdrop'] = max(0, self._rate(p.rx_dropped, pr.rx_dropped if pr else None, prev_ts, now))
            rate['txdrop'] = max(0, self._rate(p.tx_dropped, pr.tx_dropped if pr else None, prev_ts, now))
            rate['rxbytes_total'] = p.rx_bytes
            rate['txbytes_total'] = p.tx_bytes
            self.rate[dpid][pno] = rate
            # phat hien tac nghen
            speed = self.port_speed.get(dpid, {}).get(pno, 0)
            self._detect_congestion(dpid, pno, pname, rate, speed)
        # luu lan poll nay lam "lan truoc"
        self.port_prev[dpid] = {p.port_no: p for p in ev.msg.body if p.port_no < 0xffff0000}
        self.prev_ts[dpid] = now

    @staticmethod
    def _rate(cur, prev, prev_ts, now):
        if prev is None or prev_ts is None:
            return 0
        dt = now - prev_ts
        if dt <= 0:
            return 0
        return (cur - prev) / dt

    def _detect_congestion(self, dpid, pno, pname, rate, speed):
        speed = speed or MIN_PORT_SPEED
        util = max((rate['rx'] + rate['tx']) / speed * 100.0, 0.0)
        if util >= CONGEST_HIGH:
            level = 'HIGH'
        elif util >= CONGEST_LOW:
            level = 'WARN'
        else:
            level = 'OK'
        self.congestion[dpid][pno] = {
            'util': round(util, 2),
            'level': level,
            'name': pname,
            'rx': rate['rx'],
            'tx': rate['tx'],
            'ts': time.time(),
        }

    # -----------------------------------------------------------------
    def _monitor(self):
        # Cap nhat lich su theo chu ky
        while True:
            snap = self._snapshot()
            self._lock.acquire()
            try:
                self.history.append(snap)
                if len(self.history) > HISTORY_LEN:
                    self.history = self.history[-HISTORY_LEN:]
            finally:
                self._lock.release()
            hub.sleep(1)   # lich su 1 giaay (bang thong tron de hinh duoc)

    def _snapshot(self):
        total_rx = 0
        total_tx = 0
        ports = 0
        cnt = {'5': 0, '8': 0, '68': 0, '66': 0, '70': 0, '69': 0}
        for dpid, dp in self.switches.items():
            d = self.rate.get(dpid, {})
            rx = sum(v['rx'] for v in d.values())
            tx = sum(v['tx'] for v in d.values())
            total_rx += rx
            total_tx += tx
            ports += len(d)
        return {
            'ts': time.time(),
            'switches': list(self.switches.keys()),
            'total_rx': total_rx,
            'total_tx': total_tx,
            'ports': ports,
        }

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dpid = ev.datapath.id
        if ev.state == DEAD_DISPATCHER:
            for m in (self.switches, self.up_time, self.port_name,
                      self.port_speed, self.port_stats, self.prev_ts,
                      self.port_prev, self.rate, self.congestion):
                m.pop(dpid, None)
            self.logger.info('NOC: switch %s ngat ket noi', dpid)

    # =================================================================
    # HAM XAY DU LIEU CHO REST (truy xuat tu NocController)
    # =================================================================
    def get_switches(self):
        out = []
        for dpid, dp in self.switches.items():
            info = SWITCH_INFO.get(dpid, {'name': str(dpid), 'role': 'Unknown'})
            up = time.time() - self.up_time.get(dpid, 0)
            out.append({
                'dpid': dpid,
                'name': info.get('name', dpid),
                'role': info.get('role', 'Unknown'),
                'connected': True,
                'uptime': round(up, 1),
                'ports': len(self.port_name.get(dpid, {})),
                'datapath': dp.id,
            })
        return out

    def get_ports(self, dpid=None):
        out = []
        ids = [dpid] if dpid else list(self.switches.keys())
        for did in ids:
            if did not in self.switches:
                continue
            speed_map = self.port_speed.get(did, {})
            rate_map = self.rate.get(did, {})
            name_map = self.port_name.get(did, {})
            for pno in sorted(name_map.keys()):
                if pno >= 0xffff0000:
                    continue
                r = rate_map.get(pno, {})
                speed = speed_map.get(pno, 0)
                util = 0.0
                if speed:
                    util = (r.get('rx', 0) + r.get('tx', 0)) / speed * 100.0
                out.append({
                    'dpid': did,
                    'port': pno,
                    'name': name_map.get(pno, str(pno)),
                    'speed': speed,
                    'rx': r.get('rx', 0),
                    'tx': r.get('tx', 0),
                    'rxbytes_total': r.get('rxbytes_total', 0),
                    'txbytes_total': r.get('txbytes_total', 0),
                    'rxpkt': r.get('rxpkt', 0),
                    'txpkt': r.get('txpkt', 0),
                    'rxerr': r.get('rxerr', 0),
                    'txerr': r.get('txerr', 0),
                    'rxdrop': r.get('rxdrop', 0),
                    'txdrop': r.get('txdrop', 0),
                    'util': round(util, 2),
                })
        return out

    def get_congestion(self):
        out = []
        for dpid, cp in self.congestion.items():
            if dpid not in self.switches:
                continue
            for pno, c in cp.items():
                if c['level'] in ('HIGH', 'WARN'):
                    info = SWITCH_INFO.get(dpid, {})
                    out.append({
                        'dpid': dpid,
                        'switch': info.get('name', dpid),
                        'port': pno,
                        'name': c.get('name', str(pno)),
                        'util': c['util'],
                        'level': c['level'],
                        'rx': c['rx'],
                        'tx': c['tx'],
                        'ts': c.get('ts', 0),
                    })
        # sap xep muc do nghiem trong truoc
        out.sort(key=lambda x: (-(x['level'] == 'HIGH'), -x['util']))
        return out

    def get_topology(self):
        # Mo ta topo campless (chi tiet lien ket duoc khai trong switch .sh)
        # Dist-SW1(5)/Dist-SW2(8) noi Access + Core. Access noi 2 hop len Dist.
        # Dong ban: du lieu lich su de ve (ta chi tra ve danh sach lien ke)
        links = [
            {'src': 5, 'dst': 8},
            {'src': 5, 'dst': 68}, {'src': 5, 'dst': 66},
            {'src': 5, 'dst': 70}, {'src': 5, 'dst': 69},
            {'src': 8, 'dst': 68}, {'src': 8, 'dst': 66},
            {'src': 8, 'dst': 70}, {'src': 8, 'dst': 69},
        ]
        return {
            'switches': self.get_switches(),
            'links': links,
        }

    def get_summary(self):
        switches = self.get_switches()
        ports = self.get_ports()
        cong = self.get_congestion()
        total_rx = sum(p['rx'] for p in ports)
        total_tx = sum(p['tx'] for p in ports)
        up = len(switches)
        return {
            'switches_up': up,
            'switches_total': len(SWITCH_INFO),
            'ports': len(ports),
            'ports_up': len([p for p in ports if (p['rx'] + p['tx']) > 0]),
            'total_rx': total_rx,
            'total_tx': total_tx,
            'congestion_high': len([c for c in cong if c['level'] == 'HIGH']),
            'congestion_warn': len([c for c in cong if c['level'] == 'WARN']),
        }

    def get_history(self):
        self._lock.acquire()
        try:
            return list(self.history)
        finally:
            self._lock.release()


class NocController(ControllerBase):
    def __init__(self, req, resp, data, **kwargs):
        super(NocController, self).__init__(req, resp, data, **kwargs)
        self.monitor = data['monitor']

    @staticmethod
    def panic(detail):
        body = '{ "status": "error", "message": "%s" }' % detail
        return Response(content_type='application/json', body=body.encode(), status=400)

    def switches(self, req, **kwargs):
        return _json(self.monitor.get_switches())

    def ports(self, req, **kwargs):
        dpid = None
        try:
            v = (req.GET.get('dpid') or '').strip()
            if v:
                dpid = int(v)
        except (ValueError, AttributeError):
            dpid = None
        return _json(self.monitor.get_ports(dpid))

    def congestion(self, req, **kwargs):
        return _json(self.monitor.get_congestion())

    def topology(self, req, **kwargs):
        return _json(self.monitor.get_topology())

    def summary(self, req, **kwargs):
        return _json(self.monitor.get_summary())

    def history(self, req, **kwargs):
        return _json(self.monitor.get_history())

    # Dashboard HTML - GET /
    def index(self, req, **kwargs):
        return Response(content_type='text/html', body=DASHBOARD_HTML.encode('utf-8'))


def _json(obj):
    import json
    return Response(content_type='application/json',
                    body=json.dumps(obj).encode('utf-8'))


# =====================================================================
#  DASHBOARD HTML - self-contained, dung Chart.js (CDN)
#  Truy cap tu PC-Management:  http://10.1.99.10:8080/
# =====================================================================
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Campus SDN - NOC Monitoring</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0b1220;--panel:#111a2e;--border:#1f2b44;--text:#c8d4f0;--muted:#7a89ad;
--accent:#3aa0ff;--ok:#22c55e;--warn:#f59e0b;--high:#ef4444;}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;background:var(--bg);color:var(--text)}
header{background:linear-gradient(90deg,#101a30,#0c1526);padding:14px 24px;display:flex;
align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)}
header h1{margin:0;font-size:18px;font-weight:600;letter-spacing:.5px}
header .hdr-sub{color:var(--muted);font-size:12px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;
font-size:12px;font-weight:600;border:1px solid var(--border)}
.pill .dot{width:8px;height:8px;border-radius:50%}
.dot-ok{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.main{padding:20px 24px;display:grid;grid-template-columns:260px 1fr;gap:20px}
.grid-kpi{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.kpi .lab{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.kpi .val{font-size:22px;font-weight:700;margin-top:6px}
.kpi .sub{font-size:11px;color:var(--muted);margin-top:4px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:20px}
.card h2{margin:0 0 12px;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase}
.badge{display:inline-block;padding:2px 9px;border-radius:6px;font-size:11px;font-weight:700}
.badge-ok{background:rgba(34,197,94,.15);color:var(--ok)}
.badge-warn{background:rgba(245,158,11,.15);color:var(--warn)}
.badge-high{background:rgba(239,68,68,.15);color:var(--high)}
.bar{height:6px;background:#0a1322;border-radius:4px;overflow:hidden;min-width:80px}
.bar>span{display:block;height:100%;border-radius:4px}
.sidebar .sw-item{padding:9px 12px;border-radius:8px;margin-bottom:8px;border:1px solid var(--border);
font-size:13px;display:flex;justify-content:space-between;align-items:center}
.sw-item .s-name{font-weight:600}
.sw-item .s-role{font-size:11px;color:var(--muted)}
.sw-up{color:var(--ok);font-size:13px}
.sw-down{color:var(--high);font-size:13px}
@media(max-width:1100px){.main{grid-template-columns:1fr}.sidebar{order:2}}
</style>
</head>
<body>
<header>
  <div>
    <h1>&#128230; Campus SDN - NOC Live Dashboard</h1>
    <div class="hdr-sub" id="hdr-status">Dang ket noi toi controller...</div>
  </div>
  <span class="pill"><span class="dot dot-ok"></span><span id="live-text">LIVE</span></span>
</header>

<div class="main">

  <div class="sidebar">
    <div class="card">
      <h2>Switches</h2>
      <div id="sw-list">Dang tai...</div>
    </div>
    <div class="card">
      <h2>Canh bao nghen</h2>
      <div id="cong-list">Khong co tac nghen</div>
    </div>
  </div>

  <div>
    <div class="grid-kpi">
      <div class="kpi"><div class="lab">Tong luong Rx</div><div class="val" id="kpi-rx">0</div><div class="sub">Mbps hien tai</div></div>
      <div class="kpi"><div class="lab">Tong luong Tx</div><div class="val" id="kpi-tx">0</div><div class="sub">Mbps hien tai</div></div>
      <div class="kpi"><div class="lab">Switch Online</div><div class="val" id="kpi-sw">0/6</div><div class="sub">dang ket noi</div></div>
      <div class="kpi"><div class="lab">Tac nghen</div><div class="val" id="kpi-cong">0</div><div class="sub">warn/high</div></div>
    </div>

    <div class="card">
      <h2>Bang thong tong (Rx / Tx)</h2>
      <canvas id="chart-traffic" style="height:240px"></canvas>
    </div>

    <div class="card">
      <h2>Chi tiet port - phan bo luu luong</h2>
      <table>
        <thead><tr><th>Switch</th><th>Port</th><th>Rx (Mbps)</th><th>Tx (Mbps)</th><th>Util</th><th>Status</th></tr></thead>
        <tbody id="port-table"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const fmtB=(b)=>{if(b>=1e9)return (b/1e9).toFixed(2)+' Gbps';if(b>=1e6)return (b/1e6).toFixed(2)+' Mbps';if(b>=1e3)return (b/1e3).toFixed(1)+' Kbps';return b+' bps'};
const fmtMbps=(b)=>((b)/1e6).toFixed(2);
const utilColor=(u)=>u>=90?'var(--high)':u>=70?'var(--warn)':'var(--ok)';

let trafficChart=null;
async function jget(url){const r=await fetch(url);if(!r.ok)throw new Error(url+' '+r.status);return r.json()}

async function refresh(){
  try{
    const sum=await jget('/noc/summary');
    const sw=await jget('/noc/switches');
    const ports=await jget('/noc/ports');
    const cong=await jget('/noc/congestion');
    const hist=await jget('/noc/history');

    document.getElementById('hdr-status').textContent=
      'Cap nhat '+new Date().toLocaleTimeString()+' - Controller 10.1.99.10:8080';
    document.getElementById('kpi-rx').textContent=fmtMbps(sum.total_rx);
    document.getElementById('kpi-tx').textContent=fmtMbps(sum.total_tx);
    document.getElementById('kpi-sw').textContent=sum.switches_up+'/'+sum.switches_total;
    document.getElementById('kpi-cong').textContent=(sum.congestion_high+sum.congestion_warn);

    // sidebar switch list
    document.getElementById('sw-list').innerHTML=sw.map(s=>
      '<div class="sw-item"><div><div class="s-name">'+s.name+'</div>'+
      '<div class="s-role">'+s.role+' - dpid '+s.dpid+'</div></div>'+
      '<span class="sw-up">&#9679;</span></div>').join('');

    // congestion list
    let chtml='<table><thead><tr><th>Switch</th><th>Port</th><th>Util</th><th></th></tr></thead><tbody>'+
      cong.map(c=>'<tr><td>'+c.switch+'</td><td>'+c.name+'</td><td>'+c.util.toFixed(1)+'%</td>'+
      '<td><span class="badge badge-'+c.level.toLowerCase()+'">'+c.level+'</span></td></tr>').join('')+
      '</tbody></table>';
    document.getElementById('cong-list').innerHTML=cong.length?chtml:'<span style="color:var(--ok)">Khong co tac nghen</span>';

    // port table
    document.getElementById('port-table').innerHTML=ports.map(p=>{
      const info=sw.find(x=>x.dpid===p.dpid)||{name:p.dpid};
      return '<tr><td>'+info.name+' ('+p.dpid+')</td><td>'+p.name+'</td>'+
        '<td>'+fmtMbps(p.rx)+'</td><td>'+fmtMbps(p.tx)+'</td>'+
        '<td><div class="bar"><span style="width:'+Math.min(100,p.util)+'%;background:'+utilColor(p.util)+'"></span></div></td>'+
        '<td><span class="badge badge-'+((p.util>=90)?'high':(p.util>=70)?'warn':'ok')+'">'+p.util.toFixed(1)+'%</span></td></tr>'
    }).join('');

    if(!trafficChart){
      trafficChart=new Chart(document.getElementById('chart-traffic'),{
        type:'line',
        data:{labels:[],datasets:[
          {label:'Rx',data:[],borderColor:'var(--accent)',backgroundColor:'rgba(58,160,255,.15)',fill:true,tension:.3,borderWidth:2},
          {label:'Tx',data:[],borderColor:'var(--ok)',backgroundColor:'rgba(34,197,94,.12)',fill:true,tension:.3,borderWidth:2}
        ]},
        options:{responsive:true,maintainAspectRatio:false,animation:false,
          plugins:{legend:{labels:{color:'var(--text)'}}},
          scales:{x:{ticks:{color:'var(--muted)'},grid:{color:'var(--border)'}},
                  y:{beginAtZero:true,ticks:{color:'var(--muted)',callback:v=>Math.floor(v)+'M'},grid:{color:'var(--border)'}}}}
      });
    }
    const h=hist.slice(-60);
    trafficChart.data.labels=h.map(x=>new Date(x.ts*1000).toLocaleTimeString());
    trafficChart.data.datasets[0].data=h.map(x=>+(x.total_rx/1e6).toFixed(2));
    trafficChart.data.datasets[1].data=h.map(x=>+(x.total_tx/1e6).toFixed(2));
    trafficChart.update();
  }catch(e){
    document.getElementById('hdr-status').textContent='Loi ket noi: '+e.message;
  }
}
refresh();
setInterval(refresh,3000);
</script>
</body>
</html>
"""
