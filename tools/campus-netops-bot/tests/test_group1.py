"""Kiểm thử offline nhóm 1: vEdge qua vManage API, FW-ASAv chỉ đọc, DHCP-Server tại chỗ.
Mẫu JSON lấy từ vManage thật (vEdge1-S300, 30/10/2026)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from campus import diagnose as dg  # noqa: E402
from campus import guard, service  # noqa: E402

IFACE = [
    {"vpn-id": "0", "ifname": "ge0/0", "ip-address": "100.64.30.1/30", "port-type": "transport", "af-type": "ipv4",
     "if-admin-status": "Up", "if-oper-status": "Up", "rx-drops": 5},
    {"vpn-id": "0", "ifname": "ge0/3", "ip-address": "-", "port-type": "service", "af-type": "ipv4",
     "if-admin-status": "Down", "if-oper-status": "Down"},
    {"vpn-id": "0", "ifname": "system", "ip-address": "10.200.30.1/32", "port-type": "loopback", "af-type": "ipv4",
     "if-admin-status": "Up", "if-oper-status": "Up"},
]
BGP = [{"vpn-id": 0, "peer-addr": "100.64.30.2", "as": 64512, "state": "established"}]
ROUTE = [{"vpn-id": 0, "prefix": "0.0.0.0/0", "protocol": "bgp", "nexthop-addr": "100.64.30.2",
          "nexthop-ifname": "ge0/0", "rstatus": "F S"}]
CONTROL = [{"peer-type": "vsmart", "state": "up", "system-ip": "10.9.0.13", "local-color": "mpls"},
           {"peer-type": "vmanage", "state": "up", "system-ip": "10.9.3.10", "local-color": "mpls"}]
OMP = [{"type": "vsmart", "peer": "10.9.0.13", "state": "up"}]
BFD = [{"system-ip": "10.200.40.1", "site-id": 400, "state": "up", "local-color": "mpls", "color": "mpls"},
       {"system-ip": "10.200.100.1", "site-id": 100, "state": "up", "local-color": "mpls", "color": "biz-internet"}]


class TestVedgeApi(unittest.TestCase):
    def test_real_samples_ok(self):
        for parse, data in [(dg.api_interfaces, IFACE), (dg.api_bgp, BGP), (dg.api_default_route, ROUTE),
                            (dg.api_control, CONTROL), (dg.api_omp, OMP), (dg.api_bfd, BFD)]:
            self.assertEqual(parse(data).status, dg.OK, parse.__name__)

    def test_failures(self):
        self.assertEqual(dg.api_interfaces([dict(IFACE[0], **{"if-oper-status": "Down"})]).status, dg.FAIL)
        self.assertEqual(dg.api_bgp([dict(BGP[0], state="active")]).status, dg.FAIL)
        self.assertEqual(dg.api_default_route([dict(ROUTE[0], rstatus="")]).status, dg.FAIL)
        self.assertEqual(dg.api_control(CONTROL[1:]).status, dg.FAIL)            # mất vSmart
        self.assertEqual(dg.api_bfd([dict(BFD[0], state="down"), BFD[1]]).status, dg.WARN)

    def test_service_uses_api_out_of_scope(self):
        fake = mock.Mock()
        fake.devices.return_value = [{"host-name": "vEdge1-S300", "system-ip": "10.200.30.1", "reachability": "reachable"},
                                     {"host-name": "vEdge-S500", "system-ip": "10.200.50.1", "reachability": "unreachable"}]
        data = {p: d for (_, p, _), d in zip(dg.VEDGE_API_STEPS, [IFACE, BGP, ROUTE, CONTROL, OMP, BFD])}
        fake.device_data.side_effect = lambda path, sid: data[path]
        with mock.patch.dict(os.environ, {"NETOPS_TRANSPORT": "ssh"}), mock.patch.object(service, "vmanage", lambda: fake):
            service._vm_cache["ts"] = 0
            ok = service.diagnose("vEdge1-S300")
            self.assertIn("qua vManage API", ok.text)
            self.assertIn("mọi lớp đều bình thường", ok.text)
            down = service.diagnose("vEdge-S500")
            self.assertIn("❌ Quản lý: vManage ↔ thiết bị", down.text)
            self.assertEqual(fake.device_data.call_count, 6)          # vEdge-S500 không gọi API realtime
        service._vm_cache["ts"] = 0


ASA_FO = "\tThis host: Primary - Active \n\tOther host: Secondary - Standby Ready \n"
ASA_BRIEF = ("Interface                  IP-Address      OK? Method Status                Protocol\n"
             "GigabitEthernet0/0         10.1.2.1        YES CONFIG up                    up\n"
             "GigabitEthernet0/6         unassigned      YES unset  administratively down up\n"
             "Management0/0              10.1.99.33      YES CONFIG up                    up\n")
ASA_OSPF = ("Neighbor ID     Pri   State           Dead Time   Address         Interface\n"
            "10.1.0.2          1   FULL/DR         0:00:33     10.1.2.6        inside2\n"
            "10.1.0.1          1   FULL/DR         0:00:37     10.1.2.2        inside\n")
ASA_ASP = ("Frame drop:\n  Flow is denied by configured rule (acl-drop)                               919\n"
           "  No valid adjacency (no-adjacency)                                          12\n")


class TestAsa(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(dg.asa_failover(ASA_FO).status, dg.OK)
        self.assertEqual(dg.asa_failover("\tThis host: Primary - Active \n\tOther host: Secondary - Failed \n").status,
                         dg.WARN)
        self.assertEqual(dg.asa_interfaces(ASA_BRIEF).status, dg.OK)              # Gi0/6 không có IP → bỏ qua
        self.assertEqual(dg.asa_ospf(ASA_OSPF).status, dg.OK)
        self.assertEqual(dg.asa_ospf(ASA_OSPF.splitlines()[0]).status, dg.FAIL)
        self.assertEqual(dg.asa_default("Gateway of last resort is 10.1.3.2 to network 0.0.0.0").status, dg.OK)
        self.assertEqual(dg.asa_asp_drop(ASA_ASP).status, dg.OK)                  # lần đầu: chỉ ghi mốc
        prev = dg.asp_counts(ASA_ASP)
        self.assertEqual(dg.asa_asp_drop(ASA_ASP, prev).status, dg.OK)            # không tăng
        c = dg.asa_asp_drop(ASA_ASP.replace("12", "20"), prev)
        self.assertEqual(c.status, dg.WARN)                                         # no-adjacency tăng → cảnh báo
        self.assertIn("bất đối xứng", c.summary)

    def test_packet_tracer_guard(self):
        ok, _ = guard.check("asa", "packet-tracer input inside tcp 10.1.90.10 40000 8.8.8.8 443")
        self.assertTrue(ok)
        self.assertFalse(guard.check("ios", "packet-tracer input inside tcp 1.1.1.1 1 2.2.2.2 2")[0])
        self.assertFalse(guard.check("asa", "packet-tracer input inside")[0])
        self.assertTrue(guard.check("asa", "packet-tracer input inside tcp 1.1.1.1 1 2.2.2.2 443 | include Action")[0])
        self.assertFalse(guard.check("asa", "packet-tracer input inside tcp 1.1.1.1 1 2.2.2.2 443 | redirect x")[0])
        self.assertFalse(guard.check("asa", "configure terminal")[0])


class TestDhcp(unittest.TestCase):
    def test_scopes(self):
        s = [{"ScopeId": "10.1.10.0", "Free": 98, "InUse": 2, "PercentageInUse": 2.0},
             {"ScopeId": "10.1.20.0", "Free": 100, "InUse": 0, "PercentageInUse": 0}]
        self.assertEqual(dg.dhcp_scopes(s).status, dg.OK)
        self.assertEqual(dg.dhcp_scopes([dict(s[0], Free=0)]).status, dg.FAIL)
        self.assertEqual(dg.dhcp_scopes([]).status, dg.FAIL)

    def test_status_off_dhcp_server(self):
        with mock.patch("campus.dhcp_local.available", return_value=False):
            self.assertFalse(service.dhcp_status().ok)


if __name__ == "__main__":
    unittest.main()
