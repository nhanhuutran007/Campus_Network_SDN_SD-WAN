"""Kiem thu logic cay du lieu cua campus_switch_13.py (khong can Ryu).
Chay:  python configs/01-Site100-Campus/test/test_campus_tree.py
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import campus_switch_13 as cs  # noqa: E402

ALL = set(cs.OVS_NODES)


def links(down=()):
    return {lid: lid not in down for lid in cs.LINKS}


def nodes_of(tree):
    out = set()
    for lid in tree:
        out.update(cs.link_nodes(lid))
    return out


class TreeTest(unittest.TestCase):
    def assertSpanning(self, root, tree, connected):
        # Cay: so canh = so nut - 1 va phu het cac switch dang ket noi
        n = nodes_of(tree) | {root}
        self.assertEqual(len(tree), len(n) - 1, 'khong phai cay: %s' % sorted(tree))
        self.assertTrue(connected <= n, 'thieu switch: %s' % (connected - n))

    def test_normal(self):
        root, tree, parent = cs.compute_data_tree(ALL, links())
        self.assertEqual(root, 'C1')
        self.assertEqual(tree, {'D1-C1', 'D2-C1', 'A1-D1', 'A2-D1', 'A3-D1', 'A4-D1'})
        self.assertSpanning(root, tree, ALL)
        ports = cs.tree_ports(tree)
        self.assertEqual(ports[8], {'ens10'})
        self.assertEqual(ports[5], {'ens9', 'ens4', 'ens5', 'ens6', 'ens7'})
        self.assertEqual(ports[68], {'ens4'})

    def test_dist1_uplink_down(self):
        root, tree, _ = cs.compute_data_tree(ALL, links(down={'D1-C1'}))
        self.assertEqual(root, 'C1')
        self.assertIn('D1-D2', tree)
        self.assertSpanning(root, tree, ALL)
        for a in ('A1', 'A2', 'A3', 'A4'):
            self.assertIn(a + '-D2', tree)       # Access chuyen sang Dist-SW2

    def test_dist1_dead(self):
        conn = ALL - {5}
        root, tree, _ = cs.compute_data_tree(conn, links())
        self.assertEqual(root, 'C1')
        self.assertEqual(tree, {'D2-C1', 'A1-D2', 'A2-D2', 'A3-D2', 'A4-D2'})
        self.assertSpanning(root, tree, conn)

    def test_core1_unreachable_falls_back_core2(self):
        root, tree, _ = cs.compute_data_tree(ALL, links(down={'D1-C1', 'D2-C1'}))
        self.assertEqual(root, 'C2')
        self.assertTrue(tree & {'D1-C2', 'D2-C2'})
        self.assertFalse(tree & {'D1-C1', 'D2-C1'})
        self.assertSpanning(root, tree, ALL)

    def test_access_link_down(self):
        root, tree, _ = cs.compute_data_tree(ALL, links(down={'A1-D1'}))
        self.assertIn('A1-D2', tree)
        self.assertNotIn('A1-D1', tree)
        self.assertSpanning(root, tree, ALL)

    def test_access_isolated(self):
        root, tree, _ = cs.compute_data_tree(ALL, links(down={'A1-D1', 'A1-D2'}))
        self.assertNotIn(68, nodes_of(tree))
        self.assertSpanning(root, tree, ALL - {68})

    def test_no_core_link(self):
        root, tree, _ = cs.compute_data_tree(
            ALL, links(down={'D1-C1', 'D2-C1', 'D1-C2', 'D2-C2'}))
        self.assertIsNone(root)
        self.assertEqual(tree, set())

    def test_deterministic(self):
        r = [cs.compute_data_tree(ALL, links(down={'D1-C1'})) for _ in range(20)]
        self.assertTrue(all(x[1] == r[0][1] for x in r))

    def test_probe_mac_unique(self):
        macs = [cs.probe_mac(l) for l in cs.CORE_PROBE]
        self.assertEqual(len(set(macs)), len(macs))
        for m in macs:
            self.assertTrue(m.startswith(cs.PROBE_MAC_BASE))


if __name__ == '__main__':
    unittest.main(verbosity=2)


class NonBlockingSendTest(unittest.TestCase):
    def test_full_queue_drops_instead_of_blocking(self):
        import queue
        import threading

        class DP(object):
            pass
        dp = DP()
        dp.send_q = queue.Queue(2)
        dp._send_q_sem = threading.BoundedSemaphore(2)   # cung API voi eventlet
        cs._nonblocking_send(dp)
        self.assertTrue(dp.send(b'a'))
        self.assertTrue(dp.send(b'b'))
        t0 = time.time()
        self.assertFalse(dp.send(b'c'))          # ban goc se treo o day
        self.assertLess(time.time() - t0, cs.SEND_WAIT + 0.5)
        self.assertEqual(dp.campus_dropped, 1)
        dp.send_q = None
        dp._send_q_sem.release()
        self.assertFalse(dp.send(b'd'))          # dang dong ket noi
