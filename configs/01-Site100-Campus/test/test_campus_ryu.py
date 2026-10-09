"""Kiem thu tich hop campus_switch_13.py voi parser OpenFlow 1.3 THAT cua Ryu
(khong can eventlet/controller): datapath gia gom moi send_msg.

Can thu vien Ryu (thu muc chua goi 'ryu') + netaddr, six trong PYTHONPATH:
    PYTHONPATH=<ryu_lib>;<deps> python test/test_campus_ryu.py
"""
import collections
import os
import sys
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

# ---- stub app_manager + hub (khong can eventlet) ----
import ryu  # noqa: E402
base = types.ModuleType('ryu.base')
am = types.ModuleType('ryu.base.app_manager')


class _Guard(object):
    """Thuoc tinh noi bo cua RyuApp that: app ghi de se lam hong Ryu."""
    def put(self, *a):
        pass


class RyuApp(object):
    RESERVED = ('CONF', '_event_stop', '_events_sem', 'event_handlers', 'events',
                'is_active', 'main_thread', 'name', 'network', 'observers', 'threads')

    def __init__(self, *a, **k):
        import logging
        self.logger = logging.getLogger('test')
        self.events = _Guard()

    def __setattr__(self, k, v):
        if k in RyuApp.RESERVED and k in self.__dict__:
            raise AssertionError('app ghi de thuoc tinh noi bo RyuApp: %s' % k)
        object.__setattr__(self, k, v)


am.RyuApp = RyuApp
am.lookup_service_brick = lambda name: None
base.app_manager = am
sys.modules['ryu.base'] = base
sys.modules['ryu.base.app_manager'] = am
hubmod = types.ModuleType('ryu.lib.hub')
hubmod.spawn = lambda *a, **k: None
hubmod.sleep = lambda s: None
sys.modules['ryu.lib.hub'] = hubmod
import ryu.lib  # noqa: E402
ryu.lib.hub = hubmod
ctl = types.ModuleType('ryu.controller')
evm = types.ModuleType('ryu.controller.ofp_event')
for n in ('EventOFPSwitchFeatures', 'EventOFPPortDescStatsReply', 'EventOFPPacketIn',
          'EventOFPStateChange', 'EventOFPPortStatus', 'EventOFPBarrierReply',
          'EventOFPFlowStatsReply', 'EventOFPPortStatsReply', 'EventOFPTableStatsReply'):
    setattr(evm, n, n)
hdl = types.ModuleType('ryu.controller.handler')
hdl.MAIN_DISPATCHER, hdl.DEAD_DISPATCHER, hdl.CONFIG_DISPATCHER = 'main', 'dead', 'config'
hdl.set_ev_cls = lambda *a, **k: (lambda f: f)
ctl.ofp_event, ctl.handler = evm, hdl
sys.modules.update({'ryu.controller': ctl, 'ryu.controller.ofp_event': evm,
                    'ryu.controller.handler': hdl})

from ryu.ofproto import ofproto_v1_3 as ofp, ofproto_v1_3_parser as parser  # noqa: E402
from ryu.lib.packet import packet, ethernet, arp, vlan, ipv4, icmp  # noqa: E402
import campus_switch_13 as cs  # noqa: E402

# ---- stub ryu.app.wsgi (that can webob/eventlet) cho campus_noc_monitor ----
wsgimod = types.ModuleType('ryu.app.wsgi')


class _CtlBase(object):
    def __init__(self, req, resp, data, **kw):
        pass


