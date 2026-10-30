"""Theo dõi chủ động: alarm vManage + sức khoẻ Ryu → danh sách Alert để đẩy lên Telegram.

Không phụ thuộc Telegram (kiểm thử offline được). Mỗi lần `poll()` trả về các alert MỚI:
- vManage: alarm chưa thấy (theo uuid), đã lọc cpu/memory-usage; lần poll đầu chỉ ghi nhớ,
  không đổ dồn alarm cũ. Mất vManage/khôi phục cũng là một alert (kế hoạch B của mail cảnh báo:
  báo được cả khi chính vManage chết).
- Ryu: so trạng thái với lần trước — OVS mất/nối lại controller, link chết/sống, controller khựng dài.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field

from . import inventory
from .labapi import LabApiError, alarm_hosts, alarm_target, is_recovery

log = logging.getLogger(__name__)
STALL_ALERT_MS = int(os.getenv("ALERT_STALL_MS", "6000"))    # > 6 s là OVS bắt đầu mất kết nối


@dataclass
class Alert:
    key: str                 # dùng cho nút "Tắt 1 giờ"
    level: str               # critical | major | info | recovery
    text: str
    diagnose: list[str] = field(default_factory=list)   # đích cho nút "Chẩn đoán"

    @property
    def icon(self) -> str:
        return {"critical": "🔴", "major": "🟠", "recovery": "🟢"}.get(self.level, "🔵")


class AlertMonitor:
    def __init__(self, vmanage=None, ryu=None, state_file: str | None = None):
        self.vm, self.ryu = vmanage, ryu
        self.state_file = state_file
        self.seen: set[str] = set()
        self.primed = False
        self.vm_down_since: float | None = None
        self.vm_fail = 0
        self.ryu_prev: dict | None = None
        self.ryu_down_since: float | None = None
        self.muted: dict[str, float] = {}
        self._last_stall: float | None = None
        self._load()

    # ---------------------------------------------------------------- trạng thái
    def _load(self):
        if self.state_file and os.path.isfile(self.state_file):
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    st = json.load(f)
                self.seen = set(st.get("seen", []))
                self.primed = bool(self.seen)
                self.muted = {k: v for k, v in st.get("muted", {}).items() if v > time.time()}
            except (OSError, ValueError):
                log.warning("Không đọc được %s, bắt đầu trạng thái mới", self.state_file)

    def _save(self):
        if not self.state_file:
            return
        tmp = self.state_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"seen": sorted(self.seen)[-5000:], "muted": self.muted}, f)
        os.replace(tmp, self.state_file)

    def mute(self, key: str, seconds: int = 3600):
        self.muted[key] = time.time() + seconds
        self._save()

    def _is_muted(self, key: str) -> bool:
        return self.muted.get(key, 0) > time.time()

    # ---------------------------------------------------------------- vManage
    def _poll_vmanage(self) -> list[Alert]:
        try:
            alarms = self.vm.alarms(hours=1)
        except LabApiError as e:
            self.vm_fail += 1
            # 2 lần liên tiếp mới báo — tránh báo nhầm khi một request lỡ timeout
            if self.vm_fail == 2 and self.vm_down_since is None:
                self.vm_down_since = time.time()
                return [Alert("vmanage-down", "critical",
                              f"vManage không phản hồi: {e}\nMail cảnh báo của vManage cũng sẽ không gửi được.",
                              ["vManage"])]
            return []
        out = []
        self.vm_fail = 0
        if self.vm_down_since is not None:
            mins = (time.time() - self.vm_down_since) / 60
            self.vm_down_since = None
            out.append(Alert("vmanage-down", "recovery", f"vManage phản hồi trở lại sau {mins:.0f} phút."))
        new = [a for a in alarms if a.get("uuid") not in self.seen]
        self.seen.update(a.get("uuid") for a in new)
        if not self.primed:          # lần đầu: chỉ ghi nhớ
            self.primed = True
            return out
        for a in new:
            hosts = alarm_hosts(a)
            key = f"{a.get('type')}:{alarm_target(a)}"
            if self._is_muted(key):
                continue
            level = "recovery" if is_recovery(a) else {"Critical": "critical", "Major": "major"}.get(
                a.get("severity"), "info")
            diag = [h for h in hosts if (d := inventory.resolve(h)) and d.role == "vedge"]
            text = (f"{a.get('rule_name_display', a.get('type'))} — {alarm_target(a)}\n"
                    f"{a.get('message', '')}")
            out.append(Alert(key, level, text, [] if level == "recovery" else diag))
        return out

    # ---------------------------------------------------------------- Ryu
    def _poll_ryu(self) -> list[Alert]:
        try:
            h = self.ryu.health()
        except LabApiError as e:
            if self.ryu_down_since is None and self.ryu_prev is not None:
                self.ryu_down_since = time.time()
                return [Alert("ryu-down", "critical", f"Mất kết nối Ryu controller: {e}", ["sdn"])]
            return []
        out = []
        if self.ryu_down_since is not None:
            self.ryu_down_since = None
            out.append(Alert("ryu-down", "recovery", "Ryu controller phản hồi trở lại."))
        cur = {"conn": {s["name"]: bool(s.get("connected")) for s in h.get("switches", [])},
               "bad_links": sorted(m for lvl, m in h.get("issues", []) if m.startswith("Lien ket"))}
        prev, self.ryu_prev = self.ryu_prev, cur
        if prev is not None:
            for name, ok in cur["conn"].items():
                was = prev["conn"].get(name)
                if was and not ok and not self._is_muted(f"ovs:{name}"):
                    out.append(Alert(f"ovs:{name}", "critical", f"{name} mất kết nối Ryu controller "
                                     "(OVS giữ flow cũ, thay đổi topology sẽ không được xử lý).", ["sdn"]))
                elif was is False and ok:
                    out.append(Alert(f"ovs:{name}", "recovery", f"{name} đã nối lại Ryu controller."))
            for m in sorted(set(cur["bad_links"]) - set(prev["bad_links"])):
                if not self._is_muted(f"link:{m}"):
                    out.append(Alert(f"link:{m}", "major", m.replace("Lien ket", "Liên kết").replace("chet", "chết"),
                                     ["sdn"]))
            for m in sorted(set(prev["bad_links"]) - set(cur["bad_links"])):
                out.append(Alert(f"link:{m}", "recovery", m.replace("Lien ket", "Liên kết").replace(" chet", " đã sống lại")))
        c = h.get("controller", {})
        last = c.get("stall_last")
        if last and last != self._last_stall:
            log_ = [x for x in c.get("stall_log", []) if x[0] == last]
            ms = log_[0][1] if log_ else 0
            self._last_stall = last
            if prev is not None and ms >= STALL_ALERT_MS and not self._is_muted("ryu-stall"):
                out.append(Alert("ryu-stall", "major",
                                 f"Ryu controller khựng {ms / 1000:.1f} s — OVS có thể mất kết nối tạm thời.", ["sdn"]))
        return out

    def poll(self) -> list[Alert]:
        out = []
        if self.vm:
            out += self._poll_vmanage()
        if self.ryu and self.ryu.ep is not None:
            out += self._poll_ryu()
        self._save()
        return out
