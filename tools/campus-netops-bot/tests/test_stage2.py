"""Kiểm thử offline giai đoạn 2: parser chẩn đoán (output thật lấy từ lab 29/10/2026),
dừng ở lớp lỗi đầu tiên, AlertMonitor với vManage/Ryu giả."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from campus import diagnose as dg  # noqa: E402
from campus import service  # noqa: E402
from campus.alerts import AlertMonitor  # noqa: E402
from campus.console import ConsoleError  # noqa: E402
from campus.labapi import LabApiError  # noqa: E402

IFACE = """interface vpn 0 interface ge0/0 af-type ipv4
 ip-address        100.64.30.1/30
 if-admin-status   Up
 if-oper-status    Up
 port-type         transport
 mtu               1500
interface vpn 0 interface ge0/3 af-type ipv4
 ip-address        -
 if-admin-status   Down
 if-oper-status    Down
 port-type         service
interface vpn 0 interface system af-type ipv4
 ip-address        10.200.30.1/32
 if-admin-status   Up
 if-oper-status    Up
 port-type         loopback
"""
BGP = """vpn                    0
local-as               65020
                       MSG       MSG       OUT                     PREFIX  PREFIX  PREFIX
NEIGHBOR         AS    RCVD      SENT      Q      UPTIME           RCVD    VALID   INSTALLED  STATE
---------------------------------------------------------------------------------------------------------
100.64.30.2      64512 6056      5503      0      3:19:39:26       16      16      16         established
"""
ROUTE = """VPN    PREFIX              PROTOCOL         SUB TYPE  IF NAME     ADDR             VPN      TLOC IP          COLOR            ENCAP  STATUS
---------------------------------------------------------------------------------------------------------------------------------------------
0      0.0.0.0/0           bgp              e         ge0/0       100.64.30.2      -        -                -                -      F,S
"""
CONTROL = """control summary 0
 vbond_counts            1
 vmanage_counts          1
 vsmart_counts           1
 valid_controller_counts 2
