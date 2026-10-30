"""NetBox (tuỳ chọn): tra IP thiết bị và lưu bản backup cấu hình (đã che bí mật).

Khác bản gốc: KHÔNG đọc mật khẩu từ custom field `ssh_password/ssh_secret` nữa — ai có
token đọc NetBox sẽ thấy hết mật khẩu. Credentials nằm ở file cục bộ (campus/credentials.py).
Danh mục thiết bị nạp vào NetBox bằng `scripts/export_netbox.py`.
"""
import logging
import os

from dotenv import load_dotenv

from campus.redact import redact

logger = logging.getLogger(__name__)


class NetboxClient:
    def __init__(self):
        load_dotenv()
        url, token = os.getenv("NETBOX_URL"), os.getenv("NETBOX_TOKEN")
        self.nb = None
        if url and token:
            import pynetbox
            self.nb = pynetbox.api(url=url, token=token)

    def get_device_ip(self, device_name: str) -> str | None:
        if not self.nb:
            return None
        device = self.nb.dcim.devices.get(name=device_name)
        if not device or not device.primary_ip4:
            return None
        return str(device.primary_ip4.address).split("/")[0]

    def backup_device_config(self, device_name: str, config_text: str) -> str:
        if not self.nb:
            return "LỖI: Chưa cấu hình NETBOX_URL/NETBOX_TOKEN."
        device = self.nb.dcim.devices.get(name=device_name)
        if not device:
            return f"LỖI: Không có thiết bị '{device_name}' trên NetBox."
        ctx = device.local_context_data or {}
        ctx["running_config"] = redact(config_text)
        device.local_context_data = ctx
        device.save()
        return f"Đã sao lưu cấu hình (đã che bí mật) của '{device_name}' lên NetBox."


netbox_client = NetboxClient()
