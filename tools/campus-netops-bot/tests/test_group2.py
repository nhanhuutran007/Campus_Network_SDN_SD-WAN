"""Kiểm thử offline nhóm 2: quản trị chi nhánh qua overlay SD-WAN (Brand-FW, SwitchBrand, SW truy cập).
Mẫu `show track` lấy từ Brand-FW-S200 thật (30/10/2026)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from campus import diagnose as dg  # noqa: E402
from campus import inventory, service  # noqa: E402
from campus.console import ConsoleError, SshTransport  # noqa: E402

TRACK = """Track 1
  Response Time Reporter 10 reachability
  Reachability is Up
  2 changes, last change 00:26:53
  Latest operation return code: OK
  Tracked by:
    STATIC-IP-ROUTING 0
Track 2
  Response Time Reporter 20 reachability
  Reachability is Up
  2 changes, last change 00:26:48
  Tracked by:
    STATIC-IP-ROUTING 0
"""
IP_BRIEF = """Interface                  IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0.60      10.2.60.1       YES CONFIG up                    up
GigabitEthernet0/0.70      10.2.70.1       YES CONFIG up                    up
GigabitEthernet0/0.99      10.2.99.1       YES CONFIG up                    up
GigabitEthernet0/1         10.2.1.1        YES CONFIG up                    up
"""
TRUNK = """Port        Mode             Encapsulation  Status        Native vlan
Et0/0       on               802.1q         trunking      1
"""
DHCPD = "Interface vlan60, Configured for DHCP SERVER\nInterface vlan70, Configured for DHCP SERVER\n"
BINDING = "IP address       Client-ID         Lease expiration        Type\n10.2.60.100  0100.5079.6668.2b   86000 seconds  Automatic\n"
EDGES = [{"host-name": "vEdge1-S200", "system-ip": "10.200.2.1", "site-id": "200", "reachability": "reachable",
          "bfdSessionsUp": 8, "bfdSessions": 8},
         {"host-name": "vEdge2-S200", "system-ip": "10.200.2.2", "site-id": "200", "reachability": "reachable",
          "bfdSessionsUp": 8, "bfdSessions": 8},
         {"host-name": "vEdge1-S300", "system-ip": "10.200.30.1", "site-id": "300", "reachability": "reachable"}]


class TestParsers(unittest.TestCase):
    def test_tracks(self):
        self.assertEqual(dg.asa_tracks(TRACK).status, dg.OK)
        self.assertEqual(dg.asa_tracks(TRACK.replace("Reachability is Up", "Reachability is Down", 1)).status, dg.WARN)
        self.assertEqual(dg.asa_tracks(TRACK.replace("is Up", "is Down")).status, dg.FAIL)
        self.assertEqual(dg.asa_tracks("").status, dg.FAIL)

    def test_sdwan_edges(self):
        self.assertEqual(dg.sdwan_edges("200", EDGES).status, dg.OK)
        one = [EDGES[0], dict(EDGES[1], reachability="unreachable")]
        self.assertEqual(dg.sdwan_edges("200", one).status, dg.WARN)
        none = [dict(e, reachability="unreachable") for e in EDGES[:2]]
        self.assertEqual(dg.sdwan_edges("200", none).status, dg.FAIL)
        self.assertEqual(dg.sdwan_edges("400", EDGES).status, dg.FAIL)            # site không có vEdge

    def test_trunk_relabel(self):
        c = dg.trunk("L2 Uplink SW-S200-1")(TRUNK)
        self.assertEqual((c.layer, c.status), ("L2 Uplink SW-S200-1", dg.OK))

    def test_dtp_trunk_is_warning(self):
        # SW-S400-1 thật (30/10): uplink trunk do DTP, không cấu hình tường minh
        out = "Port        Mode             Encapsulation  Status        Native vlan\nEt0/0       auto             n-802.1q       trunking      1\n"
        c = dg.ios_trunk(out)
        self.assertEqual(c.status, dg.WARN)
        self.assertIn("DTP", c.summary)


class FakeConsole:
    """Trả output mẫu theo (thiết bị, lệnh); ghi lại thiết bị đã được mở phiên."""
    def __init__(self, fail=()):
        self.fail, self.opened = set(fail), []

    def run(self, dev, cmds):
        self.opened.append(dev.name)
        if dev.name in self.fail:
            raise ConsoleError(f"SSH {dev.name} không kết nối được")
        table = {"show track": TRACK, "show interface ip brief": IP_BRIEF, "show interfaces trunk": TRUNK,
                 "show dhcpd state": DHCPD, "show dhcpd binding": BINDING}
        return [table[c] for c in cmds]


class TestBranchDiagnosis(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"NETOPS_TRANSPORT": "ssh"})
        self.env.start()
        self.vm = mock.Mock()
        self.vm.devices.return_value = EDGES

    def tearDown(self):
        self.env.stop()
        service._console = None

    def _run(self, target, console):
        with mock.patch.object(service, "console", lambda: console), mock.patch.object(service, "vmanage", lambda: self.vm):
            return service.diagnose(target)

    def test_all_layers_ok(self):
        fc = FakeConsole()
        res = self._run("site 200", fc)
        self.assertIn("mọi lớp đều bình thường", res.text)
        self.assertEqual(fc.opened, ["Brand-FW-S200", "SwitchBrand-S200", "SW-S200-1", "SW-S200-2", "Brand-FW-S200"])
        for alias in ("branch 200", "chi nhánh 200"):
            self.assertIn("Chẩn đoán chi nhánh Site 200", self._run(alias, FakeConsole()).text)

    def test_overlay_down_stops_before_ssh(self):
        self.vm.devices.return_value = [dict(e, reachability="unreachable") for e in EDGES[:2]]
        fc = FakeConsole()
        res = self._run("site 200", fc)
        self.assertIn("❌ SD-WAN: 2 vEdge", res.text)
        self.assertEqual(fc.opened, [])                       # không SSH khi overlay đã chết

    def test_unreachable_switch_is_first_failure(self):
        res = self._run("site 200", FakeConsole(fail={"SW-S200-1"}))
        self.assertIn("lỗi đầu tiên ở lớp **L2 Uplink SW-S200-1**", res.text)

    def test_dhcp_target_unchanged(self):
        self.assertIn("Chẩn đoán DHCP Site 300", self._run("dhcp 300", FakeConsole()).text)


class TestBranchInventory(unittest.TestCase):
    def test_branch_mgmt(self):
        fw = inventory.resolve("Brand-FW-S300")
        self.assertEqual((fw.mgmt_ip, fw.mgmt_alt), ("10.3.1.1", "10.3.1.5"))
        self.assertEqual(inventory.resolve("SwitchBrand-S400").mgmt_ip, "10.4.99.2")
        self.assertEqual(inventory.resolve("57").mgmt_ip, "10.4.99.12")       # SW57 = .12, SW60 = .11 (configs/)

    def test_fallback_to_alt_ip(self):
        """IP chính lỗi mạng → thử outside2; sai mật khẩu thì không thử tiếp."""
        import paramiko
        tried = []

        class FakeClient:
            def set_missing_host_key_policy(self, *_):
                pass

            def connect(self, ip, **_):
                tried.append(ip)
                raise OSError("timed out")

            def close(self):
                pass

        creds = mock.Mock()
        creds.get.return_value = ("netops", "x")
        with mock.patch.object(paramiko, "SSHClient", FakeClient):
            with self.assertRaises(ConsoleError) as cm:
                with SshTransport(creds).session(inventory.resolve("Brand-FW-S200")):
                    pass
        self.assertEqual(tried, ["10.2.1.1", "10.2.1.5"])
        self.assertIn("10.2.1.5", str(cm.exception))
        creds.get.assert_called_with("netops FW")                             # ASA dùng dòng mật khẩu FW


if __name__ == "__main__":
    unittest.main()
