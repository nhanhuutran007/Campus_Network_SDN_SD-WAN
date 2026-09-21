# =====================================================================
#  campus_switch_13.py - App SDN quan ly toan bo L2 campus (Ryu)
#  Do an: Campus Network ket hop SDN + SD-WAN (EVE-NG)
#
#  Switch duoc quan ly (datapath-id = node-id, khai trong script .sh):
#     5  = Dist-SW1       8  = Dist-SW2
#     68 = Access-SW1    66  = Access-SW2    70 = Access-SW3    69 = Access-SW4
#
#  Chuc nang:
#   1) L2 switching co nhan thuc VLAN (reactive): hoc MAC theo VLAN,
#      cai flow unicast, flood trong dung VLAN (khong tron VLAN).
#      - table-miss -> CONTROLLER (packet-in): controller quyet dinh
#        forward tung frame, KHONG dung NORMAL cua OVS kernel (tranh MAC
#        flapping khi topology co L2 loop).
#      - Cac port "access" nhan/gan VLAN qua cau hinh OVS tag=
#        (OVS tu push VLAN o ingress, pop VLAN o egress).
#      - Cac port "trunk" mang VLAN 10,20,30,40,90,99.
# 2) L2_TREE_BLOCK: chong loop tap trung (STM central):
    #      - Cac port (dpid, ten-port) trong L2_TREE_BLOCK bi LOAI khoi tap
    #        flood cua cac VLAN data (10..90) va duoc cai flow DROP priority 100.
    #      - VLAN 99 (mgmt/control) KHONG bi chan tren cac port THUONG de giu
    #        ket noi OVS <-> Ryu, NHUNG bi chan tren cac port tao vong L2
    #        (khai trong VLAN99_TREE_BLOCK) de cho control-plane trong full-mesh
    #        (Dist inter-dist, Access dual-home, Core cheo) khong tao broadcast
    #        storm lam switch ngat/reconnect lien tuc.
    #      - Cay data va cay VLAN 99 khac nhau vi STP live tren Core/Farm:
    #          data: VPC -> Access ens4 -> sw5 ens9 -> Core-SW1
    #          vlan99: Controller -> Farm -> Core-SW1 -> sw8 ens10
    #                  -> inter-dist ens8 -> sw5 -> Access ens4
#   3) ACL proactive (demo bao mat tap trung): cai flow drop priority
#      40000 cho port trong BLOCK_PORTS ngay khi switch ket noi.
#   4) Northbound REST API: chay chung ryu.app.ofctl_rest (port 8080)
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
from ryu.lib.packet import vlan as vlan_pkt
from ryu.lib import hub

