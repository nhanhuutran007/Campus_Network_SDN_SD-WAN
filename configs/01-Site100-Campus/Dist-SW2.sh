#!/bin/bash
# =============================================================
#  Dist-SW2 - Distribution switch (Node ID 8, OVS) - SDN managed
#  Trunk: ens4..ens10 (VLAN 10,20,30,40,90,99)
#  Mgmt:  10.1.99.12/24 (VLAN 99 qua bridge br-mgmt)
#  SDN:   datapath-id 8, controller 10.1.99.10:6653 (SDN_CONTROLLER, qua VLAN 99 mgmt)
#  ens4  -> Access-SW1 e2 | ens5 -> Access-SW2 e2 | ens6 -> Access-SW3 e2 | ens7 -> Access-SW4 e2
#  ens8  <-> Dist-SW1 e5 | ens9 -> Core-SW2 Gi0/2 | ens10 -> Core-SW1 Gi1/2
#  (Control plane chay tren VLAN 99 mgmt - link uplink san co, khong can link rieng)
#  (NIC index i -> ens(3+i): e1..e7 = ens4..ens10)
# =============================================================

for p in ens4 ens5 ens6 ens7 ens8 ens9 ens10; do ip link set $p up; done

# Image OVS base co san br0/patch-mgmt -> reset OVS DB cho sach
service openvswitch-switch stop 2>/dev/null
rm -f /etc/openvswitch/conf.db
service openvswitch-switch start 2>/dev/null
sleep 3

ovs-vsctl add-br br0
ovs-vsctl add-br br-mgmt

for p in ens4 ens5 ens6 ens7 ens8 ens9 ens10; do
    ovs-vsctl add-port br0 $p
    ovs-vsctl set port $p trunks=10,20,30,40,90,99
done

# Mgmt qua VLAN 99: patch pair noi br0 (patch-mgmt) <-> br-mgmt (mgmt-peer)
ovs-vsctl add-port br0 patch-mgmt -- set interface patch-mgmt type=patch options:peer=mgmt-peer
ovs-vsctl add-port br-mgmt mgmt-peer -- set interface mgmt-peer type=patch options:peer=patch-mgmt
ovs-vsctl set port patch-mgmt tag=99

ip addr add 10.1.99.12/24 dev br-mgmt
ip link set br-mgmt up
ip link set br0 up

# ---- SDN: OVS do Ryu controller quan ly (OpenFlow 1.3) ----
ovs-vsctl set bridge br0 protocols=OpenFlow13
ovs-vsctl set bridge br0 other_config:datapath-id=0000000000000008
ovs-vsctl set-controller br0 tcp:10.1.99.10:6653
# fail_mode=secure: chi forward theo flow cua SDN controller
ovs-vsctl set bridge br0 fail_mode=secure
# Tat STP: OVS STP chan frame truoc OpenFlow pipeline, lam mat packet-in
ovs-vsctl set bridge br0 stp_enable=false

# Kiem tra: ovs-vsctl show -> "is_connected: true"
