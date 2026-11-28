#!/bin/bash
# qos_ns.sh up|down : namespace thay Brand-FW Site 200/300 de do QoS/SLA cua lop SD-WAN (28/11/2026).
# up  : tat Brand-FW 37 (S200) va 39 (S300), tao lt_q200/lt_q300 mang dung 2 dia chi outside cua FW
#       (10.X.1.1 phia vEdge1, 10.X.1.5 phia vEdge2) + IP "may chu" 10.X.200.10/32 (vEdge dinh tuyen 10.X.0.0/16 ve FW).
# down: go namespace, bat lai Brand-FW 37, 39.
# ten  bridge_vEdge1 bridge_vEdge2 X  fw
SITES="q200 vnet0_63 vnet0_64 2 37
q300 vnet0_75 vnet0_74 3 39"
case "$1" in
up)
  echo "$SITES" | while read n b1 b2 x fw; do
    /root/stopn.sh $fw >/dev/null 2>&1
    for k in $(seq 1 30); do ss -tln | grep -q ":$((32768+fw)) " || break; sleep 1; done
    if ss -tln | grep -q ":$((32768+fw)) "; then echo "FW $fw van chay - bo qua $n"; continue; fi
    ip netns list | grep -qw "lt_$n" && { echo "$n da co"; continue; }
    ip netns add lt_$n
    ip link add v1_$n type veth peer name e1 netns lt_$n
    ip link add v2_$n type veth peer name e2 netns lt_$n
    ip link set v1_$n master $b1 up; ip link set v2_$n master $b2 up
    ip netns exec lt_$n sh -c "ip link set lo up; ip link set e1 up; ip link set e2 up
      sysctl -qw net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.e1.rp_filter=0 net.ipv4.conf.e2.rp_filter=0
      ip addr add 10.$x.1.1/30 dev e1; ip addr add 10.$x.1.5/30 dev e2; ip addr add 10.$x.200.10/32 dev lo
      ip route add default via 10.$x.1.2 dev e1"
    echo "$n: FW $fw tat, 10.$x.1.1 tren $b1, 10.$x.1.5 tren $b2, may chu 10.$x.200.10"
  done
  ;;
down)
  echo "$SITES" | while read n b1 b2 x fw; do
    ip link del v1_$n 2>/dev/null; ip link del v2_$n 2>/dev/null; ip netns del lt_$n 2>/dev/null
    /root/startn.sh $fw
  done
  ip netns list
  ;;
esac
