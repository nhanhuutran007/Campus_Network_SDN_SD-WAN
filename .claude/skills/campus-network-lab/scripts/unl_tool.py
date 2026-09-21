#!/usr/bin/env python3
"""Công cụ cục bộ cho file topology EVE-NG `Campus Network SDN SD-WAN.unl`.

Chỉ đọc/ghi file trên máy, KHÔNG kết nối EVE-NG. Chạy từ bất kỳ đâu trong repo.

  validate            Kiểm tra XML, ID trùng, network treo, tập config="1" và config nhúng
  nodes               Liệt kê node: id, tên, template, image, cờ config, cổng console (tenant 6)
  drift               So config nhúng trong .unl với file nguồn trong configs/
  dump  <id>          In config nhúng của node ra stdout
  embed <id> <file>   Nhúng lại <file> vào <config id="id"> (mặc định chỉ dry-run; --write để ghi)

Điểm mấu chốt: mọi thay đổi .unl được làm ở mức BYTE bằng thay thế đúng khối
<config id="N">…</config>. Không parse-rồi-serialize XML (sẽ đổi EOL/thuộc tính
hàng loạt và làm diff hàng nghìn dòng).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # Windows cp1252 sẽ lỗi với tiếng Việt
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

UNL_NAME = "Campus Network SDN SD-WAN.unl"
TENANT = 6  # tenant của host EVE 1; console = 32768 + 128*tenant + node-id

# Invariant đã chốt: đúng 51 node dùng config nhúng (config="1").
# Khi cố ý đổi (thêm/bớt node có config nhúng) phải sửa hằng số này VÀ SKILL.md.
EXPECTED_CONFIG_NODE_IDS = {
    1, 2, 3, 4, 6, 7, 14, 15, 16, 17, 18, 19, 20, 21, 24, 26, 27, 28,
    29, 30, 31, 32, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
    50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65,
}

S100, S200, S300 = "01-Site100-Campus", "02-Site200-CanTho", "03-Site300-DaNang"
S400, S900, SP = "04-Site400-NhaTrang", "05-Site900-Controller", "06-ServiceProvider"


def _build_config_map() -> dict[int, str]:
    """node-id -> đường dẫn config nguồn (tương đối configs/)."""
    m = {
        1: f"{S100}/FW-ASAv-Active/config.cfg",
        2: f"{S100}/FW-ASAv-Standby/config.cfg",
        3: f"{S100}/Core-SW1/config.cfg",
        4: f"{S100}/Core-SW2/config.cfg",
        6: f"{S100}/vEdge2-S100/config.cfg",
        7: f"{S100}/SwitchDMZ/config.cfg",
        24: f"{S100}/SwitchServerFarm/config.cfg",
        26: f"{SP}/Internet/config.cfg",
        27: f"{SP}/MPLS/config.cfg",
        28: f"{S100}/vEdge1-S100/config.cfg",
        29: f"{S200}/vEdge1-S200/config.cfg",
        30: f"{S300}/vEdge1-S300/config.cfg",
        31: f"{S400}/vEdge1-S400/config.cfg",
        32: f"{S900}/Switch32/config.cfg",
        37: f"{S200}/Brand-FW/config.cfg",
        38: f"{S400}/Brand-FW/config.cfg",
        39: f"{S300}/Brand-FW/config.cfg",
        40: f"{S300}/vEdge2-S300/config.cfg",
        41: f"{S400}/vEdge2-S400/config.cfg",
        42: f"{S200}/vEdge2-S200/config.cfg",
        61: f"{S900}/Switch61/config.cfg",
        62: f"{S300}/SwitchBrand/config.cfg",
        63: f"{S200}/SwitchBrand/config.cfg",
        64: f"{S400}/SwitchBrand/config.cfg",
        65: f"{S900}/vEdge65/config.cfg",
    }
    for i in range(14, 22):
        m[i] = f"{S100}/VPC{i}/config.txt"
    for i, site in [(43, S200), (44, S200), (46, S200), (47, S200),
                    (48, S300), (50, S300), (53, S300), (54, S300),
                    (45, S400), (49, S400), (51, S400), (52, S400)]:
        m[i] = f"{site}/VPC{i}/config.txt"
    for i, site in [(55, S200), (56, S200), (58, S300), (59, S300), (57, S400), (60, S400)]:
        m[i] = f"{site}/SW{i}/config.cfg"
    return m


CONFIG_MAP = _build_config_map()


def find_root(start: Path) -> Path:
    for base in [start, *start.parents]:
        if (base / UNL_NAME).is_file():
            return base
    sys.exit(f"Không tìm thấy {UNL_NAME!r} từ {start} trở lên. Dùng --unl.")


def resolve_unl(arg: str | None) -> Path:
    return Path(arg) if arg else find_root(Path.cwd()) / UNL_NAME


def config_blocks(raw: bytes) -> dict[int, bytes]:
    """node-id -> base64 (bytes) của config nhúng."""
    return {int(m.group(1)): m.group(2)
            for m in re.finditer(rb'<config id="(\d+)">([^<]*)</config>', raw)}


def decode_block(b64: bytes) -> bytes:
    return base64.b64decode(b"".join(b64.split()), validate=True)


def norm(data: bytes) -> bytes:
    """Chuẩn hoá để so sánh nội dung: EOL và khoảng trắng cuối dòng/cuối file."""
    text = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return b"\n".join(line.rstrip() for line in text.split(b"\n")).rstrip(b"\n")


# --------------------------------------------------------------------------- validate
def cmd_validate(args: argparse.Namespace) -> int:
    path = resolve_unl(args.unl)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        raw = path.read_bytes()
        root = ET.fromstring(raw)
    except (OSError, ET.ParseError) as exc:
        print(f"LỖI: không đọc được XML: {exc}")
        return 1

    nodes = root.findall(".//nodes/node")
    networks = root.findall(".//networks/network")
    node_ids = [int(n.get("id")) for n in nodes]
    net_ids = [int(n.get("id")) for n in networks]

    for label, ids in (("node", node_ids), ("network", net_ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            errors.append(f"{label} id trùng: {dup}")

    known_nets = set(net_ids)
    for n in nodes:
        for itf in n.findall("interface"):
            nid = itf.get("network_id")
            if nid and int(nid) not in known_nets:
                errors.append(f"node {n.get('id')} ({n.get('name')}) e{itf.get('id')}"
                              f" trỏ tới network_id {nid} không tồn tại")

    flagged = {int(n.get("id")) for n in nodes if n.get("config") == "1"}
    blocks = config_blocks(raw)
    embedded = set(blocks)
    if flagged - embedded:
        errors.append(f'config="1" nhưng THIẾU config nhúng: {sorted(flagged - embedded)}')
    if embedded - flagged:
        errors.append(f'Có config nhúng nhưng node không bật config="1": {sorted(embedded - flagged)}')
    if flagged != EXPECTED_CONFIG_NODE_IDS:
        errors.append("Tập config=\"1\" lệch invariant 51 node — thiếu: "
                      f"{sorted(EXPECTED_CONFIG_NODE_IDS - flagged)}, thừa: "
                      f"{sorted(flagged - EXPECTED_CONFIG_NODE_IDS)}")
    for nid, b64 in blocks.items():
        try:
            if not decode_block(b64).strip():
                errors.append(f"config nhúng node {nid} rỗng")
        except (binascii.Error, ValueError):
            errors.append(f"config nhúng node {nid} không phải base64 hợp lệ")

    if path.with_suffix(".unl.bak").exists() or Path(str(path) + ".bak").exists():
        warnings.append(".unl.bak tồn tại — dự án đã quy ước KHÔNG giữ file .bak")
    if b"\r\n" in raw:
        warnings.append("File .unl có CRLF — bản chuẩn trong repo dùng LF; kiểm tra công cụ đã ghi lại file")

    print(f"File: {path}")
    print(f"  node={len(nodes)} (chuẩn 67)  network={len(networks)} (chuẩn 100)  "
          f'config="1"={len(flagged)} (chuẩn 51)  config nhúng={len(embedded)}')
    for w in warnings:
        print(f"CẢNH BÁO: {w}")
    for e in errors:
        print(f"LỖI: {e}")
    print("KẾT QUẢ:", "ĐẠT" if not errors else f"KHÔNG ĐẠT ({len(errors)} lỗi)")
    print("Lưu ý: XML hợp lệ không chứng minh cú pháp IOS/ASAv/OVS hợp lệ — cần kiểm tra trên thiết bị.")
    return 1 if errors else 0


# --------------------------------------------------------------------------- nodes
def cmd_nodes(args: argparse.Namespace) -> int:
    root = ET.parse(resolve_unl(args.unl)).getroot()
    base = 32768 + 128 * TENANT
    print(f"{'id':>3}  {'tên':<16} {'template':<9} {'cfg':<3} {'ram':>5}  {'cổng(t6)':<8} image")
    for n in sorted(root.findall(".//nodes/node"), key=lambda x: int(x.get("id"))):
        nid = int(n.get("id"))
        print(f"{nid:>3}  {n.get('name', ''):<16} {n.get('template', ''):<9} "
              f"{n.get('config', '-'):<3} {n.get('ram', '-'):>5}  {base + nid:<8} {n.get('image', '')}")
    print(f"\nCổng console = 32768 + 128*{TENANT} + node-id (chỉ là gợi ý; xác nhận bằng `ss -tlnp` trên host).")
    print("Tên trùng (vEdge1, SW, VPC…) là bình thường — phân biệt bằng id, xem references/topology-and-conventions.md.")
    return 0


# --------------------------------------------------------------------------- drift
def cmd_drift(args: argparse.Namespace) -> int:
    unl = resolve_unl(args.unl)
    cfg_dir = Path(args.configs) if args.configs else unl.parent / "configs"
    blocks = config_blocks(unl.read_bytes())
    bad = 0
    for nid in sorted(blocks):
        rel = CONFIG_MAP.get(nid)
        if rel is None:
            print(f"[{nid:>2}] ?? không có trong CONFIG_MAP của script")
            bad += 1
            continue
        src = cfg_dir / rel
        if not src.is_file():
            print(f"[{nid:>2}] THIẾU FILE NGUỒN  {rel}")
            bad += 1
            continue
        emb, file_bytes = decode_block(blocks[nid]), src.read_bytes()
        if emb == file_bytes:
            status = "GIỐNG HỆT"
        elif norm(emb) == norm(file_bytes):
            status = "khác EOL/khoảng trắng"
        else:
            status = "LỆCH NỘI DUNG"
            bad += 1
        if status != "GIỐNG HỆT" or args.verbose:
            print(f"[{nid:>2}] {status:<22} {rel}")
    print(f"\n{len(blocks)} config nhúng, {bad} lệch/thiếu.")
    if bad:
        print("Hướng xử lý: xác định nguồn chuẩn (host 1 → repo, một chiều) rồi `embed` hoặc sửa file nguồn.")
    return 1 if bad else 0


# --------------------------------------------------------------------------- dump / embed
def cmd_dump(args: argparse.Namespace) -> int:
    blocks = config_blocks(resolve_unl(args.unl).read_bytes())
    if args.node_id not in blocks:
        print(f"Node {args.node_id} không có config nhúng.", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(decode_block(blocks[args.node_id]))
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    unl = resolve_unl(args.unl)
    raw = unl.read_bytes()
    pattern = re.compile(rb'(<config id="%d">)([^<]*)(</config>)' % args.node_id)
    if not pattern.search(raw):
        print(f"Node {args.node_id} chưa có khối <config> — thêm node mới phải sửa .unl thủ công "
              "(bật config=\"1\" + thêm khối) rồi mới dùng embed.", file=sys.stderr)
        return 1
    new_b64 = base64.b64encode(Path(args.file).read_bytes())
    new_raw, count = pattern.subn(lambda m: m.group(1) + new_b64 + m.group(3), raw)
    assert count == 1
    old_dec = decode_block(pattern.search(raw).group(2))
    new_dec = Path(args.file).read_bytes()
    print(f"Node {args.node_id}: {len(old_dec)}B -> {len(new_dec)}B; "
          f"nội dung {'GIỐNG' if old_dec == new_dec else 'KHÁC'}; "
          f"file .unl {len(raw)}B -> {len(new_raw)}B")
    if not args.write:
        print("Dry-run — thêm --write để ghi. Sau khi ghi chạy: validate, rồi `git diff --stat`.")
        return 0
    unl.write_bytes(new_raw)  # ghi bytes: giữ nguyên EOL
    print("Đã ghi. Chạy `validate` và kiểm tra `git diff --stat` chỉ đổi đúng 1 khối.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--unl", help=f"đường dẫn {UNL_NAME} (mặc định: tự tìm từ thư mục hiện tại)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sub.add_parser("nodes").set_defaults(fn=cmd_nodes)
    d = sub.add_parser("drift")
    d.add_argument("--configs", help="thư mục configs/ (mặc định: cạnh file .unl)")
    d.add_argument("-v", "--verbose", action="store_true", help="in cả node khớp")
    d.set_defaults(fn=cmd_drift)
    du = sub.add_parser("dump")
    du.add_argument("node_id", type=int)
    du.set_defaults(fn=cmd_dump)
    e = sub.add_parser("embed")
    e.add_argument("node_id", type=int)
    e.add_argument("file")
    e.add_argument("--write", action="store_true")
    e.set_defaults(fn=cmd_embed)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