class _Resp(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


wsgimod.WSGIApplication, wsgimod.ControllerBase, wsgimod.Response = object, _CtlBase, _Resp
sys.modules['ryu.app.wsgi'] = wsgimod
import campus_noc_monitor as nm  # noqa: E402


class FakeWsgi(object):
    class mapper(object):
        @staticmethod
        def connect(*a, **k):
            pass
    registory = {}

PORTS = {5: ['ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9', 'ens10', 'patch-mgmt'],
         8: ['ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9', 'ens10', 'patch-mgmt'],
         68: ['ens4', 'ens5', 'ens6', 'ens7', 'patch-mgmt'],
         66: ['ens4', 'ens5', 'ens6', 'ens7', 'patch-mgmt'],
         70: ['ens4', 'ens5', 'ens6', 'ens7', 'patch-mgmt'],
         69: ['ens4', 'ens5', 'ens6', 'ens7', 'patch-mgmt']}


class FakeDP(object):
    def __init__(self, dpid):
        self.id = dpid
        self.ofproto = ofp
        self.ofproto_parser = parser
        self.sent = []
        self.xid = 100
        self.is_active = True

    def set_xid(self, msg):
        self.xid += 1
        msg.set_xid(self.xid)
        return self.xid

    def send_msg(self, msg):
        if msg.xid is None:
            self.set_xid(msg)
        msg.serialize()             # bat loi dong goi OpenFlow that su
        self.sent.append(msg)

    def flows(self, cls=parser.OFPFlowMod):
        return [m for m in self.sent if isinstance(m, cls)]


class Ev(object):
    def __init__(self, msg, **kw):
        self.msg = msg
        self.__dict__.update(kw)


def portdesc(dp):
    body = []
    for i, name in enumerate(PORTS[dp.id], 1):
        body.append(parser.OFPPort(port_no=i, hw_addr='00:50:06:00:%02x:%02x' % (dp.id, i),
                                   name=name.encode(), config=0, state=0, curr=0,
                                   advertised=0, supported=0, peer=0, curr_speed=1000000,
                                   max_speed=1000000))
    msg = parser.OFPPortDescStatsReply(dp)
    msg.body = body
    return Ev(msg)


class PacketIn(object):
    def __init__(self, dp, in_port, data):
        self.datapath = dp
        self.match = {'in_port': in_port}
        self.data = data
        self.buffer_id = ofp.OFP_NO_BUFFER


class CampusRyuTest(unittest.TestCase):
    def setUp(self):
        cs.STATE_DIR = cs.METRIC_DIR = os.path.join(HERE, '_tmp')
        import shutil
        shutil.rmtree(cs.STATE_DIR, ignore_errors=True)     # moi test bat dau sach (vlans/policies)
        self.app = cs.CampusSwitch13()
        self.dps = {}
        for d in cs.OVS_NODES:
            dp = FakeDP(d)
            self.dps[d] = dp
            self.app._switch_features_handler(Ev(parser.OFPSwitchFeatures(dp)))
            self.app._port_desc_handler(portdesc(dp))

    def pno(self, dpid, name):
        return self.app.port_no[dpid][name]

    def deliver_probes(self, skip=()):
        """Moi lien ket OVS<->OVS: probe tu dau a toi dau b va nguoc lai."""
        for lid, l in cs.LINKS.items():
            if lid in cs.CORE_PROBE or lid in skip:
                continue
            for src, dst in ((l['a'], l['b']), (l['b'], l['a'])):
                sdp = self.dps[src[0]]
                sdp.sent = []
                self.app._send_probe(lid, src)
                out = [m for m in sdp.sent if isinstance(m, parser.OFPPacketOut)]
                self.assertEqual(len(out), 1)
                ddp = self.dps[dst[0]]
                self.app._packet_in_handler(Ev(PacketIn(ddp, self.pno(*dst), out[0].data)))

    def deliver_core_replies(self, skip=()):
        for lid, (vid, ip, src_ip) in cs.CORE_PROBE.items():
            dpid, pname = cs.LINKS[lid]['a']
            dp = self.dps[dpid]
            dp.sent = []
            self.app._send_core_probe(lid)
            po = [m for m in dp.sent if isinstance(m, parser.OFPPacketOut)][0]
            req = packet.Packet(po.data)
            a = req.get_protocol(arp.arp)
            self.assertEqual((a.dst_ip, a.src_ip), (ip, src_ip))
            self.assertEqual(req.get_protocol(vlan.vlan).vid, vid)
            if lid in skip:
                continue
            rep = packet.Packet()
            rep.add_protocol(ethernet.ethernet(dst=a.src_mac, src='aa:bb:cc:00:00:01',
                                               ethertype=0x8100))
            rep.add_protocol(vlan.vlan(vid=vid, ethertype=0x0806))
            rep.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac='aa:bb:cc:00:00:01',
                                     src_ip=ip, dst_mac=a.src_mac, dst_ip=src_ip))
            rep.serialize()
            self.app._packet_in_handler(Ev(PacketIn(dp, self.pno(dpid, pname), rep.data)))

    # ------------------------------------------------------------------
    def test_connect_installs_guards_and_tree(self):
        self.assertEqual(self.app.root, 'C1')
        self.assertEqual(self.app.tree, {'D1-C1', 'D2-C1', 'A1-D1', 'A2-D1', 'A3-D1', 'A4-D1'})
        # Dist-SW2: moi trunk tru ens10 bi DROP data
        self.assertEqual(self.app.blocked[8], {'ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9'})
        self.assertEqual(self.app.blocked[5], {'ens8', 'ens10'})
        self.assertEqual(self.app.blocked[68], {'ens5'})
        # Guard VLAN 99 tren Dist (10/10): 2 duong len Core-SW1, khong vong qua Core
        def mg(d):
            out = {}
            name = {v: k for k, v in self.app.port_no[d].items()}
            for m in self.dps[d].flows():
                if m.cookie == cs.CK_GUARD and m.priority == cs.P_MGMT:
                    acts, vid = [], m.match['vlan_vid'] & 0xfff
                    for i in m.instructions:
                        for a in i.actions:
                            if isinstance(a, parser.OFPActionSetField):
                                vid = a.value & 0xfff
                            else:
                                acts.append((name[a.port], vid))
                    out[(name[m.match['in_port']], m.match['vlan_vid'] & 0xfff)] = sorted(acts)
            return out
        g5, g8 = mg(5), mg(8)
        I5, I8 = cs.MGMT_INTERDIST[5], cs.MGMT_INTERDIST[8]
        self.assertEqual(g5[('ens10', 99)], [])          # Core-SW2 ngoai VLAN 99 (2 router + flood = bao)
        self.assertEqual(g5[('ens4', 99)], [('ens8', I5['up']), ('ens9', 99)])   # Access -> Core + qua Dist kia
        self.assertEqual(g8[('ens4', 99)], [('ens10', 99), ('ens8', I8['up'])])
        self.assertEqual(g5[('ens9', 99)], [('ens4', 99), ('ens5', 99), ('ens6', 99), ('ens7', 99),
                                            ('ens8', I5['down']), ('patch-mgmt', 99)])
        self.assertEqual(g5[('patch-mgmt', 99)], [('ens8', 99), ('ens9', 99)])   # 2 duong: Et0/2 + qua sw8
        # sw5 -> sw8 VLAN 99 = "di len" (giong bootstrap 0xba5e): chi ra cong Core
        self.assertEqual(g8[('ens8', 99)], [('ens10', 99)])
        self.assertEqual(g5[('ens8', I8['up'])], [('ens9', 99)])
        self.assertEqual(g8[('ens8', I5['down'])], [('ens4', 99), ('ens5', 99), ('ens6', 99), ('ens7', 99),
                                                    ('patch-mgmt', 99)])   # xuong: patch + Access, khong ra Core
        self.assertEqual(g5[('ens8', 99)], [('ens4', 99), ('ens5', 99), ('ens6', 99), ('ens7', 99),
                                            ('patch-mgmt', 99)])     # sw8 -> sw5 VLAN 99 = xuong (nhu ban cu)
        g68 = [m for m in self.dps[68].flows() if m.priority == cs.P_MGMT]
        self.assertEqual(g68, [])           # Access khong co guard 99 (flow co dinh 0xba5f)
        # Xoa bootstrap Dist (cookie 0xba5e) va flow cu cookie 0
        dels = [m for m in self.dps[5].flows() if m.command == ofp.OFPFC_DELETE]
        # Guard KHONG bao gio bi xoa (chi ghi de): dut ket noi giua chung khong lam mat VLAN 99
        self.assertFalse(any(m.cookie == cs.CK_GUARD for m in dels))
        self.assertTrue(any(m.cookie == cs.CK_BOOT_DIST for m in dels))
        self.assertTrue(any(m.cookie == 0 for m in dels))

    def test_probes_mark_links_and_cut_reroutes(self):
        now = time.time()
        self.deliver_probes()
        self.deliver_core_replies()
        for lid in cs.LINKS:
            self.assertIs(self.app._eval_link(lid, time.time()), True, lid)
        # Mo phong cat A1-D1 kieu silent: flow drop 65500 tren CA HAI dau
        for dp in self.dps.values():
            dp.sent = []
        self.app.api_link_test('A1-D1', 'down', 'silent')
        cuts = [(d, m) for d, dp in self.dps.items() for m in dp.flows()
                if m.priority == cs.P_TEST_CUT]
        self.assertEqual(sorted(d for d, _ in cuts), [5, 68])
        # Probe khong qua duoc A1-D1 -> het han -> cay doi
        self.app.seen[('A1-D1', 'a')] = now - 10
        self.app.seen[('A1-D1', 'b')] = now - 10
        self.app.probe_since['A1-D1'] = now - 10
        for dp in self.dps.values():
            dp.sent = []
        self.app._liveness_loop_once = None
        up = self.app._eval_link('A1-D1', time.time())
        self.assertIs(up, False)
        self.app._set_link('A1-D1', False, time.time(), 'test')
        self.assertIn('A1-D2', self.app.tree)
        self.assertNotIn('A1-D1', self.app.tree)
        self.assertEqual(self.app.blocked[68], {'ens4'})
        # Thu tu an toan tren Access-SW1: ADD chan ens4 truoc DELETE_STRICT mo ens5
        seq = [m for m in self.dps[68].flows() if m.priority == cs.P_BLOCK]
        self.assertEqual(seq[0].command, ofp.OFPFC_ADD)
        self.assertEqual(seq[-1].command, ofp.OFPFC_DELETE_STRICT)
        # Barrier gui toi cac switch co thay doi; hoan tat khi du reply
        ev = [e for e in self.app.event_log if e['kind'] == 'link_down'][-1]
        self.assertNotIn('done', ev)
        for d, dp in self.dps.items():
            for b in dp.flows(parser.OFPBarrierRequest):
                rep = parser.OFPBarrierReply(dp)
                rep.xid = b.xid
                self.app._barrier_reply_handler(Ev(rep))
        self.assertTrue(ev.get('done'))
        self.assertIsNotNone(ev.get('converge_ms'))
        self.assertIsNotNone(ev.get('total_ms'))   # moc kich hoat = luc bam mo phong

    @staticmethod
    def sim_vlan99(origin, dead_links=(), dead_nodes=(), reflect=True, override=None):
        """Mo phong 1 khung broadcast VLAN 99 qua MGMT_RULES (Dist), 0xba5f (Access) va
        Core-SW1 (flood ra moi cong VLAN 99 tru cong vao). origin: dpid OVS hoac 'C1'.
        Tra ve (so ban toi Core-SW1, so ban Core nhan lai khung do chinh no flood,
        Counter ban toi patch tung OVS, so ban bi flow reflect chan). Loi neu vong."""
        peer = {}
        for lid, l in cs.LINKS.items():
            if lid in dead_links or l['a'][0] in dead_nodes or l['b'][0] in dead_nodes:
                continue
            peer[l['a']] = l['b']
            peer[l['b']] = l['a']
        rules = {d: {(src, vid): outs for src, vid, outs in cs.MGMT_RULES[d]} for d in cs.DIST}
        rules.update(override or {})
        core_ports = [(d, cs.DIST_CORE[d]) for d in cs.DIST]
        res = {'core': 0, 'core_echo': 0, 'patch': collections.Counter(), 'reflect': 0}
        queue, steps = [], 0

        def emit(node, port, vid, from_core):
            nxt = peer.get((node, port))
            if nxt is None:
                return
            if nxt[0] == 'C1':
                res['core'] += 1
                if from_core:
                    res['core_echo'] += 1
                    return
                for cp in core_ports:              # Core flood ra cong VLAN 99 con lai
                    if cp in peer and peer[cp][1] != nxt[1]:
                        queue.append((cp[0], cp[1], vid, True))
                return
            if nxt[0] == 'C2':
                raise AssertionError('VLAN 99 toi Core-SW2 qua %s.%s' % (node, port))
            queue.append((nxt[0], nxt[1], vid, from_core))

        if origin == 'C1':
            for cp in core_ports:
                if cp in peer:
                    queue.append((cp[0], cp[1], 99, True))
        elif origin in cs.DIST:
            for port, vid in rules[origin][(cs.MGMT_PORT, 99)]:
                emit(origin, port, vid, False)
        else:
            for port in ('ens4', 'ens5'):
                emit(origin, port, 99, False)
        while queue:
            steps += 1
            if steps > 500:
                raise AssertionError('vong VLAN 99 (origin %s)' % origin)
            node, port, vid, from_core = queue.pop(0)
            if node not in cs.DIST:                # Access: uplink -> patch (0xba5f)
                res['patch'][node] += 1
                continue
            if (reflect and from_core and port == cs.DIST_CORE[node] and origin != 'C1'):
                res['reflect'] += 1                # eth_src = MAC quan tri OVS -> drop
                continue
            for oport, ovid in rules[node].get((port, vid), []):
                if oport == cs.MGMT_PORT:
                    res['patch'][node] += 1
                else:
                    emit(node, oport, ovid, from_core)
        return res

    def test_mgmt_vlan99_loop_free(self):
        """VLAN 99 (10/10): khong vong, Core-SW1 KHONG BAO GIO nhan lai khung no flood
        (-> khong thay BPDU cua chinh no -> khong Backup/Dispute), khong phan xa ve OVS
        nguon, khong toi Core-SW2; moi OVS co 2 duong toi Core."""
        sim = self.sim_vlan99
        down = sim('C1')
        self.assertEqual(down['core_echo'], 0)
        for d in cs.OVS_NODES:                      # Dist: 2 ban, Access: 4 ban (huu han)
            self.assertEqual(down['patch'][d], 2 if d in cs.DIST else 4, (d, dict(down['patch'])))
        for o in cs.OVS_NODES:
            r = sim(o)
            self.assertEqual(r['core'], 2 if o in cs.DIST else 4, (o, r))   # nhieu duong doc lap
            self.assertEqual(r['patch'][o], 0, (o, r))      # khong quay ve nguon
        # Khong co flow reflect thi khung OVS bi Core flood quay ve chinh no (ly do co flow)
        self.assertGreater(self.sim_vlan99(68, reflect=False)['patch'][68], 0)

    def test_mgmt_vlan99_survives_any_single_failure(self):
        """Mat bat ky 1 lien ket / 1 Dist: moi OVS con song van toi Core-SW1 va nhan
        duoc khung tu Core - KHONG can STP hay controller chuyen mach."""
        cases = [({lid}, ()) for lid in cs.LINKS] + [((), (5,)), ((), (8,))]
        for links, nodes in cases:
            down = self.sim_vlan99('C1', links, nodes)
            self.assertEqual(down['core_echo'], 0)
            for o in cs.OVS_NODES:
                if o in nodes:
                    continue
                self.assertGreaterEqual(self.sim_vlan99(o, links, nodes)['core'], 1, (links, nodes, o))
                self.assertGreaterEqual(down['patch'][o], 1, (links, nodes, o))
        # Hong kep A4-D1 + D2-C1 (kich ban S5): Access-SW4 chi con ens5 -> sw8 -> T -> sw5 -> Et0/2
        two = {'A4-D1', 'D2-C1'}
        self.assertEqual(self.sim_vlan99(69, two)['core'], 1)
        self.assertGreaterEqual(self.sim_vlan99('C1', two)['patch'][69], 1)
        self.assertEqual(self.sim_vlan99('C1', two)['core_echo'], 0)

    def test_mgmt_vlan99_bootstrap_compatible(self):
        """Dist vua khoi dong lai chi co bootstrap 0xba5e (flood VLAN 99 giua cac cong
        trong CAMPUS_BOOTSTRAP99_PORTS, KHONG co ens9/ens10 len Core voi Dist-SW1) trong
        khi Dist kia da co flow moi: Dist do van toi Core-SW1 -> noi lai controller."""
        def boot(ports):
            return {(p, 99): [(q, 99) for q in ports if q != p] for p in ports}
        b5 = boot(['patch-mgmt', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8'])   # Dist-SW1.env
        b8 = boot(['patch-mgmt', 'ens8', 'ens10'])                           # Dist-SW2.env
        r = self.sim_vlan99(5, override={5: b5})
        self.assertGreaterEqual(r['core'], 1)
        self.assertEqual(self.sim_vlan99('C1', override={5: b5})['core_echo'], 0)
        self.assertGreaterEqual(self.sim_vlan99('C1', override={5: b5})['patch'][5], 1)
        old5 = {('ens8', 99): [('patch-mgmt', 99), ('ens9', 99)],
                ('patch-mgmt', 99): [('ens8', 99), ('ens9', 99)]}           # guard ban 09/10
        self.assertGreaterEqual(self.sim_vlan99(5, override={5: old5})['core'], 1)
        self.assertGreaterEqual(self.sim_vlan99('C1', override={5: old5})['patch'][5], 1)
        self.assertGreaterEqual(self.sim_vlan99(8, override={8: b8})['core'], 1)
        self.assertEqual(self.sim_vlan99('C1', override={8: b8})['core_echo'], 0)
        self.assertGreaterEqual(self.sim_vlan99('C1', override={8: b8})['patch'][8], 1)

    def test_reflect_flows_from_arp(self):
        arp_text = ('IP address       HW type     Flags       HW address            Mask     Device\n'
                    '10.1.99.11       0x1         0x2         50:00:00:05:00:01     *        ens3\n'
                    '10.1.99.21       0x1         0x2         50:00:00:44:00:01     *        ens3\n'
                    '10.1.99.22       0x1         0x0         00:00:00:00:00:00     *        ens3\n'
                    '10.1.99.1        0x1         0x2         aa:bb:cc:00:00:01     *        ens3\n')
        self.assertTrue(self.app._refresh_mgmt_macs(arp_text))
        self.assertEqual(self.app.mgmt_mac, {5: '50:00:00:05:00:01', 68: '50:00:00:44:00:01'})
        self.assertFalse(self.app._refresh_mgmt_macs(arp_text))
        self.dps[8].sent = []
        self.app._install_reflect(self.dps[8])
        fl = [m for m in self.dps[8].flows() if m.cookie == cs.CK_REFLECT]
        self.assertEqual(len(fl), 2)
        self.assertTrue(all(m.priority == cs.P_REFLECT and m.instructions == [] and
                            m.match['in_port'] == self.pno(8, 'ens10') for m in fl))
        self.dps[8].sent = []
        self.app._install_reflect(self.dps[8])          # da cai -> khong gui lai
        self.assertEqual(self.dps[8].flows(), [])

    def test_control_loss_not_link_down(self):
        """Cat D2-C1 lam mat VLAN 99 toi moi OVS: khong duoc ket luan lien ket chet."""
        self.deliver_probes()
        self.deliver_core_replies()
        self.app.api_link_test('D2-C1', 'down', 'silent')
        pm = [m for m in self.dps[8].sent if isinstance(m, parser.OFPPortMod)]
        self.assertEqual(pm[-1].config, ofp.OFPPC_NO_RECV | ofp.OFPPC_NO_FWD)  # chan 2 chieu
        self.app.api_link_test('D1-D2', 'down', 'silent')
        cut = [m for m in self.dps[8].flows() if m.priority == cs.P_TEST_CUT]
        self.assertEqual(cut[0].hard_timeout, cs.CUT_MAX)       # OVS-OVS: tu het han tren switch
        self.app.test_cut['D2-C1']['expires'] = 0               # het han -> controller bat lai cong
        self.app.api_link_test('D2-C1', 'up', 'silent')
        pm = [m for m in self.dps[8].sent if isinstance(m, parser.OFPPortMod)]
        self.assertEqual(pm[-1].config, 0)
        now = time.time()
        for k in list(self.app.seen):
            self.app.seen[k] = now - 10
        for lid in cs.LINKS:
            self.app.probe_since[lid] = now - 10
        for d in self.app.last_rx:
            self.app.last_rx[d] = now - 10                      # moi OVS im lang
        for lid in cs.LINKS:
            self.assertIsNone(self.app._eval_link(lid, now), lid)
        self.app.last_rx[5] = now                               # sw5 con lien lac, Access im lang
        self.assertIs(self.app._eval_link('D1-C1', now), False)
        self.assertIsNone(self.app._eval_link('A1-D1', now))    # khong chan cong Access tren sw5
        for d in self.app.last_rx:
            self.app.last_rx[d] = now
        self.app.last_rx[5] = now - 10                          # chi Dist-SW1 chet -> ket luan ngay
        self.assertIs(self.app._eval_link('A1-D1', now), False)
        # 10/10: moi OVS co nhieu duong quan tri -> PortMod admin tren A1-D2 duoc phep
        r = self.app.api_link_test('A1-D2', 'down', 'admin')
        self.assertEqual(r['mode'], 'admin')

    def test_admin_mode_portmod(self):
        self.app.api_link_test('D1-C1', 'down', 'admin')
        pm = [m for m in self.dps[5].sent if isinstance(m, parser.OFPPortMod)]
        self.assertEqual(len(pm), 1)
        self.assertEqual(pm[0].config, ofp.OFPPC_PORT_DOWN)
        # OVS bao PortStatus -> lien ket chet ngay (khong cho probe)
        st = parser.OFPPortStatus(self.dps[5])
        st.desc = parser.OFPPort(port_no=self.pno(5, 'ens9'), hw_addr='00:00:00:00:00:01',
                                 name=b'ens9', config=ofp.OFPPC_PORT_DOWN, state=0, curr=0,
                                 advertised=0, supported=0, peer=0, curr_speed=0, max_speed=0)
        self.app._port_status_handler(Ev(st))
        self.assertFalse(self.app.link_state['D1-C1'])
        self.assertIn('D1-D2', self.app.tree)

    def test_dist2_dead_access_frozen(self):
        """Dist-SW2 chet -> 4 Access mat controller (VLAN 99 di qua sw8) nhung van chay:
        sw5 KHONG duoc chan cong xuong Access (truoc day: 4 VLAN mat 100%)."""
        for d in (8, 68, 66, 70, 69):
            self.app._state_change_handler(Ev(None, datapath=self.dps[d], state='dead'))
        self.assertEqual(set(self.app.switches), {5})
        self.assertEqual(self.app.tree, {'D1-C1', 'A1-D1', 'A2-D1', 'A3-D1', 'A4-D1'})
        self.assertEqual(self.app.blocked[5], {'ens8', 'ens10'})
        topo = self.app.api_topology()
        frozen = {n['name'] for n in topo['nodes'] if n['frozen']}
        self.assertEqual(frozen, {'Access-SW1', 'Access-SW2', 'Access-SW3', 'Access-SW4'})
        # Dist-SW1 chet tiep -> Access khong con duong nao: bo khoi cay
        self.app._state_change_handler(Ev(None, datapath=self.dps[5], state='dead'))
        self.assertEqual(self.app.tree, set())

    def test_controller_stall_no_false_down(self):
        """Controller khung 3 s: switch gui goi lai truoc khong duoc lam lien ket Core cua no chet gia."""
        self.deliver_probes()
        self.deliver_core_replies()
        now = time.time()
        for k in list(self.app.seen):
            self.app.seen[k] = now - 4
        for lid in cs.LINKS:
            self.app.probe_since[lid] = now - 10
        for d in self.app.last_rx:
            self.app.last_rx[d] = now - 4
        self.app.last_rx[5] = now                       # sw5 gui goi dau tien sau khi chay lai
        self.assertIs(self.app._eval_link('D1-C1', now), False)    # chua biet bi khung
        self.app._check_stall(3.0, now)
        self.assertIsNone(self.app._eval_link('D1-C1', now))
        self.assertEqual(self.app.event_log[-1]['kind'], 'controller_stall')
        later = now + cs.CORE_TIMEOUT + 0.1             # het an han, probe van khong ve -> chet that
        self.app.last_rx[5] = later
        self.assertIs(self.app._eval_link('D1-C1', later), False)
        self.app._check_stall(0.2, now)                 # tre nho: khong tinh
        self.assertEqual(self.app.stall_count, 1)

    def test_liveness_loop_link_down_is_not_stall(self):
        """Chay that _liveness_loop voi dong ho gia: lien ket chet binh thuong KHONG duoc
        bi coi la controller khung (loi 09/10: bien 'last' trung ten -> an han gia)."""
        self.deliver_probes()
        self.deliver_core_replies()
        clock = [time.time()]
        ticks = [0]

        class Stop(Exception):
            pass

        def fake_sleep(s):
            ticks[0] += 1
            if ticks[0] > 40:
                raise Stop()
            clock[0] += s
            for d in self.app.last_rx:
                self.app.last_rx[d] = clock[0]          # kenh dieu khien khoe
            for k in list(self.app.seen):
                if k[0] != 'A4-D1':
                    self.app.seen[k] = clock[0]         # moi lien ket khac van co probe
        real_time, real_sleep = cs.time.time, cs.hub.sleep
        cs.time.time, cs.hub.sleep = (lambda: clock[0]), fake_sleep
        try:
            self.app._liveness_loop()
        except Stop:
            pass
        finally:
            cs.time.time, cs.hub.sleep = real_time, real_sleep
        self.assertFalse(self.app.link_state['A4-D1'])
        self.assertEqual(self.app.stall_count, 0)
        self.assertNotIn('A4-D1', self.app.tree)

    def test_switch_down_reroutes(self):
        dp5 = self.dps[5]
        self.app._state_change_handler(Ev(None, datapath=dp5, state='dead'))
        self.assertNotIn(5, self.app.switches)
        self.assertEqual(self.app.tree, {'D2-C1', 'A1-D2', 'A2-D2', 'A3-D2', 'A4-D2'})
        self.assertEqual(self.app.blocked[8], {'ens8', 'ens9'})

    def test_l2_learning_and_flood(self):
        dp68 = self.dps[68]
        dp68.sent = []
        # VPC VLAN 10 tren Access-SW1 ens6 (khong tag) gui ARP broadcast
        p = packet.Packet()
        p.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:50:79:66:68:0e',
                                         ethertype=0x0806))
        p.add_protocol(arp.arp(src_mac='00:50:79:66:68:0e', src_ip='10.1.10.100',
                               dst_ip='10.1.10.1'))
        p.serialize()
        self.app._packet_in_handler(Ev(PacketIn(dp68, self.pno(68, 'ens6'), p.data)))
        po = [m for m in dp68.sent if isinstance(m, parser.OFPPacketOut)]
        self.assertEqual(len(po), 1)
        outs = [a.port for a in po[0].actions if isinstance(a, parser.OFPActionOutput)]
        # flood: ens7 (access VLAN 10) + ens4 (uplink thuoc cay), KHONG ens5 (bi chan)
        self.assertEqual(sorted(outs), sorted([self.pno(68, 'ens7'), self.pno(68, 'ens4')]))
        self.assertTrue(any(isinstance(a, parser.OFPActionPushVlan) for a in po[0].actions))
        # Frame VLAN 99 khong duoc controller flood
        dp68.sent = []
        q = packet.Packet()
        q.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:50:06:00:44:01',
                                         ethertype=0x8100))
        q.add_protocol(vlan.vlan(vid=99, ethertype=0x0806))
        q.add_protocol(arp.arp(src_ip='10.1.99.21', dst_ip='10.1.99.10'))
        q.serialize()
        self.app._packet_in_handler(Ev(PacketIn(dp68, self.pno(68, 'ens4'), q.data)))
        self.assertEqual([m for m in dp68.sent if isinstance(m, parser.OFPPacketOut)], [])

    def test_rarp_announce_after_reroute(self):
        dp69 = self.dps[69]
        p = packet.Packet()
        p.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:06:00:00:18:00',
                                         ethertype=0x0806))
        p.add_protocol(arp.arp(src_mac='00:06:00:00:18:00', src_ip='10.1.40.102',
                               dst_ip='10.1.40.1'))
        p.serialize()
        self.app._packet_in_handler(Ev(PacketIn(dp69, self.pno(69, 'ens7'), p.data)))
        self.assertIn((40, '00:06:00:00:18:00'), self.app.hosts)
        dp69.sent = []
        self.app._set_link('A4-D1', False, time.time(), 'test')
        po = [m for m in dp69.sent if isinstance(m, parser.OFPPacketOut)
              and packet.Packet(m.data).get_protocol(ethernet.ethernet).src == '00:06:00:00:18:00']
        self.assertEqual(len(po), 1)
        self.assertEqual(po[0].actions[0].port, self.pno(69, 'ens5'))   # uplink MOI (Dist-SW2)
        v = packet.Packet(po[0].data).get_protocol(vlan.vlan)
        self.assertEqual((v.vid, v.ethertype), (40, 0x8035))
        ev = [e for e in self.app.event_log if e['kind'] == 'link_down'][-1]
        self.assertEqual(ev['announced'], 1)

    def test_barrier_timeout_dead_switch(self):
        # sw5 chet nhung TCP chua dong: van trong self.switches, khong tra barrier
        self.app._set_link('A1-D1', False, time.time(), 'test')
        ev = [e for e in self.app.event_log if e['kind'] == 'link_down'][-1]
        for d, dp in self.dps.items():
            if d == 5:
                continue
            for b in dp.flows(parser.OFPBarrierRequest):
                rep = parser.OFPBarrierReply(dp)
                rep.xid = b.xid
                self.app._barrier_reply_handler(Ev(rep))
        self.assertNotIn('done', ev)
        op_id = [k for k, v in self.app._ops.items() if isinstance(k, tuple) and v['ev'] is ev][0]
        self.app._ops[op_id]['started'] -= 5
        self.app._finish_if_done(op_id, force=True)
        self.assertTrue(ev.get('done'))
        self.assertEqual(ev['unanswered'], ['Dist-SW1'])
        self.assertIsNotNone(ev['converge_ms'])

    def test_vlan_add_move_delete(self):
        for dp in self.dps.values():
            dp.sent = []
        ev = self.app.api_vlan_apply('add', 50, 'Phong Lab', ['Access-SW1.ens7'])
        self.assertEqual(self.app.access_cfg[68]['ens7'], 50)
        self.assertIn(50, self.app.data_vlans)
        # chi Access-SW1 bi anh huong -> 1 barrier
        self.assertEqual(len(self.dps[68].flows(parser.OFPBarrierRequest)), 1)
        self.assertEqual(self.dps[66].flows(parser.OFPBarrierRequest), [])
        self.assertIn('vlan 50', ev['core_config']['Core-SW1'])
        self.assertIn('ip address 10.1.50.2 255.255.255.0', ev['core_config']['Core-SW1'])
        self.assertIn('vrrp 50 priority 100', ev['core_config']['Core-SW2'])
        self.assertGreater(ev['core_commands'], 20)
        # khung khong tag tu ens7 -> VLAN 50: flood len uplink (tag 50), KHONG sang ens6 (VLAN 10)
        dp68 = self.dps[68]
        dp68.sent = []
        p = packet.Packet()
        p.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:50:79:66:68:13',
                                         ethertype=0x0806))
        p.add_protocol(arp.arp(src_ip='10.1.50.100', dst_ip='10.1.50.1'))
        p.serialize()
        self.app._packet_in_handler(Ev(PacketIn(dp68, self.pno(68, 'ens7'), p.data)))
        po = [m for m in dp68.sent if isinstance(m, parser.OFPPacketOut)][0]
        outs = [a.port for a in po.actions if isinstance(a, parser.OFPActionOutput)]
        self.assertEqual(outs, [self.pno(68, 'ens4')])
        vids = [a.value for a in po.actions if isinstance(a, parser.OFPActionSetField)]
        self.assertEqual(vids, [cs.OFPVID_PRESENT | 50])
        # api_vlans hien thi
        v = [x for x in self.app.api_vlans()['vlans'] if x['vid'] == 50][0]
        self.assertEqual(v['ports'], ['Access-SW1.ens7'])
        # xoa -> cong ve VLAN goc 10
        ev2 = self.app.api_vlan_apply('delete', 50)
        self.assertEqual(self.app.access_cfg[68]['ens7'], 10)
        self.assertNotIn(50, self.app.data_vlans)
        self.assertIn('no vlan 50', ev2['core_config']['Core-SW2'])
        for bad in [('add', 99), ('add', 10), ('delete', 10), ('add', 300)]:
            with self.assertRaises(ValueError):
                self.app.api_vlan_apply(bad[0], bad[1], 'x', ['Access-SW1.ens6'])
        with self.assertRaises(ValueError):
            self.app.api_vlan_apply('add', 60, 'x', ['Dist-SW1.ens4'])
        with self.assertRaises(ValueError):
            self.app.api_vlan_apply('add', 60, 'x', ['Access-SW1.ens4'])

    def test_pipeline_two_tables(self):
        f = self.dps[68].flows()
        t0_miss = [m for m in f if m.table_id == 0 and m.priority == 0 and m.cookie == cs.CK_MISS]
        t1_miss = [m for m in f if m.table_id == 1 and m.priority == 0 and m.cookie == cs.CK_MISS]
        self.assertTrue(t0_miss and isinstance(t0_miss[0].instructions[0], parser.OFPInstructionGotoTable))
        self.assertTrue(t1_miss)
        dels = [m for m in f if m.command == ofp.OFPFC_DELETE]
        self.assertTrue(all(m.table_id == ofp.OFPTT_ALL for m in dels))
        # chan cay o bang 0 voi uu tien < 45000 (flow co dinh quan tri cua Access)
        blk = [m for m in f if m.priority == cs.P_BLOCK and m.command == ofp.OFPFC_ADD]
        self.assertTrue(blk and all(m.table_id == 0 for m in blk))
        self.assertLess(cs.P_BLOCK, 45000)

    def test_policy_add_stats_delete(self):
        for dp in self.dps.values():
            dp.sent = []
        ev = self.app.api_policy_apply('add', {'name': 'Cach ly CNTT-HanhChinh', 'action': 'deny',
                                               'src': 'vlan:10', 'dst': 'vlan:40', 'proto': 'icmp',
                                               'bidir': True, 'prio': 100})
        pid = ev['policy']
        for d in cs.ACCESS:
            adds = [m for m in self.dps[d].flows() if m.command == ofp.OFPFC_ADD
                    and m.cookie == cs.CK_POLICY | pid]
            self.assertEqual(len(adds), 2)                  # hai chieu
            self.assertEqual(adds[0].priority, cs.P_POLICY + 100)
            self.assertEqual(adds[0].instructions, [])      # deny -> drop
            m = dict(adds[0].match.items())
            self.assertEqual(m['ipv4_src'], ('10.1.10.0', '255.255.255.0'))
            self.assertEqual(m['ip_proto'], 1)
        for d in cs.DIST:
            self.assertEqual([m for m in self.dps[d].flows() if m.cookie & cs.CK_POLICY_MASK == cs.CK_POLICY], [])
        # allow -> goto bang 1; tcp dport
        ev2 = self.app.api_policy_apply('add', {'action': 'allow', 'src': 'vlan:10',
                                                'dst': '10.1.90.10', 'proto': 'tcp', 'dport': 443,
                                                'prio': 200})
        a = [m for m in self.dps[68].flows() if m.cookie == cs.CK_POLICY | ev2['policy']
             and m.command == ofp.OFPFC_ADD][0]
        self.assertIsInstance(a.instructions[0], parser.OFPInstructionGotoTable)
        self.assertEqual(dict(a.match.items())['tcp_dst'], 443)
        # bo dem goi: gom tu reply cua cac Access
        for d in cs.ACCESS:
            rep = parser.OFPFlowStatsReply(self.dps[d])
            rep.flags = 0
            rep.body = [parser.OFPFlowStats(table_id=0, duration_sec=1, duration_nsec=0, priority=20100,
                                            idle_timeout=0, hard_timeout=0, flags=0,
                                            cookie=cs.CK_POLICY | pid, packet_count=5, byte_count=500,
                                            match=parser.OFPMatch(), instructions=[])]
            self.app._flow_stats_handler(Ev(rep))
        st = [r for r in self.app.api_policies() if r['id'] == pid][0]
        self.assertEqual(st['packets'], 20)
        # tat / xoa
        self.app.api_policy_apply('disable', pid=pid)
        self.assertFalse(self.app.policies[pid]['enabled'])
        self.app.api_policy_apply('delete', pid=pid)
        self.assertNotIn(pid, self.app.policies)
        for bad in [{'action': 'x'}, {'proto': 'gre'}, {'proto': 'icmp', 'dport': 22},
                    {'src': '10.1.300.0/24'}, {'prio': 5000}]:
            with self.assertRaises(ValueError):
                self.app.api_policy_apply('add', bad)
        # chinh sach duoc cai lai khi Access ket noi lai
        self.app.api_policy_apply('add', {'action': 'deny', 'src': 'vlan:20', 'dst': 'vlan:30'})
        dp70 = self.dps[70]
        dp70.sent = []
        self.app.switches.pop(70)
        self.app._port_desc_handler(portdesc(dp70))
        self.assertTrue([m for m in dp70.flows() if m.cookie & cs.CK_POLICY_MASK == cs.CK_POLICY
                         and m.command == ofp.OFPFC_ADD])

    def test_frame_from_blocked_port_ignored(self):
        dp8 = self.dps[8]
        dp8.sent = []
        p = packet.Packet()
        p.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:11:22:33:44:55',
                                         ethertype=0x8100))
        p.add_protocol(vlan.vlan(vid=10, ethertype=0x0806))
        p.add_protocol(arp.arp(src_ip='10.1.10.100', dst_ip='10.1.10.1'))
        p.serialize()
        self.app._packet_in_handler(Ev(PacketIn(dp8, self.pno(8, 'ens4'), p.data)))
        self.assertEqual([m for m in dp8.sent if isinstance(m, parser.OFPPacketOut)], [])

    def test_api_topology_shape(self):
        t = self.app.api_topology()
        self.assertEqual(t['root'], 'Core-SW1')
        self.assertEqual(len(t['links']), len(cs.LINKS))
        self.assertEqual(len(t['nodes']), 8)
        import json
        json.dumps(t)                       # phai serialize duoc cho REST


