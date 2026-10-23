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
ovs-vsctl --timeout=10 set-controller br0 tcp:10.1.99.10:6653 tcp:10.1.99.10:6654   # 6653 = Ryu (chuyen tiep), 6654 = ONOS (GUI/giam sat)
ovs-vsctl --timeout=10 set Bridge br0 fail_mode=secure
ovs-vsctl --timeout=10 set Bridge br0 stp_enable=false

# BFD 100 ms x 3 tren lien ket Access<->Dist (23/10/2026): OVS tu bo co LIVE cua
# cong chet trong ~0,3 s -> group FAST_FAILOVER cua Ryu chuyen uplink khong can
# controller (cat tap tren host EVE khong lam VM mat carrier). Tuy chon: rong = tat.
read -r -a campus_bfd_ports <<< "${CAMPUS_BFD_PORTS:-}"
for campus_port in "${campus_bfd_ports[@]}"; do
    ovs-vsctl --timeout=10 set Interface "$campus_port" \
        bfd:enable=true bfd:min_tx=100 bfd:min_rx=100 bfd:decay_min_rx=0
done

read -r -a campus_bootstrap99_ports <<< "$CAMPUS_BOOTSTRAP99_PORTS"

# Bootstrap VLAN 99 (mgmt/control) tren CAY ACYCLIC — KHONG dung NORMAL.
# Topology lab co lai (Access dual-home 2 Dist + inter-dist ens8 + 2 Dist-Core
# uplink + Core1/2 noi Farm) nen NORMAL chi can flood tren toan bo port mang
# VLAN 99 la tao broadcast loop ngay khi ca 6 node OVS boot truoc khi Ryu kip
# cai TREE-BLOCK (storm 09/2026). Thay vao do, moi node chi flood VLAN 99
# trong tap CAMPUS_BOOTSTRAP99_PORTS = cay management (khac cay data), khop
# voi VLAN99_TREE_BLOCK cua controller. Dung port trentrunk (vlan_mode=trunk)
# neu muon giu 99 o cac port du phong cho failover (ens5/ens8/ens10): chung
# van nhan mong VLAN 99 nhung flow bootstrap nay KHONG flood ra chung.
bootstrap_ofports=()
for campus_port in "${campus_bootstrap99_ports[@]}"; do
    campus_ofport=$(ovs-vsctl --timeout=10 --if-exists get Interface "$campus_port" ofport)
    if [[ ! "$campus_ofport" =~ ^[0-9]+$ ]]; then
        echo "[campus-ovs] BOOTSTRAP99 port $campus_port khong co ofport ($campus_ofport)" >&2
        exit 1
    fi
    bootstrap_ofports+=("$campus_ofport")
done

# Xoa NORMAL bootstrap cu (priority 50000) neu con sot tu phien truoc.
# (Field dl_vlan=99 + priority 50000: trong ca in_port, nen non-strict del
#  se xoa duoc ca flow per-port bootstrap cua lan chay truoc -> idempotent.)
ovs-ofctl -O OpenFlow13 del-flows br0 'priority=50000,dl_vlan=99'

# Flow bootstrap: moi port cay output den cac port cay con lai (loai in_port
# de tranh hairpin echo -> khong the tao loop). Bao gom patch-mgmt de traffic
# in-band tu br-mgmt den controller di dung mot uplink cua cay.
for campus_idx in "${!bootstrap_ofports[@]}"; do
    campus_src="${bootstrap_ofports[$campus_idx]}"
    campus_actions=""
    for campus_other in "${bootstrap_ofports[@]}"; do
        if [[ "$campus_other" == "$campus_src" ]]; then
            continue
        fi
        if [[ -n "$campus_actions" ]]; then
            campus_actions+=","
        fi
        campus_actions+="output:$campus_other"
    done
    if [[ -z "$campus_actions" ]]; then
        continue
    fi
    ovs-ofctl -O OpenFlow13 add-flow br0 \
        "priority=50000,dl_vlan=99,cookie=0xba5e,in_port=$campus_src,actions=$campus_actions"
done
echo "[campus-ovs] VLAN99 bootstrap tree ${CAMPUS_NODE_NAME}: ${CAMPUS_BOOTSTRAP99_PORTS}"
