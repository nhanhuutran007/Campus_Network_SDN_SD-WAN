# =====================================================================
#  campus_switch_13.py - App SDN quan ly toan bo L2 campus (Ryu)
#  Do an: Campus Network ket hop SDN + SD-WAN (EVE-NG)
#
#  Switch duoc quan ly (datapath-id = node-id, khai trong script .sh):
#     5  = Dist-SW1       8  = Dist-SW2
#     68 = Access-SW1    66  = Access-SW2    70 = Access-SW3    69 = Access-SW4
#  (AccessTest node 10 da xoa khoi lab 04/08/2026)
#
#  Chuc nang:
#   1) L2 switching co nhan thuc VLAN (reactive): hoc MAC theo VLAN,
#      cai flow unicast, flood trong dung VLAN (khong tron VLAN).
#      - Cac port "access" (noi PC) nhan/gan VLAN qua cau hinh OVS tag=
#        (OVS tu push VLAN o ingress, pop VLAN o egress).
#      - Cac port "trunk" mang VLAN 10,20,30,40,90,99.
#      - OVS STP phai tat vi co the chan frame truoc OpenFlow pipeline;
#        app controller chiu trach nhiem forwarding tren topology lab.
#   2) ACL proactive (demo bao mat tap trung): cai flow drop priority
#      40000 cho port trong BLOCK_PORTS ngay khi switch ket noi.
#   3) Northbound REST API: chay chung ryu.app.ofctl_rest (port 8080)
#      de truy van/cai flow tu xa (xem cuoi file).
#
#  Chay:
#     ryu-manager --ofp-tcp-listen-port 6653 /root/ryu-app/campus_switch_13.py ryu.app.ofctl_rest
# =====================================================================

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet

OFPVID_PRESENT = ofproto_v1_3.OFPVID_PRESENT


class CampusSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # VLAN di qua cac trunk cua campus (theo bang 2.2 md)
    TRUNK_VLANS = [10, 20, 30, 40, 90, 99]

    # Cau hinh port tung switch (ten port = ten trong OVS)
    #  - 'trunk' : noi Core/Dist/Access (mang TRUNK_VLANS)
    #  - 'mgmt'  : patch port sang bridge quan ly (VLAN 99)
    #  - 'access': port noi PC, ghi VLAN access cua port do
    PORT_CFG = {
        5:  {'trunk': ['ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9', 'ens10'],
             'mgmt': ['patch-mgmt'], 'access': {}},
        8:  {'trunk': ['ens4', 'ens5', 'ens6', 'ens7', 'ens8', 'ens9', 'ens10'],
             'mgmt': ['patch-mgmt'], 'access': {}},
        68: {'trunk': ['ens4', 'ens5'], 'mgmt': [], 'access': {'ens6': 10, 'ens7': 10}},
        66: {'trunk': ['ens4', 'ens5'], 'mgmt': [], 'access': {'ens6': 20, 'ens7': 20}},
        70: {'trunk': ['ens4', 'ens5'], 'mgmt': [], 'access': {'ens6': 30, 'ens7': 30}},
        69: {'trunk': ['ens4', 'ens5'], 'mgmt': [], 'access': {'ens6': 40, 'ens7': 40}},
    }

    # BLOCK_PORTS: demo ACL tap trung qua controller
    #  (dpid, ten-port) -> ly do. Port bi chan se bi DROP moi luu luong.
    #  Mac dinh de trong de tat ca VPC campus co the dung DHCP.
    #  Vi du: {(68, 'ens6'): 'Chan VPC14'}.
    BLOCK_PORTS = {}

    def __init__(self, *args, **kwargs):
        super(CampusSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}   # dpid -> {(vlan, mac): port}
        self.vlan_ports = {}    # dpid -> {vlan: set(port_no)}
        self.port_name = {}     # dpid -> {ten: port_no}
        self.access_ports = {}  # dpid -> {port_no: vlan} (port access)
        self.switches = {}      # dpid -> datapath

    # -----------------------------------------------------------------
    # Ryu 4.34: EventOFPSwitchFeatures duoc gui khi datapath o CONFIG
    # dispatcher (chi dpset nhan duoc khi dang ky MAIN_DISPATCHER).
    # Luu y: message OFPSwitchFeatures KHONG chua danh sach port
    # (ev.msg.ports khong ton tai trong OF1.3/Ryu 4.34) -> phai hoi
    # port desc stats truoc khi xay dung cau hinh port.
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        self.switches[dpid] = dp
        self.mac_to_port[dpid] = {}
        self.logger.info('Switch %s connect, requesting port desc', dpid)
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        # Table-miss bat buoc trong fail_mode=secure: gui frame chua co flow
        # len controller de sinh EventOFPPacketIn. OFPCML_NO_BUFFER tranh loi
        # buffer_id cua mot so phien ban OVS khi controller gui PacketOut.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        instructions = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions)]
        table_miss = parser.OFPFlowMod(datapath=dp, priority=0,
                                       match=match,
                                       instructions=instructions)
        dp.send_msg(table_miss)

        req = parser.OFPPortDescStatsRequest(datapath=dp, flags=0)
        dp.send_msg(req)

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc_stats_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        if dpid not in self.switches:
            return

        cfg = self.PORT_CFG.get(dpid)
        if cfg is None:
            self.logger.warning('Switch %s khong co trong PORT_CFG', dpid)
            cfg = {'trunk': [], 'mgmt': [], 'access': {}}

        name2no = {}
        for p in ev.msg.body:
            pname = p.name.decode('utf-8', 'replace') if isinstance(p.name, bytes) else p.name
            name2no[pname] = p.port_no
        self.port_name[dpid] = name2no
        self.logger.info('PORTDESC %s: %s', dpid, sorted(name2no.keys()))

        vlans = {}
        for v in self.TRUNK_VLANS:
            vlans[v] = set()
        for pname in cfg.get('trunk', []):
            pno = name2no.get(pname)
            if pno is None:
                continue
            for v in self.TRUNK_VLANS:
                vlans[v].add(pno)
        for pname in cfg.get('mgmt', []):
            pno = name2no.get(pname)
            if pno is None:
                continue
            vlans[99].add(pno)
        access = {}
        for pname, v in cfg.get('access', {}).items():
            pno = name2no.get(pname)
            if pno is None:
                continue
            vlans.setdefault(v, set()).add(pno)
            access[pno] = v

        self.vlan_ports[dpid] = vlans
        self.access_ports[dpid] = access

        self.logger.info('Switch %s san sang: %s', dpid,
                         {v: sorted(p) for v, p in vlans.items()})
        self._install_block_rules(dp)

    # -----------------------------------------------------------------
    def _install_block_rules(self, dp):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        name2no = self.port_name.get(dp.id, {})
        for (dpid, pname), reason in self.BLOCK_PORTS.items():
            if dpid != dp.id:
                continue
            pno = name2no.get(pname)
            if pno is None:
                self.logger.warning('BLOCK: khong tim thay port %s', pname)
                continue
            match = parser.OFPMatch(in_port=pno)
            instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, [])]
            mod = parser.OFPFlowMod(datapath=dp, priority=40000,
                                    match=match, instructions=instructions)
            dp.send_msg(mod)
            self.logger.info('DA CHAN port %s (%s) tren switch %s: %s',
                             pname, pno, dpid, reason)

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        src = eth.src
        dst = eth.dst

        vlan_vid = msg.match.get('vlan_vid')
        vlan = (vlan_vid & 0x0fff) if vlan_vid else 0
        if vlan == 0:
            vlan = self.access_ports.get(dpid, {}).get(in_port, 0)

        if vlan == 0:
            vlan_vid = 0            # khong tag
        else:
            vlan_vid = OFPVID_PRESENT | vlan

        table = self.mac_to_port.setdefault(dpid, {})
        table[(vlan, src)] = in_port

        out_port = table.get((vlan, dst))
        if out_port is not None and out_port != in_port:
            actions = [parser.OFPActionOutput(out_port)]
            instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst,
                                    eth_src=src, vlan_vid=vlan_vid)
            mod = parser.OFPFlowMod(datapath=dp, priority=1, match=match,
                                    instructions=instructions, buffer_id=msg.buffer_id)
            dp.send_msg(mod)
            if msg.buffer_id == ofproto.OFP_NO_BUFFER:
                out = parser.OFPPacketOut(datapath=dp, buffer_id=ofproto.OFP_NO_BUFFER,
                                          in_port=in_port, actions=actions, data=msg.data)
                dp.send_msg(out)
            return

        # Flood trong dung VLAN (khong dung OFPP_FLOOD de khong lan VLAN)
        out_ports = self.vlan_ports.get(dpid, {}).get(vlan, set()) - {in_port}
        actions = [parser.OFPActionOutput(p) for p in sorted(out_ports)]
        if not actions:
            return
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions)
        dp.send_msg(out)

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dpid = ev.datapath.id
        if ev.state == DEAD_DISPATCHER:
            self.mac_to_port.pop(dpid, None)
            self.vlan_ports.pop(dpid, None)
            self.port_name.pop(dpid, None)
            self.access_ports.pop(dpid, None)
            self.switches.pop(dpid, None)
            self.logger.info('Switch %s ngat ket noi', dpid)