class CampusNocTest(unittest.TestCase):
    """Tab Suc khoe + Kich ban cua campus_noc_monitor (09/10/2026)."""
    setUp_switch = CampusRyuTest.setUp
    pno = CampusRyuTest.pno
    deliver_probes = CampusRyuTest.deliver_probes
    deliver_core_replies = CampusRyuTest.deliver_core_replies

    def setUp(self):
        self.setUp_switch()
        nm.SCEN_FILE = os.path.join(HERE, '_tmp', 'scenarios.json')
        nm.PERF_FILE = os.path.join(HERE, '_tmp', 'perf.json')
        if os.path.exists(nm.SCEN_FILE):
            os.remove(nm.SCEN_FILE)
        self.mon = nm.CampusNocMonitor(wsgi=FakeWsgi())
        self.mon.sw = lambda: self.app
        for d in cs.OVS_NODES:
            self.mon.switches[d] = self.dps[d]
            self.mon.up_time[d] = time.time() - 60
        self.deliver_probes()
        self.deliver_core_replies()
        now = time.time()
        for d in cs.OVS_NODES:
            self.app.last_rx[d] = now

    def test_window_stats(self):
        smp = [(100 + i * 0.1, None if 10 <= i < 15 else 1.0) for i in range(20)]
        w = nm.window_stats(smp, 100, 102, 0.1)
        self.assertEqual((w['sent'], w['lost']), (20, 5))
        self.assertAlmostEqual(w['outage_ms'], 500, delta=1)
        self.assertEqual(nm.window_stats(smp, 100, 100.9, 0.1)['outage_ms'], 0.0)

    def test_health_normal_then_dist2_dead(self):
        import json
        h = self.mon.get_health()
        json.dumps(h)
        self.assertEqual([i for i in h['issues'] if i[0] == 'bad'], [])
        self.assertEqual(h['links_up'], len(cs.LINKS))
        a1 = [r for r in h['switches'] if r['name'] == 'Access-SW1'][0]
        self.assertIn('Dist-SW2', a1['mgmt_path'])
        for d in (8, 68, 66, 70, 69):
            self.app._state_change_handler(Ev(None, datapath=self.dps[d], state='dead'))
        h = self.mon.get_health()
        rows = {r['name']: r for r in h['switches']}
        self.assertTrue(rows['Access-SW3']['frozen'])
        self.assertEqual(h['switches'][0]['mgmt_paths'], 2)      # Dist-SW1: Et0/2 + qua Dist-SW2 (lien ket song)
        self.assertTrue(any('Access-SW3 mat ket noi controller - dang giu duong cu' in i[1] for i in h['issues']))

    def test_stp_poll_and_role_warning(self):
        old_walk, old_get = nm.snmp_walk, nm.snmp_get
        coms = []

        def walk(host, com, base, limit=64):
            coms.append(com)
            if base == nm.OID_RSTP_ROLE:            # (cong, VLAN): VLAN 1 bo qua
                return {'3.1': 3, '3.99': 5, '7.99': 3, '6.99': 3}   # Et0/2 backup: co vong
            return {'3': 3, '6': 6, '7': 7}

        def get(host, com, oids, **k):
            return {oids[0]: {'3': b'Et0/2', '6': b'Et1/1', '7': b'Et1/2'}[oids[0].rsplit('.', 1)[1]]}
        nm.snmp_walk, nm.snmp_get = walk, get
        try:
            self.mon._stp_poll('10.1.99.1', 'ro')
        finally:
            nm.snmp_walk, nm.snmp_get = old_walk, old_get
        self.assertEqual(coms[0], 'ro')             # IOL khong co context community@99
        ports = {p['port']: p for p in self.mon.stp['ports']}
        self.assertEqual(sorted(ports), ['Et0/2', 'Et1/1', 'Et1/2'])
        self.assertEqual(ports['Et1/2']['link'], 'D2-C1')
        self.assertEqual(ports['Et0/2']['role'], 'backup')
        h = self.mon.get_health()
        self.assertTrue(any('Et0/2 la backup' in i[1] for i in h['issues']))
        ports['Et0/2']['role'] = 'designated'
        self.assertFalse(any('STP' in i[1] for i in self.mon.get_health()['issues']))

    def test_scenario_result_verdict_and_cut_cycle(self):
        sc = nm.SCENARIOS[1]                        # S2: A4-D1
        self.assertEqual(sc['links'], ['A4-D1'])
        e0 = max([e['id'] for e in self.app.api_events()] or [0])
        t0 = time.time()
        self.app.api_link_test('A4-D1', 'down', 'silent', max_s=40)
        self.assertIn('A4-D1', self.app.test_cut)
        self.assertFalse(self.mon._healthy())
        topo = self.app.api_topology()
        self.app.api_link_test('A4-D1', 'up', 'silent')
        self.assertEqual(self.app.test_cut, {})
        t1 = t0 + 15
        ok = nm.PingTarget('10.1.40.102', 0.1)
        bad = nm.PingTarget('10.1.10.100', 0.1)
        for i in range(300):                        # 30 s, mat 1,2 s luc cat
            ts = t0 + i * 0.1
            ok.record(ts, None if 20 <= i < 32 else 1.0)
            bad.record(ts, None if 10 <= i < 90 else 1.0)    # mat 8 s -> khong dat
        self.mon.pinger.targets = collections.OrderedDict([('10.1.40.102', ok)])
        r = self.mon._scen_result(sc, 'mo phong', t0, t1, t0 + 30, t1 + 2, e0, ['10.1.40.102'], topo)
        self.assertEqual(r['verdict'], 'DAT', r['fails'])
        self.assertAlmostEqual(r['worst_cut_ms'], 1200, delta=1)
        self.assertEqual(r['restore_ms'], 2000)
        self.mon.pinger.targets['10.1.10.100'] = bad
        r = self.mon._scen_result(sc, 'mo phong', t0, t1, t0 + 30, None, e0,
                                  ['10.1.40.102', '10.1.10.100'], topo)
        self.assertEqual(r['verdict'], 'KHONG DAT')
        self.assertEqual(len(r['fails']), 2)        # khong ve day du + gian doan 8 s
        import json
        with open(nm.SCEN_FILE) as f:
            self.assertEqual(len(json.load(f)), 2)

    def test_scenario_start_validation(self):
        with self.assertRaises(ValueError):
            self.mon.scen_start(['S9'])
        with self.assertRaises(Exception):
            self.mon.scen_start(['S1'], targets=['khong-phai-ip'])
        r = self.mon.scen_start(['S1', 'S9'], hold=1, gap=1)     # hub.spawn gia: khong chay that
        self.assertEqual(r['ids'], ['S1'])
        self.assertEqual((self.mon.scen['hold'], self.mon.scen['gap']), (5.0, 8.0))
        with self.assertRaises(ValueError):
            self.mon.scen_start(['S2'])             # dang chay


if __name__ == '__main__':
    unittest.main(verbosity=2)
