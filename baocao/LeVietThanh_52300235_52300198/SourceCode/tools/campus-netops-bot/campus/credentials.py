"""Đọc mật khẩu từ file credentials cục bộ (bảng Markdown, ngoài repo).

Định dạng mỗi dòng: `| <thiết bị/khoá> | <tài khoản> | <mật khẩu> | <ghi chú> |`.
Khoá tra cứu là chuỗi con của cột đầu (vd "vEdge chi nhánh"). Mật khẩu không bao giờ
được log, in, hay đưa vào tham số tool của LLM.
"""
from __future__ import annotations

import os
import threading

DEFAULT_PATH = os.path.expanduser(r"~/.claude/campus-lab-credentials.md")


class CredentialError(Exception):
    pass


class CredentialStore:
    def __init__(self, path: str | None = None):
        self.path = os.path.expanduser(path or os.getenv("CAMPUS_CRED_FILE") or DEFAULT_PATH)
        self._rows: list[tuple[str, str, str]] | None = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._rows is not None:
                return
            if not os.path.isfile(self.path):
                raise CredentialError(f"Không thấy file credentials (đặt CAMPUS_CRED_FILE): {self.path}")
            rows = []
            with open(self.path, encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines:
                if not line.startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 3 or set(cells[0]) <= {"-", " "}:
                    continue
                rows.append((cells[0], cells[1].strip("`"), cells[2].strip("`")))
            self._rows = rows

    def get(self, tag: str) -> tuple[str, str]:
        """Trả (tài khoản, mật khẩu) của dòng đầu tiên có cột 1 chứa `tag`."""
        self._load()
        for key, user, pw in self._rows:
            if tag in key:
                return user, pw
        raise CredentialError(f"Không có dòng credentials cho '{tag}'")
