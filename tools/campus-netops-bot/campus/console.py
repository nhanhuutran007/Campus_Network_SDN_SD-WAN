"""Chạy lệnh qua console telnet của node EVE-NG.

Đường đi: SSH tới server EVE → kênh `direct-tcpip` tới 127.0.0.1:<32768 + 128*tenant + node-id>.
Không cần IP quản trị trên thiết bị, nên vẫn vào được khi mất VLAN 99 hay mất route.

Rào an toàn của driver:
- Console đang ở config mode / initial dialog / hỏi mật khẩu lạ → dừng, không gõ đè
  (có thể đang có người thao tác).
- Đăng nhập sai một lần là dừng (vEdge khoá tài khoản ~15 phút nếu thử lại).
- Mỗi node chỉ một phiên tại một thời điểm (console vEdge chỉ nhận 1 session).
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import threading
import time

from .credentials import CredentialStore
from .inventory import Device

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\x1b[=>]")
PROMPT = re.compile(r"(?m)^([\w.\-/]+(?:\([\w\-]+\))?)([>#])\s*$")
TIMEOUTS = {"show": 60, "ping": 60, "traceroute": 120}
# paramiko in "Secsh channel open FAILED" mỗi khi node tắt — lỗi đã được báo bằng ConsoleError
logging.getLogger("paramiko.transport").setLevel(logging.CRITICAL)


class ConsoleError(Exception):
    pass


def clean(raw: str) -> str:
    return ANSI.sub("", raw.replace("\x00", "")).replace("\r", "")


def last_line(text: str) -> str:
    lines = [l for l in text.split("\n") if l.strip()]
    return lines[-1].rstrip() if lines else ""


class Session:
    """Một phiên console đã sẵn sàng nhận lệnh (đã enable / đăng nhập)."""

    def __init__(self, channel, device: Device, creds: CredentialStore):
        self.ch = channel
        self.dev = device
        self.creds = creds
        self.prompt = ""          # "Host#" ở exec mode
        self._prompt_re = None    # khớp cả "Host#" lẫn "Host(config-if)#"
        self.logged_in_by_us = False
        self._last_tail = ""

    # --- I/O mức thấp ---
    def _read(self, until=None, quiet=1.5, limit=10.0) -> str:
        """Đọc tới khi `until(buf)` đúng, hoặc im lặng `quiet` giây, hoặc hết `limit`."""
        # làm sạch trên toàn buffer: chuỗi ANSI (vd ESC[?7h của vEdge) có thể bị cắt giữa hai lần recv
        raw, t0, last = b"", time.time(), time.time()
        while time.time() - t0 < limit:
            try:
                data = self.ch.recv(65535)
            except Exception:       # socket.timeout của paramiko
                data = b""
            if data:
                raw += data
                last = time.time()
                if until and until(clean(raw.decode("utf-8", "replace"))):
                    break
                continue
            if until is None and time.time() - last > quiet:
                break
            time.sleep(0.05)
        return clean(raw.decode("utf-8", "replace"))

    def _send(self, text: str):
        self.ch.send(text + "\r")

    def _set_prompt(self, host: str):
        self.prompt = host + "#"
        self._prompt_re = re.compile(re.escape(host) + r"(\([^)]*\))?#\s*$")

    def _at_prompt(self, buf: str) -> bool:
        return bool(self._prompt_re and self._prompt_re.search(last_line(buf)))

    @property
    def in_config_mode(self) -> bool:
        return self._last_tail.endswith(")#")

    # --- khởi tạo theo nền tảng ---
    def prepare(self):
        self._send("")
        out = self._read(quiet=1.5, limit=10)
        tail = last_line(out)
        low = out.lower()
        if "initial configuration dialog" in low or tail.endswith("[yes/no]:"):
            raise ConsoleError("Thiết bị đang ở initial configuration dialog — cần xử lý tay.")
        if ("first login" in low or "reset by the administrator" in low
                or re.search(r"(old|new) password:\s*$", tail.lower())):
            # ASA bắt đổi mật khẩu ở lần SSH đầu sau khi user được tạo HOẶC admin đặt lại mật khẩu
            # (`username ... password` từ CLI) — không tự đổi
            self.ch.send("\x03")
            raise ConsoleError("ASA bắt đổi mật khẩu (user mới hoặc admin vừa đặt lại mật khẩu) "
                               "— SSH tay một lần và đặt lại đúng mật khẩu trong file credentials.")
        if re.search(r"\)#\s*$", tail):
            raise ConsoleError("Console đang ở config mode (có thể có người đang cấu hình) — không gõ đè.")
        if self.dev.platform == "viptela":
            self._prepare_viptela(tail)
        else:
            self._prepare_ios_like(tail)

    def _prepare_ios_like(self, tail: str):
        if tail.endswith(">"):
            self._send("enable")
            out = self._read(quiet=1.5, limit=8)
            if "assword" in last_line(out):
                if "new password" in last_line(out).lower():
                    # ASA 9.12+ chưa có enable password: gửi gì vào đây là ĐẶT mật khẩu mới
                    self.ch.send("\x03")
                    raise ConsoleError("ASA hỏi 'Enter new password' khi enable (chưa có enable password, "
                                       "user chưa auto-enable) — dừng, không đặt mật khẩu.")
                if self.dev.platform != "asa":
                    self.ch.send("\x03")
                    raise ConsoleError("IOS hỏi enable password không có trong bảng — dừng.")
                _, pw = self.creds.get(self.dev.cred_tag)
                self._send(pw)
                out = self._read(quiet=1.5, limit=8)
            tail = last_line(out)
        m = PROMPT.match(tail)
        if not m or m.group(2) != "#":
            raise ConsoleError(f"Không vào được privileged mode (prompt cuối: {tail[-40:]!r}).")
        self._set_prompt(m.group(1))
        self._send("terminal pager 0" if self.dev.platform == "asa" else "terminal length 0")
        self._read(until=self._at_prompt, limit=8)

    def _prepare_viptela(self, tail: str):
        if tail.endswith("login:"):
            user, pw = self.creds.get(self.dev.cred_tag)
            self._send(user)
            out = self._read(until=lambda b: last_line(b).endswith("Password:"), limit=15)
            if not last_line(out).endswith("Password:"):
                raise ConsoleError("Không thấy 'Password:' sau khi gửi tài khoản.")
            self._send(pw)
            out = self._read(until=lambda b: bool(re.search(r"#\s*$", b)) or "incorrect" in b.lower(),
                             limit=40)
            if "incorrect" in out.lower():
                raise ConsoleError("Login incorrect — dừng, không thử lại (tránh khoá tài khoản 15 phút). "
                                   "Nếu node mới boot, chờ ~3 phút rồi thử lại.")
            tail = last_line(out)
            self.logged_in_by_us = True
        elif tail.endswith("Password:"):
            self.ch.send("\x03")
            raise ConsoleError("Console đang dở bước nhập mật khẩu — thử lại sau.")
        m = PROMPT.match(tail)
        if not m or m.group(2) != "#":
            raise ConsoleError(f"Không thấy prompt Viptela (prompt cuối: {tail[-40:]!r}). "
                               "Node có thể chưa boot xong.")
        self._set_prompt(m.group(1))
        self._send("paginate false")
        self._read(until=self._at_prompt, limit=8)

    # --- chạy lệnh ---
    def run(self, command: str, timeout: float | None = None, answers=()) -> str:
        """Gửi một lệnh, chờ prompt. `answers` = [(regex, trả lời)] cho câu hỏi xác nhận
        (vd "Destination filename [x]?" của `copy`)."""
        verb = (command.split() or [""])[0].lower()
        limit = timeout or next((t for v, t in TIMEOUTS.items() if v.startswith(verb[:2])), 60)
        # Xả dữ liệu tồn (log %SYS-5-CONFIG_I + prompt in lại khi `logging synchronous`), nếu không
        # lệnh sau sẽ nhận nhầm prompt cũ và mọi output lệch đi một lệnh.
        self._read(quiet=0.3, limit=1.5)
        self._send(command)
        t0, out = time.time(), ""
        pats = [(re.compile(p), r) for p, r in answers]
        echo = command.strip()[:15]

        def question(buf: str):
            tail = last_line(buf)
            return next((r for p, r in pats if p.search(tail)), None)

        def finished(buf: str) -> bool:
            # chỉ nhận prompt xuất hiện SAU echo của chính lệnh này
            body = (out + buf)
            if echo and echo not in body:
                return False
            return self._at_prompt(body[body.find(echo) + len(echo):] if echo else body)

        while True:
            chunk = self._read(until=lambda b: finished(b) or question(b) is not None,
                               limit=max(1.0, limit - (time.time() - t0)))
            out += chunk
            reply = question(chunk) if chunk else None
            if reply is None or finished("") or time.time() - t0 >= limit:
                break
            self._send(reply)
            out += "\n"
        done = finished("")
        self._last_tail = last_line(out).rstrip()
        if not done:
            self.ch.send("\x03")    # huỷ lệnh còn chạy (ping/traceroute dài)
            self._read(quiet=1, limit=4)
        lines = out.split("\n")
        idx = next((i for i, l in enumerate(lines) if echo and echo in l), -1)
        lines = lines[idx + 1:]                     # bỏ log tồn + dòng echo lệnh
        if done and lines and self._at_prompt(lines[-1]):
            lines = lines[:-1]                      # bỏ prompt cuối
        text = "\n".join(lines).strip("\n")
        if not done:
            text += f"\n[!] Hết {limit:.0f} s mà chưa thấy prompt — output có thể bị cắt."
        return text

    def close(self):
        try:
            if self.logged_in_by_us:
                self._send("exit")
                self._read(quiet=0.5, limit=2)
        finally:
            self.ch.close()


class EveConsole:
    """Quản lý một kết nối SSH tới server EVE và mở phiên console cho từng node."""

    def __init__(self, creds: CredentialStore | None = None):
        self.creds = creds or CredentialStore()
        self.host = os.getenv("EVE_HOST", "100.86.110.39")
        self.tenant = int(os.getenv("EVE_TENANT", "0"))
        self.cred_tag = os.getenv("EVE_CRED_TAG", "EVE-NG SDWAN_LAB")
        self.port_base = 32768 + 128 * self.tenant
        self._ssh = None
        self._ssh_lock = threading.Lock()
        self._node_locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def transport(self):
        import paramiko
        with self._ssh_lock:
            if self._ssh is None or not self._ssh.get_transport() or not self._ssh.get_transport().is_active():
                user, pw = self.creds.get(self.cred_tag)
                c = paramiko.SSHClient()
                c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    c.connect(self.host, username=user, password=pw, timeout=15,
                              look_for_keys=False, allow_agent=False)
                except Exception as e:
                    raise ConsoleError(f"Không SSH được tới server EVE {self.host}: {type(e).__name__}") from None
                self._ssh = c
            return self._ssh.get_transport()

    def _node_lock(self, node_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._node_locks.setdefault(node_id, threading.Lock())

    def run(self, device: Device, commands: list[str]) -> list[str]:
        with self.session(device) as s:
            return [s.run(c) for c in commands]

    @contextlib.contextmanager
    def session(self, device: Device):
        """Phiên console giữ nguyên qua nhiều bước (dùng cho quy trình thay đổi cấu hình)."""
        if not device.managed:
            raise ConsoleError(f"{device.name} ({device.platform}) chưa hỗ trợ điều khiển qua console.")
        lock = self._node_lock(device.node_id)
        if not lock.acquire(timeout=90):
            raise ConsoleError(f"{device.name} đang bận phiên khác — thử lại sau.")
        try:
            port = self.port_base + device.node_id
            try:
                ch = self.transport().open_channel("direct-tcpip", ("127.0.0.1", port), ("127.0.0.1", 0))
            except ConsoleError:
                raise
            except Exception:
                raise ConsoleError(f"Không mở được console {device.name} (cổng {port}) — node có đang chạy?") from None
            ch.settimeout(0.3)
            s = Session(ch, device, self.creds)
            try:
                s.prepare()
                yield s
            finally:
                s.close()
        finally:
            lock.release()

    def close(self):
        with self._ssh_lock:
            if self._ssh:
                self._ssh.close()
                self._ssh = None


class SshTransport:
    """Quản trị in-band: SSH thẳng tới IP quản trị của thiết bị (chạy trên NetOps-Server trong topo).

    Dùng lại `Session` (cùng logic prompt, xác nhận, chống gõ đè config mode) trên kênh
    `invoke_shell` của paramiko — thư viện nền của Netmiko. Thiết bị không có `mgmt_ip`
    thì nằm ngoài phạm vi: bot không có đường nào khác để vào.
    """

    def __init__(self, creds: CredentialStore | None = None):
        self.creds = creds or CredentialStore()
        self.cred_tag = os.getenv("NETOPS_CRED_TAG", "netops (SSH Site 100)")
        # ASA 9.20 cấm 3 ký tự liên tiếp/lặp trong mật khẩu nên FW có dòng mật khẩu netops riêng
        self.fw_cred_tag = os.getenv("NETOPS_FW_CRED_TAG", "netops FW")
        self._node_locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _node_lock(self, node_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._node_locks.setdefault(node_id, threading.Lock())

    def run(self, device: Device, commands: list[str]) -> list[str]:
        with self.session(device) as s:
            return [s.run(c) for c in commands]

    @contextlib.contextmanager
    def session(self, device: Device):
        import paramiko
        if not device.managed or not device.mgmt_ip:
            raise ConsoleError(f"{device.name} ngoài phạm vi quản lý in-band của NetOps-Server (chưa có IP quản trị/SSH).")
        lock = self._node_lock(device.node_id)
        if not lock.acquire(timeout=90):
            raise ConsoleError(f"{device.name} đang bận phiên khác — thử lại sau.")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            user, pw = self.creds.get(self.fw_cred_tag if device.platform == "asa" else self.cred_tag)
            try:
                client.connect(device.mgmt_ip, username=user, password=pw, timeout=15, banner_timeout=20,
                               auth_timeout=20, look_for_keys=False, allow_agent=False)
            except paramiko.AuthenticationException:
                raise ConsoleError(f"SSH {device.name} ({device.mgmt_ip}): sai tài khoản netops.") from None
            except Exception as e:
                raise ConsoleError(f"SSH {device.name} ({device.mgmt_ip}) không kết nối được: {type(e).__name__}") from None
            ch = client.invoke_shell(width=511, height=0)
            ch.settimeout(0.3)
            s = Session(ch, device, self.creds)
            try:
                s.prepare()
                yield s
            finally:
                s.close()
        finally:
            client.close()
            lock.release()