"""
OMP = """PEER             TYPE    ID        ID        ID        ID        STATE    UPTIME           R/I/S
------------------------------------------------------------------------------------------------------
10.9.0.13        vsmart  1         1         900       None      up       3:19:39:23       15/8/3
"""
BFD = """SYSTEM IP        SITE ID  STATE       COLOR            COLOR            SOURCE IP
-------------------------------------------------------------------------------------------
10.200.40.1      400      up          mpls             mpls             100.64.30.1                     100.64.40.1
10.200.40.2      400      up          mpls             biz-internet     100.64.30.1                     203.0.113.17
10.200.200.1     200      down        mpls             mpls             100.64.30.1                     100.64.200.1
"""
GOOD = [IFACE, BGP, ROUTE, CONTROL, OMP, BFD.replace("down    ", "up      ")]


class TestVedgeParsers(unittest.TestCase):
    def test_real_outputs(self):
        self.assertEqual(dg.vedge_interfaces(IFACE).status, dg.OK)      # ge0/3 là service, không tính
        self.assertEqual(dg.vedge_bgp(BGP).status, dg.OK)
        self.assertEqual(dg.vedge_default_route(ROUTE).status, dg.OK)
        self.assertEqual(dg.vedge_control(CONTROL).status, dg.OK)
        self.assertEqual(dg.vedge_omp(OMP).status, dg.OK)
        c = dg.vedge_bfd(BFD)
        self.assertEqual(c.status, dg.WARN)
        self.assertIn("2/3", c.summary)

    def test_failures(self):
        self.assertEqual(dg.vedge_interfaces(IFACE.replace("Up\n port-type         transport",
                                                           "Down\n port-type         transport")).status, dg.FAIL)
        self.assertEqual(dg.vedge_bgp(BGP.replace("established", "active")).status, dg.FAIL)
        self.assertEqual(dg.vedge_control(CONTROL.replace("vsmart_counts           1", "vsmart_counts           0")).status,
                         dg.FAIL)
        self.assertEqual(dg.vedge_bfd(BFD.replace(" up ", " down ")).status, dg.FAIL)
        self.assertEqual(dg.vedge_default_route("no routes").status, dg.FAIL)

    def test_stop_at_first_fail(self):
        outs = list(GOOD)
        outs[1] = BGP.replace("established", "idle")
        rep = dg.run_layers("x", outs, dg.VEDGE_STEPS)
        st = [c.status for c in rep.checks]
        self.assertEqual(st, [dg.OK, dg.FAIL, dg.SKIP, dg.SKIP, dg.SKIP, dg.SKIP])
        self.assertIn("L3 Underlay BGP", rep.render())

    def test_all_good(self):
        rep = dg.run_layers("x", GOOD, dg.VEDGE_STEPS)
        self.assertEqual(rep.status, dg.OK)


class TestBranchParsers(unittest.TestCase):
    def test_asa(self):
        brief = ("Interface                  IP-Address      OK? Method Status                Protocol\n"
                 "GigabitEthernet0/1.60      10.2.60.1       YES CONFIG up                    up\n"
                 "GigabitEthernet0/1.70      10.2.70.1       YES CONFIG down                  down\n")
        self.assertEqual(dg.asa_gateways("200")(brief).status, dg.FAIL)
        self.assertEqual(dg.asa_gateways("200")(brief.replace("down                  down", "up                    up")).status,
                         dg.OK)
        self.assertEqual(dg.asa_dhcpd_state("Context  Configured as DHCP Server\n"
                                            "Interface nongnghiep, Configured for DHCP SERVER\n").status, dg.OK)
        self.assertEqual(dg.asa_dhcpd_state("Context  Not Configured for DHCP\n").status, dg.FAIL)
        self.assertEqual(dg.asa_dhcpd_binding("IP address  Client Identifier\n  10.2.60.100  0100.5079.6668.2b\n").status,
                         dg.OK)

    def test_ios(self):
        self.assertEqual(dg.ios_trunk("Port        Mode         Encapsulation  Status        Native vlan\n"
                                      "Et0/0       on           802.1q         trunking      1\n").status, dg.OK)
        self.assertEqual(dg.ios_trunk("").status, dg.FAIL)
        self.assertEqual(dg.ping_ok("p", "")("Success rate is 100 percent (5/5), round-trip").status, dg.OK)
        self.assertEqual(dg.ping_ok("p", "")("Success rate is 0 percent (0/5)").status, dg.FAIL)


HEALTH = {"switches": [{"name": n, "connected": True, "mgmt_paths": 2} for n in
                       ("Dist-SW1", "Dist-SW2", "Access-SW1", "Access-SW2", "Access-SW3", "Access-SW4")],
          "issues": [], "links_up": 13, "links_total": 13,
          "controller": {"stalls_1h": 2, "stall_max_ms_1h": 1400, "cpu_pct": 7, "stall_log": []}}


class TestSdn(unittest.TestCase):
    def test_report(self):
        self.assertEqual(dg.sdn_report(HEALTH).status, dg.OK)
        h = {**HEALTH, "switches": [dict(s) for s in HEALTH["switches"]]}
        h["switches"][2]["connected"] = False
        self.assertEqual(dg.sdn_report(h).checks[0].status, dg.FAIL)


class FakeVM:
    def __init__(self):
        self.data, self.fail = [], False

    def alarms(self, hours=1):
        if self.fail:
            raise LabApiError("timeout")
        return list(self.data)


class FakeRyu:
    ep = object()

    def __init__(self):
        self.h = HEALTH

    def health(self):
        return self.h


def alarm(uuid, typ, sev, host):
    return {"uuid": uuid, "type": typ, "severity": sev, "rule_name_display": typ, "message": "m",
            "values_short_display": [{"host-name": host}], "entry_time": time.time() * 1000}


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.vm, self.ryu = FakeVM(), FakeRyu()
        self.vm.data = [alarm("old", "node_down", "Critical", "vEdge1-S300")]
        self.mon = AlertMonitor(self.vm, self.ryu)

    def test_first_poll_primes_only(self):
        self.assertEqual(self.mon.poll(), [])
        self.vm.data.append(alarm("n1", "node_down", "Critical", "vEdge2-S200"))
        al = self.mon.poll()
        self.assertEqual(len(al), 1)
        self.assertEqual(al[0].level, "critical")
        self.assertEqual(al[0].diagnose, ["vEdge2-S200"])
        self.assertEqual(self.mon.poll(), [])          # không gửi lại

    def test_recovery_and_mute(self):
        self.mon.poll()
        self.vm.data.append(alarm("u1", "node_up", "Medium", "vEdge2-S200"))
        self.assertEqual(self.mon.poll()[0].level, "recovery")
        self.mon.mute("tloc_down:vEdge1-S400")
        self.vm.data.append(alarm("t1", "tloc_down", "Major", "vEdge1-S400"))
        self.assertEqual(self.mon.poll(), [])

    def test_vmanage_down_needs_two_failures(self):
        self.mon.poll()
        self.vm.fail = True
        self.assertEqual(self.mon.poll(), [])
        al = self.mon.poll()
        self.assertEqual([a.key for a in al], ["vmanage-down"])
        self.assertEqual(self.mon.poll(), [])
        self.vm.fail = False
        self.assertEqual(self.mon.poll()[0].level, "recovery")

    def test_ryu_transitions(self):
        self.mon.poll()
        h = {**HEALTH, "switches": [dict(s) for s in HEALTH["switches"]],
             "issues": [("bad", "Lien ket A1-D1 chet")]}
        h["switches"][2]["connected"] = False
        self.ryu.h = h
        keys = sorted(a.key for a in self.mon.poll())
        self.assertEqual(keys, ["link:Lien ket A1-D1 chet", "ovs:Access-SW1"])
        self.ryu.h = HEALTH
        self.assertEqual({a.level for a in self.mon.poll()}, {"recovery"})

    def test_state_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "st.json")
            m = AlertMonitor(self.vm, None, p)
            m.poll()
            m2 = AlertMonitor(self.vm, None, p)     # khởi động lại: không báo lại alarm cũ
            self.vm.data.append(alarm("n2", "site_down", "Critical", "vEdge1-S400"))
            self.assertEqual([a.key for a in m2.poll()], ["site_down:vEdge1-S400"])


class FakeConsole:
    def __init__(self, outputs, fail_on=None):
        self.outputs, self.fail_on, self.calls = outputs, fail_on, []

    def run(self, dev, cmds):
        self.calls.append((dev.name, cmds))
        if dev.name == self.fail_on:
            raise ConsoleError("node tắt")
        return [self.outputs[c] for c in cmds]


class TestExecute(unittest.TestCase):
    def tearDown(self):
        service._console = None

    def test_one_session_per_device(self):
        service._console = FakeConsole({s[2]: o for s, o in zip(dg.VEDGE_STEPS, GOOD)})
        res = service.diagnose("vEdge1-S300")
        self.assertTrue(res.ok)
        self.assertEqual(len(service._console.calls), 1)
        self.assertIn("mọi lớp đều bình thường", res.text)

    def test_console_failure_is_a_failed_layer(self):
        service._console = FakeConsole({}, fail_on="SwitchBrand-S200")
        res = service.diagnose("dhcp 200")
        self.assertIn("❌ L2 Trunk SwitchBrand: không vào được SwitchBrand-S200", res.text)
        self.assertIn("⏸ Dịch vụ: dhcpd", res.text)
        self.assertEqual(len(service._console.calls), 1)   # không mở tiếp Brand-FW


if __name__ == "__main__":
    unittest.main()
