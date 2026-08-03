#!/bin/bash
# =============================================================
#  Dist-SW2 - Distribution switch (Node ID 8, OVS)
#  Trunk: eth1..eth7 (VLAN 10,20,30,40,90,99)
#  Mgmt:  10.1.99.12/24 (VLAN 99 qua bridge br-mgmt)
#  eth1 -> Access-SW1 e2 | eth2 -> Access-SW2 e2 | eth3 -> Access-SW3 e2 | eth4 -> Access-SW4 e2
#  eth5 <-> Dist-SW1 eth5 | eth6 -> Core-SW2 Gi0/2 | eth7 -> Core-SW1 Gi1/2
# =============================================================

for p in eth1 eth2 eth3 eth4 eth5 eth6 eth7; do ip link set $p up; done

ovs-vsctl add-br br0
ovs-vsctl add-br br-mgmt

for p in eth1 eth2 eth3 eth4 eth5 eth6 eth7; do
    ovs-vsctl add-port br0 $p
    ovs-vsctl set port $p trunks=10,20,30,40,90,99
done

ovs-vsctl add-port br0 patch-mgmt
ovs-vsctl add-port br-mgmt patch-mgmt
ovs-vsctl set port patch-mgmt tag=99

ip addr add 10.1.99.12/24 dev br-mgmt
ip link set br-mgmt up
ip link set br0 up
