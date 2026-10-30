"""Client REST chỉ-đọc cho vManage (dataservice) và Ryu (Campus SDN Console + ofctl_rest).

Mặc định đi qua tunnel SSH của server EVE (`tunnel.Forwarder`). Nếu bot chạy ngay trên server
EVE, đặt VMANAGE_URL / SDN_CTL thành URL thật và VMANAGE_DIRECT=1 / SDN_DIRECT=1 để bỏ tunnel.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from urllib.parse import urlparse

import requests
import urllib3

from .console import EveConsole
from .tunnel import Forwarder

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)   # vManage dùng chứng chỉ tự ký
log = logging.getLogger(__name__)

# Alarm "ồn": vEdge 1–2 vCPU sinh hàng nghìn cpu/memory-usage mỗi tuần — không đẩy lên Telegram.
NOISY_TYPES = set(filter(None, os.getenv("ALERT_NOISY_TYPES", "cpu-usage,memory-usage,disk-usage").split(",")))


class LabApiError(Exception):
    pass


class _Endpoint:
    """URL gốc tới một dịch vụ trong lab, qua tunnel nếu cần (tạo một lần, dùng lại)."""

    def __init__(self, console: EveConsole, url: str, direct: bool):
        self.console, self.url, self.direct = console, url.rstrip("/"), direct
        self._fwd: Forwarder | None = None
        self._lock = threading.Lock()

    def base(self) -> str:
        if self.direct:
            return self.url
        with self._lock:
            u = urlparse(self.url)
            if self._fwd is None:
                port = u.port or (443 if u.scheme == "https" else 80)
                self._fwd = Forwarder(self.console.transport, u.hostname, port)
            return f"{u.scheme}://127.0.0.1:{self._fwd.port}{u.path}"


class VManage:
    def __init__(self, console: EveConsole):
        self.ep = _Endpoint(console, os.getenv("VMANAGE_URL", "https://10.9.1.10"),
                            os.getenv("VMANAGE_DIRECT") == "1")
        self.cred_tag = os.getenv("VMANAGE_CRED_TAG", "vManager (33)")
        self.creds = console.creds
        self._s: requests.Session | None = None
        self._login_at = 0.0
        self._lock = threading.Lock()

    def _session(self) -> requests.Session:
        with self._lock:
            if self._s and time.time() - self._login_at < 20 * 60:
                return self._s
            user, pw = self.creds.get(self.cred_tag)
            s = requests.Session()
            s.verify = False
            base = self.ep.base()
            try:
                r = s.post(base + "/j_security_check", data={"j_username": user, "j_password": pw}, timeout=30)
            except requests.RequestException as e:
                raise LabApiError(f"vManage không phản hồi ({type(e).__name__})") from None
            if r.status_code != 200 or "<html" in r.text.lower():
                raise LabApiError("Đăng nhập vManage thất bại (sai tài khoản hoặc vManage chưa sẵn sàng).")
            tok = s.get(base + "/dataservice/client/token", timeout=30)
            if tok.status_code == 200:
                s.headers["X-XSRF-TOKEN"] = tok.text
            self._s, self._login_at = s, time.time()
            return s

    def _call(self, method: str, path: str, **kw):
        for attempt in (1, 2):
            s = self._session()
            try:
                r = s.request(method, self.ep.base() + path, timeout=60, **kw)
            except requests.RequestException as e:
                raise LabApiError(f"vManage không phản hồi ({type(e).__name__})") from None
            if r.status_code in (401, 403) or "<html" in r.text[:200].lower():
                self._s = None          # phiên hết hạn → đăng nhập lại một lần
                if attempt == 1:
                    continue
            if r.status_code != 200:
                raise LabApiError(f"vManage {path} trả HTTP {r.status_code}")
            return r.json().get("data", [])
        raise LabApiError("vManage từ chối phiên đăng nhập.")

    def devices(self) -> list[dict]:
        return self._call("GET", "/dataservice/device")

    def device_data(self, path: str, system_ip: str) -> list[dict]:
        """Dữ liệu realtime một thiết bị: /dataservice/device/<...>?deviceId=<system-ip> (chỉ đọc)."""
        if not path.startswith("/dataservice/device/"):
            raise LabApiError("Chỉ cho đọc /dataservice/device/*")
        return self._call("GET", f"{path}?deviceId={system_ip}")

    def alarms(self, hours: int = 1, size: int = 1000, include_noisy: bool = False) -> list[dict]:
        q = {"query": {"condition": "AND", "rules": [
            {"value": [str(hours)], "field": "entry_time", "type": "date", "operator": "last_n_hours"}]},
            "size": size}
        data = self._call("POST", "/dataservice/alarms", json=q)
        if not include_noisy:
            data = [a for a in data if a.get("type") not in NOISY_TYPES]
        return sorted(data, key=lambda a: a.get("entry_time", 0))


class Ryu:
    def __init__(self, console: EveConsole):
        url = os.getenv("SDN_CTL", "")
        self.ep = _Endpoint(console, url, os.getenv("SDN_DIRECT") == "1") if url else None

    def _get(self, path: str):
        if self.ep is None:
            raise LabApiError("Chưa đặt SDN_CTL (vd http://<IP ens6 node 9>:8080) — IP ens6 lấy DHCP, "
                              "xem 'ip neigh' trên server EVE.")
        try:
            r = requests.get(self.ep.base() + path, timeout=20)
        except requests.RequestException as e:
            raise LabApiError(f"Ryu controller không phản hồi ({type(e).__name__})") from None
        if r.status_code != 200:
            raise LabApiError(f"Ryu {path} trả HTTP {r.status_code}")
        return r.json()

    def health(self) -> dict:
        h = self._get("/campus/health")
        if "error" in h:
            raise LabApiError(f"Ryu: {h['error']}")
        return h

    def switches(self) -> list[int]:
        return self._get("/stats/switches")

    def flows(self, dpid: int) -> list[dict]:
        return self._get(f"/stats/flow/{dpid}").get(str(dpid), [])


def alarm_hosts(a: dict) -> list[str]:
    return [v.get("host-name") for v in a.get("values_short_display") or a.get("values") or [] if v.get("host-name")]


def alarm_target(a: dict) -> str:
    """Tên thiết bị; alarm cấp site (BFD_Site_Up…) không có host-name → 'site <id>'."""
    hosts = alarm_hosts(a)
    if hosts:
        return ", ".join(hosts)
    sites = sorted({str(v["site-id"]) for v in a.get("values") or [] if v.get("site-id")})
    return ", ".join(f"site {x}" for x in sites) or "?"


def is_recovery(a: dict) -> bool:
    t = a.get("type", "")
    return t.endswith("_up") or t.endswith("-up")
