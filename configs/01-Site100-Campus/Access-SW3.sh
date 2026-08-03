#!/bin/bash
# =============================================================
#  Access-SW3 - Access switch VLAN 30 - Khoa Luat (Node ID 70, OVS)
#  Mgmt:  10.1.99.23/24 (VLAN 99 qua br-mgmt)
#  eth1 -> Dist-SW1 e3 (trunk) | eth2 -> Dist-SW2 e3 (trunk)
#  eth3 -> VPC15 (access VLAN 30) | eth4 -> VPC16 (access VLAN 30)
# =============================================================

for p in eth1 eth2 eth3 eth4; do ip link set $p up; done

ovs-vsctl add-br br0
ovs-vsctl add-br br-mgmt

ovs-vsctl add-port br0 eth1
ovs-vsctl set port eth1 trunks=10,20,30,40,90,99
ovs-vsctl add-port br0 eth2
ovs-vsctl set port eth2 trunks=10,20,30,40,90,99

ovs-vsctl add-port br0 eth3
ovs-vsctl set port eth3 tag=30
ovs-vsctl add-port br0 eth4
ovs-vsctl set port eth4 tag=30

ovs-vsctl add-port br0 patch-mgmt
ovs-vsctl add-port br-mgmt patch-mgmt
ovs-vsctl set port patch-mgmt tag=99

ip addr add 10.1.99.23/24 dev br-mgmt
ip link set br-mgmt up
ip link set br0 up
