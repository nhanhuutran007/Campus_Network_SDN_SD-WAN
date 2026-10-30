"""Kiểm thử offline giai đoạn 3: rào lệnh cấu hình, so sức khoẻ, tuân thủ, drift, và quy trình
thay đổi (duyệt → áp → kiểm → rollback) với thiết bị giả."""
import contextlib
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from campus import change, compliance, drift, health, inventory  # noqa: E402
from campus.change import ChangeError, ChangeManager  # noqa: E402

BRIEF_OK = ("Interface              IP-Address      OK? Method Status                Protocol\n"
            "Ethernet0/0            unassigned      YES unset  up                    up\n"
            "Ethernet0/1            unassigned      YES unset  up                    up\n")
BRIEF_E01_DOWN = BRIEF_OK.replace("Ethernet0/1            unassigned      YES unset  up                    up",
                                  "Ethernet0/1            unassigned      YES unset  administratively down down")
VRRP = ("Interface          Grp Pri Time  Own Pre State   Master addr     Group addr\n"
        "Vl10               10  110 3570       Y  Master  10.1.10.2       10.1.10.1\n")
BGP = ("Neighbor        V           AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd\n"
       "100.64.254.2    4        64512    6159    6146       18    0    0 3d21h           8\n"
       "203.0.113.21    4        65040       0       0        1    0    0 never    Idle\n")


class TestValidate(unittest.TestCase):
    def test_blocked(self):
        for c in ["reload", "write memory", "copy run start", "do show run", "end", "username a secret b",
                  "enable secret x", "no router bgp 65000", "snmp-server community x RO", "configure replace x"]:
            self.assertTrue(change.validate("ios", [c]), c)
        for c in ["commit", "rollback configuration 0", "system system-ip 1.1.1.1", "no vpn 0", "vbond 1.2.3.4"]:
            self.assertTrue(change.validate("viptela", [c]), c)

    def test_allowed(self):
        self.assertEqual(change.validate("ios", ["interface Loopback99", " description x", "exit"]), [])
        self.assertEqual(change.validate("viptela", ["system", " location x"]), [])
        self.assertTrue(change.validate("asa", ["hostname x"]))           # ASA chưa hỗ trợ rollback
        self.assertTrue(change.validate("ios", ["x"] * 41))

    def test_preview(self):
        self.assertEqual(change.preview("interface Vlan10\n ip address 1.1.1.1 255.0.0.0\n",
                                        ["interface Vlan10", " shutdown"]),
                         ["= interface Vlan10", "+  shutdown"])


class TestHealth(unittest.TestCase):
    def test_ios_parse(self):
        snap = health.parse("ios", [BRIEF_OK, BGP, "", VRRP])
        self.assertEqual(snap["interface up/up"], {"Ethernet0/0", "Ethernet0/1"})
        self.assertEqual(snap["BGP established"], {"100.64.254.2"})      # Idle không tính
        self.assertEqual(snap["VRRP"], {"Vl10 grp 10 Master"})

    def test_compare(self):
        a = health.parse("ios", [BRIEF_OK, BGP, "", VRRP])
        b = health.parse("ios", [BRIEF_E01_DOWN, BGP, "", VRRP.replace("Master", "Backup")])
        lost = health.compare(a, b)
        self.assertIn("interface up/up: Ethernet0/1", lost)
        self.assertIn("VRRP: Vl10 grp 10 Master", lost)
        self.assertEqual(health.compare(b, a), ["VRRP: Vl10 grp 10 Backup"])


class TestCompliance(unittest.TestCase):
    def test_core_missing_helper(self):
        cfg = "interface Vlan10\n vrrp 10 ip 10.1.10.1\n!\ninterface Vlan20\n ip helper-address 10.1.90.10\n"
        bad = [d for ok, d in compliance.core_rules(inventory.resolve("Core-SW1"), cfg) if not ok]
        self.assertIn("Vlan10 relay DHCP tới 10.1.90.10", bad)
        self.assertIn("Vlan20 VRRP gateway 10.1.20.1", bad)

    def test_vedge_wrong_color_and_sysip(self):
        cfg = ("system\n system-ip 10.200.300.1\n site-id 300\n!\nvpn 0\n interface ge0/0\n"
               "  ip address 203.0.113.13/30\n  tunnel-interface\n   color mpls\n  !\n !\n")
        bad = [d for ok, d in compliance.vedge_rules(inventory.resolve("vEdge1-S300"), cfg) if not ok]
        self.assertEqual(len(bad), 2)

    def test_internet_missing_filter(self):
        cfg = (" neighbor 203.0.113.9 remote-as 65010\n neighbor 203.0.113.21 remote-as 65040\n"
               "  neighbor 203.0.113.9 prefix-list NO_DEFAULT_IN in\n")
        bad = [d for ok, d in compliance.internet_rules(inventory.resolve("Internet"), cfg) if not ok]
        self.assertEqual(len(bad), 1)
        self.assertIn("203.0.113.21", bad[0])

    def test_brandfw_pool(self):
        cfg = "dhcpd address 10.2.60.50-10.2.60.199 vlan60\ndhcpd enable vlan60\n"
        bad = [d for ok, d in compliance.brandfw_rules(inventory.resolve("Brand-FW-S200"), cfg) if not ok]
        self.assertEqual(len(bad), 1)


class TestDrift(unittest.TestCase):
    def test_normalize(self):
        a = drift.normalize("Building configuration...\nCurrent configuration : 10 bytes\n!\nhostname R\n"
                            "username admin secret 9 $9$x\n! Last configuration change at x\nend\n")
        self.assertEqual(a, ["hostname R"])


