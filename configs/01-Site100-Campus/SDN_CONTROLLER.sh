#!/bin/bash
# =============================================================
#  SDN_CONTROLLER - Ryu Controller (Node ID 9, EVE-NG)
#  OpenFlow listen: 0.0.0.0:6653 | REST northbound (ofctl_rest): :8080
#
#  Mgmt (VLAN 99 - MANAGEMENT, out-of-band qua link san co):
#    ens3  = 10.1.99.10/24  (e0 -> SwitchServerFarm e1/0, access VLAN 99)
#    ens6  = e3 -> Cloud-NAT (pnet0, Internet) - cai pip/apt
#    (Control plane SDN chay tren VLAN 99 mgmt - moi switch co br-mgmt
#     10.1.99.11/.12/.21-.24, khong can link rieng tu controller)
#    Image linux-ubuntu-ovs-16p: interface trong VM ten ens3..ens18
#    (NIC index i -> ens(3+i), khong phai ethX!)
# =============================================================

# 0) Fix OVS image: tat OVS bridge mac dinh (br0 chiem ens9/ens10) (05/08/2026)
ovs-vsctl --if-exists del-br br0 2>/dev/null
service openvswitch-switch stop 2>/dev/null
systemctl disable openvswitch-switch 2>/dev/null
pkill -f ovs-vswitchd 2>/dev/null

# 1) Khoi dong interface + gan IP mgmt (VLAN 99)
for i in 3 6; do ip link set ens$i up; done
ip addr add 10.1.99.10/24 dev ens3 || true
ip route add default via 10.1.99.1 dev ens3 || true

# 2) e3/ens6 = Cloud-NAT (pnet0) - tu dong xin DHCP de co Internet (cai pip/apt)
dhclient ens6 2>/dev/null || true

# 3) Cai dat Ryu (neu chua co; pin version da kiem nghiem 05/08/2026)
if ! command -v ryu-manager > /dev/null 2>&1; then
    if ip route get 8.8.8.8 > /dev/null 2>&1; then
        apt-get update
        apt-get install -y python3-pip python3.6-dev build-essential git || true
        pip3 install --upgrade pip setuptools || true
        # Ryu 4.34 + eventlet 0.30.2 + greenlet 0.4.17 + netaddr 0.8.0 (da kiem nghiem)
        pip3 install --ignore-installed ryu 2>/dev/null || pip3 install ryu || true
        pip3 install 'netaddr<1.0' 'eventlet==0.30.2' 'greenlet==0.4.17' 2>/dev/null || true
    else
        echo "[SDN_CONTROLLER.sh] No internet - skip apt/pip install"
    fi
fi

# 4) App SDN campus (lay tu repo: configs/01-Site100-Campus/campus_switch_13.py)
mkdir -p /root/ryu-app
if [ -f /root/campus_switch_13.py ]; then
    cp -f /root/campus_switch_13.py /root/ryu-app/campus_switch_13.py
fi

# 5) Chay Ryu: app quan ly campus + REST northbound (ofctl_rest port 8080)
pkill -f ryu-manager 2>/dev/null || true
sleep 2
nohup ryu-manager --ofp-tcp-listen-port 6653 /root/ryu-app/campus_switch_13.py ryu.app.ofctl_rest \
    > /root/ryu.log 2>&1 &

# Kiem tra:
#   tail -f /root/ryu.log
#   ss -tlnp | grep -E '6653|8080'
#   curl http://127.0.0.1:8080/stats/switches   -> [5, 8, 68, 66, 70, 69]
#   grep 'san sang' /root/ryu.log  (6 switch)
