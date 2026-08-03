#!/bin/bash
# =============================================================
#  AccessTest - OVS switch TEST DOC LAP (Node ID 10, EVE-NG)
#  Chay trong lab rieng de test OpenFlow co dung duoc hay khong.
#  e1  = control-plane -> noi TRUC TIEP vao SDN_CONTROLLER e1
#  e2  = data plane    -> VPC11 (10.1.101.11)
#  e3  = data plane    -> VPC12 (10.1.101.12)
#  Br0 duoc quan ly boi Ryu controller 192.168.100.1:6653 (OpenFlow 1.3)
# =============================================================

# 1) Khoi dong cac cong
ip link set e1 up
ip link set e2 up
ip link set e3 up

# 2) Gan IP control-plane (e1 KHONG them vao br0 - chi noi controller)
ip addr add 192.168.100.2/24 dev e1

# 3) Tao switch ao br0 va gom cac cong data plane
ovs-vsctl add-br br0
ovs-vsctl add-port br0 e2
ovs-vsctl add-port br0 e3

# 4) Ep OVS dung OpenFlow 1.3 va tro ve controller (port 6653)
ovs-vsctl set bridge br0 protocols=OpenFlow13
ovs-vsctl set-controller br0 tcp:192.168.100.1:6653

# 5) Kiem tra: ovs-vsctl show -> thay "is_connected: true"
