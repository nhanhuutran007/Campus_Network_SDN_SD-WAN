# =====================================================================
#  campus_switch_13.py - App SDN dieu khien L2 campus chinh (Site 100)
#  Do an: Campus Network ket hop SDN + SD-WAN (EVE-NG)
#  Phien ban 2 (10/2026): cay du lieu tinh theo do thi + tham do lien ket
#
#  Switch (datapath-id = node-id):
#     5  = Dist-SW1        8  = Dist-SW2
#     68 = Access-SW1     66 = Access-SW2     70 = Access-SW3     69 = Access-SW4
#  Core-SW1 / Core-SW2 la IOL (khong chay OpenFlow) - la "goc" cua cay.
#
#  Chuc nang:
#   1) L2 switching theo VLAN (reactive): hoc MAC theo VLAN, flood trong
#      dung VLAN tren cac canh cua CAY DU LIEU.
#   2) Cay du lieu (data VLAN) tinh tap trung tren do thi lien ket tinh
#      (LINKS) + trang thai song/chet thuc te -> Dijkstra tu Core-SW1
#      (du phong Core-SW2). Canh ngoai cay bi DROP (priority 100).
#   3) Phat hien mat lien ket CHU DONG: probe ethertype 0x88B5 tren moi
#      lien ket OVS<->OVS (ca hai chieu) va ARP probe toi SVI Core tren
#      lien ket OVS<->Core. Trong EVE, mat lien ket/node KHONG lam cong
#      ben kia doi trang thai -> khong the chi dua vao PortStatus.
#   4) VLAN 99 (quan tri/control) KHONG phu thuoc cay: flow "guard" tinh,
#      co huong, priority 60000 tren Dist (xem MGMT_FLOWS) -> flow cu KHONG
#      BAO GIO cat duong ve controller (sua be tac FAILOVER/RECOVERY cua
#      phien ban 1) va khong phan xa khung quan tri ve chinh Access.
#   5) Nhat ky su kien + do thoi gian hoi tu: moc phat hien -> barrier
#      reply cua moi switch bi anh huong. Ghi /root/ryu-app/metrics/.
#   6) API cho campus_noc_monitor (giao dien tap trung): trang thai do
#      thi/cay, su kien, mo phong mat lien ket.
#
#  Chay:
#     ryu-manager --ofp-tcp-listen-port 6653 campus_switch_13.py \
#         campus_noc_monitor.py ryu.app.ofctl_rest
# =====================================================================

import collections
import csv
import heapq
import json
import os
import struct
import time

try:  # cho phep kiem thu logic cay ngoai Ryu (test/test_campus_tree.py)
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import (
        MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls,
    )
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, arp
    from ryu.lib.packet import vlan as vlan_pkt
    from ryu.lib import hub
    _RyuApp = app_manager.RyuApp
    OFPVID_PRESENT = ofproto_v1_3.OFPVID_PRESENT
except ImportError:  # pragma: no cover
    _RyuApp = object
    OFPVID_PRESENT = 0x1000

    def set_ev_cls(*a, **k):
        return lambda f: f
    MAIN_DISPATCHER = DEAD_DISPATCHER = CONFIG_DISPATCHER = None

    class ofp_event(object):
        EventOFPSwitchFeatures = EventOFPPortDescStatsReply = None
        EventOFPPacketIn = EventOFPStateChange = EventOFPPortStatus = None
        EventOFPBarrierReply = EventOFPFlowStatsReply = None

APP_DIR = '/root/ryu-app'
STATE_DIR = os.path.join(APP_DIR, 'state')
METRIC_DIR = os.path.join(APP_DIR, 'metrics')

# ---------------------------------------------------------------------
#  TOPO TINH (khop campus_network_sdn_sdwan.md 2.2.2 va .unl)
# ---------------------------------------------------------------------
NODE_NAMES = {
    5: 'Dist-SW1', 8: 'Dist-SW2',
    68: 'Access-SW1', 66: 'Access-SW2', 70: 'Access-SW3', 69: 'Access-SW4',
    'C1': 'Core-SW1', 'C2': 'Core-SW2',
}
DIST = (5, 8)
ACCESS = (68, 66, 70, 69)
OVS_NODES = DIST + ACCESS
MGMT_VLAN = 99
MGMT_PORT = 'patch-mgmt'
CONTROLLER_IP = '10.1.99.10'
MGMT_IP = {5: '10.1.99.11', 8: '10.1.99.12', 68: '10.1.99.21',
           66: '10.1.99.22', 70: '10.1.99.23', 69: '10.1.99.24'}

# VLAN du lieu mac dinh (VLAN them dong luu o state/vlans.json - giai doan 2)
BASE_DATA_VLANS = {10: 'Khoa CNTT', 20: 'Toan-Thong ke', 30: 'Luat',
                   40: 'Hanh chinh', 90: 'Server Farm'}
BASE_ACCESS_PORTS = {68: {'ens6': 10, 'ens7': 10}, 66: {'ens6': 20, 'ens7': 20},
                     70: {'ens6': 30, 'ens7': 30}, 69: {'ens6': 40, 'ens7': 40}}
TRUNK_PORTS = {
    5: ['ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9', 'ens10'],
    8: ['ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9', 'ens10'],
    68: ['ens4', 'ens5'], 66: ['ens4', 'ens5'], 70: ['ens4', 'ens5'],
    69: ['ens4', 'ens5'],
}
# VLAN 99 tren Dist: luong TINH, CO HUONG, KHONG PHAN XA (khong phu thuoc cay).
#  Access gui khung quan tri len CA HAI uplink (flow co dinh 0xba5f). Neu Dist
#  flood tu do, khung cua Access-SW1 di sw5 -> ens8 -> sw8 -> quay ve chinh
#  Access-SW1 qua uplink thu hai -> br-mgmt hoc sai MAC cua chinh no -> goi
#  controller gui ve bi drop ~20s (da gap 03/10/2026). Vi vay:
#   - Access <-> controller di THANG qua Dist-SW2 (Access ens5 -> sw8 -> ens10
#     -> Core-SW1); ban sao di vao Dist-SW1 bi bo.
#   - Dist-SW1 <-> controller qua inter-dist (sw5 ens8 <-> sw8 ens8).
#   - sw5.ens10 (->Core-SW2) va ens9 (Core Et0/2 khong mang 99): drop.
#  Loi ich: Dist-SW1 chet -> Access van noi controller -> Ryu chuyen du lieu
#  sang Dist-SW2 ngay (khong can co che failover rieng nhu phien ban 1).
_ACC = ['ens4', 'ens5', 'ens6', 'ens7']
MGMT_FLOWS = {
    8: {'ens10': _ACC + ['ens8', MGMT_PORT],
        'ens8': ['ens10', MGMT_PORT],
        MGMT_PORT: ['ens10', 'ens8'] + _ACC,
        'ens4': ['ens10', MGMT_PORT], 'ens5': ['ens10', MGMT_PORT],
        'ens6': ['ens10', MGMT_PORT], 'ens7': ['ens10', MGMT_PORT],
        'ens9': []},
    5: {'ens8': [MGMT_PORT],
        MGMT_PORT: ['ens8'],
        'ens4': [], 'ens5': [], 'ens6': [], 'ens7': [], 'ens9': [], 'ens10': []},
}

