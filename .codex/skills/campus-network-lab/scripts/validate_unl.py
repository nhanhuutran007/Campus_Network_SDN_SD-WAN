#!/usr/bin/env python3
"""Validate stable invariants of the Campus Network EVE-NG .unl file."""

from __future__ import annotations

import argparse
import base64
import binascii
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_CONFIG_NODE_IDS = {
    1, 2, 3, 4, 6, 7, 14, 15, 16, 17, 18, 19, 20, 21, 24, 26, 27, 28,
    29, 30, 31, 32, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
    50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65,
}


def parse_id(element: ET.Element, attribute: str, errors: list[str]) -> int | None:
    raw = element.get(attribute)
    if raw is None:
        errors.append(f"<{element.tag}> thiếu thuộc tính {attribute!r}")
        return None
    try:
        return int(raw)
    except ValueError:
        errors.append(f"<{element.tag}> có {attribute} không phải số: {raw!r}")
        return None


def duplicates(values: list[int]) -> list[int]:
    seen: set[int] = set()
    repeated: set[int] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def format_ids(values: set[int]) -> str:
    return ", ".join(str(value) for value in sorted(values)) or "không có"


def validate(path: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return [f"Không đọc được XML: {exc}"], warnings, {}

    nodes = root.findall(".//nodes/node")
    networks = root.findall(".//networks/network")
    embedded = root.findall(".//configs/config")

    node_id_pairs = [
        (node, value)
        for node in nodes
        if (value := parse_id(node, "id", errors)) is not None
    ]
    node_ids = [value for _, value in node_id_pairs]
    network_ids = [
        value for network in networks
        if (value := parse_id(network, "id", errors)) is not None
    ]
    embedded_ids = [
        value for config in embedded
        if (value := parse_id(config, "id", errors)) is not None
    ]

    for label, values in (
        ("node", node_ids), ("network", network_ids), ("embedded config", embedded_ids)
    ):
        repeated = duplicates(values)
        if repeated:
            errors.append(f"ID {label} bị trùng: {', '.join(map(str, repeated))}")

    config_node_ids = {
        node_id
        for node, node_id in node_id_pairs
        if node.get("config") == "1"
    }
    missing_expected = EXPECTED_CONFIG_NODE_IDS - config_node_ids
    unexpected = config_node_ids - EXPECTED_CONFIG_NODE_IDS
    if missing_expected:
        errors.append(f"Thiếu node config=1 theo invariant: {format_ids(missing_expected)}")
    if unexpected:
        errors.append(f"Node config=1 ngoài invariant: {format_ids(unexpected)}")

    embedded_id_set = set(embedded_ids)
    missing_embedded = config_node_ids - embedded_id_set
    extra_embedded = embedded_id_set - config_node_ids
    if missing_embedded:
        errors.append(f"Node config=1 thiếu config nhúng: {format_ids(missing_embedded)}")
    if extra_embedded:
        warnings.append(f"Config nhúng không có node config=1: {format_ids(extra_embedded)}")

    known_networks = set(network_ids)
    dangling: list[str] = []
    for node in nodes:
        node_id = node.get("id", "?")
        for interface in node.findall("./interface"):
            raw_network_id = interface.get("network_id")
            if raw_network_id is None:
                continue
            try:
                network_id = int(raw_network_id)
            except ValueError:
                errors.append(
                    f"Node {node_id} interface {interface.get('id', '?')} có network_id lỗi: "
                    f"{raw_network_id!r}"
                )
                continue
            if network_id not in known_networks:
                dangling.append(
                    f"node {node_id}/interface {interface.get('id', '?')} -> network {network_id}"
                )
    if dangling:
        errors.append("Network reference không tồn tại: " + "; ".join(dangling))

    for config in embedded:
        config_id = config.get("id", "?")
        payload = "".join((config.text or "").split())
        if not payload:
            errors.append(f"Config nhúng {config_id} rỗng")
            continue
        try:
            base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            errors.append(f"Config nhúng {config_id} không phải base64 hợp lệ")

    stats = {
        "nodes": len(nodes),
        "networks": len(networks),
        "config_nodes": len(config_node_ids),
        "embedded_configs": len(embedded),
    }
    return errors, warnings, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unl", type=Path, help="Đường dẫn tới file .unl chính")
    args = parser.parse_args()

    errors, warnings, stats = validate(args.unl)
    if stats:
        print(
            "Thống kê: "
            f"nodes={stats['nodes']}, networks={stats['networks']}, "
            f"config=1={stats['config_nodes']}, embedded={stats['embedded_configs']}"
        )
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"FAIL: {len(errors)} lỗi, {len(warnings)} cảnh báo")
        return 1
    print(f"PASS: 0 lỗi, {len(warnings)} cảnh báo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
