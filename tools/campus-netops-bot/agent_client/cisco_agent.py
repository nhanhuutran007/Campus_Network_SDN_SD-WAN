"""Transport SSH (Netmiko) cho thiết bị có IP quản trị — dùng ngoài EVE hoặc khi bật SSH.

Lab Campus mặc định đi qua console EVE (`campus/console.py`); file này giữ lại từ bản gốc,
đã sửa: mỗi lần gọi dùng dict kết nối riêng (trước đây dùng chung → hai request đồng thời
ghi đè host/mật khẩu của nhau) và báo lỗi bằng exception thay vì chuỗi "Timeout error".
"""
import logging

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

logger = logging.getLogger(__name__)


class DeviceError(Exception):
    pass


class AgentCiscoClient:
    def __init__(self, device_type: str = "cisco_ios"):
        self.device_type = device_type

    def _params(self, host, username, password, secret=None):
        return {"device_type": self.device_type, "host": host, "username": username,
                "password": password, "secret": secret or password}

    def _run(self, host, username, password, secret, fn):
        try:
            with ConnectHandler(**self._params(host, username, password, secret)) as conn:
                conn.enable()
                return fn(conn)
        except NetmikoTimeoutException:
            raise DeviceError(f"Hết thời gian kết nối tới {host}") from None
        except NetmikoAuthenticationException:
            raise DeviceError(f"Sai tài khoản/mật khẩu khi vào {host}") from None

    def show_command(self, command, host, username, password, secret=None) -> str:
        logger.info("SSH %s: %s", host, command)
        return self._run(host, username, password, secret,
                         lambda c: c.send_command(command, read_timeout=30))

    def ping_command(self, command, host, username, password, secret=None) -> str:
        if not command.startswith("ping"):
            raise DeviceError("Lệnh phải bắt đầu bằng 'ping'.")
        return self._run(host, username, password, secret,
                         lambda c: c.send_command(command, read_timeout=60))

    def config_command(self, commands, host, username, password, secret=None) -> str:
        """Không được gọi ở giai đoạn 1 (bot chỉ đọc); giữ cho giai đoạn 3 (có duyệt + rollback)."""
        if isinstance(commands, str):
            commands = commands.splitlines()
        commands = [c.strip() for c in commands if c.strip()]
        if not commands:
            raise DeviceError("Không có lệnh cấu hình.")
        return self._run(host, username, password, secret, lambda c: c.send_config_set(commands))
