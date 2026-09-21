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
read -r -a campus_bootstrap99_ports <<< "$CAMPUS_BOOTSTRAP99_PORTS"

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

# IMPORTANT: a patch port NEVER applies its ingress 'tag' to frames that
# enter the bridge through it.  Setting patch-mgmt as an access port with
# tag=99 therefore leaves the management frames UNTAGGED inside br0, so
# they match no dl_vlan=99 rule and are dropped - the switch can never
# reach the controller.  Keep the patch ports as plain pass-through and
# tag the management traffic in the Linux stack (VLAN 99 subinterface)
# before it crosses the patch.
ovs-vsctl --timeout=10 clear Port patch-mgmt tag vlan_mode trunks
ovs-vsctl --timeout=10 clear Port mgmt-peer tag vlan_mode trunks

ip link set br0 up
ip link set br-mgmt up

if ! ip link show br-mgmt.99 >/dev/null 2>&1; then
    ip link add link br-mgmt name br-mgmt.99 type vlan id 99
fi
ip link set br-mgmt.99 up
ip addr flush dev br-mgmt scope global || true
ip addr replace "$CAMPUS_MGMT_CIDR" dev br-mgmt.99

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

# VLAN 99 bootstrap MUST be a spanning tree, NOT actions=NORMAL.
# NORMAL floods VLAN 99 out every trunk99 port.  On dual-homed nodes this
# recreates the full-mesh loop (e.g. node8: ens9->Core-SW2 + ens10->Core-SW1
# with the two cores directly linked) and the ARP storm swallows the OF
# handshake to 10.1.99.10 before Ryu can install TREE-BLOCK rules.
# Instead: bridge ONLY the ports listed in CAMPUS_BOOTSTRAP99_PORTS for VLAN
# 99 (per-ingress-port rules), and drop every other VLAN 99 packet.  Ryu
# replaces these rules right after the handshake.
campus_loopports=""
for campus_bp_port in "${campus_bootstrap99_ports[@]}"; do
    if [[ "$campus_bp_port" != "patch-mgmt" ]]; then
        campus_loopports="$campus_loopports $campus_bp_port"
    fi
done
read -r -a campus_bootstrap_phys <<< "$campus_loopports"

# build output list for a packet coming IN on $campus_in: all bootstrap
# physical ports + patch-mgmt, minus the ingress port itself.
campus_build_outputs() {
    local campus_in="$1"
    local campus_outs=""
    local bp_port
    for bp_port in patch-mgmt "${campus_bootstrap_phys[@]}"; do
        if [[ "$bp_port" == "$campus_in" ]]; then
            continue
        fi
        campus_outs="${campus_outs:+$campus_outs,}output:$bp_port"
    done
    printf '%s' "$campus_outs"
}

# drop any previous bootstrap flows so re-running is idempotent.
ovs-ofctl -O OpenFlow13 del-flows br0 'priority=50000,dl_vlan=99' 2>/dev/null || true

for campus_bp in patch-mgmt "${campus_bootstrap_phys[@]}"; do
    campus_outs="$(campus_build_outputs "$campus_bp")"
    ovs-ofctl -O OpenFlow13 add-flow br0 \
        "priority=50000,dl_vlan=99,in_port=${campus_bp},actions=${campus_outs}"
done

# catch-all drop for all other VLAN 99 ingress ports - same priority as
# the in_port-specific rules so OVS's most-specific-match wins; all at
# priority=50000 so Ryu's "del-flows priority=50000,dl_vlan=99" removes
# them all once the handshake completes.
ovs-ofctl -O OpenFlow13 add-flow br0 "priority=50000,dl_vlan=99,actions=drop"

echo "[campus-ovs] Restored ${CAMPUS_NODE_NAME}: ${CAMPUS_MGMT_CIDR} on br-mgmt.99, DPID ${CAMPUS_DPID}, boot99 tree=(${campus_loopports})"

