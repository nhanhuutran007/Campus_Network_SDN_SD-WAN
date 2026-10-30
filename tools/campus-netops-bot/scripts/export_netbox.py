"""Xuất danh mục Campus ra CSV để import vào NetBox (Sites, Device Roles, Devices).

    python scripts/export_netbox.py [thư_mục_ra]   (mặc định netbox-import/)

Không xuất mật khẩu. Import theo thứ tự: sites → device-roles → devices
(NetBox: Organization > Sites > Import, Devices > Device Roles > Import, Devices > Import).
Device Type "EVE-NG Node" và Manufacturer "Cisco" phải tạo trước trên NetBox.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.stdout.reconfigure(encoding="utf-8")
from campus.inventory import DEVICES  # noqa: E402

SITE_NAMES = {"100": "Site 100 - Campus chinh", "200": "Site 200 - Can Tho", "300": "Site 300 - Da Nang",
              "400": "Site 400 - Nha Trang", "500": "Site 500", "900": "Site 900 - SD-WAN Controller",
              "SP": "Service Provider"}


def slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def main(out: str):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "sites.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "slug", "status", "description"])
        for code, name in SITE_NAMES.items():
            w.writerow([name, slug(name), "active", f"site-id {code}"])
    roles = sorted({d.role for d in DEVICES})
    with open(os.path.join(out, "device-roles.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "slug", "color"])
        for r in roles:
            w.writerow([r, slug(r), "9e9e9e"])
    with open(os.path.join(out, "devices.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "role", "manufacturer", "device_type", "site", "status", "comments"])
        for d in DEVICES:
            w.writerow([d.name, d.role, "Cisco", "EVE-NG Node", SITE_NAMES[d.site], "active",
                        f"EVE node {d.node_id}; platform {d.platform}"])
    print(f"Đã ghi {len(SITE_NAMES)} site, {len(roles)} role, {len(DEVICES)} thiết bị vào {out}/")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "netbox-import")
