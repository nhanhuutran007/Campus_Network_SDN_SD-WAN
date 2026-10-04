#!/usr/bin/env bash
# Prepare controller networking and keep Ryu in the foreground for systemd.

set -Eeuo pipefail

ip link set ens3 up
ip addr del 10.1.100.2/24 dev ens3 2>/dev/null || true
ip addr replace 10.1.99.10/24 dev ens3

# ens6 is optional Cloud-NAT. DHCP is managed independently by
# campus-cloud-dhcp.service so restarting Ryu never creates another lease.
if ip link show ens6 >/dev/null 2>&1; then
    ip link set ens6 up
fi

# Firewall ens6 (LAN that, 10/2026): REST/GUI Ryu 8080 (ofctl_rest sua duoc flow)
# va ONOS 8181/8101 KHONG xac thuc -> chi host EVE (CAMPUS_ADMIN_SRC) duoc vao.
# ens3 (VLAN 99: OVS, PC-Management) khong bi anh huong. Idempotent.
CAMPUS_ADMIN_SRC="${CAMPUS_ADMIN_SRC:-10.215.28.26}"
if command -v iptables >/dev/null 2>&1; then
    iptables -N CAMPUS_ENS6 2>/dev/null || iptables -F CAMPUS_ENS6
    iptables -A CAMPUS_ENS6 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    iptables -A CAMPUS_ENS6 -s "$CAMPUS_ADMIN_SRC" -j ACCEPT
    iptables -A CAMPUS_ENS6 -p udp --sport 67 --dport 68 -j ACCEPT   # DHCP Cloud-NAT
    iptables -A CAMPUS_ENS6 -p icmp --icmp-type echo-request -j ACCEPT
    iptables -A CAMPUS_ENS6 -j DROP
    iptables -C INPUT -i ens6 -j CAMPUS_ENS6 2>/dev/null || iptables -I INPUT -i ens6 -j CAMPUS_ENS6
fi

ryu_bin="$(command -v ryu-manager || true)"
if [[ -z "$ryu_bin" ]]; then
    echo "[campus-ryu] ryu-manager is not installed" >&2
    exit 1
fi

readonly ryu_app=/root/ryu-app/campus_switch_13.py
readonly noc_app=/root/ryu-app/campus_noc_monitor.py
if [[ ! -f "$ryu_app" ]]; then
    echo "[campus-ryu] Missing $ryu_app" >&2
    exit 1
fi
if [[ -f "$noc_app" ]]; then
    NOC_ARGS=( "$noc_app" )
else
    NOC_ARGS=()
fi

exec "$ryu_bin" --ofp-tcp-listen-port 6653 \
    "$ryu_app" "${NOC_ARGS[@]}" ryu.app.ofctl_rest >> /root/ryu.log 2>&1