# Lien ket: id -> a=(dpid, port), b=(dpid|'C1'|'C2', port), w=trong so
#  Trong so chon cay binh thuong: Core-SW1 -> sw5 (ens9) va sw8 (ens10);
#  4 Access treo duoi sw5; inter-dist va Access->sw8 la du phong.
LINKS = collections.OrderedDict([
    ('D1-C1', {'a': (5, 'ens9'), 'b': ('C1', 'Et0/2'), 'w': 1}),
    ('D2-C1', {'a': (8, 'ens10'), 'b': ('C1', 'Et1/2'), 'w': 2}),
    ('D1-C2', {'a': (5, 'ens10'), 'b': ('C2', 'Et1/2'), 'w': 1}),
    ('D2-C2', {'a': (8, 'ens9'), 'b': ('C2', 'Et0/2'), 'w': 2}),
    ('D1-D2', {'a': (5, 'ens8'), 'b': (8, 'ens8'), 'w': 2}),
    ('A1-D1', {'a': (68, 'ens4'), 'b': (5, 'ens4'), 'w': 1}),
    ('A2-D1', {'a': (66, 'ens4'), 'b': (5, 'ens5'), 'w': 1}),
    ('A3-D1', {'a': (70, 'ens4'), 'b': (5, 'ens6'), 'w': 1}),
    ('A4-D1', {'a': (69, 'ens4'), 'b': (5, 'ens7'), 'w': 1}),
    ('A1-D2', {'a': (68, 'ens5'), 'b': (8, 'ens4'), 'w': 2}),
    ('A2-D2', {'a': (66, 'ens5'), 'b': (8, 'ens5'), 'w': 2}),
    ('A3-D2', {'a': (70, 'ens5'), 'b': (8, 'ens6'), 'w': 2}),
    ('A4-D2', {'a': (69, 'ens5'), 'b': (8, 'ens7'), 'w': 2}),
])
# ARP probe toi SVI Core (VLAN, IP Core, IP nguon gia - ngoai pool DHCP)
CORE_PROBE = {
    'D1-C1': (10, '10.1.10.2', '10.1.10.250'),
    'D2-C1': (99, '10.1.99.1', '10.1.99.250'),
    'D1-C2': (10, '10.1.10.3', '10.1.10.251'),
    'D2-C2': (10, '10.1.10.3', '10.1.10.252'),
}
DATA_ROOTS = ('C1', 'C2')

PROBE_ETHERTYPE = 0x88B5
PROBE_DST = '02:5d:00:00:00:01'
PROBE_SRC = '02:5d:00:00:00:02'          # probe OVS<->OVS
PROBE_MAC_BASE = '02:5d:00:00:01:'       # + chi so lien ket (ARP probe Core)
PROBE_MAC_MASK = 'ff:ff:ff:ff:ff:00'
PROBE_INTERVAL = 0.5        # giay giua 2 lan probe OVS<->OVS
CORE_PROBE_INTERVAL = 1.0   # giay giua 2 lan ARP probe toi Core
LINK_TIMEOUT = 2.0          # OVS<->OVS: ~4 probe that bai -> chet
OP_TIMEOUT = 1.0            # cho barrier toi da 1s (switch chet nhung TCP chua dong se khong tra loi)
HOST_TTL = 900              # quen host khong thay goi sau 15 phut
UP_HOLD = 1.0               # lien ket vua chet phai thay probe lien tuc >= 1s moi coi la song (chong dao dong)
CORE_TIMEOUT = 3.5          # OVS<->Core: ~3 ARP that bai -> chet

# Priority / cookie
P_PROBE = 65000
P_TEST_CUT = 65500          # mo phong cat lien ket "im lang"
P_MGMT = 60000
P_BLOCK = 40000             # chan canh ngoai cay (bang 0). Duoi 45000 = flow co dinh
                            # VLAN 99 cua Access (0xba5f) -> khong cat duong quan tri
P_POLICY = 20000            # + uu tien luat (1..999), bang 0
P_L2 = 1                    # flow unicast hoc duoc (bang 1)
T_CTRL = 0                  # bang 0: probe, quan tri, cay, CHINH SACH
T_FWD = 1                   # bang 1: chuyen tiep L2 (hoc MAC, table-miss -> controller)
CK_GUARD = 0x5d01
CK_TREE = 0x5d02
CK_TEST = 0x5d03
CK_MISS = 0x5d00
CK_POLICY = 0x5d100000      # | id luat (bo dem goi theo tung luat)
CK_POLICY_MASK = 0xfffffffffff00000
CK_BOOT_DIST = 0xba5e       # bootstrap Campus-OVS-restore.sh (Dist)
COOKIE_ALL = 0xffffffffffffffff


# ---------------------------------------------------------------------
#  LOGIC CAY (ham thuan - kiem thu duoc ngoai Ryu)
# ---------------------------------------------------------------------
def link_nodes(lid):
    l = LINKS[lid]
    return l['a'][0], l['b'][0]


def compute_data_tree(connected, link_up):
    """Tinh cay du lieu.
    connected: tap dpid OVS dang noi controller.
    link_up:   dict lid -> bool (lien ket dung duoc).
    Tra ve (root, tap lid thuoc cay, parent{node: (cha, lid)}).
    Goc = Core-SW1 neu con it nhat 1 lien ket song toi no, nguoc lai Core-SW2.
    Core khong noi L2 voi nhau -> chi dung lien ket cua goc duoc chon."""
    usable = {}
    for lid, l in LINKS.items():
        if not link_up.get(lid, False):
            continue
        a, b = link_nodes(lid)
        if a not in connected or (b not in ('C1', 'C2') and b not in connected):
            continue
        usable[lid] = l
    for root in DATA_ROOTS:
        if not any(link_nodes(lid)[1] == root for lid in usable):
            continue
        other = [r for r in DATA_ROOTS if r != root]
        edges = {lid: l for lid, l in usable.items()
                 if link_nodes(lid)[1] not in other}
        adj = collections.defaultdict(list)
        for lid, l in edges.items():
            a, b = link_nodes(lid)
            adj[a].append((b, lid, l['w']))
            adj[b].append((a, lid, l['w']))
        # Dijkstra xac dinh: (chi phi, trong so canh cuoi, id canh) nho nhat thang
        parent = {}
        done = set()
        heap = [(0, 0, '', str(root), root, None)]
        while heap:
            d, w, lid, _k, n, frm = heapq.heappop(heap)
            if n in done:
                continue
            done.add(n)
            if frm is not None:
                parent[n] = (frm, lid, w)
            for m, mlid, mw in adj[n]:
                if m not in done:
                    heapq.heappush(heap, (d + mw, mw, mlid, str(m), m, n))
        tree = set(p[1] for p in parent.values())
        return root, tree, {k: (v[0], v[1]) for k, v in parent.items()}
    return None, set(), {}


def tree_ports(tree):
    """dpid -> tap ten cong trunk dang hoat dong (thuoc cay)."""
    out = collections.defaultdict(set)
    for lid in tree:
        l = LINKS[lid]
        for end in (l['a'], l['b']):
            if end[0] in OVS_NODES:
                out[end[0]].add(end[1])
    return out


def probe_mac(lid):
    return PROBE_MAC_BASE + '%02x' % list(LINKS).index(lid)


def dpid_is_access(dpid):
    return dpid in ACCESS


def port_link(dpid, pname):
    for lid, l in LINKS.items():
        if l['a'] == (dpid, pname) or l['b'] == (dpid, pname):
            return lid
    return None


