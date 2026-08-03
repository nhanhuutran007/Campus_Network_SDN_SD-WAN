#!/bin/bash
# =============================================================
#  SDN_CONTROLLER - Ryu Controller (Node ID 9, EVE-NG)
#  IP: e0 = 10.1.100.2/24  (mang 10.1.100.0/24 - SwitchServerFarm e1/0)
#  OpenFlow listen port: 6653
# =============================================================

# 1) Khoi dong interface + gan IP control-plane
ip link set e0 up
ip addr add 10.1.100.2/24 dev e0

# 2) Cai dat Ryu (neu chua co) - theo HuondanchitietController_OVS.md
apt-get update
apt-get install -y python3-pip git

# Ryu chua tuong thich hoan toan voi thu vien Python moi -> ha cap 2 thu vien
pip3 install --upgrade ryu 2>/dev/null || pip3 install ryu
pip3 install 'netaddr<1.0' 'eventlet<0.31' 2>/dev/null || true

# 3) Tai ma nguon app (thay duong dan bang app cua ban neu khac)
mkdir -p /root/ryu-app
# git clone <url-app> /root/ryu-app   <-- neu can

# 4) Chay Ryu controller (app simple switch - goi o day co the thay bang app da tai)
nohup ryu-manager --ofp-tcp-listen-port 6653 /usr/local/lib/python3.8/dist-packages/ryu/app/simple_switch_13.py \
    > /root/ryu.log 2>&1 &

# Kiem tra: tail -f /root/ryu.log  |  ss -tlnp | grep 6653
