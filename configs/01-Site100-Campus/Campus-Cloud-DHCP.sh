#!/usr/bin/env bash
# Keep optional Cloud-NAT DHCP independent from the Ryu process lifecycle.

set -Eeuo pipefail

if [[ ! -e /sys/class/net/ens6 ]]; then
    echo "[campus-dhcp] ens6 is absent; nothing to do"
    exit 0
fi

ip link set ens6 up

if ! command -v dhclient >/dev/null 2>&1; then
    echo "[campus-dhcp] dhclient is not installed; skipping optional Cloud-NAT"
    exit 0
fi

if pgrep -af 'dhclient.*ens6' >/dev/null 2>&1; then
    echo "[campus-dhcp] DHCP client for ens6 is already running"
    exit 0
fi

if ip -4 -o addr show dev ens6 scope global | grep -q .; then
    echo "[campus-dhcp] ens6 already has an IPv4 lease"
    exit 0
fi

exec dhclient -nw ens6