# ---------------------------------------------------------------------
class CampusSwitch13(_RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION] if _RyuApp is not object else []

    def __init__(self, *args, **kwargs):
        super(CampusSwitch13, self).__init__(*args, **kwargs)
        for d in (STATE_DIR, METRIC_DIR):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass
        self.switches = {}          # dpid -> datapath
        self.port_no = {}           # dpid -> {ten: port_no}
        self.port_hw = {}           # dpid -> {port_no: hw_addr}
        self.port_down = {}         # dpid -> set(port_no) (PortStatus link/admin down)
        self.mac_to_port = {}       # dpid -> {(vlan, mac): port}
        self.data_vlans = dict(BASE_DATA_VLANS)
        self.access_cfg = {k: dict(v) for k, v in BASE_ACCESS_PORTS.items()}
        # Trang thai lien ket: lan cuoi nhan probe theo tung chieu
        self.seen = {}              # (lid, 'a'|'b') -> ts nhan probe tai dau do
        self.probe_since = {}       # lid -> ts bat dau probe (ca 2 dau ket noi)
        self._first_seen = {}       # (lid, side) -> ts dau chuoi probe lien tuc
        self.link_state = {lid: True for lid in LINKS}   # lac quan luc khoi dong
        self.link_changed = {lid: time.time() for lid in LINKS}
        self.test_cut = {}          # lid -> mode dang mo phong
        self.core_mac = {}          # lid -> MAC SVI Core (hoc tu ARP reply)
        self.hosts = {}             # (vlan, mac) -> (dpid, cong access, ts)
        self.pktin = collections.Counter()      # dpid -> tong packet-in (tai len controller)
        self.pktin_kind = collections.Counter()  # 'probe' | 'data'
        self.policies = collections.OrderedDict()   # id -> luat
        self.policy_stats = {}      # id -> {'packets':, 'bytes':, 'ts':}
        self._stats_acc = {}        # dpid -> {pid: [pk, by]} (dang gom reply nhieu phan)
        self._stats_by_dp = {}
        self._policy_seq = 0
        self.root = None
        self.tree = set()
        self.parent = {}
        self.blocked = {}           # dpid -> set(ten cong dang bi DROP)
        self.tree_version = 0
        self.event_log = collections.deque(maxlen=500)  # KHONG dung self.events: la hang doi su kien noi bo cua RyuApp
        self._ops = {}              # xid -> op_id ; op_id -> dict
        self._op_seq = 0
        self._seq = 0
        self._pending_reason = None
        self._load_state()
        self._load_policies()
        if _RyuApp is not object:
            hub.spawn(self._probe_loop)
            hub.spawn(self._liveness_loop)
            hub.spawn(self._policy_stats_loop)

    # ================================================================
    #  Luu / nap trang thai (VLAN dong - giai doan 2 dung tiep)
    # ================================================================
    def _save_state(self):
        st = {'vlans': {str(v): n for v, n in self.data_vlans.items() if v not in BASE_DATA_VLANS},
              'access': {str(d): ports for d, ports in self.access_cfg.items()}}
        path = os.path.join(STATE_DIR, 'vlans.json')
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(st, f, indent=1, sort_keys=True)
        os.replace(tmp, path)

    def _load_state(self):
        path = os.path.join(STATE_DIR, 'vlans.json')
        try:
            with open(path) as f:
                st = json.load(f)
            for v, name in st.get('vlans', {}).items():
                self.data_vlans[int(v)] = name
            for dpid, ports in st.get('access', {}).items():
                self.access_cfg.setdefault(int(dpid), {}).update(
                    {p: int(v) for p, v in ports.items()})
        except (IOError, OSError, ValueError):
            pass

    # ================================================================
    #  Nhat ky su kien + do thoi gian
    # ================================================================
    def _event(self, kind, detail, **extra):
        self._seq += 1
        ev = {'id': self._seq, 'ts': time.time(), 'kind': kind, 'detail': detail}
        ev.update(extra)
        self.event_log.append(ev)
        self.logger.info('EVENT %s: %s %s', kind, detail,
                         {k: v for k, v in extra.items() if k.endswith('_ms')})
        return ev

    def _write_metric(self, ev):
        path = os.path.join(METRIC_DIR, 'events.csv')
        cols = ['ts', 'kind', 'detail', 'trigger', 'detect_ms', 'converge_ms',
                'total_ms', 'switches', 'flow_mods', 'tree_version', 'root']
        try:
            new = not os.path.exists(path)
            with open(path, 'a') as f:
                w = csv.writer(f)
                if new:
                    w.writerow(cols)
                w.writerow([time.strftime('%Y-%m-%d %H:%M:%S',
                                          time.localtime(ev['ts']))] +
                           [ev.get(c, '') for c in cols[1:]])
        except (IOError, OSError):
            pass

    def _start_op(self, ev, t_detect, t_trigger=None):
        self._op_seq += 1
        op = {'ev': ev, 't_detect': t_detect, 't_trigger': t_trigger,
              'pending': set(), 'mods': 0, 'switches': 0, 'xid_dpid': {},
              'last_reply': None, 'started': time.time()}
        self._ops[('op', self._op_seq)] = op
        return ('op', self._op_seq)

    def _barrier(self, dp, op_id):
        parser = dp.ofproto_parser
        req = parser.OFPBarrierRequest(dp)
        dp.set_xid(req)
        self._ops[req.xid] = op_id
        self._ops[op_id]['pending'].add(req.xid)
        self._ops[op_id]['xid_dpid'][req.xid] = dp.id
        self._ops[op_id]['switches'] += 1
        dp.send_msg(req)

    def _finish_if_done(self, op_id, force=False):
        op = self._ops.get(op_id)
        if op is None or (op['pending'] and not force):
            return
        now = time.time()
        if op['pending']:
            # Het han: chot theo reply cuoi cung nhan duoc, ghi ro switch im lang
            op['ev']['unanswered'] = sorted(NODE_NAMES.get(op['xid_dpid'][x], x)
                                            for x in op['pending'])
            for x in op['pending']:
                self._ops.pop(x, None)
            now = op['last_reply'] or now
        ev = op['ev']
        ev['converge_ms'] = round((now - op['t_detect']) * 1000, 1)
        if op['t_trigger']:
            ev['detect_ms'] = round((op['t_detect'] - op['t_trigger']) * 1000, 1)
            ev['total_ms'] = round((now - op['t_trigger']) * 1000, 1)
        ev['switches'] = op['switches']
        ev['flow_mods'] = op['mods']
        ev['done'] = True
        self.logger.info('HOI TU %s: converge=%sms total=%sms (%s switch, %s flow-mod)',
                         ev['kind'], ev.get('converge_ms'), ev.get('total_ms'),
                         op['switches'], op['mods'])
        self._write_metric(ev)
        del self._ops[op_id]

    @set_ev_cls(ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER)
    def _barrier_reply_handler(self, ev):
        op_id = self._ops.pop(ev.msg.xid, None)
        if op_id is None or op_id not in self._ops:
            return
        self._ops[op_id]['pending'].discard(ev.msg.xid)
        self._ops[op_id]['last_reply'] = time.time()
        self._finish_if_done(op_id)

    # ================================================================
    #  Ket noi switch
    # ================================================================
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        self.logger.info('Switch %s (%s) connect', dp.id, NODE_NAMES.get(dp.id))
        # Pipeline: bang 0 (kiem soat) mac dinh -> bang 1 (chuyen tiep);
        # bang 1 table-miss -> controller (L2 reactive).
        self._add_flow(dp, 0, parser.OFPMatch(), [], cookie=CK_MISS, table=T_CTRL, goto=T_FWD)
        self._add_flow(dp, 0, parser.OFPMatch(),
                       [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)],
                       cookie=CK_MISS, table=T_FWD)
        dp.send_msg(parser.OFPPortDescStatsRequest(datapath=dp, flags=0))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        if dpid not in OVS_NODES:
            self.logger.warning('Switch %s khong thuoc campus - bo qua', dpid)
            return
        ofp = dp.ofproto
        n2n, hw, down = {}, {}, set()
        for p in ev.msg.body:
            name = p.name.decode('utf-8', 'replace') if isinstance(p.name, bytes) else p.name
            n2n[name] = p.port_no
            hw[p.port_no] = p.hw_addr
            if (p.state & ofp.OFPPS_LINK_DOWN) or (p.config & ofp.OFPPC_PORT_DOWN):
                down.add(p.port_no)
        if self.switches.get(dpid) is dp and self.port_no.get(dpid) == n2n:
            # PortDesc thu hai trong cung ket noi (vd do campus_noc_monitor yeu
            # cau): chi cap nhat trang thai cong, khong cai lai guard/cay.
            self.port_hw[dpid] = hw
            self.port_down[dpid] = down
            return
        first = dpid not in self.switches
        self.switches[dpid] = dp
        self.port_no[dpid] = n2n
        self.port_hw[dpid] = hw
        self.port_down[dpid] = down
        self.mac_to_port[dpid] = {}
        self.blocked[dpid] = set()
        # Thu tu an toan: guard (quan tri + probe) TRUOC, roi xoa flow cu cua
        # phien ban truoc (cookie 0 - nguon goc be tac), roi cay.
        self._install_guards(dp)
        self._delete_cookie(dp, 0)
        self._delete_cookie(dp, CK_TREE)
        self._delete_cookie(dp, CK_TEST)
        self._delete_cookie(dp, CK_POLICY, CK_POLICY_MASK)
        self._install_policies(dp)
        now = time.time()
        for lid in LINKS:
            a, b = link_nodes(lid)
            if dpid in (a, b):
                self.probe_since[lid] = now
        if first:
            self._event('switch_up', '%s ket noi controller' % NODE_NAMES[dpid],
                        dpid=dpid)
        self._recompute('switch_up %s' % NODE_NAMES[dpid], t_detect=now, force=True)
        if dpid in DIST:
            self._delete_cookie(dp, CK_BOOT_DIST)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state != DEAD_DISPATCHER or dp.id is None:
            return
        if self.switches.get(dp.id) is not dp:
            return      # ket noi cu da bi ket noi moi thay the
        dpid = dp.id
        del self.switches[dpid]
        self.mac_to_port.pop(dpid, None)
        now = time.time()
        self._event('switch_down', '%s mat ket noi controller' % NODE_NAMES.get(dpid, dpid),
                    dpid=dpid)
        for lid in LINKS:
            if dpid in link_nodes(lid):
                self.probe_since.pop(lid, None)
        self._recompute('switch_down %s' % NODE_NAMES.get(dpid, dpid), t_detect=now)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        p = msg.desc
        down = (p.state & ofp.OFPPS_LINK_DOWN) or (p.config & ofp.OFPPC_PORT_DOWN)
        s = self.port_down.setdefault(dp.id, set())
        was = p.port_no in s
        if down:
            s.add(p.port_no)
        else:
            s.discard(p.port_no)
        if bool(down) != was:
            name = p.name.decode('utf-8', 'replace') if isinstance(p.name, bytes) else p.name
            lid = port_link(dp.id, name)
            if lid:
                self._set_link(lid, not down, time.time(),
                               'PortStatus %s.%s %s' % (NODE_NAMES.get(dp.id), name,
                                                        'down' if down else 'up'))

    # ================================================================
    #  Flow helper
    # ================================================================
    def _add_flow(self, dp, prio, match, actions, cookie=0, idle=0, table=T_CTRL,
                  goto=None):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        inst = []
        if actions:
            inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions))
        if goto is not None:
            inst.append(parser.OFPInstructionGotoTable(goto))
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=table, priority=prio, match=match,
                                      instructions=inst, cookie=cookie,
                                      idle_timeout=idle, command=ofp.OFPFC_ADD))

    def _del_strict(self, dp, prio, match, table=T_CTRL):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=table, priority=prio, match=match,
                                      command=ofp.OFPFC_DELETE_STRICT,
                                      out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))

    def _delete_cookie(self, dp, cookie, mask=COOKIE_ALL):
        """Xoa theo cookie tren MOI bang (mac dinh Ryu dung table_id=0)."""
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=ofp.OFPTT_ALL, cookie=cookie,
                                      cookie_mask=mask, command=ofp.OFPFC_DELETE,
                                      out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                      match=parser.OFPMatch()))

    def _install_guards(self, dp):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        dpid = dp.id
        n2n = self.port_no.get(dpid, {})
        self._delete_cookie(dp, CK_GUARD)
        to_ctl = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, P_PROBE, parser.OFPMatch(eth_type=PROBE_ETHERTYPE), to_ctl,
                       cookie=CK_GUARD)
        self._add_flow(dp, P_PROBE, parser.OFPMatch(
            eth_dst=(PROBE_MAC_BASE + '00', PROBE_MAC_MASK)), to_ctl, cookie=CK_GUARD)
        if dpid not in DIST:
            return      # Access: VLAN 99 do flow co dinh 0xba5f (nut la) dam nhiem
        for src, dsts in MGMT_FLOWS[dpid].items():
            if src not in n2n:
                continue
            outs = [parser.OFPActionOutput(n2n[d]) for d in dsts if d in n2n]
            self._add_flow(dp, P_MGMT, parser.OFPMatch(
                in_port=n2n[src], vlan_vid=OFPVID_PRESENT | MGMT_VLAN), outs,
                cookie=CK_GUARD)
        self.logger.info('GUARD %s: VLAN99 tinh co huong %s', NODE_NAMES[dpid],
                         {k: v for k, v in MGMT_FLOWS[dpid].items() if v})

    # ================================================================
    #  Tham do lien ket
    # ================================================================
    def _probe_loop(self):
        last_core = 0
        while True:
            hub.sleep(PROBE_INTERVAL)
            now = time.time()
            do_core = now - last_core >= CORE_PROBE_INTERVAL
            if do_core:
                last_core = now
            for lid, l in LINKS.items():
                try:
                    if lid in CORE_PROBE:
                        if do_core:
                            self._send_core_probe(lid)
                    else:
                        self._send_probe(lid, l['a'])
                        self._send_probe(lid, l['b'])
                except Exception as e:      # khong de vong probe chet
                    self.logger.debug('probe %s loi: %s', lid, e)

    def _send_probe(self, lid, end):
        dpid, pname = end
        dp = self.switches.get(dpid)
        pno = self.port_no.get(dpid, {}).get(pname)
        if dp is None or pno is None:
            return
        payload = struct.pack('!HH', dpid, pno) + lid.encode('ascii').ljust(8, b'\0')
        e = ethernet.ethernet(dst=PROBE_DST, src=PROBE_SRC, ethertype=PROBE_ETHERTYPE)
        pkt = packet.Packet()
        pkt.add_protocol(e)
        pkt.add_protocol(payload)
        pkt.serialize()
        self._packet_out(dp, pno, pkt.data)

    def _send_core_probe(self, lid):
        dpid, pname = LINKS[lid]['a']
        dp = self.switches.get(dpid)
        pno = self.port_no.get(dpid, {}).get(pname)
        if dp is None or pno is None:
            return
        vid, dst_ip, src_ip = CORE_PROBE[lid]
        mac = probe_mac(lid)
        # Broadcast lan dau; khi da biet MAC Core thi ARP unicast (khong lam
        # nhieu VLAN du lieu cua may tram moi giay).
        dst = self.core_mac.get(lid, 'ff:ff:ff:ff:ff:ff')
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(dst=dst, src=mac, ethertype=0x8100))
        pkt.add_protocol(vlan_pkt.vlan(vid=vid, ethertype=0x0806))
        pkt.add_protocol(arp.arp(opcode=arp.ARP_REQUEST, src_mac=mac, src_ip=src_ip,
                                 dst_mac='00:00:00:00:00:00', dst_ip=dst_ip))
        pkt.serialize()
        self._packet_out(dp, pno, pkt.data)

    def _packet_out(self, dp, pno, data):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                                        in_port=ofp.OFPP_CONTROLLER,
                                        actions=[parser.OFPActionOutput(pno)], data=data))

    def _probe_received(self, dpid, in_port, data, eth):
        now = time.time()
        if eth.ethertype == PROBE_ETHERTYPE:
            body = data[14:]
            if len(body) < 12:
                return
            sdpid, sport = struct.unpack('!HH', body[:4])
            lid = body[4:12].rstrip(b'\0').decode('ascii', 'replace')
            l = LINKS.get(lid)
            if l is None:
                return
            # Nhan tai dau nao? (kiem tra dung cap cong - phat hien cam nham day)
            for side, end in (('a', l['a']), ('b', l['b'])):
                if end[0] == dpid and self.port_no.get(dpid, {}).get(end[1]) == in_port:
                    self._mark_seen(lid, side, now)
            return
        # ARP reply tu Core
        pkt = packet.Packet(data)
        a = pkt.get_protocol(arp.arp)
        if a is None or a.opcode != arp.ARP_REPLY:
            return
        for lid, (vid, ip, _src) in CORE_PROBE.items():
            end = LINKS[lid]['a']
            if (end[0] == dpid and a.src_ip == ip and a.dst_mac == probe_mac(lid)
                    and self.port_no.get(dpid, {}).get(end[1]) == in_port):
                self.core_mac[lid] = a.src_mac
                self._mark_seen(lid, 'a', now)
                self._mark_seen(lid, 'b', now)

    def _mark_seen(self, lid, side, now):
        timeout = CORE_TIMEOUT if lid in CORE_PROBE else LINK_TIMEOUT
        if now - self.seen.get((lid, side), 0) > timeout:
            self._first_seen[(lid, side)] = now     # bat dau chuoi probe lien tuc moi
        self.seen[(lid, side)] = now

    def _liveness_loop(self):
        while True:
            hub.sleep(0.1)
            now = time.time()
            for op_id in [k for k in self._ops if isinstance(k, tuple)]:
                op = self._ops.get(op_id)
                if op and now - op['started'] > OP_TIMEOUT:
                    self._finish_if_done(op_id, force=True)
            for lid in LINKS:
                up = self._eval_link(lid, now)
                if up is not None and up != self.link_state[lid]:
                    last = max(self.seen.get((lid, 'a'), 0), self.seen.get((lid, 'b'), 0))
                    self._set_link(lid, up, now,
                                   'probe %s' % ('phuc hoi' if up else 'het han'),
                                   t_trigger=None if up else (last or None))

    def _eval_link(self, lid, now):
        """True/False neu da du bang chung, None neu chua (giu trang thai cu)."""
        l = LINKS[lid]
        a, b = link_nodes(lid)
        ends = [x for x in (a, b) if x in OVS_NODES]
        if any(x not in self.switches for x in ends):
            return None         # switch mat ket noi da duoc xu ly rieng
        for end in (l['a'], l['b']):
            if end[0] in OVS_NODES:
                pno = self.port_no.get(end[0], {}).get(end[1])
                if pno is None or pno in self.port_down.get(end[0], set()):
                    return False
        since = self.probe_since.get(lid)
        if since is None:
            return None
        timeout = CORE_TIMEOUT if lid in CORE_PROBE else LINK_TIMEOUT
        sides = ('a',) if lid in CORE_PROBE else ('a', 'b')
        fresh = all(now - self.seen.get((lid, s), 0) <= timeout for s in sides)
        if fresh:
            if not self.link_state.get(lid):
                first = min(self._first_seen.get((lid, s), now) for s in sides)
                if now - first < UP_HOLD:
                    return None
            return True
        if now - since <= timeout:
            return None         # moi bat dau probe, chua du thoi gian ket luan
        return False

    def _set_link(self, lid, up, now, why, t_trigger=None):
        if self.link_state.get(lid) == up:
            return
        self.link_state[lid] = up
        self.link_changed[lid] = now
        if lid in self.test_cut and up is False:
            t_trigger = self.test_cut[lid].get('ts', t_trigger)
        self._recompute('%s %s (%s)' % (lid, 'up' if up else 'down', why),
                        t_detect=now, t_trigger=t_trigger,
                        kind='link_up' if up else 'link_down', link=lid)

    # ================================================================
    #  Tinh lai + ap cay
    # ================================================================
    def _usable_links(self):
        return {lid: bool(self.link_state.get(lid)) for lid in LINKS}

    def _recompute(self, why, t_detect, t_trigger=None, force=False,
                   kind='tree', link=None):
        connected = set(self.switches)
        root, tree, parent = compute_data_tree(connected, self._usable_links())
        ports = tree_ports(tree)
        changed = (tree != self.tree or root != self.root)
        if not changed and not force:
            if kind in ('link_up', 'link_down'):
                self._event(kind, why + ' - cay khong doi', link=link,
                            tree_version=self.tree_version, root=root)
            return
        old_tree = self.tree
        self.root, self.tree, self.parent = root, tree, parent
        if changed:
            self.tree_version += 1
        ev = self._event(kind if kind != 'tree' else 'tree_change', why, link=link,
                         tree_version=self.tree_version, root=root,
                         added=sorted(tree - old_tree), removed=sorted(old_tree - tree),
                         trigger='inject' if (link in self.test_cut) else 'auto')
        op_id = self._start_op(ev, t_detect, t_trigger)
        for dpid, dp in list(self.switches.items()):
            self._apply_switch(dp, ports.get(dpid, set()), op_id, flush=changed)
        if changed:
            ev['announced'] = self._announce_hosts(ports)
            if _RyuApp is not object:
                hub.spawn(self._announce_later, ports)
        self._finish_if_done(op_id)

    def _apply_switch(self, dp, active, op_id, flush):
        parser = dp.ofproto_parser
        dpid = dp.id
        n2n = self.port_no.get(dpid, {})
        want = set(p for p in TRUNK_PORTS.get(dpid, []) if p not in active)
        have = self.blocked.get(dpid, set())
        mods = 0
        # Chan truoc, mo sau: khong bao gio co khoang thoi gian vong L2
        for name in sorted(want - have):
            pno = n2n.get(name)
            if pno is None:
                continue
            self._add_flow(dp, P_BLOCK, parser.OFPMatch(
                in_port=pno, vlan_vid=(OFPVID_PRESENT, OFPVID_PRESENT)), [],
                cookie=CK_TREE)
            mods += 1
        for name in sorted(have - want):
            pno = n2n.get(name)
            if pno is None:
                continue
            self._del_strict(dp, P_BLOCK, parser.OFPMatch(
                in_port=pno, vlan_vid=(OFPVID_PRESENT, OFPVID_PRESENT)))
            mods += 1
        if flush:
            # Vi tri MAC thay doi tren MOI switch khi cay doi (vd sw5 van tro
            # may cua Access-SW1 ve cong da chet) -> xoa flow unicast da hoc.
            self._delete_cookie(dp, 0)
            self.mac_to_port[dpid] = {}
            mods += 1
        self.blocked[dpid] = want
        op = self._ops[op_id]
        op['mods'] += mods
        if mods:
            self._barrier(dp, op_id)

    # ----------------------------------------------------------------
    #  Thong bao vi tri MAC (RARP) sau khi cay doi
    #  Core-SW1/2 la switch truyen thong: bang MAC cua no van tro host ve
    #  nhanh cu -> goi tra ve host bi day vao canh da chet cho toi khi host tu
    #  phat goi (do duoc ~11-12 s, 04/10/2026). Ky thuat chuan khi di chuyen
    #  may ao: phat RARP voi MAC nguon = MAC host, di theo duong MOI len Core.
    # ----------------------------------------------------------------
    def _announce_hosts(self, ports):
        sent = 0
        now = time.time()
        for (vlan, mac), (dpid, pno, ts) in list(self.hosts.items()):
            if now - ts > HOST_TTL:
                del self.hosts[(vlan, mac)]
                continue
            dp = self.switches.get(dpid)
            if dp is None:
                continue
            n2n = self.port_no.get(dpid, {})
            ups = [n2n[p] for p in ports.get(dpid, set()) if p in n2n]
            if not ups:
                continue
            pkt = packet.Packet()
            pkt.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src=mac,
                                               ethertype=0x8100))
            pkt.add_protocol(vlan_pkt.vlan(vid=vlan, ethertype=0x8035))
            pkt.add_protocol(arp.arp(opcode=3, src_mac=mac, src_ip='0.0.0.0',
                                     dst_mac=mac, dst_ip='0.0.0.0'))
            pkt.serialize()
            for up in ups:
                self._packet_out(dp, up, pkt.data)
                sent += 1
        return sent

    def _announce_later(self, ports):
        hub.sleep(0.3)      # lap lai 1 lan: phong khi flow moi chua kip cai xong
        self._announce_hosts(ports)

    def _data_ports(self, dpid, vlan):
        """Cong flood cho VLAN du lieu: trunk thuoc cay + access cua VLAN."""
        n2n = self.port_no.get(dpid, {})
        out = set()
        for name in TRUNK_PORTS.get(dpid, []):
            if name not in self.blocked.get(dpid, set()) and name in n2n:
                out.add(n2n[name])
        for name, v in self.access_cfg.get(dpid, {}).items():
            if v == vlan and name in n2n:
                out.add(n2n[name])
        return out

    # ================================================================
    #  Packet-in: probe + L2 theo VLAN
    # ================================================================
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        in_port = msg.match['in_port']
        self.pktin[dpid] += 1
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        if eth.ethertype == PROBE_ETHERTYPE or eth.dst.startswith(PROBE_MAC_BASE):
            self.pktin_kind['probe'] += 1
            self._probe_received(dpid, in_port, msg.data, eth)
            return
        self.pktin_kind['data'] += 1
        if dpid not in self.port_no:
            return
        n2n = self.port_no[dpid]
        access = {n2n[p]: v for p, v in self.access_cfg.get(dpid, {}).items() if p in n2n}
        trunk = set(n2n[p] for p in TRUNK_PORTS.get(dpid, []) if p in n2n)
        vtag = pkt.get_protocol(vlan_pkt.vlan)
        tagged = eth.ethertype == 0x8100 and vtag is not None
        if tagged:
            vlan = vtag.vid
        else:
            vlan = access.get(in_port, 0)
        if vlan == 0 or vlan == MGMT_VLAN or vlan not in self.data_vlans:
            return      # VLAN 99 do guard/bootstrap lo; VLAN la -> bo
        if in_port in trunk:
            name = next((k for k, v in n2n.items() if v == in_port), None)
            if name in self.blocked.get(dpid, set()):
                return  # canh ngoai cay (flow DROP chua kip cai)
        src, dst = eth.src, eth.dst
        table = self.mac_to_port.setdefault(dpid, {})
        table[(vlan, src)] = in_port
        if in_port in access:
            self.hosts[(vlan, src)] = (dpid, in_port, time.time())

        def egress(ports):
            acts, cur = [], tagged
            for p in ports:
                if p in access:
                    if cur:
                        acts.append(parser.OFPActionPopVlan())
                        cur = False
                else:
                    if not cur:
                        acts.append(parser.OFPActionPushVlan(0x8100))
                        acts.append(parser.OFPActionSetField(vlan_vid=OFPVID_PRESENT | vlan))
                        cur = True
                acts.append(parser.OFPActionOutput(p))
            return acts

        out = table.get((vlan, dst))
        if out is not None and out != in_port:
            acts = egress([out])
            m = {'in_port': in_port, 'eth_dst': dst}
            if tagged:
                m['vlan_vid'] = OFPVID_PRESENT | vlan
            self._add_flow(dp, P_L2, parser.OFPMatch(**m), acts, cookie=0, idle=300,
                           table=T_FWD)
        else:
            acts = egress(sorted(self._data_ports(dpid, vlan) - {in_port}))
        if acts:
            dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                                            in_port=in_port, actions=acts, data=msg.data))

    # ================================================================
    #  API cho campus_noc_monitor
    # ================================================================
    def api_topology(self):
        now = time.time()
        links = []
        for lid, l in LINKS.items():
            a, b = link_nodes(lid)
            ages = [now - self.seen[(lid, s)] for s in ('a', 'b') if (lid, s) in self.seen]
            links.append({
                'id': lid, 'a': [a, l['a'][1]], 'b': [b, l['b'][1]],
                'a_name': NODE_NAMES[a], 'b_name': NODE_NAMES[b], 'w': l['w'],
                'up': bool(self.link_state.get(lid)), 'in_tree': lid in self.tree,
                'probe_age': round(min(ages), 2) if ages else None,
                'since': round(now - self.link_changed.get(lid, now), 1),
                'test_cut': self.test_cut.get(lid, {}).get('mode'),
                'kind': 'core' if lid in CORE_PROBE else 'ovs',
            })
        nodes = [{'id': n, 'name': NODE_NAMES[n],
                  'role': 'Core' if n in ('C1', 'C2') else ('Distribution' if n in DIST else 'Access'),
                  'connected': (n in self.switches) if n in OVS_NODES else None,
                  'parent': NODE_NAMES.get(self.parent.get(n, (None,))[0]) if n in self.parent else None}
                 for n in list(OVS_NODES) + ['C1', 'C2']]
        return {'root': NODE_NAMES.get(self.root), 'tree_version': self.tree_version,
                'nodes': nodes, 'links': links,
                'blocked': {NODE_NAMES[d]: sorted(v) for d, v in self.blocked.items()},
                'vlans': [{'vid': v, 'name': n} for v, n in sorted(self.data_vlans.items())],
                'timers': {'probe_ms': PROBE_INTERVAL * 1000, 'link_timeout_ms': LINK_TIMEOUT * 1000,
                           'core_probe_ms': CORE_PROBE_INTERVAL * 1000,
                           'core_timeout_ms': CORE_TIMEOUT * 1000}}

    def api_counters(self):
        return {'pktin': dict(self.pktin), 'pktin_kind': dict(self.pktin_kind),
                'hosts': len(self.hosts), 'policies': len(self.policies)}

    def api_events(self, since_id=0, kinds=None):
        return [e for e in list(self.event_log)
                if e['id'] > since_id and (not kinds or e['kind'] in kinds)]

    # ================================================================
    #  VLAN dong (muc tieu 1: thoi gian them VLAN / khu vuc mang)
    # ================================================================
    def api_vlans(self):
        out = []
        for vid, name in sorted(self.data_vlans.items()):
            ports = []
            for dpid in ACCESS:
                for pname, v in sorted(self.access_cfg.get(dpid, {}).items()):
                    if v == vid:
                        ports.append('%s.%s' % (NODE_NAMES[dpid], pname))
            out.append({'vid': vid, 'name': name, 'base': vid in BASE_DATA_VLANS,
                        'ports': ports, 'subnet': '10.1.%d.0/24' % vid})
        free = {}
        for dpid in ACCESS:
            free[NODE_NAMES[dpid]] = sorted(
                p for p in self.port_no.get(dpid, {})
                if p not in TRUNK_PORTS.get(dpid, []) and p != MGMT_PORT)
        return {'vlans': out, 'access_ports': free}

    def _resolve_ports(self, ports):
        """['Access-SW1.ens7', ...] -> {dpid: [ten cong]} (chi cong access cua Access)."""
        by_name = {v: k for k, v in NODE_NAMES.items()}
        res = collections.defaultdict(list)
        for item in ports or []:
            sw, _, pname = item.partition('.')
            dpid = by_name.get(sw)
            if dpid not in ACCESS:
                raise ValueError('chi gan VLAN cho cong cua Access: %s' % item)
            if pname in TRUNK_PORTS.get(dpid, []) or pname == MGMT_PORT or not pname:
                raise ValueError('khong phai cong access: %s' % item)
            res[dpid].append(pname)
        return res

    def api_vlan_apply(self, action, vid, name='', ports=None):
        """action add|delete|ports. Tra ve su kien (thoi gian trien khai do bang
        barrier tren cac switch bi anh huong) + doan cau hinh Core can lam tay."""
        t0 = time.time()
        vid = int(vid)
        if not 2 <= vid <= 254 or vid == MGMT_VLAN:
            raise ValueError('VLAN phai trong 2..254 va khac 99 (quy uoc IP 10.1.<VLAN>.0/24)')
        if action == 'add' and vid in self.data_vlans:
            raise ValueError('VLAN %d da ton tai' % vid)
        if action in ('delete', 'ports') and vid not in self.data_vlans:
            raise ValueError('VLAN %d chua ton tai' % vid)
        if action == 'delete' and vid in BASE_DATA_VLANS:
            raise ValueError('khong xoa VLAN goc %d' % vid)
        if action not in ('add', 'delete', 'ports'):
            raise ValueError('action phai la add/delete/ports')
        target = self._resolve_ports(ports) if action != 'delete' else {}
        affected = set()
        if action == 'add':
            self.data_vlans[vid] = name or ('VLAN%d' % vid)
        if action in ('delete', 'ports'):
            for dpid in ACCESS:          # tra cac cong dang thuoc VLAN nay ve VLAN goc
                for pname in [q for q, v in self.access_cfg.get(dpid, {}).items() if v == vid]:
                    if action == 'delete' or pname not in target.get(dpid, []):
                        back = BASE_ACCESS_PORTS.get(dpid, {}).get(pname)
                        if back:
                            self.access_cfg[dpid][pname] = back
                        else:
                            self.access_cfg[dpid].pop(pname, None)
                        affected.add(dpid)
        for dpid, plist in target.items():
            for pname in plist:
                self.access_cfg.setdefault(dpid, {})[pname] = vid
                affected.add(dpid)
        label = self.data_vlans.get(vid, name)
        if action == 'delete':
            self.data_vlans.pop(vid, None)
            self.hosts = {k: v for k, v in self.hosts.items() if k[0] != vid}
        self._save_state()
        ev = self._event('vlan_' + action, 'VLAN %d (%s) %s, cong: %s' % (
            vid, label, action,
            ', '.join('%s.%s' % (NODE_NAMES[d], q) for d, pl in sorted(target.items()) for q in pl) or '-'),
            vid=vid, trigger='api')
        op_id = self._start_op(ev, t0, t0)
        for dpid in sorted(affected):
            dp = self.switches.get(dpid)
            if dp is None:
                continue
            # Doi VLAN cua cong access: xoa flow unicast da hoc (co the tro sai VLAN)
            self._delete_cookie(dp, 0)
            self.mac_to_port[dpid] = {}
            self._ops[op_id]['mods'] += 1
            self._barrier(dp, op_id)
        self._finish_if_done(op_id)
        ev['core_config'] = self.core_config(vid, label, delete=(action == 'delete'))
        ev['core_commands'] = sum(len([l for l in c.splitlines() if l.strip()])
                                  for c in ev['core_config'].values())
        return ev

    @staticmethod
    def core_config(vid, name, delete=False):
        """Doan IOS cho Core-SW1/2 (truyen thong, ngoai OpenFlow) - lam tay / script console."""
        name = ''.join(c for c in (name or 'VLAN%d' % vid).upper() if c.isalnum() or c in '-_')[:30]
        out = {}
        for core, host, prio in (('Core-SW1', 2, 150), ('Core-SW2', 3, 100)):
            if delete:
                # Thu tu an toan cho IOL (04/10/2026: day 'no interface VlanX' khi
                # Core dang la VRRP Master lam Core-SW1 IOL crash): go VRRP +
                # shutdown SVI truoc, roi OSPF, trunk, SVI, VLAN.
                lines = ['configure terminal',
                         'interface Vlan%d' % vid, ' no vrrp %d' % vid, ' shutdown',
                         'router ospf 1', ' no network 10.1.%d.0 0.0.0.255 area 0' % vid,
                         'interface Ethernet0/2', ' switchport trunk allowed vlan remove %d' % vid,
                         'interface Ethernet1/2', ' switchport trunk allowed vlan remove %d' % vid,
                         'no interface Vlan%d' % vid,
                         'no vlan %d' % vid,
                         'end', 'write memory']
            else:
                lines = ['configure terminal',
                         'vlan %d' % vid, ' name %s' % (name or 'VLAN%d' % vid),
                         'interface Ethernet0/2', ' switchport trunk allowed vlan add %d' % vid,
                         'interface Ethernet1/2', ' switchport trunk allowed vlan add %d' % vid,
                         'interface Vlan%d' % vid,
                         ' description %s - VRRP VIP 10.1.%d.1' % (name, vid),
                         ' ip address 10.1.%d.%d 255.255.255.0' % (vid, host),
                         ' vrrp %d ip 10.1.%d.1' % (vid, vid),
                         ' vrrp %d priority %d' % (vid, prio),
                         ' ip helper-address 10.1.90.10',
                         ' no shutdown',
                         'router ospf 1', ' network 10.1.%d.0 0.0.0.255 area 0' % vid,
                         'end', 'write memory']
            out[core] = chr(10).join(lines)
        return out

    # ================================================================
    #  CHINH SACH TAP TRUNG (muc tieu 5)
    #  Luat: {id, name, action: deny|allow, src, dst ('any' | 'vlan:10' |
    #  CIDR 10.1.90.0/24 | IP), proto: ip|icmp|tcp|udp, dport, bidir, prio (1-999),
    #  enabled}. Cai o bang 0 cua 4 Access (moi luong host di qua Access), khop
    #  IP: deny -> drop, allow -> goto bang 1. Cookie rieng -> bo dem goi.
    # ================================================================
    PROTO = {'ip': None, 'icmp': 1, 'tcp': 6, 'udp': 17}

    @staticmethod
    def _addr(spec):
        spec = (spec or 'any').strip().lower()
        if spec in ('any', '*', ''):
            return None
        if spec.startswith('vlan:'):
            v = int(spec.split(':', 1)[1])
            return ('10.1.%d.0' % v, '255.255.255.0')
        ip, _, plen = spec.partition('/')
        parts = [int(x) for x in ip.split('.')]
        if len(parts) != 4 or any(not 0 <= x <= 255 for x in parts):
            raise ValueError('dia chi sai: %s' % spec)
        plen = int(plen or 32)
        if not 0 <= plen <= 32:
            raise ValueError('prefix sai: %s' % spec)
        mask = (0xffffffff << (32 - plen)) & 0xffffffff
        return (ip, '.'.join(str((mask >> s) & 0xff) for s in (24, 16, 8, 0)))

    def _policy_matches(self, parser, r):
        """Tra ve danh sach OFPMatch (2 neu bidir)."""
        proto = self.PROTO[r['proto']]
        out = []
        dirs = [(r['src'], r['dst'])]
        if r.get('bidir'):
            dirs.append((r['dst'], r['src']))
        for src, dst in dirs:
            m = {'eth_type': 0x0800}
            a, b = self._addr(src), self._addr(dst)
            if a:
                m['ipv4_src'] = a
            if b:
                m['ipv4_dst'] = b
            if proto:
                m['ip_proto'] = proto
            if r.get('dport') and r['proto'] in ('tcp', 'udp'):
                m['%s_dst' % r['proto']] = int(r['dport'])
            out.append(parser.OFPMatch(**m))
        return out

    def _install_policy_rule(self, dp, r):
        if dpid_is_access(dp.id) and r.get('enabled', True):
            parser = dp.ofproto_parser
            for m in self._policy_matches(parser, r):
                if r['action'] == 'deny':
                    self._add_flow(dp, P_POLICY + int(r['prio']), m, [],
                                   cookie=CK_POLICY | r['id'], table=T_CTRL)
                else:
                    self._add_flow(dp, P_POLICY + int(r['prio']), m, [],
                                   cookie=CK_POLICY | r['id'], table=T_CTRL, goto=T_FWD)
            return len(self._policy_matches(parser, r))
        return 0

    def _install_policies(self, dp):
        for r in self.policies.values():
            self._install_policy_rule(dp, r)

    def _validate_rule(self, r):
        r = dict(r)
        r['action'] = (r.get('action') or 'deny').lower()
        if r['action'] not in ('deny', 'allow'):
            raise ValueError('action phai la deny/allow')
        r['proto'] = (r.get('proto') or 'ip').lower()
        if r['proto'] not in self.PROTO:
            raise ValueError('proto phai la ip/icmp/tcp/udp')
        r['src'] = r.get('src') or 'any'
        r['dst'] = r.get('dst') or 'any'
        self._addr(r['src'])
        self._addr(r['dst'])
        if r.get('dport'):
            r['dport'] = int(r['dport'])
            if not 1 <= r['dport'] <= 65535 or r['proto'] not in ('tcp', 'udp'):
                raise ValueError('dport chi dung voi tcp/udp, 1..65535')
        r['prio'] = int(r.get('prio') or 100)
        if not 1 <= r['prio'] <= 999:
            raise ValueError('prio 1..999 (lon hon = uu tien hon)')
        r['bidir'] = bool(r.get('bidir', False))
        r['enabled'] = bool(r.get('enabled', True))
        r['name'] = (r.get('name') or '%s %s->%s %s' % (r['action'], r['src'], r['dst'], r['proto']))[:60]
        return r

    def _save_policies(self):
        path = os.path.join(STATE_DIR, 'policies.json')
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'seq': self._policy_seq, 'rules': list(self.policies.values())}, f, indent=1)
        os.replace(tmp, path)

    def _load_policies(self):
        try:
            with open(os.path.join(STATE_DIR, 'policies.json')) as f:
                st = json.load(f)
            self._policy_seq = int(st.get('seq', 0))
            for r in st.get('rules', []):
                self.policies[int(r['id'])] = r
        except (IOError, OSError, ValueError):
            pass

    def api_policies(self):
        out = []
        for pid, r in self.policies.items():
            d = dict(r)
            d.update(self.policy_stats.get(pid, {'packets': 0, 'bytes': 0}))
            out.append(d)
        return out

    def api_policy_apply(self, action, rule=None, pid=None):
        """action add|delete|enable|disable. Ap len 4 Access, thoi gian toi barrier."""
        t0 = time.time()
        if action == 'add':
            r = self._validate_rule(rule or {})
            self._policy_seq += 1
            r['id'] = self._policy_seq
            r['created'] = t0
            self.policies[r['id']] = r
        else:
            pid = int(pid)
            if pid not in self.policies:
                raise ValueError('khong co luat %s' % pid)
            r = self.policies[pid]
            if action in ('enable', 'disable'):
                r['enabled'] = (action == 'enable')
            elif action != 'delete':
                raise ValueError('action phai la add/delete/enable/disable')
        self._save_policies()
        ev = self._event('policy_' + action, '#%d %s (%s %s -> %s %s%s%s)' % (
            r['id'], r['name'], r['action'], r['src'], r['dst'], r['proto'],
            (' :%s' % r['dport']) if r.get('dport') else '', ' hai chieu' if r.get('bidir') else ''),
            policy=r['id'], trigger='api')
        op_id = self._start_op(ev, t0, t0)
        for dpid, dp in sorted(self.switches.items()):
            if not dpid_is_access(dpid):
                continue
            self._delete_cookie(dp, CK_POLICY | r['id'])
            n = 1
            if action != 'delete' and r.get('enabled', True):
                n += self._install_policy_rule(dp, r)
            self._ops[op_id]['mods'] += n
            self._barrier(dp, op_id)
        if action == 'delete':
            del self.policies[r['id']]
            self.policy_stats.pop(r['id'], None)
            self._save_policies()
        self._finish_if_done(op_id)
        return ev

    def _policy_stats_loop(self):
        while True:
            hub.sleep(5)
            if not self.policies:
                continue
            for dpid, dp in list(self.switches.items()):
                if not dpid_is_access(dpid):
                    continue
                try:
                    parser = dp.ofproto_parser
                    dp.send_msg(parser.OFPFlowStatsRequest(
                        dp, 0, T_CTRL, dp.ofproto.OFPP_ANY, dp.ofproto.OFPG_ANY,
                        CK_POLICY, CK_POLICY_MASK, parser.OFPMatch()))
                except Exception:
                    pass

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_handler(self, ev):
        now = time.time()
        acc = self._stats_acc.setdefault(ev.msg.datapath.id, {})
        for st in ev.msg.body:
            if st.cookie & CK_POLICY_MASK != CK_POLICY:
                continue
            pid = st.cookie & ~CK_POLICY_MASK & 0xfffff
            a = acc.setdefault(pid, [0, 0])
            a[0] += st.packet_count
            a[1] += st.byte_count
        if ev.msg.flags & 0x1:          # OFPMPF_REPLY_MORE
            return
        self._stats_by_dp[ev.msg.datapath.id] = acc
        self._stats_acc[ev.msg.datapath.id] = {}
        tot = {}
        for d in self._stats_by_dp.values():
            for pid, (pk, by) in d.items():
                t = tot.setdefault(pid, [0, 0])
                t[0] += pk
                t[1] += by
        self.policy_stats = {pid: {'packets': v[0], 'bytes': v[1], 'ts': now}
                             for pid, v in tot.items()}

    def api_link_test(self, lid, action, mode='silent'):
        """Mo phong mat lien ket (danh gia muc tieu 2).
        mode 'silent': DROP moi khung vao o CA HAI dau (giong dut cap, dau
           kia khong thay link down) -> phat hien bang probe.
        mode 'admin':  OFPPortMod PORT_DOWN o dau a (OVS bao PortStatus ngay).
        action 'down' | 'up'."""
        if lid not in LINKS:
            raise ValueError('lien ket khong ton tai: %s' % lid)
        l = LINKS[lid]
        ends = [e for e in (l['a'], l['b']) if e[0] in OVS_NODES]
        now = time.time()
        if action == 'down':
            self.test_cut[lid] = {'mode': mode, 'ts': now}
            self._event('test_inject', 'Mo phong cat %s (%s)' % (lid, mode), link=lid)
        elif action == 'up':
            mode = self.test_cut.pop(lid, {}).get('mode', mode)
            self._event('test_restore', 'Khoi phuc %s (%s)' % (lid, mode), link=lid)
        else:
            raise ValueError('action phai la down/up')
        for dpid, pname in (ends if mode == 'silent' else ends[:1]):
            dp = self.switches.get(dpid)
            pno = self.port_no.get(dpid, {}).get(pname)
            if dp is None or pno is None:
                continue
            parser = dp.ofproto_parser
            ofp = dp.ofproto
            if mode == 'silent':
                m = parser.OFPMatch(in_port=pno)
                if action == 'down':
                    self._add_flow(dp, P_TEST_CUT, m, [], cookie=CK_TEST)
                else:
                    self._del_strict(dp, P_TEST_CUT, m)
            else:
                cfg = ofp.OFPPC_PORT_DOWN if action == 'down' else 0
                dp.send_msg(parser.OFPPortMod(
                    datapath=dp, port_no=pno, hw_addr=self.port_hw[dpid][pno],
                    config=cfg, mask=ofp.OFPPC_PORT_DOWN, advertise=0))
        return {'link': lid, 'action': action, 'mode': mode, 'ts': now}
