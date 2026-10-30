"""Backup running-config và so lệch (drift) với `configs/` trong repo.

Backup lưu bản ĐÃ CHE bí mật (dùng để so lệch / lưu vết); điểm khôi phục thật cho rollback
nằm trên chính thiết bị (unix:/flash: — xem change.py), nên không cần giữ mật khẩu trên đĩa.
"""
from __future__ import annotations

import difflib
import os
import re

from .redact import redact

_HERE = os.path.dirname(os.path.abspath(__file__))
# repo: tools/campus-netops-bot/campus → ../../../configs ; NetOps-Server: C:\netops\app\campus → ..\..\configs
_CANDIDATES = [os.path.join(_HERE, "..", "..", "..", "configs"), os.path.join(_HERE, "..", "..", "configs")]
CONFIGS = os.getenv("CAMPUS_CONFIGS_DIR") or next(
    (os.path.abspath(p) for p in _CANDIDATES if os.path.isdir(os.path.join(p, "01-Site100-Campus"))),
    os.path.abspath(_CANDIDATES[0]))

PATHS = {
    "FW-ASAv-Active": "01-Site100-Campus/FW-ASAv-Active", "FW-ASAv-Standby": "01-Site100-Campus/FW-ASAv-Standby",
    "Core-SW1": "01-Site100-Campus/Core-SW1", "Core-SW2": "01-Site100-Campus/Core-SW2",
    "SwitchDMZ": "01-Site100-Campus/SwitchDMZ", "SwitchServerFarm": "01-Site100-Campus/SwitchServerFarm",
    "vEdge1-S100": "01-Site100-Campus/vEdge1-S100", "vEdge2-S100": "01-Site100-Campus/vEdge2-S100",
    "Brand-FW-S200": "02-Site200-CanTho/Brand-FW", "SwitchBrand-S200": "02-Site200-CanTho/SwitchBrand",
    "SW-S200-1": "02-Site200-CanTho/SW55", "SW-S200-2": "02-Site200-CanTho/SW56",
    "vEdge1-S200": "02-Site200-CanTho/vEdge1-S200", "vEdge2-S200": "02-Site200-CanTho/vEdge2-S200",
    "Brand-FW-S300": "03-Site300-DaNang/Brand-FW", "SwitchBrand-S300": "03-Site300-DaNang/SwitchBrand",
    "SW-S300-1": "03-Site300-DaNang/SW58", "SW-S300-2": "03-Site300-DaNang/SW59",
    "vEdge1-S300": "03-Site300-DaNang/vEdge1-S300", "vEdge2-S300": "03-Site300-DaNang/vEdge2-S300",
    "Brand-FW-S400": "04-Site400-NhaTrang/Brand-FW", "SwitchBrand-S400": "04-Site400-NhaTrang/SwitchBrand",
    "SW-S400-1": "04-Site400-NhaTrang/SW57", "SW-S400-2": "04-Site400-NhaTrang/SW60",
    "vEdge1-S400": "04-Site400-NhaTrang/vEdge1-S400", "vEdge2-S400": "04-Site400-NhaTrang/vEdge2-S400",
    "Switch32": "05-Site900-Controller/Switch32", "Switch61": "05-Site900-Controller/Switch61",
    "vManage": "05-Site900-Controller/vManager-33", "vSmart": "05-Site900-Controller/vSmart-34",
    "vBond": "05-Site900-Controller/vBond-35",
    "Internet": "06-ServiceProvider/Internet", "MPLS": "06-ServiceProvider/MPLS",
    "vEdge-S500": "07-Site500/vEdge65",
}

_NOISE = re.compile(r"^(Building configuration|Current configuration|! Last configuration change|"
                    r"! NVRAM config last updated|ntp clock-period|: Saved|: Serial Number|: Hardware|"
                    r"Cryptochecksum|end$|!|:$)")


def normalize(text: str) -> list[str]:
    out = []
    for line in redact(text.replace("\r", "")).splitlines():
        l = line.rstrip()
        # dòng bí mật (đã che) không so: repo cố ý không lưu mật khẩu; "commit" ở cuối file Viptela
        if not l.strip() or _NOISE.match(l.strip()) or "***" in l or l.strip() == "commit":
            continue
        out.append(l)
    return out


def repo_config(device: str) -> str | None:
    rel = PATHS.get(device)
    if not rel:
        return None
    p = os.path.join(CONFIGS, rel, "config.cfg")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def diff(device: str, running: str) -> tuple[int, int, list[str]] | None:
    """(+dòng chỉ có trên thiết bị, -dòng chỉ có trong repo, unified diff) hoặc None nếu repo không có file."""
    repo = repo_config(device)
    if repo is None:
        return None
    a, b = normalize(repo), normalize(running)
    d = list(difflib.unified_diff(a, b, f"repo/{PATHS[device]}", f"live/{device}", lineterm="", n=0))
    plus = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
    minus = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
    return plus, minus, d


def save_backup(folder: str, device: str, running: str) -> str:
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, f"{device}.cfg")
    with open(p, "w", encoding="utf-8") as f:
        f.write(redact(running.replace("\r", "")) + "\n")
    return p
