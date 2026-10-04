"""Kiem thu tich hop campus_switch_13.py voi parser OpenFlow 1.3 THAT cua Ryu
(khong can eventlet/controller): datapath gia gom moi send_msg.

Can thu vien Ryu (thu muc chua goi 'ryu') + netaddr, six trong PYTHONPATH:
    PYTHONPATH=<ryu_lib>;<deps> python test/test_campus_ryu.py
"""
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
          'EventOFPFlowStatsReply'):
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
        # Guard VLAN 99 tren Dist: luong tinh co huong, khong phan xa
        def mg(d):
            out = {}
            for m in self.dps[d].flows():
                if m.cookie == cs.CK_GUARD and m.priority == cs.P_MGMT:
                    name = {v: k for k, v in self.app.port_no[d].items()}
                    ports = [name[a.port] for i in m.instructions for a in i.actions]
                    out[name[m.match['in_port']]] = sorted(ports)
            return out
        g5, g8 = mg(5), mg(8)
        self.assertEqual(g5['ens8'], ['ens9', 'patch-mgmt'])   # du phong qua Core-SW1 Et0/2
        self.assertEqual(g5['ens10'], [])                # Core-SW2 ngoai VLAN 99 (2 router + flood = bao)
        self.assertEqual(g5['ens4'], [])                 # ban sao tu Access bi bo
        self.assertEqual(g8['ens4'], ['ens10', 'ens8', 'patch-mgmt'])  # Access -> controller
        self.assertFalse(any(p in v for v in g5.values() for p in ('ens4', 'ens5', 'ens6', 'ens7')))
        self.assertEqual(g8['ens8'], ['ens10', 'ens4', 'ens5', 'ens6', 'ens7', 'patch-mgmt'])
        self.assertIn('ens4', g8['ens10'])              # controller -> Access
        g68 = [m for m in self.dps[68].flows() if m.priority == cs.P_MGMT]
        self.assertEqual(g68, [])           # Access khong co guard 99 (flow co dinh 0xba5f)
        # Xoa bootstrap Dist (cookie 0xba5e) va flow cu cookie 0
        dels = [m for m in self.dps[5].flows() if m.command == ofp.OFPFC_DELETE]
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

    def test_mgmt_vlan99_loop_free(self):
        """Mo phong khung VLAN 99 di qua MGMT_FLOWS + lien ket OVS<->OVS: khong vong,
        khong quay ve Access nguon; den duoc 2 cong Core-SW1 (Et1/2, Et0/2), khong toi Core-SW2."""
        peer = {}
        for l in cs.LINKS.values():
            if l['b'][0] in cs.OVS_NODES:
                peer[l['a']] = l['b']
                peer[l['b']] = l['a']
        # Access: patch-mgmt -> ca 2 uplink (flow co dinh 0xba5f)
        acc = {n: {cs.MGMT_PORT: ['ens4', 'ens5']} for n in (68, 66, 70, 69)}
        flows = dict(cs.MGMT_FLOWS)
        flows.update(acc)
        for src in (68, 5, 8):
            seen, core, stack = set(), set(), [(src, p) for p in flows[src][cs.MGMT_PORT]]
            while stack:
                n, port = stack.pop()
                self.assertNotIn((n, port), seen, 'vong tai %s %s' % (n, port))
                seen.add((n, port))
                nxt = peer.get((n, port))
                if nxt is None:
                    core.add((n, port))
                    continue
                if nxt[0] == src:
                    self.fail('phan xa ve nguon %s qua %s' % (src, nxt))
                for q in flows.get(nxt[0], {}).get(nxt[1], []):
                    if q != cs.MGMT_PORT:
                        stack.append((nxt[0], q))
            self.assertTrue({(8, 'ens10'), (5, 'ens9')} <= core and (5, 'ens10') not in core, (src, core))

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
        # admin PortMod tren duong quan tri bi tu choi
        with self.assertRaises(ValueError):
            self.app.api_link_test('A1-D2', 'down', 'admin')

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
