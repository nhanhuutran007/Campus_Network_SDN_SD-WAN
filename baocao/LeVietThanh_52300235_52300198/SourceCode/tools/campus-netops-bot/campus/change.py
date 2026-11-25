"""Giai đoạn 3: thay đổi cấu hình có duyệt + kiểm sau thay đổi + tự rollback.

Vòng đời một yêu cầu:
  propose  → kiểm lệnh (rào cấu hình), đọc running-config để xem trước dòng nào mới   [pending]
  approve  → người duyệt (khác người yêu cầu nếu bật CHANGE_FOUR_EYES) bấm Duyệt       [running]
  execute  → chụp sức khoẻ → điểm khôi phục → áp lệnh → chờ ổn định → chụp lại → so sánh
             - đạt:  IOS `write memory`; Viptela `commit` xác nhận                    [done]
             - lỗi cú pháp / mất kết nối: IOS `configure replace <backup> force`;
               Viptela `commit abort` (huỷ commit confirmed)                          [rolled_back]
  undo     → trong UNDO_WINDOW: IOS `configure replace` + `write memory`;
             Viptela `rollback configuration 0` + `commit`                            [undone]

LLM chỉ được TẠO yêu cầu (propose); không có đường nào để LLM tự duyệt hay tự chạy.
Mọi bước ghi vào audit log dạng JSON Lines.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field

from . import health, inventory
from .console import ConsoleError, EveConsole
from .credentials import CredentialError
from .redact import redact

SUPPORTED = {"ios", "vios", "viptela"}
MAX_LINES = 40
PENDING_TTL = int(os.getenv("CHANGE_PENDING_TTL", "600"))       # yêu cầu chờ duyệt hết hạn sau 10 phút
UNDO_WINDOW = int(os.getenv("CHANGE_UNDO_WINDOW", "3600"))      # được hoàn tác trong 1 giờ
SETTLE = {"ios": int(os.getenv("CHANGE_SETTLE_IOS", "15")), "vios": int(os.getenv("CHANGE_SETTLE_IOS", "15")),
          "viptela": int(os.getenv("CHANGE_SETTLE_VIPTELA", "40"))}   # BFD detect 7 s + control
CONFIRM_MIN = 5                     # commit confirmed: vEdge tự rollback sau 5 phút nếu bot chết giữa chừng
BACKUP_FS = {"ios": "unix:", "vios": "flash:"}   # IOL lưu file trên unix:, vIOS trên flash:

# Lệnh cấm trong yêu cầu thay đổi (bot tự quản lý commit/save/rollback, và không đụng tài khoản/khoá)
_BLOCK_COMMON = [
    r"^do\b", r"^end\b", r"^(reload|reboot|poweroff|halt)\b", r"^(write|copy|erase|delete|format|archive)\b",
    r"^configure\b", r"^clear\b", r"^debug\b", r"^request\b",
    r"^(no\s+)?username\b", r"^(no\s+)?enable\s+(secret|password)\b", r"\bpassword\b", r"\bsecret\b",
    r"^(no\s+)?snmp-server\s+community\b", r"^crypto\s+key\s+zeroize\b", r"^(no\s+)?aaa\b",
    r"^no\s+router\s+(bgp|ospf)\b",          # xoá cả tiến trình định tuyến
    r"^no\s+vpn\s+0\b",                      # Viptela: xoá transport VPN
]
_BLOCK_VIPTELA = [r"^(commit|rollback|abort|exit|top|config)\b", r"^(no\s+)?system\s+(system-ip|site-id|organization-name)\b",
                  r"^(no\s+)?vbond\b"]
_ERR = {"ios": re.compile(r"^% (Invalid|Incomplete|Ambiguous|Unknown|Bad|.*not\s+allowed|.*error)", re.I | re.M),
        "viptela": re.compile(r"(syntax error|^Error:|^Aborted:|invalid value|unknown element)", re.I | re.M)}
_ERR["vios"] = _ERR["ios"]
IOS_ANSWERS = [(r"\[[^\]]*\]\?\s*$", ""), (r"\[confirm\]\s*$", "")]


class ChangeError(Exception):
    pass


def _err_line(platform: str, out: str) -> str:
    """Dòng báo lỗi của thiết bị (bỏ dòng chỉ có dấu ^ đánh dấu vị trí)."""
    m = _ERR[platform].search(out)
    if not m:
        return out.strip()[:160]
    start = out.rfind("\n", 0, m.start()) + 1
    end = out.find("\n", m.end())
    return out[start:end if end != -1 else None].strip()[:160]


def validate(platform: str, commands: list[str]) -> list[str]:
    """Trả danh sách lý do bị chặn (rỗng = hợp lệ)."""
    errs = []
    if platform not in SUPPORTED:
        errs.append(f"Nền tảng '{platform}' chưa hỗ trợ thay đổi có rollback (chỉ IOS/IOL, vIOS, Viptela). "
                    "ASA: đề xuất lệnh để làm tay.")
    if not commands:
        errs.append("Không có lệnh nào.")
    if len(commands) > MAX_LINES:
        errs.append(f"Tối đa {MAX_LINES} dòng mỗi yêu cầu.")
    rules = _BLOCK_COMMON + (_BLOCK_VIPTELA if platform == "viptela" else [])
    for c in commands:
        if re.search(r"[\x00-\x08\x0b-\x1f;`|]", c):
            errs.append(f"'{c}': chứa ký tự điều khiển, ';' hoặc '|'.")
            continue
        for r in rules:
            if re.search(r, c.strip(), re.I):
                errs.append(f"'{c.strip()}': bị chặn (quy tắc {r}).")
                break
    return errs


def preview(running: str, commands: list[str]) -> list[str]:
    """Đánh dấu dòng nào đã có sẵn trong running-config (theo dòng, bỏ thụt lề)."""
    have = {l.strip() for l in running.splitlines()}
    return [f"{'=' if c.strip() in have else '+'} {c}" for c in commands]


@dataclass
class ChangeRequest:
    id: str
    device: str
    commands: list[str]
    reason: str
    requester: str
    created: float = field(default_factory=time.time)
    status: str = "pending"        # pending|running|done|rolled_back|failed|cancelled|expired|undone
    approver: str = ""
    preview: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    backup: str = ""
    finished: float = 0.0
    origin_chat: int = 0
    announced: bool = False

    @property
    def platform(self) -> str:
        return inventory.resolve(self.device).platform

    def card(self) -> str:
        lines = [f"📝 Yêu cầu #{self.id} — {self.device} ({self.platform})",
                 f"Người yêu cầu: {self.requester}", f"Lý do: {self.reason or '-'}", "", "Lệnh (+ mới, = đã có):"]
        lines += self.preview or self.commands
        rb = ("configure replace <bản sao running-config> force" if self.platform != "viptela"
              else f"commit confirmed {CONFIRM_MIN} → commit abort nếu kiểm lỗi")
        lines += ["", f"Rollback: {rb}", f"Hết hạn sau {PENDING_TTL // 60} phút nếu chưa duyệt."]
        return "\n".join(lines)


class ChangeManager:
    def __init__(self, console: EveConsole, audit_path: str | None = None):
        self.console = console
        self.audit_path = audit_path
        self.requests: dict[str, ChangeRequest] = {}
        self._lock = threading.Lock()          # chống duyệt cùng yêu cầu hai lần
        self._audit_lock = threading.Lock()

    # ------------------------------------------------------------ audit
    def _audit(self, req: ChangeRequest, event: str, **extra):
        if not self.audit_path:
            return
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, "id": req.id, "device": req.device,
               "status": req.status, "requester": req.requester, "approver": req.approver,
               "commands": req.commands, **extra}
        with self._audit_lock, open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _note(self, req: ChangeRequest, msg: str, progress=None):
        req.log.append(f"{time.strftime('%H:%M:%S')} {msg}")
        if progress:
            progress(msg)

    # ------------------------------------------------------------ propose
    def propose(self, device: str, commands, reason: str, requester: str, origin_chat: int = 0) -> ChangeRequest:
        dev = inventory.resolve(device)
        if dev is None:
            raise ChangeError(f"Không tìm thấy thiết bị '{device}'.")
        if isinstance(commands, str):
            commands = commands.splitlines()
        commands = [c.rstrip() for c in commands if c.strip()]
        errs = validate(dev.platform, commands)
        if errs:
            raise ChangeError("Yêu cầu bị từ chối:\n- " + "\n- ".join(errs))
        req = ChangeRequest(secrets.token_hex(3), dev.name, commands, reason, requester, origin_chat=origin_chat)
        try:
            run_cmd = "show running-config"
            running = self.console.run(dev, [run_cmd])[0]
            req.preview = preview(running, commands)
        except (ConsoleError, CredentialError) as e:
            raise ChangeError(f"Không đọc được running-config của {dev.name}: {e}") from None
        self.requests[req.id] = req
        self._audit(req, "proposed")
        return req

    def get(self, rid: str) -> ChangeRequest:
        req = self.requests.get(rid)
        if req is None:
            raise ChangeError(f"Không có yêu cầu #{rid}.")
        if req.status == "pending" and time.time() - req.created > PENDING_TTL:
            req.status = "expired"
            self._audit(req, "expired")
        return req

    def cancel(self, rid: str, who: str) -> ChangeRequest:
        req = self.get(rid)
        if req.status != "pending":
            raise ChangeError(f"#{rid} đang ở trạng thái {req.status}, không huỷ được.")
        req.status, req.approver = "cancelled", who
        self._audit(req, "cancelled")
        return req

    def unannounced_since(self, ts: float) -> list[ChangeRequest]:
        """Yêu cầu tạo từ `ts` (vd do agent đề xuất trong một lượt chat) chưa hiện thẻ duyệt."""
        out = [r for r in self.requests.values() if r.created >= ts and not r.announced and r.status == "pending"]
        for r in out:
            r.announced = True
        return out

    # ------------------------------------------------------------ execute
    def approve_and_run(self, rid: str, approver: str, four_eyes: bool = False, progress=None) -> ChangeRequest:
        with self._lock:
            req = self.get(rid)
            if req.status != "pending":
                raise ChangeError(f"#{rid} đang ở trạng thái {req.status}.")
            if four_eyes and approver == req.requester:
                raise ChangeError("Chế độ 4 mắt: người duyệt phải khác người yêu cầu.")
            req.status, req.approver = "running", approver
        self._audit(req, "approved")
        dev = inventory.resolve(req.device)
        try:
            with self.console.session(dev) as s:
                if dev.platform == "viptela":
                    self._run_viptela(s, req, progress)
                else:
                    self._run_ios(s, req, dev.platform, progress)
        except (ConsoleError, CredentialError) as e:
            req.status = "failed"
            self._note(req, f"❌ Lỗi console: {e}. Viptela sẽ tự rollback sau {CONFIRM_MIN} phút nếu đã commit "
                            "confirmed; IOS: kiểm tay bằng /show.", progress)
        req.finished = time.time()
        self._audit(req, "finished", log=req.log)
        return req

    def _snapshot(self, s, platform: str, in_config: bool = False) -> dict:
        pre = "do " if in_config else ""
        outs = [s.run(pre + c, timeout=60) for c in health.SNAPSHOT_CMDS[platform]]
        return health.parse(platform, outs)

    def _run_ios(self, s, req: ChangeRequest, platform: str, progress):
        before = self._snapshot(s, platform)
        self._note(req, f"Trước: {health.summary(before)}", progress)
        req.backup = f"{BACKUP_FS[platform]}netops-{req.id}.cfg"
        out = s.run(f"copy running-config {req.backup}", timeout=60, answers=IOS_ANSWERS)
        if "bytes copied" not in out:
            req.status = "failed"
            self._note(req, f"❌ Không tạo được điểm khôi phục, KHÔNG áp lệnh: {out.strip()[-120:]}", progress)
            return
        self._note(req, f"Điểm khôi phục: {req.backup}", progress)
        s.run("configure terminal")
        for c in req.commands:
            out = s.run(c, timeout=30)
            if _ERR[platform].search(out):
                s.run("end")
                self._note(req, f"❌ Thiết bị từ chối '{c}': {_err_line(platform, out)}", progress)
                self._rollback_ios(s, req, before, platform, progress)
                return
        s.run("end")
        self._note(req, f"Đã áp {len(req.commands)} dòng, chờ {SETTLE[platform]} s cho ổn định...", progress)
        time.sleep(SETTLE[platform])
        after = self._snapshot(s, platform)
        lost = health.compare(before, after)
        if lost:
            self._note(req, "❌ Kiểm sau thay đổi KHÔNG ĐẠT — mất: " + "; ".join(lost[:8]), progress)
            self._rollback_ios(s, req, before, platform, progress)
            return
        s.run("write memory", timeout=60, answers=IOS_ANSWERS)
        req.status = "done"
        self._note(req, f"✅ Đạt (sau: {health.summary(after)}), đã write memory. Hoàn tác được trong "
                        f"{UNDO_WINDOW // 60} phút.", progress)

    def _rollback_ios(self, s, req, before, platform, progress):
        out = s.run(f"configure replace {req.backup} force", timeout=120, answers=IOS_ANSWERS)
        ok = "Rollback Done" in out
        time.sleep(SETTLE[platform])
        lost = health.compare(before, self._snapshot(s, platform))
        req.status = "rolled_back" if ok else "failed"
        self._note(req, ("↩️ Đã rollback bằng configure replace" if ok else
                         f"⚠️ configure replace không báo 'Rollback Done': {out.strip()[-160:]}")
                   + ("; sức khoẻ đã như trước." if not lost else "; VẪN mất: " + "; ".join(lost[:5])), progress)

    def _run_viptela(self, s, req: ChangeRequest, progress):
        before = self._snapshot(s, "viptela")
        self._note(req, f"Trước: {health.summary(before)}", progress)
        s.run("config exclusive")
        for c in req.commands:
            out = s.run(c, timeout=30)
            if _ERR["viptela"].search(out):
                s.run("abort")
                req.status = "rolled_back"
                self._note(req, f"❌ Thiết bị từ chối '{c}': {_err_line('viptela', out)} — đã abort, chưa commit gì.",
                           progress)
                return
        out = s.run("commit check", timeout=60)
        if _ERR["viptela"].search(out) or "Validation complete" not in out:
            s.run("abort")
            req.status = "rolled_back"
            self._note(req, f"❌ commit check không đạt: {out.strip()[:200]} — đã abort.", progress)
            return
        out = s.run(f"commit confirmed {CONFIRM_MIN} comment netops-{req.id}", timeout=120)
        if _ERR["viptela"].search(out):
            s.run("abort")
            req.status = "failed"
            self._note(req, f"❌ commit lỗi: {out.strip()[:200]}", progress)
            return
        self._note(req, f"Đã commit confirmed {CONFIRM_MIN} phút, chờ {SETTLE['viptela']} s cho BFD/control ổn định...",
                   progress)
        time.sleep(SETTLE["viptela"])
        lost = health.compare(before, self._snapshot(s, "viptela", in_config=True))
        if lost:
            s.run("commit abort", timeout=60)
            s.run("end")
            time.sleep(SETTLE["viptela"])
            still = health.compare(before, self._snapshot(s, "viptela"))
            req.status = "rolled_back"
            self._note(req, "❌ Kiểm sau thay đổi KHÔNG ĐẠT — mất: " + "; ".join(lost[:8]) +
                       "\n↩️ Đã commit abort (vEdge quay về cấu hình cũ)" +
                       ("; sức khoẻ đã như trước." if not still else "; VẪN mất: " + "; ".join(still[:5])), progress)
            return
        s.run("commit", timeout=60)          # xác nhận commit confirmed
        s.run("end")
        req.status = "done"
        self._note(req, f"✅ Đạt, đã xác nhận commit. Hoàn tác được trong {UNDO_WINDOW // 60} phút.", progress)

    # ------------------------------------------------------------ undo
    def undo(self, rid: str, who: str, progress=None) -> ChangeRequest:
        req = self.get(rid)
        if req.status != "done":
            raise ChangeError(f"#{rid} ở trạng thái {req.status}, chỉ hoàn tác được thay đổi đã xong.")
        if time.time() - req.finished > UNDO_WINDOW:
            raise ChangeError("Quá thời hạn hoàn tác.")
        dev = inventory.resolve(req.device)
        with self.console.session(dev) as s:
            if dev.platform == "viptela":
                hist = s.run("show configuration commit list", timeout=30)
                first = next((l for l in hist.splitlines() if re.match(r"^\s*\d+\s+\d+", l)), "")
                if f"netops-{req.id}" not in first:
                    raise ChangeError("Đã có commit khác sau #%s — không hoàn tác tự động, xem "
                                      "`show configuration commit list`." % rid)
                s.run("config exclusive")
                s.run("rollback configuration 0", timeout=60)
                out = s.run(f"commit comment netops-undo-{req.id}", timeout=120)
                s.run("end")
                ok = not _ERR["viptela"].search(out)
            else:
                out = s.run(f"configure replace {req.backup} force", timeout=120, answers=IOS_ANSWERS)
                ok = "Rollback Done" in out
                if ok:
                    s.run("write memory", timeout=60, answers=IOS_ANSWERS)
        req.status = "undone" if ok else "failed"
        self._note(req, f"↩️ Hoàn tác bởi {who}: {'xong' if ok else 'LỖI ' + redact(out.strip()[-160:])}", progress)
        self._audit(req, "undo", ok=ok)
        return req

    def to_dict(self, rid: str) -> dict:
        return asdict(self.get(rid))
