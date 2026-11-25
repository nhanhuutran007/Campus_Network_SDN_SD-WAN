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
    CAMPUS_ACCESS_PORTS CAMPUS_ACCESS_VLAN CAMPUS_BOOTSTRAP99_PORTS; do
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
# In-band control cua OVS tu cai flow AN voi action NORMAL cho ARP khi chua ket noi
# controller (canh bao "in_band: cannot find route for controller") => flood ARP ra moi
# cong, bo qua flow chong vong => broadcast storm luc boot. Controller di qua
# br-mgmt (khong qua cong local cua br0) nen tat in-band, dung flow bootstrap cua ta.
ovs-vsctl --timeout=10 set Bridge br0 other_config:disable-in-band=true
ovs-vsctl --timeout=10 set-controller br0 tcp:10.1.99.10:6653 tcp:10.1.99.10:6654   # 6653 = Ryu (chuyen tiep), 6654 = ONOS (GUI/giam sat)
ovs-vsctl --timeout=10 set Bridge br0 fail_mode=secure
ovs-vsctl --timeout=10 set Bridge br0 stp_enable=false

# VLAN 99 (mgmt/control) tren Access: flow CO DINH (khong bi Ryu xoa), khong NORMAL.
# - 'tag=99' cua patch-mgmt CHI ap dung cho NORMAL: frame tu br-mgmt vao OpenFlow
#   khong co tag => match in_port, tu gan VLAN 99 khi ra uplink; strip_vlan khi vao patch.
# - Mo CA hai uplink (ens4->Dist-SW1, ens5->Dist-SW2) de failover khong can Ryu;
#   Access KHONG noi cau VLAN 99 giua hai uplink (moi flow chi di patch <-> uplink),
#   va Dist-SW2 chan cong Access khi khong failover => khong tao vong.
# - cookie 0xba5f + priority 45000: app Ryu chi xoa cookie 0xba5e va priority 50000.
ovs-ofctl -O OpenFlow13 del-flows br0 'cookie=0xba5e/-1' 2>/dev/null || true
ovs-ofctl -O OpenFlow13 del-flows br0 'cookie=0xba5f/-1' 2>/dev/null || true
ovs-ofctl -O OpenFlow13 del-flows br0 'priority=50000,dl_vlan=99' 2>/dev/null || true
campus_all_outs=""
for campus_o in "${campus_trunk99_ports[@]}"; do
    campus_all_outs="${campus_all_outs:+$campus_all_outs,}output:${campus_o}"
done
ovs-ofctl -O OpenFlow13 add-flow br0 \
    "cookie=0xba5f,priority=45000,in_port=patch-mgmt,actions=mod_vlan_vid:99,${campus_all_outs}"
for campus_in in "${campus_trunk99_ports[@]}"; do
    ovs-ofctl -O OpenFlow13 add-flow br0 \
        "cookie=0xba5f,priority=45000,dl_vlan=99,in_port=${campus_in},actions=strip_vlan,output:patch-mgmt"
done

echo "[campus-ovs] Restored ${CAMPUS_NODE_NAME}: ${CAMPUS_MGMT_CIDR}, DPID ${CAMPUS_DPID}, persistent VLAN99 uplinks=(${CAMPUS_TRUNK99_PORTS})"