# =====================================================================
#  HUONG DAN DEMO
# =====================================================================
#  1) Tai app nay len controller va chay:
#       cp campus_switch_13.py /root/ryu-app/
#       ryu-manager --ofp-tcp-listen-port 6653 \
#           /root/ryu-app/campus_switch_13.py ryu.app.ofctl_rest
#     (ofctl_rest mo REST API northbound tai port 8080)
#
#  2) Kiem tra cac switch da ket noi:
#       tail -f /root/ryu.log
#       curl http://127.0.0.1:8080/stats/switches
#     -> tra ve danh sach datapath-id: [5, 8, 68, 66, 70, 69]
#
#  3) Xem flow do controller cai tren Access-SW1 (68):
#       curl http://127.0.0.1:8080/stats/flow/68 | python -m json.tool
#     -> co flow drop (priority 40000) cua VPC14 + cac flow unicast khi ping
#
#  4) Demo ACL tu dong: VPC14 (Access-SW1 ens6) bi CHAN toan bo -> khong
#     ping/DHCP duoc, cac VPC khac van binh thuong. Bo chan bang cach
#     them (68, 'ens6') vao BLOCK_PORTS roi khoi dong lai app.
#
#  5) Demo northbound (cai flow tu xa qua REST):
#     cai flow moi cho Access-SW2 (66) - vi du "drop toan bo trafic vlan 20":
#       curl -X POST -d '{"dpid": 66, "table_id": 0, "priority": 35000,
#            "match": {"vlan_vid": 4116},
#            "instructions": [{"type": "APPLY_ACTIONS", "actions": []}]}' \
#            http://127.0.0.1:8080/stats/flowentry/add
#     (vlan_vid 4116 = 0x1000 + 20 = OFPVID_PRESENT | 20)
#     Xoa flow do:
#       curl -X POST -d '{"dpid": 66, "table_id": 0, "priority": 35000,
#            "match": {"vlan_vid": 4116}}' \
#            http://127.0.0.1:8080/stats/flowentry/delete
#
#  6) Dong data plane tren OVS (khi controller mat, van con mang):
#       ovs-vsctl show  (xem "is_connected: true")
#       ovs-ofctl dump-flows br0  (xem flow table tren switch)
#     fail_mode=secure -> OVS chi forward theo flow cua controller
# =====================================================================
