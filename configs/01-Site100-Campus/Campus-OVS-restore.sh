#!/usr/bin/env bash
# Restore idempotent OVS/OpenFlow state after boot or openvswitch restart.
# Node-specific values are read from /etc/default/campus-ovs.

set -Eeuo pipefail

readonly CAMPUS_OVS_CONFIG="${CAMPUS_OVS_CONFIG:-/etc/default/campus-ovs}"

if [[ ! -r "$CAMPUS_OVS_CONFIG" ]]; then
    echo "[campus-ovs] Missing $CAMPUS_OVS_CONFIG" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "$CAMPUS_OVS_CONFIG"

for required_name in \
    CAMPUS_NODE_NAME CAMPUS_MGMT_CIDR CAMPUS_DPID \
    CAMPUS_PHYSICAL_PORTS CAMPUS_TRUNK99_PORTS CAMPUS_TRUNK_PORTS \
    CAMPUS_ACCESS_PORTS CAMPUS_ACCESS_VLAN; do
    if [[ -z "${!required_name+x}" ]]; then
        echo "[campus-ovs] Missing variable: $required_name" >&2
        exit 1
    fi
done

if [[ ! "$CAMPUS_DPID" =~ ^[0-9a-fA-F]{16}$ ]]; then
    echo "[campus-ovs] Invalid DPID: $CAMPUS_DPID" >&2
    exit 1
fi

if ! systemctl is-active --quiet openvswitch-switch.service; then
    systemctl start openvswitch-switch.service
fi

read -r -a campus_physical_ports <<< "$CAMPUS_PHYSICAL_PORTS"
read -r -a campus_trunk99_ports <<< "$CAMPUS_TRUNK99_PORTS"
read -r -a campus_trunk_ports <<< "$CAMPUS_TRUNK_PORTS"
read -r -a campus_access_ports <<< "$CAMPUS_ACCESS_PORTS"

for campus_port in "${campus_physical_ports[@]}"; do
    ip link set "$campus_port" up
done

ovs-vsctl --timeout=10 --may-exist add-br br0
ovs-vsctl --timeout=10 --may-exist add-br br-mgmt

for campus_port in "${campus_trunk99_ports[@]}"; do
    ovs-vsctl --timeout=10 --may-exist add-port br0 "$campus_port"
    ovs-vsctl --timeout=10 set Port "$campus_port" \
        vlan_mode=trunk tag=[] trunks=10,20,30,40,90,99
done

for campus_port in "${campus_trunk_ports[@]}"; do
    ovs-vsctl --timeout=10 --may-exist add-port br0 "$campus_port"
    ovs-vsctl --timeout=10 set Port "$campus_port" \
        vlan_mode=trunk tag=[] trunks=10,20,30,40,90
done

if [[ -n "$CAMPUS_ACCESS_PORTS" ]]; then
    if [[ ! "$CAMPUS_ACCESS_VLAN" =~ ^[0-9]+$ ]]; then
        echo "[campus-ovs] Invalid access VLAN: $CAMPUS_ACCESS_VLAN" >&2
        exit 1
    fi
    for campus_port in "${campus_access_ports[@]}"; do
        ovs-vsctl --timeout=10 --may-exist add-port br0 "$campus_port"
        ovs-vsctl --timeout=10 set Port "$campus_port" \
            vlan_mode=access tag="$CAMPUS_ACCESS_VLAN" trunks=[]
    done
fi

ovs-vsctl --timeout=10 --may-exist add-port br0 patch-mgmt \
    -- set Interface patch-mgmt type=patch options:peer=mgmt-peer
ovs-vsctl --timeout=10 --may-exist add-port br-mgmt mgmt-peer \
    -- set Interface mgmt-peer type=patch options:peer=patch-mgmt
ovs-vsctl --timeout=10 set Port patch-mgmt \
    vlan_mode=access tag=99 trunks=[]

ip link set br0 up
ip link set br-mgmt up
ip addr replace "$CAMPUS_MGMT_CIDR" dev br-mgmt

ovs-vsctl --timeout=10 set Bridge br0 protocols=OpenFlow13
ovs-vsctl --timeout=10 set Bridge br0 other_config:datapath-id="$CAMPUS_DPID"
ovs-vsctl --timeout=10 set-controller br0 tcp:10.1.99.10:6653
ovs-vsctl --timeout=10 set Bridge br0 fail_mode=secure
ovs-vsctl --timeout=10 set Bridge br0 stp_enable=false

campus_patch_ofport="$(ovs-vsctl get Interface patch-mgmt ofport)"
if [[ ! "$campus_patch_ofport" =~ ^[0-9]+$ ]] || (( campus_patch_ofport < 1 )); then
    echo "[campus-ovs] Invalid patch-mgmt ofport: $campus_patch_ofport" >&2
    exit 1
fi

campus_vlan_flow='priority=50000,dl_vlan=99,actions=NORMAL'
if ovs-ofctl -O OpenFlow13 dump-flows br0 | \
   grep -q 'priority=50000.*dl_vlan=99'; then
    ovs-ofctl -O OpenFlow13 --strict mod-flows br0 "$campus_vlan_flow"
else
    ovs-ofctl -O OpenFlow13 add-flow br0 "$campus_vlan_flow"
fi

campus_patch_flow="priority=50000,in_port=${campus_patch_ofport},actions=NORMAL"
if ovs-ofctl -O OpenFlow13 dump-flows br0 | \
   grep -q "priority=50000.*in_port=${campus_patch_ofport}"; then
    ovs-ofctl -O OpenFlow13 --strict mod-flows br0 "$campus_patch_flow"
else
    ovs-ofctl -O OpenFlow13 add-flow br0 "$campus_patch_flow"
fi

echo "[campus-ovs] Restored ${CAMPUS_NODE_NAME}: ${CAMPUS_MGMT_CIDR}, DPID ${CAMPUS_DPID}"
