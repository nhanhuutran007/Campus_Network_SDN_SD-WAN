"""Kiểm thử offline (không cần lab): python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from campus import guard, inventory, service  # noqa: E402
from campus.console import ConsoleError, Session  # noqa: E402
from campus.credentials import CredentialError, CredentialStore  # noqa: E402
from campus.redact import redact  # noqa: E402

# .unl chuẩn là bản trên server EVE; đặt CAMPUS_UNL=<bản tải về> để đối chiếu đúng bản đang chạy
UNL = os.getenv("CAMPUS_UNL") or os.path.join(ROOT, "..", "..", "Campus Network SDN SD-WAN.unl")


class TestInventory(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(UNL), "không có .unl")
    def test_matches_unl(self):
        self.assertEqual(inventory.verify_against_unl(UNL), [])

    def test_unique(self):
        names = [d.name.lower() for d in inventory.DEVICES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(inventory.BY_ID), len(inventory.DEVICES))

    def test_easy_to_confuse_ids(self):
        r = inventory.resolve
        self.assertEqual(r("Access-SW1").node_id, 68)
        self.assertEqual(r("Access-SW2").node_id, 66)
        self.assertEqual(r("vEdge2-S200").node_id, 42)
        self.assertEqual(r("vEdge2-S300").node_id, 40)
        self.assertEqual(r("Brand-FW-S300").node_id, 39)
        self.assertEqual(r("node 72").name, "DHCP-Server")
        self.assertEqual(r("core1").name, "Core-SW1")
        self.assertEqual(r("vedge1 s200").name, "vEdge1-S200")
        self.assertIsNone(r("không-có"))

    def test_by_site(self):
        self.assertEqual({d.site for d in inventory.by_site("Site 300")}, {"300"})


class TestGuard(unittest.TestCase):
    def ok(self, platform, cmd):
        allowed, _ = guard.check(platform, cmd)
        return allowed

    def test_allowed(self):
        self.assertTrue(self.ok("ios", "show ip bgp summary"))
        self.assertTrue(self.ok("ios", "sh run | include interface"))
        self.assertTrue(self.ok("asa", "show failover"))
        self.assertTrue(self.ok("ios", "ping 10.1.90.10"))
        self.assertTrue(self.ok("viptela", "show bfd sessions | tab"))
        self.assertTrue(self.ok("ios", "show run | include password|secret"))      # regex có "|"
        self.assertTrue(self.ok("viptela", "show running-config | include a|b | nomore"))

    def test_blocked(self):
        for cmd in ["configure terminal", "conf t", "reload", "write erase", "copy run start",
                    "clear ip bgp *", "show run | redirect flash:x", "show run\nreload",
                    "show ver; reload", "debug all", "ping", "request software reset",
                    "show tech-support", "ping 1.1.1.1 | include !", ""]:
            self.assertFalse(self.ok("ios", cmd), cmd)

    def test_viptela_ping_gets_count(self):
        ok, cmd = guard.check("viptela", "ping vpn 1 10.1.90.10")
        self.assertTrue(ok)
        self.assertTrue(cmd.endswith("count 5"))


class TestRedact(unittest.TestCase):
    def test_secrets_hidden(self):
        cfg = ("username admin privilege 15 secret 9 $9$abc\n"
               "enable password 0 S3cret!\n"
               "snmp-server community Pub1ic RO 98\n"
               " key-string 7 0822455D0A16\n"
               "interface Vlan10\n ip address 10.1.10.1 255.255.255.0")
        out = redact(cfg)
        for secret in ("$9$abc", "S3cret!", "Pub1ic", "0822455D0A16"):
            self.assertNotIn(secret, out)
        self.assertIn("ip address 10.1.10.1 255.255.255.0", out)

    def test_counters_untouched(self):
        line = "     0 input errors, 0 CRC, 0 frame, 0 overrun"
        self.assertEqual(redact(line), line)


class TestCredentials(unittest.TestCase):
    def test_lookup(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("| Thiết bị | Tài khoản | Mật khẩu | Ghi chú |\n|---|---|---|---|\n"
                    "| vEdge chi nhánh: node 29 | admin | `pw-branch` | x |\n")
        try:
            store = CredentialStore(f.name)
            self.assertEqual(store.get("vEdge chi nhánh"), ("admin", "pw-branch"))
            with self.assertRaises(CredentialError):
                store.get("không có")
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        with self.assertRaises(CredentialError):
            CredentialStore(os.path.join(tempfile.gettempdir(), "khong-ton-tai.md")).get("x")


class FakeChannel:
    """Giả lập console: mỗi lần send() trả về đoạn output theo kịch bản."""

    def __init__(self, script):
        self.script = list(script)      # [(chuỗi gửi mong đợi hoặc None, phản hồi)]
        self.pending = b""
        self.sent = []

    def send(self, data):
        self.sent.append(data)
        if self.script:
            _, resp = self.script.pop(0)
            self.pending += resp.encode()

    def recv(self, n):
        if not self.pending:
            raise TimeoutError
        d, self.pending = self.pending, b""
        return d

    def close(self):
        pass


class FakeCreds:
    def get(self, tag):
        return "admin", "pw"


class TestSession(unittest.TestCase):
    def session(self, name, script):
        s = Session(FakeChannel(script), inventory.resolve(name), FakeCreds())
        return s

    def test_ios_enable_and_show(self):
        s = self.session("Core-SW1", [
            ("", "\r\nCore-SW1>"),
            ("enable", "enable\r\nCore-SW1#"),
            ("terminal length 0", "terminal length 0\r\nCore-SW1#"),
            ("show vrrp brief", "show vrrp brief\r\nInterface  Grp Pri\r\nVl10  10 110\r\nCore-SW1#"),
        ])
        s.prepare()
        self.assertEqual(s.prompt, "Core-SW1#")
        out = s.run("show vrrp brief")
        self.assertIn("Vl10", out)
        self.assertNotIn("Core-SW1#", out)

    def test_refuses_config_mode(self):
        s = self.session("Core-SW1", [("", "\r\nCore-SW1(config-if)#")])
        with self.assertRaises(ConsoleError):
            s.prepare()

    def test_viptela_login_incorrect_stops(self):
        s = self.session("vEdge1-S200", [
            ("", "\r\nvEdge1-S200 login:"),
            ("admin", "admin\r\nPassword:"),
            ("pw", "\r\nLogin incorrect\r\nvEdge1-S200 login:"),
        ])
        with self.assertRaises(ConsoleError) as cm:
            s.prepare()
        self.assertIn("không thử lại", str(cm.exception))
        self.assertEqual(len(s.ch.sent), 3)     # không gửi lại mật khẩu lần hai

    def test_viptela_login_ok(self):
        s = self.session("vEdge1-S200", [
            ("", "\r\nvEdge1-S200 login:"),
            ("admin", "admin\r\nPassword:"),
            ("pw", "\r\nWelcome\r\nvEdge1-S200#"),
            ("paginate false", "paginate false\r\nvEdge1-S200#"),
        ])
        s.prepare()
        self.assertTrue(s.logged_in_by_us)
        self.assertEqual(s.prompt, "vEdge1-S200#")


class TestService(unittest.TestCase):
    def test_unmanaged_and_unknown(self):
        self.assertFalse(service.run_command("Access-SW1", "show version").ok)
        self.assertFalse(service.run_command("không-có", "show version").ok)
        self.assertFalse(service.run_command("Core-SW1", "conf t").ok)

    def test_list_devices(self):
        res = service.list_devices("200")
        self.assertTrue(res.ok)
        self.assertIn("vEdge2-S200", res.text)


if __name__ == "__main__":
    unittest.main()
