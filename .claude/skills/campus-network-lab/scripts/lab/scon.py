"""scon.py : console node EVE tu chinh server (socket toi 127.0.0.1:32768+id), co expect. Dung cho script do chay tren server.

Mat khau khong nam trong file hay dong lenh: script goi doc JSON {tag: mat khau} tu stdin (xem runsrv.py).
"""
import re, socket, time

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
IAC = re.compile(rb"\xff[\xfb-\xfe].")


class Con:
    def __init__(self, nid, base=32768):
        self.nid = nid
        self.s = socket.create_connection(("127.0.0.1", base + nid), timeout=10)
        self.s.settimeout(0.2)

    def _recv(self):
        try:
            d = self.s.recv(65535)
        except socket.timeout:
            return ""
        return ANSI.sub("", IAC.sub(b"", d).decode(errors="replace"))

    def expect(self, pat, timeout=30):
        buf = ""
        t0 = time.time()
        while time.time() - t0 < timeout:
            buf += self._recv()
            if re.search(pat, buf[-400:]):
                return buf
        raise TimeoutError("node %d: khong thay %r; cuoi: %r" % (self.nid, pat, buf[-200:]))

    def send(self, s):
        self.s.sendall(s.encode())

    def login(self, pw):
        """Viptela: dua ve prompt '#'. Tra ve True neu vua dang nhap (can exit khi xong)."""
        self.send("\r")
        o = self.expect(r"(login: ?$|Password: ?$|# ?$)", 20)
        if re.search(r"Password: ?$", o[-40:]):
            raise RuntimeError("node %d dang o Password:, cho het han" % self.nid)
        did = False
        if re.search(r"login: ?$", o[-40:]):
            self.send("admin\r")
            self.expect(r"Password: ?$", 15)
            self.send(pw + "\r")
            o = self.expect(r"(login: ?$|# ?$)", 40)
            if re.search(r"login: ?$", o[-40:]):
                raise RuntimeError("LOGIN FAILED node %d" % self.nid)
            did = True
        self.cmd("paginate false", 10)
        return did

    def cmd(self, c, timeout=60, prompt=r"# ?$"):
        self.send(c + "\r")
        return self.expect(prompt, timeout)

    def close(self, logout=False):
        if logout:
            try:
                self.send("exit\r")
                time.sleep(1)
            except OSError:
                pass
        self.s.close()