import socket
import subprocess
import time

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
        68: {'trunk': ['ens4', 'ens5'], 'mgmt': ['patch-mgmt'],
             'access': {'ens6': 10, 'ens7': 10}},
        66: {'trunk': ['ens4', 'ens5'], 'mgmt': ['patch-mgmt'],
             'access': {'ens6': 20, 'ens7': 20}},
        70: {'trunk': ['ens4', 'ens5'], 'mgmt': ['patch-mgmt'],
             'access': {'ens6': 30, 'ens7': 30}},
        69: {'trunk': ['ens4', 'ens5'], 'mgmt': ['patch-mgmt'],
             'access': {'ens6': 40, 'ens7': 40}},
    }

    # L2_TREE_BLOCK: loai bo port khoi forward data (chong L2 loop tap trung).
    #  - Khong them port nay vao tap flood cua VLAN 10..90.
    #  - Cai flow DROP (priority 100, match in_port+vlan data) cho port nay.
    #  - VLAN 99 (mgmt) luon duoc giu nguyen de OVS con ket noi controller.
    # Ly do block: topology lab co lai (Access dual-home 2 Dist + Dist-Core
    # full-mesh) ma OVS khong chay STP; neu de OVS NORMAL tu hoc MAC se
    # MAC-flapping -> uni-cast (vi du DHCP OFFER) bi day sai port -> mat goi.
    # Giai phap: controller cai "cay" tinh (CC a.k.a. spanning central).
    L2_TREE_BLOCK = {
        (68, 'ens5'):  'Access-SW1 -> Dist-SW2: canh 3 (dual-home)',
        (5, 'ens8'):   'Dist-SW1 <-> Dist-SW2: inter-dist',
        (5, 'ens10'):  'Dist-SW1 -> Core-SW2: dist chi dung Core-SW1',
        (8, 'ens4'):   'Dist-SW2 -> Access-SW1 (standby)',
        (8, 'ens5'):   'Dist-SW2 -> Access-SW2 (standby)',
        (8, 'ens6'):   'Dist-SW2 -> Access-SW3 (standby)',
        (8, 'ens7'):   'Dist-SW2 -> Access-SW4 (standby)',
        (8, 'ens8'):   'Dist-SW2 <-> Dist-SW1 inter-dist (standby)',
        (8, 'ens9'):   'Dist-SW2 -> Core-SW2 (standby data)',
        (8, 'ens10'):  'Dist-SW2 -> Core-SW1 (standby data)',
    }

    # VLAN99_TREE_BLOCK: cac port nay bi TREE-BLOCK CA VLAN 99 (mgmt/control),
    # khop voi topology "cay" du lieu. Ly do: VLAN 99 truoc day duoc flood
    # toan mesh (Access dual-home + inter-dist + 4 link Dist->Core + Core1/2
    # noi SwitchServerFarm) tao vong L2 -> broadcast storm -> OVS ngat ket
    # noi controller (sw8/sw68 ngat/reconnect lien tuc, DPSET multiple conn).
    # Live STP tren IOL chon Farm->Core-SW1 va Core-SW1->sw8.ens10 cho
    # VLAN 99; Core-SW1 Et0/2->sw5.ens9 va Farm->Core-SW2 deu bi block 99.
    # Vi vay cay mgmt that la:
    #   Controller -> Farm -> Core-SW1 -> sw8.ens10 -> sw8.ens8
    #   -> sw5.ens8 -> Access ens4.
    # Khi FAILOVER (sw5 chet), _apply_failover_switch se xoa TREE-BLOCK
    # (ca 99) de mo duong standby qua sw8.
    VLAN99_TREE_BLOCK = {
        (8, 'ens4'):   'Dist-SW2 -> Access-SW1 (mgmt standby)',
        (8, 'ens5'):   'Dist-SW2 -> Access-SW2 (mgmt standby)',
        (8, 'ens6'):   'Dist-SW2 -> Access-SW3 (mgmt standby)',
        (8, 'ens7'):   'Dist-SW2 -> Access-SW4 (mgmt standby)',
        (8, 'ens9'):   'Dist-SW2 -> Core-SW2: Farm chan nhanh Core-SW2 cho vlan99',
        (5, 'ens9'):   'Dist-SW1 -> Core-SW1: STP Core-SW1 chan vlan99 tren Et0/2',
        (5, 'ens10'):  'Dist-SW1 -> Core-SW2: khong nam trong cay mgmt',
    }

    # BLOCK_PORTS: demo ACL tap trung qua controller
    #  (dpid, ten-port) -> ly do. Port bi chan se bi DROP moi luu luong.
    BLOCK_PORTS = {}

    # FAILOVER sw5 -> sw8 (Dist-SW1 -> Dist-SW2). Mo duong standby CHI AN TOAN
    # khi sw5 THAT SU chet: neu sw5 con song ma sw8 mo duong, moi Access (dual-
    # home) noi cau 2 Dist -> L2 loop -> storm. Vi vay moi duong kich hoat
    # failover deu can BANG CHUNG DOC LAP (ping mgmt IP cua sw5 that bai), khong
    # chi dua vao socket OpenFlow (mat control-plane != mat data-plane).
    SW5_MGMT_IP = '10.1.99.11'
    PING_TRIES = 3              # so lan ping lien tiep that bai moi coi sw5 chet
    SOCKET_USER_TIMEOUT_MS = 15000   # socket khong ACK >15s -> chet (xem ben duoi)

    def __init__(self, *args, **kwargs):
        super(CampusSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}   # dpid -> {(vlan, mac): port}
        self.vlan_ports = {}    # dpid -> {vlan: set(port_no)}
        self.port_name = {}     # dpid -> {ten: port_no}
        self.access_ports = {}  # dpid -> {port_no: vlan} (port access)
        self.switches = {}      # dpid -> datapath
        self._failover_active = False   # sw5 down → sw8 standby active
        self._failover_pending = False  # sw5 reconnecting, wait portdesc
        # Startup watch: neu controller vua chay lai ma sw5 KHONG connect
        # trong ~35s -> sw5 da gap su co tu truoc (hard crash) -> kich hoat
        # failover ngay lap tuc (khong cho DEAD event, vi switch co the
        # mat tich tu truoc khi ryu-manager chay lai).
        hub.spawn(self._startup_failover_watch)
        # Liveness watch: kiem tra sw5 con song bang echo-request CHU DONG.
        # TCP keepalive (SO_KEEPALIVE) KHONG dam bao phat hien dead peer khi
        # node bi hard-stop/qemu kill (socket van ESTAB, khong co RST/FIN).
        # => app tu gui OFP_EchoRequest moi ~7s va theo doi phan hoi; neu
        # sw5 khong tra loi >= LOIVENESS_TIMEOUT thi kich hoat failover
        # (cung dieu kien voi DEAD event trong _state_change_handler).
        self._last_activity = {}        # dpid -> time.time() (tra loi echo gan nhat)
        # Liveness chi la kenh GIAM SAT (probe PortStats). Failover KHONG
        # duoc kich hoat khi switch CHI IM LANG ma socket con song (is_active
        # True): OVS busy/luc xu ly packet-in se tre reply -> failover gia
        # mo duong VLAN99 standby tren sw8 trong khi sw5 van song -> tao L2
        # loop VLAN99 -> broadcast storm -> ca mang OVS ngat ket noi lap.
        # => chi can TCP keepalive (idle 5s x3, da bat trong _enable_tcp_keepalive)
        # phat hien socket chet (~11s) roi DEAD_DISPATCHER lo failover.
        self._liveness_timeout = 30     # im lang >= 30s moi can kiem chung bang ping
        hub.spawn(self._failover_liveness_watch)

    def _sw5_ping_dead(self):
        """True neu sw5 KHONG tra loi ping PING_TRIES lan lien tiep (that su chet).
        Dung Popen + poll(hub.sleep) de khong chan cac green thread cua Ryu."""
        for _ in range(self.PING_TRIES):
            try:
                p = subprocess.Popen(
                    ['ping', '-c', '1', '-W', '2', self.SW5_MGMT_IP],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                waited = 0.0
                while p.poll() is None and waited < 4.0:
                    hub.sleep(0.2)
                    waited += 0.2
                if p.poll() is None:
                    p.kill()
                    p.wait()
                elif p.returncode == 0:
                    return False        # sw5 con tra loi -> khong chet
            except Exception:
                return False            # khong kiem chung duoc -> khong failover
            hub.sleep(1)
        return True

    def _sw8_alive(self):
        """sw8 (Dist-SW2) phai ket noi + song thi failover moi co y nghia. Cay
        quan tri di qua sw8 (Core-SW1 -> sw8.ens10 -> ens8 -> sw5): khi sw8 reboot,
        sw5 'bien mat' khoi controller du van song -> KHONG duoc failover."""
        dp8 = self.switches.get(8)
        return dp8 is not None and getattr(dp8, 'is_active', False)

    def _failover_if_confirmed(self, dp, reason):
        """Kich hoat failover CHI KHI ping xac nhan sw5 chet (chong failover gia)."""
        if self._failover_active or self.switches.get(5) is not dp:
            return
        if not self._sw8_alive():
            self.logger.warning('%s nhung sw8 khong ket noi -> KHONG failover '
                                '(duong quan tri co the dut o sw8)', reason)
            return
        if self._sw5_ping_dead():
            if not self._failover_active and self.switches.get(5) is dp:
                self.logger.warning('*** %s + ping %s that bai -> FAILOVER ***',
                                    reason, self.SW5_MGMT_IP)
                self._failover_activate()
        else:
            self.logger.warning(
                '%s nhung sw5 con tra loi ping -> loi control-plane, '
                'KHONG mo duong standby (tranh loop)', reason)

    def _startup_failover_watch(self):
        time.sleep(35)
        if not self._failover_active and 5 not in self.switches:
            if not self._sw8_alive():
                self.logger.warning('STARTUP: sw5 chua connect va sw8 cung khong ket noi '
                                    '-> KHONG failover')
            elif self._sw5_ping_dead():
                self.logger.info('STARTUP: sw5 khong connect trong 35s va khong '
                                 'tra loi ping -> kich hoat failover')
                self._failover_activate()
            else:
                self.logger.warning('STARTUP: sw5 chua connect nhung con tra loi '
                                    'ping -> KHONG failover (doi sw5 ket noi lai)')

    # -----------------------------------------------------------------
    # LIVENESS WATCHDOG: phat hien sw5 hard-crash ma khong can TCP
    # keepalive/DEAD event. Gui echo-request theo dinh ky; neu sw5 khong
    # phan hoi >= _liveness_timeout (60s) thi coi nhu down -> kich Hoat
    # FAILOVER. Lưu ý: QUAN TRONG chống failover GIẢ:
    #   - Chi kich Hoat FAILOVER khi socket THUC SU chet (dp.is_active == False).
    #     Khi switch chi IM LANG (is_active True) ma khong reply thi do OVS
    #     busy (vd packet-in flood, chu ky RECOVERY/FLUSH dang chay) chua
    #     tra loi kip — failover luc do chi lam mo duong VLAN99 standby tren
    #     sw8 trong luc sw5 van song -> Tao L2 loop VLAN99 -> broadcast
    #     storm -> OVS ngat hang loat (da gap 09/2026: 5 switch ngat cung luc).
    #   - Failover THAT (hard-crash qemu/kill) da duoc bat bang TCP keepalive
    #     (idle 5s, interval 2s, count 3) -> phong ~11s phat DEAD event ->
    #     _state_change_handler goi _failover_activate. Watchdog nay CHI
    #     la lop de phong khi qemu chet nhanh ma TCP chua timeout.
    def _failover_liveness_watch(self):
        while True:
            time.sleep(7)
            # Chit kiem tra khi sw5 dang duoc dang ky (da features xong)
            dp = self.switches.get(5)
            if dp is None or self._failover_active:
                continue
            last = self._last_activity.get(5, time.time())
            idle = time.time() - last
            if idle >= self._liveness_timeout:
                # Im lang lau (socket chet hoac con song): can bang chung doc lap.
                # Ping that bai => sw5 chet that => failover; ping OK => chi la
                # loi control-plane/OVS ban => KHONG mo duong standby (tranh loop).
                self._failover_if_confirmed(
                    dp, 'LIVENESS: sw5 im lang %.0fs' % idle)
                if not getattr(dp, 'is_active', True):
                    continue
            elif not getattr(dp, 'is_active', True):
                continue
            # Ryu/OVS build cua lab co luc xu ly EchoReply noi bo, khong
            # dispatch EventOFPEchoReply cho app. PortStats reply thi
            # duoc dispatch on dinh, nen dung no lam probe chu dong.
            try:
                req = dp.ofproto_parser.OFPPortStatsRequest(
                    datapath=dp, flags=0,
                    port_no=dp.ofproto.OFPP_ANY)
                dp.send_msg(req)
            except Exception:
                pass

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPEchoReply, MAIN_DISPATCHER)
    def _echo_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        self._last_activity[dpid] = time.time()

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        # Health reply cho watchdog sw5. Cap nhat cho moi dpid de state luon
        # dung neu sau nay mo rong watchdog sang switch khac.
        self._last_activity[ev.msg.datapath.id] = time.time()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        self.switches[dpid] = dp
        self._last_activity[dpid] = time.time()
        self.mac_to_port[dpid] = {}
        self.logger.info('Switch %s connect, requesting port desc', dpid)
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        self._enable_tcp_keepalive(dp)

        # Table-miss: gui frame chua co flow len controller (reactive).
        # OFPCML_NO_BUFFER tranh loi buffer_id cua mot so phien ban OVS.
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

    def _enable_tcp_keepalive(self, dp):
        """Bat TCP keepalive nhanh (idle 5s, probe 2s x3) de phat hien
        switch CHET (hard crash / node down) trong ~10-15s thay vi cho
        timeout TCP mac dinh (co the hang phut/gio). Failover sw5->sw8
        phu thuoc vao phat hien DEAD kip thoi nay."""
        try:
            sk = dp.socket
            sk.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sk.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
            sk.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
            sk.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            # KEEPALIVE KHONG chay khi con du lieu chua duoc ACK (app gui probe
            # PortStats moi 7s) -> kernel dung bo dem retransmit (tcp_retries2=15
            # ~ 15 phut) nen socket cua sw5 chet "song" rat lau. TCP_USER_TIMEOUT
            # cat ket noi khi du lieu khong duoc ACK trong SOCKET_USER_TIMEOUT_MS.
            sk.setsockopt(socket.IPPROTO_TCP,
                          getattr(socket, 'TCP_USER_TIMEOUT', 18),
                          self.SOCKET_USER_TIMEOUT_MS)
            self.logger.debug('TCP keepalive enabled for dpid %s', dp.id)
        except Exception:
            pass

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc_stats_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        if dpid not in self.switches:
            return
        # FIX ROOT CAUSE #1: Refresh dp LIVE khi switch reconnect.
        # Khi sw8 reconnect (DEAD -> reconnect), _switch_features_handler
        # da ghi dp moi, nhung neu DEAD event chay TRUOC features handler
        # (dpid da bi xoa khoi self.switches) thi _failover_activate
        # dung dp cu (stale) -> send_msg that bai.  Day la cach on dinh
        # nhat: luon cap nhat dp tai moi PORT_DESC reply (dam bao dp dang
        # hoat dong, socket con song).
        self.switches[dpid] = dp

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
                # L2_TREE_BLOCK: khong dung port nay cho VLAN data (giu 99)
                if (dpid, pname) in self.L2_TREE_BLOCK and v != 99:
                    continue
                # VLAN99_TREE_BLOCK: loai tiep VLAN 99 khoi tap flood de pha
                # vong L2 mgmt (full-mesh Dist/Access mang 99 -> storm).
                if v == 99 and (dpid, pname) in self.VLAN99_TREE_BLOCK:
                    continue
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
        self._install_tree_block_drops(dp, name2no)
        self._install_vlan99_flood(dp, name2no)

        # FAILOVER: neu sw5 dang chay standby, ap lai cac dieu chinh
        # (switch vua reconnect se mat state failover cua no).
        if self._failover_active:
            self._apply_failover_switch(dpid, dp, name2no)
        elif dpid == 8 and name2no.get('ens8') is not None:
            # Guard VLAN99 tren ens8 chi ton tai luc failover; flow DROP nay
            # nam lai trong OVS khi Ryu restart -> phai xoa khi khong failover,
            # neu khong cay mgmt chinh (sw5 <-> sw8.ens8) bi cat.
            self._vlan99_guard(dp, name2no['ens8'], False)
        # RECOVERY: khi sw5 trở ve, khoi phuc cay goc (chi khi dang failover)
        if dpid == 5 and self._failover_pending:
            self._failover_pending = False
            if self._failover_active:
                self._failover_deactivate()
            else:
                self.logger.info('Switch 5 ve (khong trong failover)')

        # Campus-OVS-restore.sh cai hai flow NORMAL priority 50000 de
        # bootstrap control-plane truoc khi Ryu co the lap trinh switch.
        # Sau PORT_DESC, cay VLAN 99 do controller quan ly da day du; neu
        # giu NORMAL, no se vuot qua TREE-BLOCK priority 100/3 va tao lai
        # broadcast loop tren topology dual-home. Xoa bootstrap SAU CUNG de
        # khong lam dut ket noi trong luc cac flow thay the chua san sang.
        self._remove_vlan99_bootstrap(dp, name2no)

    # -----------------------------------------------------------------
    # DROP frame den tu port bi khoa. L2_TREE_BLOCK ap dung VLAN data;
    # VLAN99_TREE_BLOCK doc lap vi cay management phai theo STP live Core/Farm.
    def _install_tree_block_drops(self, dp, name2no):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        dpid = dp.id
        is_of13 = (ofproto.OFP_VERSION == ofproto_v1_3.OFP_VERSION)
        blocked_ports = set(self.L2_TREE_BLOCK) | set(self.VLAN99_TREE_BLOCK)
        for bdpid, pname in sorted(blocked_ports):
            if bdpid != dpid:
                continue
            key = (bdpid, pname)
            reason = (self.VLAN99_TREE_BLOCK.get(key)
                      or self.L2_TREE_BLOCK.get(key))
            pno = name2no.get(pname)
            if pno is None:
                self.logger.warning('TREE-BLOCK: khong tim thay port %s', pname)
                continue
            for v in self.TRUNK_VLANS:
                if v == 99:
                    if key not in self.VLAN99_TREE_BLOCK:
                        continue
                elif key not in self.L2_TREE_BLOCK:
                    continue
                if is_of13:
                    match = parser.OFPMatch(in_port=pno, vlan_vid=OFPVID_PRESENT | v)
                else:
                    match = parser.OFPMatch(in_port=pno, dl_vlan=v)
                instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, [])]
                mod = parser.OFPFlowMod(datapath=dp, priority=100,
                                        match=match, instructions=instructions)
                dp.send_msg(mod)
            self.logger.info('TREE-BLOCK %s %s (port %s): %s',
                             bdpid, pname, pno, reason)

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
    # VLAN99 (mgmt/control): flood tich cuc tren CAC CANH CUA CAY VLAN 99 de
    # dap in-band OVS <-> Ryu khong bi doc (learned unicast flow) con tro
    # ve 1 uplink da chet. Neu sw5 (Dist-SW1) chet, OVS van gui control
    # den Ryu qua duong standby ens5 -> sw8.ens10 -> Core-SW1.
    # Cac canh trong VLAN99_TREE_BLOCK bi loai khoi vlan_ports; flow
    # bootstrap NORMAL se duoc xoa sau khi cac flow nay cai xong.
    def _install_vlan99_flood(self, dp, name2no):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        ports = self.vlan_ports.get(dp.id, {}).get(99, set())
        if len(ports) < 2:
            return
        for p in sorted(ports):
            others = sorted(ports - {p})
            acts = [parser.OFPActionOutput(o) for o in others]
            match = parser.OFPMatch(in_port=p, vlan_vid=OFPVID_PRESENT | 99)
            instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, acts)]
            mod = parser.OFPFlowMod(datapath=dp, priority=3, match=match,
                                    instructions=instructions)
            dp.send_msg(mod)
        # Frame control-plane sinh ra tu chinh OVS (in-band): vao tu OFPP_LOCAL,
        # flood ra tat ca port VLAN99 de luon co duong den controller.
        acts = [parser.OFPActionOutput(p) for p in sorted(ports)]
        match = parser.OFPMatch(in_port=ofproto.OFPP_LOCAL,
                                vlan_vid=OFPVID_PRESENT | 99)
        instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, acts)]
        mod = parser.OFPFlowMod(datapath=dp, priority=3, match=match,
                                instructions=instructions)
        dp.send_msg(mod)
        self.logger.info('VLAN99-FLOOD %s: moi port %s', dp.id, sorted(ports))

    def _remove_vlan99_bootstrap(self, dp, name2no):
        """Ban giao VLAN 99 tu bootstrap sang cay do Ryu quan ly.
        Campus-OVS-restore.sh cai flow per-port (khong dung NORMAL):
           priority=50000,dl_vlan=99,in_port=<tree_port>,actions=output:...
        Phai xoa CA hai dang de cay mgmt do Ryu quan ly lau dai (failover
        co the mo standby ens5/ens8/ens10 moi hoat dong)."""
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        # Cach chinh: xoa THEO COOKIE 0xba5e (Campus-OVS-restore.sh gan cookie nay
        # cho moi flow bootstrap, gom ca flow in_port=patch-mgmt khong match vlan).
        # Flow cua Ryu dung cookie 0 nen khong bi anh huong.
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, cookie=0xba5e, cookie_mask=0xffffffffffffffff,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch()))

        # Dang cu (sau 09/2026 patched to per-port): NORMAL khong in_port.
        mod = parser.OFPFlowMod(
            datapath=dp,
            command=ofproto.OFPFC_DELETE_STRICT,
            priority=50000,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch(vlan_vid=OFPVID_PRESENT | 99))
        dp.send_msg(mod)

        # Dang moi: delete strict tung port cay (match day du in_port+vlan).
        for pno in name2no.values():
            if pno is not None:
                mod = parser.OFPFlowMod(
                    datapath=dp,
                    command=ofproto.OFPFC_DELETE_STRICT,
                    priority=50000,
                    out_port=ofproto.OFPP_ANY,
                    out_group=ofproto.OFPG_ANY,
                    match=parser.OFPMatch(in_port=pno,
                                          vlan_vid=OFPVID_PRESENT | 99))
                dp.send_msg(mod)

        self.logger.info('VLAN99-BOOTSTRAP removed on dpid %s', dp.id)

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

        # VLAN: OVS lab build khong dua vlan_vid/dl_vlan vao match dict cua
        # packet-in ma GIU NGUYEN 802.1Q tag trong data. Doc cam 3 dang:
        #  1) match vlan_vid/dl_vlan (neu co)
        #  2) doc VID truc tiep tu data (0x8100 tag header)
        #  3) fallback access_ports / PORT_CFG (port access, frame khong tag)
        is_of13 = (dp.ofproto.OFP_VERSION == ofproto_v1_3.OFP_VERSION)
        vlan_vid = msg.match.get('vlan_vid')     # OF1.3 (OXM)
        dl_vlan = msg.match.get('dl_vlan')       # OF1.0/1.1
        if vlan_vid is not None:
            vlan = vlan_vid & 0x0fff
        elif dl_vlan is not None:
            vlan = int(dl_vlan)
        else:
            vlan = 0

        # Doc tag 802.1Q trong data (OVS build nay giu tag trong payload).
        data_tagged = (eth.ethertype == 0x8100)
        vlan_proto = pkt.get_protocol(vlan_pkt.vlan) if data_tagged else None
        if vlan == 0 and vlan_proto is not None:
            vlan = vlan_proto.vid

        if vlan == 0:
            vlan = self.access_ports.get(dpid, {}).get(in_port, 0)
        if vlan == 0:
            vlan = self._static_access_vlan(dpid, in_port)

        if vlan == 0:
            vlan_vid = 0            # khong tag
        else:
            vlan_vid = OFPVID_PRESENT | vlan

        # Egress theo tung port: port TRUNK phai co tag, port ACCESS phai
        # khong tag (giong OVS khi khong ho tro auto tag/pop tren data).
        # xay dung day action cho list port, quan ly trang thai tag hien tai.
        name2no = self.port_name.get(dpid, {})
        cfg = self.PORT_CFG.get(dpid, {})
        trunks = set(name2no.get(p) for p in cfg.get('trunk', []))
        trunks = {p for p in trunks if p is not None}
        access_map = {}
        for pname, pv in cfg.get('access', {}).items():
            pno = name2no.get(pname)
            if pno is not None:
                access_map[pno] = pv

        def egress_actions(ports):
            acts = []
            tagged = data_tagged
            for p in ports:
                if p in access_map:
                    if tagged:
                        acts.append(parser.OFPActionPopVlan())
                        tagged = False
                else:
                    if vlan != 0 and not tagged:
                        acts.append(parser.OFPActionPushVlan(ethertype=0x8100))
                        acts.append(parser.OFPActionSetField(vlan_vid=vlan_vid))
                        tagged = True
                acts.append(parser.OFPActionOutput(p))
            return acts

        table = self.mac_to_port.setdefault(dpid, {})
        table[(vlan, src)] = in_port

        out_port = table.get((vlan, dst))
        if out_port is not None and out_port != in_port:
            actions = egress_actions([out_port])
            instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            if is_of13:
                m = {'in_port': in_port, 'eth_dst': dst}
                if vlan:
                    m['vlan_vid'] = OFPVID_PRESENT | vlan
            else:
                m = {'in_port': in_port, 'eth_dst': dst, 'dl_vlan': vlan}
            match = parser.OFPMatch(**m)
            mod = parser.OFPFlowMod(datapath=dp, priority=1, match=match,
                                    instructions=instructions, buffer_id=msg.buffer_id)
            dp.send_msg(mod)
            if msg.buffer_id == ofproto.OFP_NO_BUFFER:
                out = parser.OFPPacketOut(datapath=dp, buffer_id=ofproto.OFP_NO_BUFFER,
                                          in_port=in_port, actions=actions,
                                          data=msg.data)
                dp.send_msg(out)
            return

        # Flood trong dung VLAN (chi dung cac port duoc phep trong "cay")
        out_ports = self.vlan_ports.get(dpid, {}).get(vlan, set()) - {in_port}
        actions = egress_actions(sorted(out_ports))
        if not actions:
            return
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            out = parser.OFPPacketOut(datapath=dp, buffer_id=ofproto.OFP_NO_BUFFER,
                                      in_port=in_port, actions=actions, data=msg.data)
        else:
            out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions)
        dp.send_msg(out)

    # -----------------------------------------------------------------
    # Fallback VLAN access: dich tu PORT_CFG tinh (khong phu thuoc state)
    def _static_access_vlan(self, dpid, in_port):
        cfg = self.PORT_CFG.get(dpid)
        if not cfg:
            return 0
        name2no = self.port_name.get(dpid, {})
        for pname, v in cfg.get('access', {}).items():
            if name2no.get(pname) == in_port:
                return v
        return 0

    # -----------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dpid = ev.datapath.id
        if ev.state == DEAD_DISPATCHER:
            # Chi xoa bang MAC hoc (dong). Giu 3 bang cau hinh tinh
            # (vlan_ports/port_name/access_ports): port OVS khong doi so,
            # giu lai de chong flap -> DHCP/Khong mat VLAN khi switch
            # ngat ket noi roi ket noi lai. Se duoc ghi de khi co
            # PORT_DESC moi.
            dp = ev.datapath
            dpid = dp.id
            self.mac_to_port.pop(dpid, None)
            self.logger.info('Switch %s ngat ket noi (giu cau hinh tinh)', dpid)
            # FAILOVER: CHI kich hoat khi day dung la ket noi sw5 dang duoc
            # dang ky (self.switches[5] is dp). Neu la connection CU da bi
            # connection moi thay the (OVS reconnect -> DPSET multiple
            # connections) thi bo qua -> khong kich hoat failover nham khi
            # sw5 van ON (chong flap gia).
            # Them: socket chet CHUA du bang chung sw5 chet (co the chi mat
            # control-plane, data-plane van chuyen mach) -> kiem chung ping
            # truoc khi mo duong standby.
            if (dpid == 5 and not self._failover_active
                    and self.switches.get(5) is dp):
                hub.spawn(self._failover_if_confirmed, dp,
                          'DEAD: socket sw5 dong')
        elif ev.state == MAIN_DISPATCHER:
            if dpid == 5:
                # sw5 tro lai: cho PORT_DESC hoan tat roi khoi phuc cay goc
                self._failover_pending = True
                self.logger.info('Switch 5 tro lai (chuan bi khoi phuc cay goc)')

    # -----------------------------------------------------------------
    # FAILOVER: sw5 (Dist-SW1) down -> chuyen du lieu qua sw8 (Dist-SW2).
    # Duong standby dự phong: VPC -> Access-SW -> sw8.ens4/5/6/7 -> sw8.ens9
    # -> Core-SW2. Core-SW1<->Core-SW2 la L3 (Po10) nen khong co vong L2.
    def _failover_activate(self):
        self._failover_active = True
        self.mac_to_port.clear()
        self.logger.info('*** FAILOVER: sw5 down — mo duong standby qua sw8 ***')
        for dpid in list(self.switches.keys()):
            n2n = self.port_name.get(dpid, {})
            dp = self.switches.get(dpid)  # luon lay dp LIVE tu dict
            if dp is None or not dp.is_active:
                continue
            self._apply_failover_switch(dpid, dp, n2n)

    def _failover_deactivate(self):
        self._failover_active = False
        self.mac_to_port.clear()
        self.logger.info('*** RECOVERY: sw5 ve — khoi phuc cay goc ***')
        for dpid in list(self.switches.keys()):
            n2n = self.port_name.get(dpid, {})
            dp = self.switches.get(dpid)  # luon lay dp LIVE tu dict
            if not n2n or dp is None or not dp.is_active:
                continue
            self._install_tree_block_drops(dp, n2n)
            self._rebuild_vlan_ports(dpid)
            # Xoa flow unicast hoc duoc trong luc failover (con tro toi
            # port standby) de buffer quay ve cay goc qua sw5.
            if dpid == 68 and n2n.get('ens5') is not None:
                self._flush_output_port(dp, n2n['ens5'])
                self._install_vlan99_flood(dp, n2n)
            if dpid == 8:
                if n2n.get('ens8') is not None:
                    self._vlan99_guard(dp, n2n['ens8'], False)
                for pname in ['ens4', 'ens5', 'ens6', 'ens7', 'ens9', 'ens10']:
                    pno = n2n.get(pname)
                    if pno is not None:
                        self._flush_output_port(dp, pno)
                self._install_vlan99_flood(dp, n2n)

    def _apply_failover_switch(self, dpid, dp, name2no):
        """Ap cac thay doi standby cho switch khi dang trong trang thai failover.
        - sw68 (Access-SW1): mo ens5 (->sw8), khoa ens4 (->sw5 da chet)
        - sw8  (Dist-SW2):   mo ens4-ens7 (->Access) + ens9 (->Core-SW2)
        Cac Access khac (66/70/69) da phi tree-block o phia ens5 nen khong doi.
        """
        if not name2no or not dp.is_active:
            return
        if dpid == 68:
            p_to_sw8 = name2no.get('ens5')
            p_to_sw5 = name2no.get('ens4')
            if p_to_sw8 is not None:
                self._remove_tree_block(dp, p_to_sw8, 'ens5')
                vp = self.vlan_ports.setdefault(68, {})
                for v in self.TRUNK_VLANS:
                    vp.setdefault(v, set()).add(p_to_sw8)
            if p_to_sw5 is not None:
                for v in self.TRUNK_VLANS:
                    self.vlan_ports.get(68, {}).get(v, set()).discard(p_to_sw5)
                # Xoa cac flow unicast cũ con tro toi sw5 da chet
                self._flush_output_port(dp, p_to_sw5)
            self.logger.info('FAILOVER sw68: mo ens5(->sw8) port %s, khoa ens4(->sw5) port %s',
                             p_to_sw8, p_to_sw5)
            self._install_vlan99_flood(dp, name2no)
        elif dpid == 8:
            # Mo cac canh Access cho ca data + VLAN99. ens10->Core-SW1 da
            # la uplink VLAN99 active trong cay management; ens9->Core-SW2
            # chi mo VLAN data (10..90), khong dua 99 vao nhanh Core-SW2.
            for pname in ['ens4', 'ens5', 'ens6', 'ens7']:
                pno = name2no.get(pname)
                if pno is None:
                    continue
                self._remove_tree_block(dp, pno, pname)
                vp = self.vlan_ports.setdefault(8, {})
                for v in self.TRUNK_VLANS:
                    vp.setdefault(v, set()).add(pno)
            core2_port = name2no.get('ens9')
            if core2_port is not None:
                self._remove_tree_block(
                    dp, core2_port, 'ens9', include_vlan99=False)
                vp = self.vlan_ports.setdefault(8, {})
                for v in self.TRUNK_VLANS:
                    if v != 99:
                        vp.setdefault(v, set()).add(core2_port)
            # KHONG chan VLAN99 o ens8: sw5 vua reboot can di qua sw8.ens8 de ve
            # controller. Khong lo loop vi Access chi la NUT LA cua VLAN 99 (flow co
            # dinh cookie 0xba5f chi di patch <-> uplink, khong noi cau 2 uplink).
            # Go guard cu (neu con tu ban truoc) va tra ens8 ve tap flood VLAN99.
            inter = name2no.get('ens8')
            if inter is not None:
                self._vlan99_guard(dp, inter, False)
                self.vlan_ports.setdefault(8, {}).setdefault(99, set()).add(inter)
            self.logger.info(
                'FAILOVER sw8: mo ens4-7 (data+99), ens9 (chi data); '
                'giu ens10 + ens8 cho VLAN99')
            self._install_vlan99_flood(dp, name2no)

    def _vlan99_guard(self, dp, pno, enable):
        """Cai/go flow DROP VLAN99 (priority 100) tren in_port pno cua sw8."""
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch(in_port=pno, vlan_vid=OFPVID_PRESENT | 99)
        if enable:
            mod = parser.OFPFlowMod(
                datapath=dp, priority=100, match=match,
                instructions=[parser.OFPInstructionActions(
                    ofproto.OFPIT_APPLY_ACTIONS, [])])
        else:
            mod = parser.OFPFlowMod(datapath=dp,
                                    command=ofproto.OFPFC_DELETE_STRICT,
                                    priority=100, match=match,
                                    out_port=ofproto.OFPP_ANY,
                                    out_group=ofproto.OFPG_ANY)
        dp.send_msg(mod)

    def _flush_output_port(self, dp, out_port):
        """Xoa moi flow con tro OUTPUT ra 1 port (de loai flow unicast cu)."""
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        # Chi xoa flow do Ryu tao (cookie 0). Flow bootstrap CO DINH cua Access
        # (cookie 0xba5f, patch <-> uplink) cung co output ra port nay; xoa chung
        # se lam Access mat duong ve controller (Access-SW1 tung roi khoi Ryu sau failover).
        mod = parser.OFPFlowMod(datapath=dp, cookie=0,
                                cookie_mask=0xffffffffffffffff,
                                command=ofproto.OFPFC_DELETE,
                                priority=0, out_port=out_port,
                                out_group=ofproto.OFPG_ANY,
                                match=parser.OFPMatch())
        dp.send_msg(mod)
        self.logger.info('FLUSH flows output port %s tren dpid %s', out_port, dp.id)

    def _remove_tree_block(self, dp, pno, pname=None, include_vlan99=True):
        """DELETE cac flow TREE-BLOCK (priority 100, in_port+vlan) cua 1 port.
        include_vlan99=False dung cho uplink Core data-only khi failover."""
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        for v in self.TRUNK_VLANS:
            if v == 99 and not include_vlan99:
                continue
            m = parser.OFPMatch(in_port=pno, vlan_vid=OFPVID_PRESENT | v)
            # DELETE_STRICT: OFPFC_DELETE (non-strict) KHONG xoa duoc flow tren
            # ban OVS cua lab (log noi UNBLOCK nhung flow DROP van con -> failover
            # khong bao gio mo duong). Strict = khop dung priority + match.
            mod = parser.OFPFlowMod(datapath=dp,
                                    command=ofproto.OFPFC_DELETE_STRICT,
                                    priority=100, match=m,
                                    out_port=ofproto.OFPP_ANY,
                                    out_group=ofproto.OFPG_ANY)
            dp.send_msg(mod)
        self.logger.info('TREE-UNBLOCK port %s tren dpid %s (vlan99=%s)',
                         pno, dp.id, include_vlan99)

    def _rebuild_vlan_ports(self, dpid):
        """Duong lai vlan_ports/access_ports tu PORT_CFG (cay goc, co tree-block)."""
        cfg = self.PORT_CFG.get(dpid)
        if cfg is None:
            return
        n2n = self.port_name.get(dpid, {})
        vlans = {}
        for v in self.TRUNK_VLANS:
            vlans[v] = set()
        for pname in cfg.get('trunk', []):
            pno = n2n.get(pname)
            if pno is None:
                continue
            for v in self.TRUNK_VLANS:
                if (dpid, pname) in self.L2_TREE_BLOCK and v != 99:
                    continue
                if v == 99 and (dpid, pname) in self.VLAN99_TREE_BLOCK:
                    continue
                vlans[v].add(pno)
        for pname in cfg.get('mgmt', []):
            pno = n2n.get(pname)
            if pno is None:
                continue
            vlans[99].add(pno)
        access = {}
        for pname, v in cfg.get('access', {}).items():
            pno = n2n.get(pname)
            if pno is None:
                continue
            vlans.setdefault(v, set()).add(pno)
            access[pno] = v
        self.vlan_ports[dpid] = vlans
        self.access_ports[dpid] = access
        self.logger.info('RECOVERY %s: khoi phuc vlan_ports %s', dpid,
                         {v: sorted(p) for v, p in vlans.items()})
