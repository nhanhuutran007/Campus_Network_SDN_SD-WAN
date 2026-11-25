"""Che bí mật trong output trước khi đưa cho LLM, Telegram hay NetBox."""
from __future__ import annotations

import re

_RULES = [
    # IOS/ASA: username x password|secret <type> <value>, enable secret/password ...
    (re.compile(r"(\b(?:password|secret|passwd)\s+(?:\d\s+)?)(\S+)", re.I), r"\1***"),
    # SNMP community
    (re.compile(r"(\bsnmp-server\s+community\s+)(\S+)", re.I), r"\1***"),
    # khoá chia sẻ: key-string, pre-shared-key, ikev2 ..., authentication key
    (re.compile(r"(\b(?:key-string|pre-shared-key|key)\s+(?:\d\s+)?)(\S+)", re.I), r"\1***"),
    # Viptela: password $6$..., organization keys trong config
    (re.compile(r"(\$\d\$)\S+"), r"\1***"),
]


def redact(text: str) -> str:
    out = []
    for line in text.splitlines():
        for pat, repl in _RULES:
            line = pat.sub(repl, line)
        out.append(line)
    return "\n".join(out)