class FakeSession:
    """Thiết bị giả: giữ trạng thái interface, phản hồi các lệnh mà ChangeManager gửi."""

    def __init__(self, platform="ios", break_on=None, reject=None):
        self.platform, self.break_on, self.reject = platform, break_on, reject
        self.broken, self.sent = False, []

    def run(self, cmd, timeout=None, answers=()):
        self.sent.append(cmd)
        c = cmd.removeprefix("do ")
        if self.reject and cmd.strip() == self.reject:
            return "% Invalid input detected at '^' marker." if self.platform == "ios" else "syntax error: unknown"
        if self.break_on and cmd.strip() == self.break_on:
            self.broken = True
        if c.startswith("copy running-config"):
            return "1026 bytes copied"
        if c.startswith("configure replace"):
            self.broken = False
            return "Total number of passes: 1\nRollback Done"
        if c == "commit abort":
            self.broken = False
        if c == "commit check":
            return "Validation complete"
        if c == "show ip interface brief":
            return BRIEF_E01_DOWN if self.broken else BRIEF_OK
        if c == "show bfd sessions":
            return "" if self.broken else "10.200.40.1      400      up          mpls             mpls"
        if c == "show control summary":
            return " vsmart_counts 1\n vmanage_counts 1\n"
        if c == "show configuration commit list":
            return "0    10014    admin      cli         2026-10-29 10:48:53             netops-%s" % self.rid
        return ""


class FakeConsole:
    def __init__(self, sess):
        self.sess = sess

    def run(self, dev, cmds):
        return ["interface Ethernet0/1\n no shutdown\n" for _ in cmds]

    @contextlib.contextmanager
    def session(self, dev):
        yield self.sess


class TestChangeFlow(unittest.TestCase):
    def setUp(self):
        change.SETTLE.update({"ios": 0, "vios": 0, "viptela": 0})
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def mgr(self, sess):
        return ChangeManager(FakeConsole(sess), self.tmp.name)

    def test_ios_success_then_undo(self):
        s = FakeSession()
        m = self.mgr(s)
        req = m.propose("SW-S500", ["interface Loopback99", " description x"], "thử", "tg:1 A")
        self.assertEqual(req.status, "pending")
        req = m.approve_and_run(req.id, "tg:2 B")
        self.assertEqual(req.status, "done")
        self.assertIn("write memory", s.sent)
        self.assertTrue(any(c.startswith("copy running-config unix:netops-") for c in s.sent))
        req = m.undo(req.id, "tg:2 B")
        self.assertEqual(req.status, "undone")
        with open(self.tmp.name, encoding="utf-8") as f:
            events = [line for line in f if line.strip()]
        self.assertEqual(len(events), 4)        # proposed, approved, finished, undo

    def test_ios_syntax_error_rolls_back(self):
        s = FakeSession(reject="lenh-sai")
        m = self.mgr(s)
        req = m.approve_and_run(m.propose("SW-S500", ["interface Loopback98", "lenh-sai"], "", "a").id, "b")
        self.assertEqual(req.status, "rolled_back")
        self.assertNotIn("write memory", s.sent)

    def test_ios_degraded_rolls_back(self):
        s = FakeSession(break_on="shutdown")
        m = self.mgr(s)
        req = m.approve_and_run(m.propose("SW-S500", ["interface Ethernet0/1", "shutdown"], "", "a").id, "b")
        self.assertEqual(req.status, "rolled_back")
        self.assertTrue(any("Ethernet0/1" in l for l in req.log))
        self.assertTrue(any(c.endswith("force") for c in s.sent))
        self.assertNotIn("write memory", s.sent)

    def test_viptela_degraded_commit_abort(self):
        s = FakeSession("viptela", break_on="shutdown")
        m = self.mgr(s)
        req = m.approve_and_run(m.propose("vEdge2-S300", ["vpn 0", " interface ge0/0", "  shutdown"], "", "a").id, "b")
        self.assertEqual(req.status, "rolled_back")
        self.assertIn("commit abort", s.sent)
        self.assertTrue(any(c.startswith("commit confirmed 5") for c in s.sent))
        self.assertNotIn("commit", s.sent)          # không xác nhận commit

    def test_viptela_success_and_undo(self):
        s = FakeSession("viptela")
        m = self.mgr(s)
        req = m.propose("vEdge2-S300", ["system", " location x"], "", "a")
        s.rid = req.id
        self.assertEqual(m.approve_and_run(req.id, "b").status, "done")
        self.assertIn("commit", s.sent)
        self.assertEqual(m.undo(req.id, "b").status, "undone")
        self.assertIn("rollback configuration 0", s.sent)

    def test_guards(self):
        m = self.mgr(FakeSession())
        with self.assertRaises(ChangeError):
            m.propose("FW-ASAv-Active", ["hostname x"], "", "a")
        req = m.propose("SW-S500", ["interface Loopback1"], "", "tg:1 A")
        with self.assertRaises(ChangeError):
            m.approve_and_run(req.id, "tg:1 A", four_eyes=True)
        req.created -= change.PENDING_TTL + 1
        with self.assertRaises(ChangeError):
            m.approve_and_run(req.id, "tg:2 B")
        self.assertEqual(req.status, "expired")

    def test_agent_requests_are_announced_once(self):
        m = self.mgr(FakeSession())
        t = time.time()
        m.propose("SW-S500", ["interface Loopback1"], "", "ai-agent")
        self.assertEqual(len(m.unannounced_since(t)), 1)
        self.assertEqual(m.unannounced_since(t), [])


if __name__ == "__main__":
    unittest.main()
