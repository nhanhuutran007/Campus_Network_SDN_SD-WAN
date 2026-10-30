"""Kiểm thử offline chế độ in-band (NetOps-Server trong topo, NETOPS_TRANSPORT=ssh)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from campus import inventory, service  # noqa: E402
from campus.console import ConsoleError, SshTransport  # noqa: E402


class TestInband(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"NETOPS_TRANSPORT": "ssh"})
        self.env.start()
        service._console = None

    def tearDown(self):
        self.env.stop()
        service._console = None

    def test_scope_is_only_devices_with_mgmt_ip(self):
        scoped = sorted(d.name for d in inventory.DEVICES if service.in_scope(d))
        self.assertEqual(scoped, ["Core-SW1", "Core-SW2", "FW-ASAv-Active", "FW-ASAv-Standby", "SwitchServerFarm"])
        self.assertIsInstance(service.console(), SshTransport)

    def test_out_of_scope_is_refused_without_network(self):
        res = service.run_command("vEdge1-S300", "show bfd sessions")
        self.assertFalse(res.ok)
        self.assertIn("ngoài phạm vi", res.text)
        with self.assertRaises(ConsoleError):
            with SshTransport().session(inventory.resolve("SwitchDMZ")):
                pass

    def test_compliance_and_backup_only_target_scope(self):
        devs = service._targets("all", {"Core-SW1": 1, "vEdge1-S300": 1, "Internet": 1})
        self.assertEqual([d.name for d in devs], ["Core-SW1"])

    def test_mgmt_ips(self):
        self.assertEqual(inventory.resolve("Core-SW2").mgmt_ip, "10.1.90.3")      # Vlan99 Core-SW2 shutdown
        self.assertEqual(inventory.resolve("SwitchServerFarm").mgmt_ip, "10.1.99.32")
        self.assertEqual(inventory.resolve("SwitchDMZ").mgmt_ip, "")               # DMZ cô lập


if __name__ == "__main__":
    unittest.main()
