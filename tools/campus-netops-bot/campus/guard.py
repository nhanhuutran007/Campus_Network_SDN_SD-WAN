"""Rào chỉ-đọc (giai đoạn 1): chỉ cho show / ping / traceroute, không cấu hình.

Kiểm theo token đầu và bộ lọc sau dấu `|` để LLM không thể lách bằng
`show run | redirect flash:x`, xuống dòng, hay lệnh viết tắt.
"""
from __future__ import annotations

import re

# token đầu được chấp nhận (chấp nhận viết tắt IOS tối thiểu)
_VERBS = {
    "show": 2,          # "sh", "sho", "show"
    "ping": 4,
    "traceroute": 5,    # "trace" trở lên
}
# bộ lọc output an toàn sau "|"
_IOS_FILTERS = {"include", "exclude", "begin", "section", "count", "i", "e", "b", "s", "inc", "exc", "beg", "sec"}
_VIPTELA_FILTERS = {"include", "exclude", "begin", "count", "tab", "nomore", "notab", "until", "select"}
# show nguy hiểm/nặng — chặn dù là show
_BLOCKED_SHOW = re.compile(r"^sh\w*\s+(tech|tech-support|controller\s+crypto)", re.I)
_BAD_CHARS = re.compile(r"[\r\n\x00-\x08\x0b-\x1f;`]")


def _verb(token: str) -> str | None:
    t = token.lower()
    for verb, minlen in _VERBS.items():
        if len(t) >= minlen and verb.startswith(t):
            return verb
    return None


def check(platform: str, command: str) -> tuple[bool, str]:
    """(True, lệnh đã chuẩn hoá) nếu được phép; (False, lý do) nếu bị chặn."""
    cmd = command.strip()
    if not cmd:
        return False, "Lệnh rỗng."
    if _BAD_CHARS.search(cmd):
        return False, "Lệnh chứa ký tự điều khiển/xuống dòng/';' — chỉ cho một lệnh mỗi lần."
    # IOS/ASA: chỉ dấu "|" đầu là pipe, phần sau là regex (`include a|b`).
    # Viptela cho nối nhiều pipe (`| tab | include x`) — tách theo " | " có khoảng trắng.
    if platform == "viptela":
        parts = re.split(r"\s\|\s", cmd)
    else:
        parts = cmd.split("|", 1)
    words = parts[0].split()
    verb = _verb(words[0])
    if verb is None and platform == "asa" and words[0].lower() == "packet-tracer":
        # ASA packet-tracer chỉ mô phỏng luồng qua chính sách, không gửi gói thật, không đổi trạng thái
        if len(words) < 6 or words[1].lower() != "input":
            return False, "packet-tracer input <if> <proto> <src> <sport> <dst> <dport>"
        verb = "packet-tracer"
    if verb is None:
        return False, f"Giai đoạn 1 chỉ cho show/ping/traceroute; '{words[0]}' bị chặn."
    if verb == "show" and _BLOCKED_SHOW.match(cmd):
        return False, "Lệnh show này quá nặng hoặc lộ khoá — bị chặn."
    if verb in ("ping", "traceroute") and len(words) < 2:
        return False, f"{verb} cần đích (vd '{verb} 10.1.90.10'); bản tương tác không được phép."
    if verb in ("ping", "traceroute") and len(parts) > 1:
        return False, f"{verb} không dùng bộ lọc '|'."
    allowed = _VIPTELA_FILTERS if platform == "viptela" else _IOS_FILTERS
    for flt in parts[1:]:
        fw = flt.split()
        if not fw or fw[0].lower() not in allowed:
            return False, f"Bộ lọc '| {flt.strip()}' không được phép."
    if platform == "viptela" and verb == "ping" and not re.search(r"\bcount\b", cmd):
        cmd += " count 5"       # ping Viptela chạy mãi nếu không có count
    return True, cmd
