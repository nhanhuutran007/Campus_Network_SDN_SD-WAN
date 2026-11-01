"""Đẩy lease DHCP sang web Site 900 — offline, output ASA thật đọc ngày 01/11/2026."""
import unittest

from campus import lease_push

S200 = """IP address       Client Identifier        Lease expiration        Type

    10.2.60.102    0100.5079.6668.2c            2677 seconds    Automatic
    10.2.60.103    0100.5079.6668.2b            2667 seconds    Automatic
    10.2.70.100    0100.5079.6668.2e            3022 seconds    Automatic
    10.2.70.101       0006.0000.4700            1834 seconds    Automatic
"""
S400 = """IP address       Client Identifier        Lease expiration        Type
    10.4.50.100    0100.5079.6668.33            2797 seconds    Automatic
    10.4.60.100       0006.0000.5200            2818 seconds    Automatic
"""


class FakeDhcp:
    def __init__(self, ok=True):
        self.ok = ok

    def available(self):
        return self.ok

    def leases(self, scope):
        if scope == "10.1.10.0":
            return [{"IP": "10.1.10.100", "ClientId": "00-50-79-66-68-0e", "HostName": None, "AddressState": "Active"}]
        return []


class TestLeasePush(unittest.TestCase):
    def test_parse_asa(self):
        rows = lease_push.parse_asa_binding(S200)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1], {"ip": "10.2.60.103", "client_id": "0100.5079.6668.2b", "expires_s": 2667})

    def test_collect_one_fw_down_others_still_sent(self):
        def run(dev, cmd):
            self.assertEqual(cmd, "show dhcpd binding")
            if dev == "Brand-FW-S300":
                raise TimeoutError("SSH timeout")
            return {"Brand-FW-S200": S200, "Brand-FW-S400": S400}[dev]
        p = lease_push.collect(run=run, dhcp=FakeDhcp())
        self.assertEqual(len(p["leases"]), 4 + 2 + 1)
        self.assertIn("Brand-FW-S300", p["errors"])
        s100 = [x for x in p["leases"] if x["site"] == "100"]
        self.assertEqual(s100[0]["client_id"], "00-50-79-66-68-0e")

    def test_collect_not_on_dhcp_server(self):
        p = lease_push.collect(run=lambda d, c: "", dhcp=FakeDhcp(ok=False))
        self.assertEqual(p["leases"], [])
        self.assertIn("DHCP-Server", p["errors"])

    def test_push_unreachable(self):
        with self.assertRaises(RuntimeError):
            lease_push.push({"leases": []}, "http://127.0.0.1:9/api/leases", "x", timeout=2)


if __name__ == "__main__":
    unittest.main()
