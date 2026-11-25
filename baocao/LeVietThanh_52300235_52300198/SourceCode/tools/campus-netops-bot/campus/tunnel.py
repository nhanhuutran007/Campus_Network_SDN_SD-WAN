"""Forward cổng cục bộ → đích trong lab, đi qua SSH của server EVE (paramiko direct-tcpip).

vManage (10.9.1.10:443) và REST Ryu (ens6 node 9 :8080) chỉ tới được từ server EVE,
nên bot chạy ở laptop mở `127.0.0.1:<cổng ngẫu nhiên>` rồi dùng requests như bình thường.
"""
from __future__ import annotations

import logging
import select
import socket
import threading

log = logging.getLogger(__name__)


class Forwarder:
    def __init__(self, transport_factory, remote_host: str, remote_port: int):
        self._transport = transport_factory     # hàm trả paramiko.Transport còn sống
        self.remote = (remote_host, remote_port)
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(16)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True, name=f"fwd-{remote_host}").start()

    def _accept(self):
        while True:
            try:
                client, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._pipe, args=(client,), daemon=True).start()

    def _pipe(self, client: socket.socket):
        try:
            chan = self._transport().open_channel("direct-tcpip", self.remote, client.getpeername())
        except Exception as e:
            log.warning("Không mở được kênh tới %s:%s — %s", *self.remote, type(e).__name__)
            client.close()
            return
        try:
            while True:
                r, _, _ = select.select([client, chan], [], [], 60)
                if not r:
                    continue
                if client in r:
                    data = client.recv(65536)
                    if not data:
                        break
                    chan.sendall(data)
                if chan in r:
                    data = chan.recv(65536)
                    if not data:
                        break
                    client.sendall(data)
        except OSError:
            pass
        finally:
            chan.close()
            client.close()

    def close(self):
        self._srv.close()
