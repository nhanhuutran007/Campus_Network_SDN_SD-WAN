#!/bin/bash
# =============================================================
#  Access-SW2 - Access switch VLAN 20 - Khoa Toan TK (Node ID 66, OVS) - SDN managed
#  ens4 -> Dist-SW1 e2 (trunk) | ens5 -> Dist-SW2 e2 (trunk)
#  ens6, ens7 -> VPC20, VPC21 (access VLAN 20)
#  Mgmt:  10.1.99.22/24 (VLAN 99 qua bridge br-mgmt)
#  SDN:   datapath-id 66, controller 10.1.99.10:6653 (SDN_CONTROLLER, qua VLAN 99 mgmt)
#  (Control plane chay tren VLAN 99 mgmt - khong can link rieng tu controller)
#  (NIC index i -> ens(3+i): e1..e4 = ens4..ens7)
# =============================================================

for p in ens4 ens5 ens6 ens7; do ip link set $p up; done

# Image OVS base co san br0/patch-mgmt -> reset OVS DB cho sach
service openvswitch-switch stop 2>/dev/null
rm -f /etc/openvswitch/conf.db
service openvswitch-switch start 2>/dev/null
sleep 3

ovs-vsctl add-br br0
ovs-vsctl add-br br-mgmt

ovs-vsctl add-port br0 ens4
ovs-vsctl set port ens4 trunks=10,20,30,40,90,99
ovs-vsctl add-port br0 ens5
ovs-vsctl set port ens5 trunks=10,20,30,40,90,99

ovs-vsctl add-port br0 ens6
ovs-vsctl set port ens6 tag=20
ovs-vsctl add-port br0 ens7
ovs-vsctl set port ens7 tag=20

# Mgmt qua VLAN 99: patch pair noi br0 (patch-mgmt) <-> br-mgmt (mgmt-peer)
ovs-vsctl add-port br0 patch-mgmt -- set interface patch-mgmt type=patch options:peer=mgmt-peer
ovs-vsctl add-port br-mgmt mgmt-peer -- set interface mgmt-peer type=patch options:peer=patch-mgmt
ovs-vsctl set port patch-mgmt tag=99

ip addr add 10.1.99.22/24 dev br-mgmt
ip link set br-mgmt up
ip link set br0 up

# ---- SDN: OVS do Ryu controller quan ly (OpenFlow 1.3) ----
ovs-vsctl set bridge br0 protocols=OpenFlow13
ovs-vsctl set bridge br0 other_config:datapath-id=0000000000000042
ovs-vsctl set-controller br0 tcp:10.1.99.10:6653
# fail_mode=secure: chi forward theo flow cua SDN controller
ovs-vsctl set bridge br0 fail_mode=secure
# Tat STP: OVS STP chan frame truoc OpenFlow pipeline, lam mat packet-in
ovs-vsctl set bridge br0 stp_enable=false

# Kiem tra: ovs-vsctl show -> "is_connected: true"
